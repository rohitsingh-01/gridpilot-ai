"""Environmental Permit Agent orchestrator subclassing the BaseReasoningAgent blueprint."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from services.workflow.interfaces.agent import AgentInput
from services.db.repositories.interfaces import IUtilityRegionRepository
from agents.base_agent import BaseReasoningAgent
from agents.site_intelligence.interfaces import (
    ToolContext,
    ISemanticService,
    IImageryService,
    IGeoService,
    BaseMapProvider,
    ICacheService,
    ITelemetryService,
)
from agents.environmental_permit.interfaces import IEnvironmentalAnalysisService
from agents.environmental_permit.models import (
    EnvironmentalEvidenceBundle,
    WetlandsQueryRequest,
    HabitatQueryRequest,
    PermitQueryRequest,
    BufferAnalysisRequest,
    WetlandResult,
    HabitatResult,
    PermitResult,
    BufferResult,
    ExecutionSummary,
)
from agents.site_intelligence.models import ToolExecutionSummary
from agents.site_intelligence.registry import ToolRegistry
from agents.environmental_permit.report import build_report


class EnvironmentalPermitAgent(BaseReasoningAgent):
    """Orchestrator class coordinating environmental queries, calculations, and reporting."""

    def __init__(
        self,
        region_repository: IUtilityRegionRepository,
        semantic_service: ISemanticService,
        imagery_service: IImageryService,
        geo_service: IGeoService,
        osm_service: BaseMapProvider,
        cache_service: ICacheService,
        telemetry_service: ITelemetryService,
        environmental_service: IEnvironmentalAnalysisService,
    ) -> None:
        super().__init__(telemetry_service)
        self.region_repo = region_repository
        self.semantic_srv = semantic_service
        self.imagery_srv = imagery_service
        self.geo_srv = geo_service
        self.osm_srv = osm_service
        self.cache_srv = cache_service
        self.env_srv = environmental_service

    def build_tool_context(self, inputs: AgentInput, trace_id: str) -> ToolContext:
        """Construct a ToolContext instance from inputs."""
        return ToolContext(
            user_repository=inputs.context.user_repository,
            project_repository=inputs.context.project_repository,
            study_repository=inputs.context.study_repository,
            region_repository=self.region_repo,
            semantic_service=self.semantic_srv,
            imagery_service=self.imagery_srv,
            geo_service=self.geo_srv,
            osm_service=self.osm_srv,
            cache_service=self.cache_srv,
            telemetry_service=self.telemetry_srv,
            environmental_service=self.env_srv,
            user=inputs.context.metadata.get("user", "environmental_permit_agent"),
            permissions=inputs.context.metadata.get("permissions", [
                "read:project", "read:study", "read:region", "read:environmental"
            ]),
            trace_id=trace_id,
        )

    async def gather_evidence(
        self,
        tool_context: ToolContext,
        inputs: AgentInput,
        tool_metrics: List[ToolExecutionSummary],
    ) -> EnvironmentalEvidenceBundle:
        """Execute environmental tools in parallel where possible, compiling an EnvironmentalEvidenceBundle."""
        start_time = time.perf_counter()
        
        # 1. Resolve Area of Interest (AOI) geometry
        aoi = inputs.task_inputs.get("aoi_geojson") or inputs.context.metadata.get("aoi_geojson") or {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]]
        }

        warnings: List[str] = []
        cache_hits = 0
        cache_misses = 0

        async def run_tool(name: str, request: Any, optional: bool = True) -> Optional[Any]:
            nonlocal cache_hits, cache_misses
            tool_start = time.perf_counter()
            success = False
            warning_count = 0
            res = None
            try:
                tool_func = ToolRegistry.get(name)
                cancellation_token = inputs.context.metadata.get("cancellation_token")
                res = await tool_func(tool_context, request, cancellation_token)
                success = True
                if res and not res.success:
                    success = False
                    if res.errors:
                        warnings.append(f"Tool {name} error: {res.errors[0]}")
                if res and getattr(res, "metrics", {}).get("cached_hit", False):
                    cache_hits += 1
                else:
                    cache_misses += 1
                return res.data if res else None
            except Exception as exc:
                warning_count = 1
                warnings.append(f"Tool {name} failed: {str(exc)}")
                if not optional:
                    raise
                return [] if "batch" in name or "query" in name else None
            finally:
                dur_ms = int((time.perf_counter() - tool_start) * 1000)
                tool_metrics.append(
                    ToolExecutionSummary(
                        tool_name=name,
                        duration_ms=dur_ms,
                        success=success,
                        cached=getattr(res, "metrics", {}).get("cached_hit", False) if res else False,
                        warning_count=warning_count,
                    )
                )

        # Execute lookups concurrently using gather
        wetlands_task = run_tool("query_wetlands", WetlandsQueryRequest(aoi_geojson=aoi))
        habitats_task = run_tool("query_critical_habitat", HabitatQueryRequest(aoi_geojson=aoi))
        permits_task = run_tool("query_permit_requirements", PermitQueryRequest(query="permits environmental conservation"))
        buffers_task = run_tool("calculate_environmental_buffers", BufferAnalysisRequest(aoi_geojson=aoi, buffer_m=100.0))

        wetlands_data, habitats_data, permits_data, buffers_data = await asyncio.gather(
            wetlands_task, habitats_task, permits_task, buffers_task
        )

        # Expose warnings for missing services
        if self.env_srv is None:
            warnings.append("IEnvironmentalAnalysisService is unavailable.")

        dur_ms = int((time.perf_counter() - start_time) * 1000)
        summary = ExecutionSummary(
            tools_executed=[m.tool_name for m in tool_metrics],
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            warnings=warnings,
            execution_duration_ms=dur_ms,
        )

        return EnvironmentalEvidenceBundle(
            wetlands=wetlands_data or [],
            habitats=habitats_data or [],
            permits=permits_data or [],
            buffers=[buffers_data] if buffers_data else [],
            execution_summary=summary,
        )

    def compile_report(
        self,
        evidence: EnvironmentalEvidenceBundle,
        tool_context: ToolContext,
        workflow_id: str,
        tool_metrics: List[ToolExecutionSummary],
    ) -> Any:
        """Assemble environmental permitting report."""
        study_id = tool_context.study_repository.study_id if hasattr(tool_context.study_repository, 'study_id') else "study_test_123"
        return build_report(
            evidence=evidence,
            trace_id=tool_context.trace_id,
            workflow_id=workflow_id,
            study_id=study_id,
        )
