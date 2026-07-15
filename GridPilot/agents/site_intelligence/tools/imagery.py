"""Satellite imagery metadata lookup tools."""
from __future__ import annotations

from typing import Optional
import asyncio

from agents.site_intelligence.interfaces import ToolContext, ImageryMetadata
from agents.site_intelligence.models import TileRequest
from agents.site_intelligence.tools.decorators import tool_wrapper


@tool_wrapper(required_permissions=["read:imagery"])
async def fetch_satellite_tile_metadata(
    context: ToolContext,
    request: TileRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> ImageryMetadata:
    """Fetch pre-cached true-color Sentinel-2 tile metadata (path, mime_type, checksum, dimensions)."""
    # Call the abstract imagery_service
    metadata = await context.imagery_service.get_metadata(
        region_id=request.region_id,
        scene_date=request.scene_date
    )
    return metadata
