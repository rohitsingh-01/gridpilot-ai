"""Pydantic validation models for the satellite imagery pre-cache pipeline configurations."""
from __future__ import annotations

from typing import List, Dict, Union, Optional
from pydantic import BaseModel, Field


class AoiSourceConfig(BaseModel):
    """Configuration for an Area of Interest source."""
    type: str = Field(pattern="^(geojson|bbox)$")
    path: Optional[str] = None
    coords: Optional[List[float]] = None


class RetryPolicyConfig(BaseModel):
    """Download and extraction retry policy configuration."""
    attempts: int = Field(default=4, ge=1)
    initial_backoff_seconds: float = Field(default=3.0, gt=0)
    exponential_factor: float = Field(default=2.0, gt=0)


class PipelineConfig(BaseModel):
    """Execution parameters for the satellite image processor."""
    provider: str = Field(pattern="^(sentinel2|landsat8|landsat9)$")
    cloud_cover_threshold: float = Field(default=0.15, ge=0, le=1)
    search_days_limit: int = Field(default=90, ge=1)
    bands: List[str] = Field(default_factory=lambda: ["red", "green", "blue"])
    output_resolution_meters: float = Field(default=10.0, gt=0)
    local_cache_path: str
    max_cache_size_gb: float = Field(default=20.0, gt=0)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)


class ImageryRootConfig(BaseModel):
    """Root configuration holding all settings for satellite imagery caching."""
    version: str
    aoi_sources: Dict[str, AoiSourceConfig]
    pipeline: PipelineConfig
