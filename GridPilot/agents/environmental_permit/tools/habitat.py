"""Critical habitat query tools supporting single and batch parallel lookups with deterministic sorting."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from agents.site_intelligence.interfaces import ToolContext
from agents.site_intelligence.tools.decorators import tool_wrapper
from agents.environmental_permit.models import (
    HabitatResult,
    HabitatQueryRequest,
    HabitatBatchRequest,
    HabitatLookupError,
    Severity,
)


def sort_habitats(habitats: List[HabitatResult]) -> List[HabitatResult]:
    """Sort habitats by severity level, dataset precedence, and species identifier."""
    severity_order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
    }
    habitats.sort(
        key=lambda h: (
            severity_order.get(h.severity, 4),
            h.quality.source_dataset,
            h.id,
        )
    )
    return habitats


@tool_wrapper(required_permissions=["read:environmental"])
async def query_critical_habitat(
    context: ToolContext,
    request: HabitatQueryRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> List[HabitatResult]:
    """Query critical habitats intersecting the target Area of Interest."""
    if context.environmental_service is None:
        context.telemetry_service.log_structured(
            "WARNING",
            "IEnvironmentalAnalysisService is unavailable. Returning empty results.",
            {"trace_id": context.trace_id}
        )
        return []

    if cancellation_token and cancellation_token.is_set():
        raise asyncio.CancelledError("Critical habitats query aborted.")

    try:
        results = await context.environmental_service.query_critical_habitats(request.aoi_geojson)
        return sort_habitats(results)
    except Exception as exc:
        raise HabitatLookupError(f"Failed to query critical habitats: {str(exc)}")


@tool_wrapper(required_permissions=["read:environmental"])
async def query_critical_habitat_batch(
    context: ToolContext,
    request: HabitatBatchRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> List[HabitatResult]:
    """Batch query critical habitats intersecting multiple target Areas of Interest concurrently."""
    if context.environmental_service is None:
        return []

    if cancellation_token and cancellation_token.is_set():
        raise asyncio.CancelledError("Batch critical habitats query aborted.")

    async def fetch_single(aoi: Dict[str, Any]) -> List[HabitatResult]:
        try:
            return await context.environmental_service.query_critical_habitats(aoi)
        except Exception as exc:
            context.telemetry_service.log_structured(
                "WARNING",
                f"Failed to query critical habitat in batch: {str(exc)}",
                {"trace_id": context.trace_id}
            )
            return []

    # Run batch queries concurrently using gather
    tasks = [fetch_single(aoi) for aoi in request.aois]
    nested_results = await asyncio.gather(*tasks)

    combined_results: List[HabitatResult] = []
    for r_list in nested_results:
        combined_results.extend(r_list)

    # Remove duplicates
    unique_results = {h.id: h for h in combined_results}.values()
    return sort_habitats(list(unique_results))
