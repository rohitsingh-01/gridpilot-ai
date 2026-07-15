"""OpenStreetMap physical infrastructure feature query tools with caching."""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import List, Optional

from agents.site_intelligence.interfaces import ToolContext, OSMFeature
from agents.site_intelligence.models import OSMRequest
from agents.site_intelligence.tools.decorators import tool_wrapper


def generate_cache_key(bbox: List[float], tags: List[str]) -> str:
    """Derive a stable SHA-256 cache key based on bounding box and tags."""
    # Ensure stable ordering of tags
    tag_str = ",".join(sorted(tags))
    bbox_str = ",".join(f"{coord:.6f}" for coord in bbox)
    combined = f"osm:{bbox_str}:{tag_str}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


@tool_wrapper(required_permissions=["read:osm"])
async def query_osm(
    context: ToolContext,
    request: OSMRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> List[OSMFeature]:
    """Query physical infrastructure features matching bbox and tags, with 24h caching."""
    # 1. Compute stable cache key
    cache_key = generate_cache_key(request.bbox, request.tags)

    # 2. Check Cache
    try:
        cached_val = await context.cache_service.get(cache_key)
        if cached_val is not None:
            # Cache Hit! Deserialize list of OSMFeature
            features_data = json.loads(cached_val)
            features = [OSMFeature.model_validate(f) for f in features_data]
            # Record telemetry metric for cache hit
            context.telemetry_service.record_metric(
                "tool.osm.cache_hit", 1.0, {"tool": "query_osm"}
            )
            return features
    except Exception as exc:
        # Cache corruption or Redis connection failure - log as warning and proceed to live query
        context.telemetry_service.log_structured(
            "WARNING",
            f"Cache lookup failed for key '{cache_key}': {str(exc)}. Recovering with fallback query.",
            {"trace_id": context.trace_id}
        )

    # 3. Check Cancellation before starting long network task
    if cancellation_token and cancellation_token.is_set():
        raise asyncio.CancelledError("OSM query aborted via cancellation token.")

    # 4. Live Query Map Provider
    features = await context.osm_service.query_features(request.bbox, request.tags)

    # 5. Populate Cache
    try:
        serialized = json.dumps([f.model_dump() for f in features])
        await context.cache_service.set(cache_key, serialized, ttl_seconds=86400)
        context.telemetry_service.record_metric(
            "tool.osm.cache_hit", 0.0, {"tool": "query_osm"}
        )
    except Exception as exc:
        # Log cache set failure but do not crash tool execution
        context.telemetry_service.log_structured(
            "WARNING",
            f"Failed to cache query results for key '{cache_key}': {str(exc)}",
            {"trace_id": context.trace_id}
        )

    return features
