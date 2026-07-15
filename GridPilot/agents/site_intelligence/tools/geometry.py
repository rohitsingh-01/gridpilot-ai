"""Geospatial calculations and buffer generation tools."""
from __future__ import annotations

from typing import Dict, Any, Optional
import asyncio

from agents.site_intelligence.interfaces import ToolContext
from agents.site_intelligence.models import BufferRequest, IntersectionRequest
from agents.site_intelligence.tools.decorators import tool_wrapper


@tool_wrapper(required_permissions=["read:spatial"])
async def calculate_buffer(
    context: ToolContext,
    request: BufferRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> Dict[str, Any]:
    """Calculate buffer boundary geometry using the injected geo_service."""
    buffered = context.geo_service.buffer(
        aoi_geojson=request.aoi_geojson,
        buffer_m=request.buffer_m
    )
    return {
        "buffered_geojson": buffered,
        "buffer_m": request.buffer_m,
    }


@tool_wrapper(required_permissions=["read:spatial"])
async def calculate_intersection(
    context: ToolContext,
    request: IntersectionRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> Dict[str, Any]:
    """Calculate whether two geometries intersect, and get their distance."""
    intersects = context.geo_service.intersects(
        geom1=request.aoi_geojson,
        geom2=request.target_geojson
    )
    dist = context.geo_service.distance(
        geom1=request.aoi_geojson,
        geom2=request.target_geojson
    )
    return {
        "intersects": intersects,
        "distance_m": dist,
    }
