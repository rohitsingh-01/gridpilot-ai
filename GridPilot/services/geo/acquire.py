"""Geospatial dataset ingestion and validation pipeline runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import yaml
from pydantic import ValidationError

import httpx
import shapefile
from shapely.geometry import shape, mapping
from shapely.ops import transform
from shapely.validation import make_valid
from pyproj import Transformer

from services.geo.config_models import DatasetsRootConfig, DatasetConfig

# Setup Structured Logging
class StructuredLogger:
    """JSON structured logger outputting to stdout for pipeline tracing."""

    def __init__(self, name: str = "gridpilot.geo") -> None:
        self.name = name

    def log(self, level: str, phase: str, message: str, **metadata: Any) -> None:
        """Log a structured JSON line."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "logger": self.name,
            "phase": phase,
            "message": message,
            **metadata,
        }
        sys.stdout.write(json.dumps(record) + "\n")
        sys.stdout.flush()

    def info(self, phase: str, message: str, **metadata: Any) -> None:
        self.log("info", phase, message, **metadata)

    def warning(self, phase: str, message: str, **metadata: Any) -> None:
        self.log("warning", phase, message, **metadata)

    def error(self, phase: str, message: str, **metadata: Any) -> None:
        self.log("error", phase, message, **metadata)


logger = StructuredLogger()


def setup_directories(root_dir: str = "data") -> None:
    """Ensure standard directory structure exists."""
    dirs = [
        os.path.join(root_dir, "raw"),
        os.path.join(root_dir, "downloads"),
        os.path.join(root_dir, "extracted"),
        os.path.join(root_dir, "processed"),
        os.path.join(root_dir, "processed", "manifests"),
        os.path.join(root_dir, "cache"),
        os.path.join(root_dir, "logs"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)


def calculate_sha256(filepath: str) -> str:
    """Calculate SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


async def download_file_with_retry(
    client: httpx.AsyncClient,
    urls: List[str],
    download_order: List[str],
    dest_path: str,
    expected_hash: str,
    max_retries: int = 3,
    initial_backoff: float = 2.0,
) -> tuple[str, str]:
    """Download a file with exponential backoff and mirror fallback.

    Returns a tuple of (downloaded_from_url, mirror_id_used).
    """
    # Create url mapping based on download order
    url_map: Dict[str, str] = {}
    for source in download_order:
        if source == "official":
            url_map["official"] = urls[0]
        elif source.startswith("mirror") and len(urls) > 1:
            # Match mirror index
            try:
                idx = int(source.replace("mirror", "")) - 1
                if 0 <= idx < len(urls) - 1:
                    url_map[source] = urls[idx + 1]
            except ValueError:
                pass

    last_error = None
    for source_id in download_order:
        url = url_map.get(source_id)
        if not url:
            continue

        logger.info(
            "download.attempt",
            f"Attempting download for source ID: {source_id}",
            url=url,
        )

        for attempt in range(max_retries):
            try:
                # 30 seconds connect and read timeout
                async with client.stream("GET", url, timeout=30.0) as response:
                    if response.status_code in [500, 502, 503, 504]:
                        raise httpx.HTTPStatusError(
                            f"Retryable status code {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                    response.raise_for_status()

                    # Write out chunk by chunk to avoid memory bloat
                    with open(dest_path, "wb") as f:
                        async for chunk in response.iter_bytes(chunk_size=16384):
                            f.write(chunk)

                # Validate integrity immediately
                download_hash = calculate_sha256(dest_path)
                if download_hash != expected_hash:
                    raise ValueError(
                        f"Checksum mismatch on download: expected {expected_hash}, got {download_hash}"
                    )

                logger.info(
                    "download.success",
                    f"Successfully downloaded and verified dataset from {source_id}",
                    url=url,
                )
                return url, source_id

            except (httpx.HTTPError, ValueError) as e:
                last_error = e
                logger.warning(
                    "download.retry",
                    f"Download attempt {attempt + 1} failed for source {source_id}: {str(e)}",
                    url=url,
                )
                if attempt < max_retries - 1:
                    # Exponential backoff
                    time.sleep(initial_backoff * (2**attempt))
                else:
                    logger.error(
                        "download.failure",
                        f"All retries failed for source {source_id}. Trying fallback...",
                        url=url,
                    )

    # If all sources failed
    raise RuntimeError(
        f"Geospatial acquisition failed for all configured sources. Last error: {str(last_error)}"
    )


def extract_archive(archive_path: str, extract_dir: str) -> None:
    """Extract zip file archives to a target directory."""
    if not zipfile.is_zipfile(archive_path):
        raise zipfile.BadZipFile("The downloaded file is not a valid ZIP archive.")

    # Remove existing extract dir if present
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)
    os.makedirs(extract_dir)

    with zipfile.ZipFile(archive_path, "r") as zip_ref:
        zip_ref.extractall(extract_dir)


def process_features(
    features_iter: Any,
    source_crs: str,
    simplify_cfg: Optional[Dict[str, Any]] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Validate, repair, normalize CRS, and optionally simplify geometries."""
    # Build coordinate transformer to WGS84
    try:
        transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
    except Exception as e:
        raise ValueError(f"Failed to initialize CRS transformer from source '{source_crs}': {str(e)}")

    processed_features = []
    min_x, min_y, max_x, max_y = float("inf"), float("inf"), float("-inf"), float("-inf")

    for f_idx, feat in enumerate(features_iter):
        geom_raw = feat.get("geometry")
        properties = feat.get("properties", {})

        if not geom_raw:
            logger.warning("geometry.validation", f"Skipping feature {f_idx}: missing geometry.")
            continue

        try:
            # Parse raw geometry using shapely
            geom = shape(geom_raw)
            if geom.is_empty:
                logger.warning("geometry.validation", f"Skipping feature {f_idx}: empty geometry.")
                continue

            # Repair geometry if invalid
            if not geom.is_valid:
                geom = make_valid(geom)

            # Reproject using pyproj transformer
            geom_projected = transform(transformer.transform, geom)

            # Extract bounds
            g_minx, g_miny, g_maxx, g_maxy = geom_projected.bounds
            min_x = min(min_x, g_minx)
            min_y = min(min_y, g_miny)
            max_x = max(max_x, g_maxx)
            max_y = max(max_y, g_maxy)

            # Optional simplification
            if simplify_cfg and simplify_cfg.get("enabled"):
                tolerance = simplify_cfg.get("tolerance", 0.0001)
                geom_projected = geom_projected.simplify(tolerance, preserve_topology=True)

            processed_features.append({
                "type": "Feature",
                "geometry": mapping(geom_projected),
                "properties": properties
            })

        except Exception as e:
            logger.warning("geometry.process_error", f"Failed to process feature {f_idx}: {str(e)}")
            continue

    bbox = {
        "min_x": min_x if min_x != float("inf") else 0.0,
        "min_y": min_y if min_y != float("inf") else 0.0,
        "max_x": max_x if max_x != float("-inf") else 0.0,
        "max_y": max_y if max_y != float("-inf") else 0.0,
    }
    return processed_features, bbox


def read_shapefile(extract_dir: str) -> tuple[List[Dict[str, Any]], str]:
    """Locate and read ESRI Shapefile and its associated projection file.

    Returns a tuple of (features_list, source_crs_string).
    """
    shp_file = None
    prj_file = None

    for root, _, files in os.walk(extract_dir):
        for f in files:
            if f.lower().endswith(".shp"):
                shp_file = os.path.join(root, f)
            elif f.lower().endswith(".prj"):
                prj_file = os.path.join(root, f)

    if not shp_file:
        raise FileNotFoundError("No .shp file found in extracted directory.")

    # Read projection file content
    source_crs = "EPSG:4326"  # Fallback/Default
    if prj_file:
        with open(prj_file, "r", encoding="utf-8") as f:
            prj_wkt = f.read().strip()
            if prj_wkt:
                source_crs = prj_wkt
    else:
        raise ValueError("Missing .prj projection file in Shapefile archive.")

    features = []
    # Remove extension to pass base path to Reader
    base_path = os.path.splitext(shp_file)[0]
    with shapefile.Reader(base_path) as sf:
        fields = [field[0] for field in sf.fields[1:]]
        for sr in sf.shapeRecords():
            geom_interface = sr.shape.__geo_interface__
            properties = dict(zip(fields, sr.record))
            features.append({
                "geometry": geom_interface,
                "properties": properties
            })

    return features, source_crs


def read_geojson_file(filepath: str) -> List[Dict[str, Any]]:
    """Parse raw GeoJSON features from file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") == "FeatureCollection":
        return data.get("features", [])
    elif data.get("type") == "Feature":
        return [data]
    else:
        raise ValueError("Invalid GeoJSON input: must be Feature or FeatureCollection.")


async def ingest_dataset(
    cfg: DatasetConfig,
    dry_run: bool = False,
    force: bool = False,
    data_dir: str = "data",
) -> Dict[str, Any]:
    """Ingest, validate, normalize, and write output for a dataset.

    Returns run statistics dictionary.
    """
    start_time = time.time()
    dest_raw_path = os.path.join(data_dir, "raw", f"{cfg.id}.zip" if cfg.format == "zip_shapefile" else f"{cfg.id}.geojson")
    dest_processed_path = os.path.join(data_dir, "processed", f"{cfg.id}.geojson")
    manifest_path = os.path.join(data_dir, "processed", "manifests", f"{cfg.id}.json")

    # Cache hit check
    if not force and os.path.exists(dest_processed_path) and os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            if manifest.get("checksum_sha256") == cfg.sha256:
                logger.info(
                    "cache.hit",
                    f"Dataset {cfg.id} is already cached and matching checksum. Skipping ingestion.",
                    dataset_id=cfg.id,
                )
                return {
                    "dataset_id": cfg.id,
                    "status": "cached",
                    "feature_count": manifest.get("feature_count", 0),
                    "duration_ms": 0,
                }
        except Exception:
            pass  # If manifest read error, force re-ingestion

    # Prepare temp files
    temp_download_path = os.path.join(data_dir, "downloads", f"{cfg.id}_download.tmp")
    extract_dir = os.path.join(data_dir, "extracted", cfg.id)

    # URLs list
    urls = [cfg.official_source_url] + cfg.mirror_urls

    logger.info(
        "ingest.start",
        f"Starting ingestion pipeline for dataset: {cfg.id}",
        dataset_id=cfg.id,
        dry_run=dry_run,
    )

    downloaded_from = "N/A"
    mirror_used = "N/A"

    if not dry_run:
        # Download
        async with httpx.AsyncClient() as client:
            downloaded_from, mirror_used = await download_file_with_retry(
                client=client,
                urls=urls,
                download_order=cfg.preferred_download_order,
                dest_path=temp_download_path,
                expected_hash=cfg.sha256,
            )

        # Move to raw folder
        if os.path.exists(dest_raw_path):
            os.remove(dest_raw_path)
        shutil.move(temp_download_path, dest_raw_path)
    else:
        logger.info("ingest.dry_run", f"Dry run active: bypassing download for {cfg.id}.")
        # Mock values for dry run manifest check
        downloaded_from = urls[0]
        mirror_used = "N/A"
        # Create a mock source for pipeline validation in dry-run if not exists
        if not os.path.exists(dest_raw_path):
            # Create empty placeholder file to avoid crash in dry-run flow
            with open(dest_raw_path, "w") as f:
                f.write("")

    features = []
    source_crs = cfg.crs

    # Extract & Load geometries
    if cfg.format == "zip_shapefile":
        if not dry_run:
            extract_archive(dest_raw_path, extract_dir)
            features, source_crs = read_shapefile(extract_dir)
        else:
            # Mock empty shapefile response for dry-run
            features = []
    else:
        if not dry_run:
            features = read_geojson_file(dest_raw_path)
        else:
            # Mock empty GeoJSON response for dry-run
            features = []

    # Process geometries (validate, transform, optional simplify)
    simplify_cfg = {"enabled": cfg.simplify.enabled, "tolerance": cfg.simplify.tolerance}
    processed_features, bbox = process_features(
        features,
        source_crs=source_crs,
        simplify_cfg=simplify_cfg,
    )

    duration_ms = int((time.time() - start_time) * 1000)

    if not dry_run:
        # Write processed file
        feature_coll = {
            "type": "FeatureCollection",
            "crs": {
                "type": "name",
                "properties": {
                    "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
                }
            },
            "features": processed_features
        }
        with open(dest_processed_path, "w", encoding="utf-8") as f:
            json.dump(feature_coll, f, indent=2)

        # Write metadata manifest file
        manifest = {
            "dataset_name": cfg.name,
            "dataset_id": cfg.id,
            "official_source_url": cfg.official_source_url,
            "downloaded_from": downloaded_from,
            "mirror_used": mirror_used,
            "license": cfg.license,
            "acquisition_timestamp": datetime.now(timezone.utc).isoformat(),
            "dataset_version": cfg.version,
            "processing_version": "1.0.0",
            "checksum_sha256": cfg.sha256,
            "original_crs": cfg.crs if cfg.format == "geojson" else "PRJ_WKT",
            "normalized_crs": "EPSG:4326",
            "feature_count": len(processed_features),
            "bounding_box": bbox,
            "file_size_bytes": os.path.getsize(dest_processed_path),
            "processing_duration_ms": duration_ms,
            "software_version": "GridPilot GeoPipeline 1.0.0"
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # Clean temporary extracted files
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)

    logger.info(
        "ingest.success",
        f"Completed ingestion for dataset: {cfg.id}",
        dataset_id=cfg.id,
        features=len(processed_features),
        duration_ms=duration_ms,
    )

    return {
        "dataset_id": cfg.id,
        "status": "success",
        "feature_count": len(processed_features),
        "duration_ms": duration_ms,
    }


async def run_pipeline(
    config_path: str = "config/datasets.yaml",
    dataset_id: Optional[str] = None,
    dry_run: bool = False,
    force: bool = False,
) -> Dict[str, Any]:
    """Run ingestion for all or a single dataset in config."""
    setup_directories()

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    # Validate configuration via Pydantic model
    try:
        root_cfg = DatasetsRootConfig.model_validate(config_data)
    except ValidationError as e:
        logger.error("config.validation_error", "Configuration schema is invalid.", errors=e.errors())
        raise

    results = {}
    datasets_to_run = (
        [root_cfg.datasets[dataset_id]]
        if dataset_id and dataset_id in root_cfg.datasets
        else list(root_cfg.datasets.values())
    )

    if dataset_id and dataset_id not in root_cfg.datasets:
        raise ValueError(f"Requested dataset ID '{dataset_id}' not found in configuration.")

    for cfg in datasets_to_run:
        try:
            results[cfg.id] = await ingest_dataset(cfg, dry_run=dry_run, force=force)
        except Exception as e:
            logger.error("ingest.error", f"Pipeline execution failed for {cfg.id}: {str(e)}")
            results[cfg.id] = {
                "dataset_id": cfg.id,
                "status": "failed",
                "error": str(e),
                "duration_ms": 0,
            }
            if not dry_run:
                # Re-raise to halt pipeline on error as per specification
                raise

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GridPilot Geospatial Acquisition CLI")
    parser.add_argument("--config", default="config/datasets.yaml", help="Path to config datasets.yaml")
    parser.add_argument("--dataset", default=None, help="Process a single dataset ID")
    parser.add_argument("--dry-run", action="store_true", help="Dry run validation check without download writes")
    parser.add_argument("--force", action="store_true", help="Bypass local cache verification")

    args = parser.parse_args()

    import asyncio
    try:
        asyncio.run(
            run_pipeline(
                config_path=args.config,
                dataset_id=args.dataset,
                dry_run=args.dry_run,
                force=args.force,
            )
        )
    except Exception as exc:
        sys.stderr.write(f"Pipeline error: {str(exc)}\n")
        sys.exit(1)
