"""Wetland query tools supporting single and batch lookups with deterministic sorting."""
from __future__ import annotations

import asyncio
from typing import List, Optional

from agents.site_intelligence.interfaces import ToolContext
from agents.site_intelligence.tools.decorators import tool_wrapper
from agents.environmental_permit.models import (
    WetlandResult,
    WetlandsQueryRequest,
    WetlandsBatchRequest,
    WetlandLookupError,
    Severity,
)


def sort_wetlands(wetlands: List[WetlandResult]) -> List[WetlandResult]:
    """Sort wetlands by severity level, dataset precedence, and feature ID."""
    severity_order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
    }
    wetlands.sort(
        key=lambda w: (
            severity_order.get(w.severity, 4),
            w.quality.source_dataset,
            w.id,
        )
    )
    return wetlands


@tool_wrapper(required_permissions=["read:environmental"])
async def query_wetlands(
    context: ToolContext,
    request: WetlandsQueryRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> List[WetlandResult]:
    """Query wetlands intersecting the target Area of Interest."""
    if context.environmental_service is None:
        # Fallback to empty list (partial success) with a logged warning
        context.telemetry_service.log_structured(
            "WARNING",
            "IEnvironmentalAnalysisService is unavailable. Returning empty results.",
            {"trace_id": context.trace_id}
        )
        return []

    if cancellation_token and cancellation_token.is_set():
        raise asyncio.CancelledError("Wetlands query aborted.")

    try:
        results = await context.environmental_service.query_wetlands(request.aoi_geojson)
        return sort_wetlands(results)
    except Exception as exc:
        raise WetlandLookupError(f"Failed to query wetlands: {str(exc)}")


@tool_wrapper(required_permissions=["read:environmental"])
async def query_wetlands_batch(
    context: ToolContext,
    request: WetlandsBatchRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> List[WetlandResult]:
    """Batch query wetlands intersecting multiple target Areas of Interest."""
    if context.environmental_service is None:
        return []

    combined_results: List[WetlandResult] = []
    
    # Process batch with cancellation check
    for aoi in request.aois:
        if cancellation_token and cancellation_token.is_set():
            raise asyncio.CancelledError("Batch wetlands query aborted.")
        
        try:
            results = await context.environmental_service.query_wetlands(aoi)
            combined_results.extend(results)
        except Exception as exc:
            context.telemetry_service.log_structured(
                "WARNING",
                f"Failed to query wetland in batch: {str(exc)}",
                {"trace_id": context.trace_id}
            )

    # Remove duplicates based on ID
    unique_results = {w.id: w for w in combined_results}.values()
    return sort_wetlands(list(unique_results))
