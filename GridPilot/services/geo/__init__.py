"""Geospatial ingestion service package exports."""
from __future__ import annotations

from services.geo.acquire import run_pipeline

__all__ = ["run_pipeline"]
