"""Site Intelligence Agent implementing the BaseReasoningAgent orchestration blueprint."""
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
    SiteIntelligenceReport,
)
from agents.site_intelligence.registry import ToolRegistry
from agents.site_intelligence.report import build_report


class SiteIntelligenceAgent(BaseReasoningAgent):
    """Subclass orchestrator for Site location checks, wetland buffers, and grid intersections."""

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
        super().__init__(telemetry_service)
        self.region_repo = region_repository
        self.semantic_srv = semantic_service
        self.imagery_srv = imagery_service
        self.geo_srv = geo_service
        self.osm_srv = osm_service
        self.cache_srv = cache_service

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
            user=inputs.context.metadata.get("user", "agent_system"),
            permissions=inputs.context.metadata.get("permissions", [
                "read:project", "read:study", "read:region", "read:imagery", "read:osm", "read:spatial", "read:semantic"
            ]),
            trace_id=trace_id,
        )

    async def gather_evidence(
        self,
        tool_context: ToolContext,
        inputs: AgentInput,
        tool_metrics: List[ToolExecutionSummary],
    ) -> EvidenceBundle:
        """Sequential tool queries to compile an EvidenceBundle."""

        async def run_tool(name: str, request: Any, optional: bool = False) -> Optional[Any]:
            tool_start = time.perf_counter()
            success = False
            warning_count = 0
            res = None
            try:
                tool_func = ToolRegistry.get(name)
                # Pass cancellation event if available in workflow context metadata
                cancellation_token = inputs.context.metadata.get("cancellation_token")
                res = await tool_func(tool_context, request, cancellation_token)
                success = True
                if res and not res.success:
                    success = False
                return res
            except Exception as exc:
                if not optional:
                    raise
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

        # 1. Database Lookups
        proj_res = await run_tool("get_project", ProjectRequest(project_id=inputs.context.project_id))
        study_res = await run_tool("get_study", StudyRequest(study_id=inputs.context.study_id))
        
        region_id = study_res.data.get("region_id") or "reg_default"
        region_res = await run_tool("get_region", RegionRequest(region_id=region_id))

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

        # 2. Satellite imagery (optional fallback)
        img_res = await run_tool(
            "fetch_satellite_tile_metadata",
            TileRequest(region_id=region_model.id, scene_date="2026-07-15"),
            optional=True,
        )

        # 3. OpenStreetMap grid (optional fallback)
        osm_res = await run_tool(
            "query_osm",
            OSMRequest(bbox=[42.0, -71.5, 42.1, -71.4], tags=["power=line"]),
            optional=True,
        )

        # 4. Spatial geometry Buffers/Intersections
        aoi_poly = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
        target_poly = {"type": "Polygon", "coordinates": [[[0.5, 0.5], [0.5, 0.6], [0.6, 0.6], [0.6, 0.5], [0.5, 0.5]]]}
        
        geom_res = await run_tool(
            "calculate_intersection",
            IntersectionRequest(aoi_geojson=aoi_poly, target_geojson=target_poly),
        )

        # 5. Semantic Search rules
        sem_res = await run_tool(
            "semantic_search",
            SearchRequest(query="wetlands restrictions regulatory precedents", collection="environmental"),
        )

        return EvidenceBundle(
            project=proj_model,
            study=study_model,
            region=region_model,
            imagery=img_res.data if img_res else None,
            osm_features=osm_res.data if osm_res else [],
            semantic_chunks=sem_res.data if sem_res else [],
            geometry_results=geom_res.data if geom_res else {},
        )

    def compile_report(
        self,
        evidence: EvidenceBundle,
        tool_context: ToolContext,
        workflow_id: str,
        tool_metrics: List[ToolExecutionSummary],
    ) -> SiteIntelligenceReport:
        """Delegate report construction to the report builder utility."""
        return build_report(
            evidence=evidence,
            trace_id=tool_context.trace_id,
            workflow_id=workflow_id,
            tool_metrics=tool_metrics,
        )
