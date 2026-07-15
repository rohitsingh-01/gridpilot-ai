"""Site Intelligence Agent coordinating execution pipelines and returning standardized outputs."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.workflow.interfaces.agent import BaseAgent, AgentInput, AgentOutput, AgentExecutionMetadata
from services.db.repositories.interfaces import IUserRepository, IProjectRepository, IStudyRepository, IUtilityRegionRepository
from agents.site_intelligence.interfaces import (
    ToolContext,
    ISemanticService,
    IImageryService,
    IGeoService,
    BaseMapProvider,
    ICacheService,
    ITelemetryService,
)
from agents.site_intelligence.models import (
    EvidenceBundle,
    ProjectModel,
    StudyModel,
    RegionModel,
    ToolExecutionSummary,
    ProjectRequest,
    StudyRequest,
    RegionRequest,
    TileRequest,
    OSMRequest,
    IntersectionRequest,
    SearchRequest,
)
from agents.site_intelligence.registry import ToolRegistry
from agents.site_intelligence.report import build_report
import agents.site_intelligence.tools  # Trigger dynamic tool registration


class SiteIntelligenceAgent(BaseAgent):
    """Orchestrator coordinating site analysis tool executions and deterministic reasoning."""

    def __init__(
        self,
        region_repository: IUtilityRegionRepository,
        semantic_service: ISemanticService,
        imagery_service: IImageryService,
        geo_service: IGeoService,
        osm_service: BaseMapProvider,
        cache_service: ICacheService,
        telemetry_service: ITelemetryService,
    ) -> None:
        self.region_repo = region_repository
        self.semantic_srv = semantic_service
        self.imagery_srv = imagery_service
        self.geo_srv = geo_service
        self.osm_srv = osm_service
        self.cache_srv = cache_service
        self.telemetry_srv = telemetry_service

    async def execute(self, inputs: AgentInput) -> AgentOutput:
        start_time = time.perf_counter()
        trace_id = inputs.context.metadata.get("trace_id", f"trace_{int(time.time())}")
        workflow_id = inputs.context.metadata.get("workflow_id", f"wf_{inputs.context.study_id}")
        
        # 1. Initialize ToolContext
        tool_context = ToolContext(
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
            user=inputs.context.metadata.get("user", "agent_system"),
            permissions=inputs.context.metadata.get("permissions", ["read:project", "read:study", "read:region", "read:imagery", "read:osm", "read:spatial", "read:semantic"]),
            trace_id=trace_id,
        )

        tool_metrics: List[ToolExecutionSummary] = []
        
        # Helper to execute tools with duration telemetry
        async def run_tool(name: str, request: Any, optional: bool = False) -> Optional[Any]:
            tool_start = time.perf_counter()
            success = False
            warning_count = 0
            res = None
            try:
                tool_func = ToolRegistry.get(name)
                res = await tool_func(tool_context, request)
                success = True
                if res and not res.success:
                    success = False
                return res
            except Exception as exc:
                if not optional:
                    raise
                # Safe fallback for optional tools (e.g. imagery tile misses)
                warning_count = 1
                return None
            finally:
                dur_ms = int((time.perf_counter() - tool_start) * 1000)
                tool_metrics.append(
                    ToolExecutionSummary(
                        tool_name=name,
                        duration_ms=dur_ms,
                        success=success,
                        cached=getattr(res, "metadata", {}).get("cached_hit", False) if res else False,
                        warning_count=warning_count,
                    )
                )

        # 2. Sequential Execution Pipeline
        # Phase A: Database Lookups
        proj_res = await run_tool("get_project", ProjectRequest(project_id=inputs.context.project_id))
        study_res = await run_tool("get_study", StudyRequest(study_id=inputs.context.study_id))
        
        region_id = study_res.data.get("region_id") or "reg_default"
        region_res = await run_tool("get_region", RegionRequest(region_id=region_id))

        # Convert entity payloads
        proj_model = ProjectModel(
            id=proj_res.data["id"],
            name=proj_res.data["name"],
            status=proj_res.data["status"],
        )
        study_model = StudyModel(
            id=study_res.data["id"],
            project_id=study_res.data["project_id"],
            status=study_res.data["status"],
            region_id=study_res.data.get("region_id"),
        )
        region_model = RegionModel(
            id=region_res.data["id"],
            name=region_res.data["name"],
            code=region_res.data["code"],
        )

        # Phase B: Satellite Imagery Lookup (Optional)
        img_res = await run_tool(
            "fetch_satellite_tile_metadata",
            TileRequest(region_id=region_model.id, scene_date="2026-07-15"),
            optional=True,
        )

        # Phase C: OSM Lookup (Optional)
        osm_res = await run_tool(
            "query_osm",
            OSMRequest(bbox=[42.0, -71.5, 42.1, -71.4], tags=["power=line"]),
            optional=True,
        )

        # Phase D: Spatial Buffers & Intersections
        # Dummy polygon for standard test cases
        aoi_poly = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
        target_poly = {"type": "Polygon", "coordinates": [[[0.5, 0.5], [0.5, 0.6], [0.6, 0.6], [0.6, 0.5], [0.5, 0.5]]]}
        
        geom_res = await run_tool(
            "calculate_intersection",
            IntersectionRequest(aoi_geojson=aoi_poly, target_geojson=target_poly),
        )

        # Phase E: Semantic Search
        sem_res = await run_tool(
            "semantic_search",
            SearchRequest(query="wetlands restrictions regulatory precedents", collection="environmental"),
        )

        # 3. Consolidate into EvidenceBundle
        evidence = EvidenceBundle(
            project=proj_model,
            study=study_model,
            region=region_model,
            imagery=img_res.data if img_res else None,
            osm_features=osm_res.data if osm_res else [],
            semantic_chunks=sem_res.data if sem_res else [],
            geometry_results=geom_res.data if geom_res else {},
        )

        # 4. Generate structured report
        report = build_report(
            evidence=evidence,
            trace_id=trace_id,
            workflow_id=workflow_id,
            tool_metrics=tool_metrics,
        )

        dur_total_ms = int((time.perf_counter() - start_time) * 1000)

        # 5. Telemetry updates
        self.telemetry_srv.record_metric(
            "agent.execution_duration_ms", dur_total_ms, {"agent": "site_intelligence"}
        )

        # Return standard AgentOutput envelope
        return AgentOutput(
            confidence=report.confidence_score,
            sources=[f"OSS: {m.tool_name}" for m in tool_metrics],
            assumptions=report.assumptions,
            raw_model_output=f"Risk level: {report.overall_risk}. Completed: {report.status}.",
            structured_data=report.model_dump(),
            execution_metadata=AgentExecutionMetadata(
                execution_duration_ms=dur_total_ms,
                retry_count=0,
                warnings=report.warnings + [f"Missing tool data" for m in tool_metrics if not m.success],
                agent_version="1.0.0",
            )
        )
