"""Unit and integration tests for the geospatial acquisition pipeline."""
from __future__ import annotations

import json
import os
import shutil
import zipfile
import hashlib
import pytest
from pydantic import ValidationError

import shapefile
import httpx
from shapely.geometry import Polygon, mapping, shape

from services.geo.config_models import DatasetConfig, DatasetsRootConfig
from services.geo.acquire import (
    run_pipeline,
    ingest_dataset,
    calculate_sha256,
    setup_directories,
)

# Enable anyio for async test support
pytestmark = pytest.mark.anyio

# Setup test constants
TEST_DATA_DIR = "test_data_lake"
MOCK_SOURCES_DIR = os.path.join(TEST_DATA_DIR, "mock_sources")


@pytest.fixture(autouse=True)
def clean_test_environment(monkeypatch):
    """Ensure test data directories are clean before and after tests and setup httpx mock."""
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    
    setup_directories(TEST_DATA_DIR)
    os.makedirs(MOCK_SOURCES_DIR, exist_ok=True)

    from contextlib import asynccontextmanager

    # Generic HTTP mock that serves files from mock_sources directory
    @asynccontextmanager
    async def mock_stream(self, method, url, **kwargs):
        url_str = str(url)
        filename = url_str.split("/")[-1]

        # Handle specific test case triggers
        if "error_trigger" in url_str:
            resp = httpx.Response(500, request=httpx.Request("GET", url))
            # Mock iter_bytes to prevent async iteration errors
            async def mock_iter_bytes(chunk_size=None):
                yield b""
            resp.iter_bytes = mock_iter_bytes
            yield resp
            return

        mock_file_path = os.path.join(MOCK_SOURCES_DIR, filename)
        if os.path.exists(mock_file_path):
            with open(mock_file_path, "rb") as f:
                content = f.read()
            resp = httpx.Response(200, content=content, request=httpx.Request("GET", url))
            
            # Mock iter_bytes to return an async generator
            async def mock_iter_bytes(chunk_size=None):
                size = chunk_size or 16384
                for i in range(0, len(content), size):
                    yield content[i : i + size]
            
            resp.iter_bytes = mock_iter_bytes
            yield resp
            return
        
        resp = httpx.Response(404, request=httpx.Request("GET", url))
        async def mock_iter_bytes(chunk_size=None):
            yield b""
        resp.iter_bytes = mock_iter_bytes
        yield resp

    monkeypatch.setattr(httpx.AsyncClient, "stream", mock_stream)
    
    yield
    
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)


def create_mock_shapefile_zip(dest_zip_path: str, include_prj: bool = True, write_bad_zip: bool = False) -> None:
    """Helper to create a temporary mock shapefile zip."""
    if write_bad_zip:
        with open(dest_zip_path, "wb") as f:
            f.write(b"NOT_A_ZIP_FILE_DATA_TRUNCATED")
        return

    base_temp = dest_zip_path.replace(".zip", "")
    with shapefile.Writer(base_temp) as w:
        w.field("WETLAND_TY", "C", 50)
        # Standard valid square polygon
        w.poly([[[1.0, 1.0], [1.0, 2.0], [2.0, 2.0], [2.0, 1.0], [1.0, 1.0]]])
        w.record("Freshwater Forested")

    # Write PRJ (NAD83 GCS)
    if include_prj:
        with open(base_temp + ".prj", "w") as f:
            f.write('GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137.0,298.257222101]],PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]')

    # Compress components into ZIP
    with zipfile.ZipFile(dest_zip_path, "w") as zf:
        extensions = [".shp", ".shx", ".dbf"]
        if include_prj:
            extensions.append(".prj")
        for ext in extensions:
            zf.write(base_temp + ext, f"mock_dataset{ext}")
            os.remove(base_temp + ext)


def create_mock_geojson(dest_path: str, features: list) -> None:
    """Helper to create a temporary mock GeoJSON file."""
    geojson_data = {
        "type": "FeatureCollection",
        "features": features
    }
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f)


# --- Test Cases ---

async def test_happy_path_geojson_ingestion():
    """Verify happy-path ingestion of a valid GeoJSON dataset."""
    mock_raw_path = os.path.join(MOCK_SOURCES_DIR, "test.geojson")
    create_mock_geojson(mock_raw_path, [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[10.0, 10.0], [10.0, 11.0], [11.0, 11.0], [11.0, 10.0], [10.0, 10.0]]]
            },
            "properties": {"name": "Habitat Area"}
        }
    ])
    expected_hash = calculate_sha256(mock_raw_path)

    cfg = DatasetConfig(
        id="test_geojson",
        name="Test Habitat",
        official_source_url="https://canonical.source/test.geojson",
        mirror_urls=[],
        preferred_download_order=["official"],
        license="MIT",
        version="v1",
        sha256=expected_hash,
        expected_size_bytes=os.path.getsize(mock_raw_path),
        format="geojson",
        crs="EPSG:4326"
    )

    stats = await ingest_dataset(cfg, dry_run=False, force=True, data_dir=TEST_DATA_DIR)
    assert stats["status"] == "success"
    assert stats["feature_count"] == 1

    # Verify manifest details
    manifest_path = os.path.join(TEST_DATA_DIR, "processed", "manifests", "test_geojson.json")
    assert os.path.exists(manifest_path)
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    assert manifest["dataset_id"] == "test_geojson"
    assert manifest["normalized_crs"] == "EPSG:4326"
    assert manifest["feature_count"] == 1


async def test_happy_path_shapefile_ingestion():
    """Verify happy-path extraction, reading, and processing of an ESRI Shapefile."""
    mock_raw_path = os.path.join(MOCK_SOURCES_DIR, "test.zip")
    create_mock_shapefile_zip(mock_raw_path, include_prj=True)
    expected_hash = calculate_sha256(mock_raw_path)

    cfg = DatasetConfig(
        id="test_shapefile",
        name="Test Wetlands",
        official_source_url="https://canonical.source/test.zip",
        mirror_urls=[],
        preferred_download_order=["official"],
        license="PD-US",
        version="v1",
        sha256=expected_hash,
        expected_size_bytes=os.path.getsize(mock_raw_path),
        format="zip_shapefile",
        crs="EPSG:4269"
    )

    stats = await ingest_dataset(cfg, dry_run=False, force=True, data_dir=TEST_DATA_DIR)
    assert stats["status"] == "success"
    assert stats["feature_count"] == 1

    # Check output exists
    processed_path = os.path.join(TEST_DATA_DIR, "processed", "test_shapefile.geojson")
    assert os.path.exists(processed_path)
    with open(processed_path, "r") as f:
        geojson = json.load(f)
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == 1


async def test_cache_hit_behavior():
    """Verify that a second run skips ingestion when processed outputs match the target checksum."""
    mock_raw_path = os.path.join(MOCK_SOURCES_DIR, "cache.geojson")
    create_mock_geojson(mock_raw_path, [])
    expected_hash = calculate_sha256(mock_raw_path)

    cfg = DatasetConfig(
        id="cache_dataset",
        name="Cached Dataset",
        official_source_url="https://canonical.source/cache.geojson",
        mirror_urls=[],
        preferred_download_order=["official"],
        license="MIT",
        version="v1",
        sha256=expected_hash,
        expected_size_bytes=os.path.getsize(mock_raw_path),
        format="geojson",
        crs="EPSG:4326"
    )

    # Ingest first time
    stats1 = await ingest_dataset(cfg, dry_run=False, force=True, data_dir=TEST_DATA_DIR)
    assert stats1["status"] == "success"

    # Ingest second time without force
    stats2 = await ingest_dataset(cfg, dry_run=False, force=False, data_dir=TEST_DATA_DIR)
    assert stats2["status"] == "cached"
    assert stats2["duration_ms"] == 0


async def test_corrupted_zip_failure():
    """Verify failure path on corrupted zip archives."""
    mock_raw_path = os.path.join(MOCK_SOURCES_DIR, "corrupted.zip")
    create_mock_shapefile_zip(mock_raw_path, write_bad_zip=True)
    expected_hash = calculate_sha256(mock_raw_path)

    cfg = DatasetConfig(
        id="corrupted",
        name="Corrupted Archive",
        official_source_url="https://canonical.source/corrupted.zip",
        mirror_urls=[],
        preferred_download_order=["official"],
        license="PD",
        version="v1",
        sha256=expected_hash,
        expected_size_bytes=os.path.getsize(mock_raw_path),
        format="zip_shapefile",
        crs="EPSG:4269"
    )

    with pytest.raises(zipfile.BadZipFile, match="not a valid ZIP archive"):
        await ingest_dataset(cfg, dry_run=False, force=True, data_dir=TEST_DATA_DIR)


async def test_missing_prj_file_failure():
    """Verify failure path on Shapefile archives missing a .prj file."""
    mock_raw_path = os.path.join(MOCK_SOURCES_DIR, "missing.zip")
    create_mock_shapefile_zip(mock_raw_path, include_prj=False)
    expected_hash = calculate_sha256(mock_raw_path)

    cfg = DatasetConfig(
        id="missing_prj",
        name="Missing PRJ",
        official_source_url="https://canonical.source/missing.zip",
        mirror_urls=[],
        preferred_download_order=["official"],
        license="PD",
        version="v1",
        sha256=expected_hash,
        expected_size_bytes=os.path.getsize(mock_raw_path),
        format="zip_shapefile",
        crs="EPSG:4269"
    )

    with pytest.raises(ValueError, match="Missing .prj projection file"):
        await ingest_dataset(cfg, dry_run=False, force=True, data_dir=TEST_DATA_DIR)


async def test_unsupported_crs_failure(monkeypatch):
    """Verify failure path when encountering unrecognized/unsupported CRS formats."""
    # Write a Shapefile with a junk WKT in the .prj
    mock_raw_path = os.path.join(MOCK_SOURCES_DIR, "bad_crs.zip")
    create_mock_shapefile_zip(mock_raw_path, include_prj=False)
    # Extract, add bad prj, and re-zip
    extract_dir = os.path.join(TEST_DATA_DIR, "extracted", "bad_crs")
    with zipfile.ZipFile(mock_raw_path, "r") as zf:
        zf.extractall(extract_dir)
    with open(os.path.join(extract_dir, "mock_dataset.prj"), "w") as f:
        f.write("JUNK_CRS_SPECIFICATION_THAT_WILL_NOT_PARSE")
    # Re-zip
    os.remove(mock_raw_path)
    with zipfile.ZipFile(mock_raw_path, "w") as zf:
        for f in os.listdir(extract_dir):
            zf.write(os.path.join(extract_dir, f), f)
    shutil.rmtree(extract_dir)

    expected_hash = calculate_sha256(mock_raw_path)

    cfg = DatasetConfig(
        id="bad_crs",
        name="Bad CRS",
        official_source_url="https://canonical.source/bad_crs.zip",
        mirror_urls=[],
        preferred_download_order=["official"],
        license="PD",
        version="v1",
        sha256=expected_hash,
        expected_size_bytes=os.path.getsize(mock_raw_path),
        format="zip_shapefile",
        crs="EPSG:99999"
    )

    with pytest.raises(ValueError, match="Failed to initialize CRS transformer"):
        await ingest_dataset(cfg, dry_run=False, force=True, data_dir=TEST_DATA_DIR)


async def test_geometry_self_intersection_repair():
    """Verify that self-intersecting geometries are repaired via make_valid."""
    mock_raw_path = os.path.join(MOCK_SOURCES_DIR, "bowtie.geojson")
    # Self-intersecting bowtie polygon
    bowtie_features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0.0, 0.0], [0.0, 2.0], [2.0, 0.0], [2.0, 2.0], [0.0, 0.0]]]
            },
            "properties": {"name": "Bowtie"}
        }
    ]
    create_mock_geojson(mock_raw_path, bowtie_features)
    expected_hash = calculate_sha256(mock_raw_path)

    cfg = DatasetConfig(
        id="bowtie",
        name="Self Intersecting",
        official_source_url="https://canonical.source/bowtie.geojson",
        mirror_urls=[],
        preferred_download_order=["official"],
        license="MIT",
        version="v1",
        sha256=expected_hash,
        expected_size_bytes=os.path.getsize(mock_raw_path),
        format="geojson",
        crs="EPSG:4326"
    )

    stats = await ingest_dataset(cfg, dry_run=False, force=True, data_dir=TEST_DATA_DIR)
    assert stats["status"] == "success"

    # Load processed file and assert shape is repaired (valid)
    processed_path = os.path.join(TEST_DATA_DIR, "processed", "bowtie.geojson")
    with open(processed_path, "r") as f:
        geojson = json.load(f)
    assert len(geojson["features"]) == 1
    # Verify that geometry in output is valid
    geom = shape(geojson["features"][0]["geometry"])
    assert geom.is_valid


async def test_optional_simplification():
    """Verify geometry optional simplification output and original preservation."""
    mock_raw_path = os.path.join(MOCK_SOURCES_DIR, "simple.geojson")
    # A detailed zigzag line/polygon
    coords = [[[0, 0], [0, 5], [1, 5], [1, 1], [2, 1], [2, 5], [3, 5], [3, 0], [0, 0]]]
    create_mock_geojson(mock_raw_path, [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": coords}, "properties": {}}])
    expected_hash = calculate_sha256(mock_raw_path)

    cfg = DatasetConfig(
        id="simple_test",
        name="Simplify Test",
        official_source_url="https://canonical.source/simple.geojson",
        mirror_urls=[],
        preferred_download_order=["official"],
        license="MIT",
        version="v1",
        sha256=expected_hash,
        expected_size_bytes=os.path.getsize(mock_raw_path),
        format="geojson",
        crs="EPSG:4326",
        simplify={
            "enabled": True,
            "tolerance": 2.0,
            "algorithm": "Douglas-Peucker"
        }
    )

    stats = await ingest_dataset(cfg, dry_run=False, force=True, data_dir=TEST_DATA_DIR)
    assert stats["status"] == "success"

    processed_path = os.path.join(TEST_DATA_DIR, "processed", "simple_test.geojson")
    assert os.path.exists(processed_path)

    # Read geometry to verify simplification occurred (fewer coordinates)
    with open(processed_path, "r") as f:
        geojson = json.load(f)
    poly = shape(geojson["features"][0]["geometry"])
    assert len(poly.exterior.coords) < 9


async def test_downloader_retry_and_mirror_fallback():
    """Verify download resilience retries and falls back to mirrors on HTTP server failure."""
    # Write expected raw mock geojson
    mock_raw_path = os.path.join(MOCK_SOURCES_DIR, "fallback.geojson")
    create_mock_geojson(mock_raw_path, [])
    expected_hash = calculate_sha256(mock_raw_path)

    cfg = DatasetConfig(
        id="fallback_test",
        name="Fallback Ingestion",
        official_source_url="https://error_trigger.source/fallback.geojson",
        mirror_urls=[
            "https://canonical.source/fallback.geojson"
        ],
        preferred_download_order=["official", "mirror1"],
        license="PD",
        version="v1",
        sha256=expected_hash,
        expected_size_bytes=os.path.getsize(mock_raw_path),
        format="geojson",
        crs="EPSG:4326"
    )

    stats = await ingest_dataset(cfg, dry_run=False, force=True, data_dir=TEST_DATA_DIR)
    assert stats["status"] == "success"
    assert stats["feature_count"] == 0
