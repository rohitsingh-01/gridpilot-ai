"""Unit and integration tests for the satellite imagery pre-cache pipeline."""
from __future__ import annotations

import json
import os
import shutil
import hashlib
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from PIL import Image

from services.geo.imagery_models import ImageryRootConfig
from services.geo.fetch_satellite import (
    run_imagery_pipeline,
    acquire_imagery,
    setup_imagery_directories,
    load_cache_index,
    save_cache_index,
    rebuild_cache_index,
    MockSentinel2Provider,
    SatelliteScene,
)

# Enable anyio for async test support
pytestmark = pytest.mark.anyio

TEST_IMAGERY_DIR = "test_imagery_lake"


@pytest.fixture(autouse=True)
def clean_test_environment():
    """Ensure test data directories are clean before and after tests."""
    if os.path.exists(TEST_IMAGERY_DIR):
        shutil.rmtree(TEST_IMAGERY_DIR)
    setup_imagery_directories(TEST_IMAGERY_DIR)
    yield
    if os.path.exists(TEST_IMAGERY_DIR):
        shutil.rmtree(TEST_IMAGERY_DIR)


def create_dummy_config() -> ImageryRootConfig:
    """Helper to return a pre-configured ImageryRootConfig for testing."""
    return ImageryRootConfig.model_validate({
        "version": "1.0.0",
        "aoi_sources": {
            "test_aoi": {
                "type": "bbox",
                "coords": [-103.5, 30.5, -101.5, 31.8]
            }
        },
        "pipeline": {
            "provider": "sentinel2",
            "cloud_cover_threshold": 0.15,
            "search_days_limit": 90,
            "bands": ["red", "green", "blue"],
            "local_cache_path": TEST_IMAGERY_DIR,
            "max_cache_size_gb": 10.0,
            "retry_policy": {
                "attempts": 2,
                "initial_backoff_seconds": 0.1,
                "exponential_factor": 1.5
            }
        }
    })


# --- Test Cases ---

async def test_cache_hit_bypasses_network():
    """Verify that a cache hit skips remote discovery and downloading."""
    cfg = create_dummy_config()
    provider = MockSentinel2Provider()

    # Pre-populate files in the local cache directory
    cache_key = "sentinel2_test_aoi_20260714"
    # Ensure current date suffix matches the cache key generated in acquire_imagery
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache_key = f"sentinel2_test_aoi_{today_str}"

    dest_cog = os.path.join(TEST_IMAGERY_DIR, "cache", f"{cache_key}.tif")
    dest_png = os.path.join(TEST_IMAGERY_DIR, "cache", f"{cache_key}.png")
    
    with open(dest_cog, "w") as f:
        f.write("DUMMY_TIFF_CONTENT")
    with open(dest_png, "w") as f:
        f.write("DUMMY_PNG_CONTENT")

    # Add entry to cache index
    index = load_cache_index(TEST_IMAGERY_DIR)
    checksum = hashlib.sha256(b"DUMMY_TIFF_CONTENT").hexdigest()
    index["entries"][cache_key] = {
        "cache_key": cache_key,
        "cog_path": dest_cog,
        "png_path": dest_png,
        "checksum_sha256": checksum,
        "acquisition_timestamp": datetime.now(timezone.utc).isoformat(),
        "oss_synced": False
    }
    save_cache_index(TEST_IMAGERY_DIR, index)

    # Ingest with dry-run and verify it returns cached status instantly
    stats = await acquire_imagery("test_aoi", cfg, provider, dry_run=True, force=False)
    assert stats["status"] == "cached"
    assert stats["duration_ms"] == 0


async def test_cache_miss_triggers_download_and_conversion():
    """Verify that a cache miss downloads bands and compiles COG/PNG outputs."""
    cfg = create_dummy_config()
    provider = MockSentinel2Provider()

    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache_key = f"sentinel2_test_aoi_{today_str}"

    # Ingest (bypassing download block via dry_run=False since mock provider creates local bands)
    stats = await acquire_imagery("test_aoi", cfg, provider, dry_run=False, force=True)
    assert stats["status"] == "success"

    # Verify processed outputs exist on disk
    dest_cog = os.path.join(TEST_IMAGERY_DIR, "cache", f"{cache_key}.tif")
    dest_png = os.path.join(TEST_IMAGERY_DIR, "cache", f"{cache_key}.png")
    dest_thumb = os.path.join(TEST_IMAGERY_DIR, "thumbnails", f"{cache_key}_thumb.jpg")
    manifest_path = os.path.join(TEST_IMAGERY_DIR, "manifests", f"{cache_key}.json")

    assert os.path.exists(dest_cog)
    assert os.path.exists(dest_png)
    assert os.path.exists(dest_thumb)
    assert os.path.exists(manifest_path)

    # Check manifest content
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    assert manifest["tile_identifier"] == "T14RNV"
    assert manifest["cloud_cover_percentage"] == 3.0  # From MockSentinel2Provider clear scene (0.03 * 100)


async def test_cloud_cover_filtering_no_scenes():
    """Verify that the pipeline throws an error if all discovered scenes exceed the cloud cover threshold."""
    cfg = create_dummy_config()
    # Set threshold to 1% (lower than our best mock scene of 3%)
    cfg.pipeline.cloud_cover_threshold = 0.01
    provider = MockSentinel2Provider()

    with pytest.raises(ValueError, match="No scenes matching cloud cover threshold"):
        await acquire_imagery("test_aoi", cfg, provider, dry_run=False, force=True)


async def test_provider_download_failure_triggers_retry():
    """Verify that a remote provider download crash triggers retries up to the policy limit."""
    cfg = create_dummy_config()
    cfg.pipeline.retry_policy.attempts = 2  # Set attempts to 2

    # Instantiate mock provider set to force download failures
    failing_provider = MockSentinel2Provider(force_fail_download=True)

    with pytest.raises(RuntimeError, match="All download attempts failed"):
        await acquire_imagery("test_aoi", cfg, failing_provider, dry_run=False, force=True)


async def test_cache_index_rebuild_from_manifests():
    """Verify that the cache index is rebuilt successfully from local manifest metadata on corruption."""
    cfg = create_dummy_config()
    provider = MockSentinel2Provider()

    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    cache_key = f"sentinel2_test_aoi_{today_str}"

    # Generate initial ingestion with manifest and valid index
    await acquire_imagery("test_aoi", cfg, provider, dry_run=False, force=True)

    # Delete index file to simulate corruption/loss
    index_path = os.path.join(TEST_IMAGERY_DIR, "cache_index.json")
    assert os.path.exists(index_path)
    os.remove(index_path)

    # Calling load_cache_index should trigger automatic rebuild
    recovered_index = load_cache_index(TEST_IMAGERY_DIR)
    assert cache_key in recovered_index["entries"]
    assert recovered_index["entries"][cache_key]["checksum_sha256"] is not None
