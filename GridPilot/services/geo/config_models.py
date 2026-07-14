"""Pydantic validation models for the geospatial dataset acquisition configurations."""
from __future__ import annotations

from typing import List, Dict, Optional
from pydantic import BaseModel, Field, HttpUrl


class SimplifyConfig(BaseModel):
    """Configuration for optional geometry simplification."""
    enabled: bool = False
    tolerance: float = Field(default=0.0001, gt=0)
    algorithm: str = Field(default="Douglas-Peucker", pattern="^(Douglas-Peucker)$")


class DatasetConfig(BaseModel):
    """Configuration details for a single target dataset."""
    id: str
    name: str
    official_source_url: str
    mirror_urls: List[str] = Field(default_factory=list)
    preferred_download_order: List[str]
    license: str
    version: str
    sha256: str
    expected_size_bytes: int = Field(gt=0)
    format: str = Field(pattern="^(zip_shapefile|geojson)$")
    crs: str = Field(pattern="^EPSG:\\d+$")
    simplify: SimplifyConfig = Field(default_factory=SimplifyConfig)


class DatasetsRootConfig(BaseModel):
    """Root configuration holding multiple dataset definitions."""
    version: str
    datasets: Dict[str, DatasetConfig]
