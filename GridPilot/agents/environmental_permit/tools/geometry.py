"""Geospatial buffer setback calculations and compliance check tools."""
from __future__ import annotations

import asyncio
from typing import Optional

from agents.site_intelligence.interfaces import ToolContext
from agents.site_intelligence.tools.decorators import tool_wrapper
from agents.environmental_permit.models import (
    BufferResult,
    BufferAnalysisRequest,
    EnvironmentalToolError,
)


@tool_wrapper(required_permissions=["read:environmental"])
async def calculate_environmental_buffers(
    context: ToolContext,
    request: BufferAnalysisRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> BufferResult:
    """Analyze actual setbacks against target bounds to flag setback compliance violations."""
    if context.environmental_service is None:
        raise EnvironmentalToolError("IEnvironmentalAnalysisService is unavailable for calculation.")

    if cancellation_token and cancellation_token.is_set():
        raise asyncio.CancelledError("Buffer calculations aborted.")

    try:
        # Calculate setbacks using service
        result = context.environmental_service.calculate_buffers(
            aoi_geojson=request.aoi_geojson,
            buffer_m=request.buffer_m
        )
        return result
    except Exception as exc:
        raise EnvironmentalToolError(f"Failed to calculate buffers: {str(exc)}")
