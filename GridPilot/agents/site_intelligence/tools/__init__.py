"""Explicit dynamic registration of Site Intelligence tools into ToolRegistry."""
from __future__ import annotations

from agents.site_intelligence.registry import ToolRegistry
from agents.site_intelligence.tools.project import get_project, get_study, get_region
from agents.site_intelligence.tools.imagery import fetch_satellite_tile_metadata
from agents.site_intelligence.tools.osm import query_osm
from agents.site_intelligence.tools.geometry import calculate_buffer, calculate_intersection
from agents.site_intelligence.tools.semantic import semantic_search

# Explicit, deterministic registration of available tools
ToolRegistry.register("get_project", get_project)
ToolRegistry.register("get_study", get_study)
ToolRegistry.register("get_region", get_region)
ToolRegistry.register("fetch_satellite_tile_metadata", fetch_satellite_tile_metadata)
ToolRegistry.register("query_osm", query_osm)
ToolRegistry.register("calculate_buffer", calculate_buffer)
ToolRegistry.register("calculate_intersection", calculate_intersection)
ToolRegistry.register("semantic_search", semantic_search)

__all__ = [
    "get_project",
    "get_study",
    "get_region",
    "fetch_satellite_tile_metadata",
    "query_osm",
    "calculate_buffer",
    "calculate_intersection",
    "semantic_search",
]
