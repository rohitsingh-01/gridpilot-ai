"""Regulatory and environmental permit lookup tools supporting batch checks."""
from __future__ import annotations

import asyncio
from typing import List, Optional

from agents.site_intelligence.interfaces import ToolContext
from agents.site_intelligence.tools.decorators import tool_wrapper
from agents.environmental_permit.models import (
    PermitResult,
    PermitQueryRequest,
    PermitBatchRequest,
    PermitLookupError,
    Severity,
)


def sort_permits(permits: List[PermitResult]) -> List[PermitResult]:
    """Sort permits by severity, dataset origin, and permit identifier."""
    severity_order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
    }
    permits.sort(
        key=lambda p: (
            severity_order.get(p.severity, 4),
            p.quality.source_dataset,
            p.id,
        )
    )
    return permits


@tool_wrapper(required_permissions=["read:environmental"])
async def query_permit_requirements(
    context: ToolContext,
    request: PermitQueryRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> List[PermitResult]:
    """Search semantic regulatory memory to isolate necessary permitting requirements."""
    if context.environmental_service is None:
        context.telemetry_service.log_structured(
            "WARNING",
            "IEnvironmentalAnalysisService is unavailable. Returning empty results.",
            {"trace_id": context.trace_id}
        )
        return []

    if cancellation_token and cancellation_token.is_set():
        raise asyncio.CancelledError("Permit requirements query aborted.")

    try:
        results = await context.environmental_service.query_permit_requirements(request.query)
        return sort_permits(results)
    except Exception as exc:
        raise PermitLookupError(f"Failed to retrieve permit requirements: {str(exc)}")


@tool_wrapper(required_permissions=["read:environmental"])
async def query_permit_requirements_batch(
    context: ToolContext,
    request: PermitBatchRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> List[PermitResult]:
    """Batch query permit requirements concurrently for multiple query targets."""
    if context.environmental_service is None:
        return []

    if cancellation_token and cancellation_token.is_set():
        raise asyncio.CancelledError("Batch permit requirements query aborted.")

    async def fetch_single(query: str) -> List[PermitResult]:
        try:
            return await context.environmental_service.query_permit_requirements(query)
        except Exception as exc:
            context.telemetry_service.log_structured(
                "WARNING",
                f"Failed to query permits in batch: {str(exc)}",
                {"trace_id": context.trace_id}
            )
            return []

    # Run concurrently
    tasks = [fetch_single(q) for q in request.queries]
    nested_results = await asyncio.gather(*tasks)

    combined_results: List[PermitResult] = []
    for r_list in nested_results:
        combined_results.extend(r_list)

    # Deduplicate
    unique_results = {p.id: p for p in combined_results}.values()
    return sort_permits(list(unique_results))
