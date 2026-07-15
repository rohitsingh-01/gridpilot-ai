"""Offline unit and integration testing suite for the Environmental Permit Agent."""
from __future__ import annotations

import asyncio
import pytest
from typing import Dict, Any, List
from unittest.mock import MagicMock

from services.workflow.interfaces.agent import AgentInput
from services.workflow.interfaces.task import WorkflowContext
from services.semantic.storage.base import BaseSemanticStore
from services.db.repositories.interfaces import IUserRepository, IProjectRepository, IStudyRepository, IUtilityRegionRepository
from agents.site_intelligence.interfaces import ToolContext, ISemanticService, IImageryService, IGeoService, BaseMapProvider
from agents.site_intelligence.tests.test_tools import MockTelemetry, MockCache
from agents.environmental_permit.interfaces import IEnvironmentalAnalysisService
from agents.environmental_permit.models import (
    EnvironmentalEvidenceBundle,
    WetlandResult,
    HabitatResult,
    PermitResult,
    BufferResult,
    QualityMetadata,
    EnvironmentalConstraint,
    ExecutionSummary,
    EnvironmentalPermitReport,
    Severity,
)
from agents.environmental_permit.agent import EnvironmentalPermitAgent
from agents.environmental_permit.tests.test_environmental_tools import MockEnvironmentalService
from agents.environmental_permit.report import build_report

pytestmark = pytest.mark.anyio


@pytest.fixture
def env_agent_context() -> ToolContext:
    """Fixture supplying mock repositories and telemetry interfaces."""
    user_repo = MagicMock(spec=IUserRepository)
    
    project_repo = MagicMock(spec=IProjectRepository)
    project_repo.project_id = "proj_test_123"
    
    study_repo = MagicMock(spec=IStudyRepository)
    study_repo.study_id = "study_test_123"

    region_repo = MagicMock(spec=IUtilityRegionRepository)

    return ToolContext(
        user_repository=user_repo,
        project_repository=project_repo,
        study_repository=study_repo,
        region_repository=region_repo,
        semantic_service=MagicMock(spec=ISemanticService),
        imagery_service=MagicMock(spec=IImageryService),
        geo_service=MagicMock(spec=IGeoService),
        osm_service=MagicMock(spec=BaseMapProvider),
        cache_service=MockCache(),
        telemetry_service=MockTelemetry(),
        environmental_service=MockEnvironmentalService(),
        user="permit_officer",
        permissions=["read:project", "read:study", "read:region", "read:environmental"],
        trace_id="env_agent_trace_456"
    )


# --- Test Cases ---

async def test_agent_execution_success(env_agent_context):
    """Verify happy path execution collects all evidence and constructs a validated report."""
    agent = EnvironmentalPermitAgent(
        region_repository=env_agent_context.region_repository,
        semantic_service=env_agent_context.semantic_service,
        imagery_service=env_agent_context.imagery_service,
        geo_service=env_agent_context.geo_service,
        osm_service=env_agent_context.osm_service,
        cache_service=env_agent_context.cache_service,
        telemetry_service=env_agent_context.telemetry_service,
        environmental_service=env_agent_context.environmental_service
    )

    workflow_ctx = WorkflowContext(
        study_id="study_test_123",
        project_id="proj_test_123",
        user_repository=env_agent_context.user_repository,
        project_repository=env_agent_context.project_repository,
        study_repository=env_agent_context.study_repository,
        semantic_store=MagicMock(spec=BaseSemanticStore),
        metadata={"user": "tester", "trace_id": "t1"}
    )
    inputs = AgentInput(context=workflow_ctx)
    output = await agent.execute(inputs)

    assert output.confidence == 0.9  # Setback buffer violation deduction of 0.1
    assert len(output.sources) == 4
    
    # Validate structure
    report = EnvironmentalPermitReport.model_validate(output.structured_data)
    assert report.execution_status == "success"
    assert len(report.permit_findings) == 5
    
    # Asserts deterministic IDs
    assert report.permit_findings[0].id == "PERMIT-0001"
    assert report.recommendations[0].id == "REC-0001"


async def test_agent_missing_wetlands_fallback(env_agent_context):
    """Verify that when wetlands query is unavailable, the agent continues and records partial success."""
    class FailingWetlandService(MockEnvironmentalService):
        async def query_wetlands(self, aoi_geojson: Dict[str, Any]) -> List[WetlandResult]:
            raise ValueError("Wetlands database is offline.")

    env_agent_context.environmental_service = FailingWetlandService()

    agent = EnvironmentalPermitAgent(
        region_repository=env_agent_context.region_repository,
        semantic_service=env_agent_context.semantic_service,
        imagery_service=env_agent_context.imagery_service,
        geo_service=env_agent_context.geo_service,
        osm_service=env_agent_context.osm_service,
        cache_service=env_agent_context.cache_service,
        telemetry_service=env_agent_context.telemetry_service,
        environmental_service=env_agent_context.environmental_service
    )

    workflow_ctx = WorkflowContext(
        study_id="study_test_123",
        project_id="proj_test_123",
        user_repository=env_agent_context.user_repository,
        project_repository=env_agent_context.project_repository,
        study_repository=env_agent_context.study_repository,
        semantic_store=MagicMock(spec=BaseSemanticStore),
        metadata={"user": "tester", "trace_id": "t1"}
    )
    inputs = AgentInput(context=workflow_ctx)
    output = await agent.execute(inputs)

    report = EnvironmentalPermitReport.model_validate(output.structured_data)
    assert report.execution_status == "partial"
    # Deductions: wetlands missing (0.3) + buffer warning (0.1) -> 0.6 confidence
    assert pytest.approx(output.confidence) == 0.6
    assert any("wetlands" in a.id.lower() or "wetland" in a.description.lower() for a in report.assumptions)


async def test_agent_report_hash_stability(env_agent_context):
    """Verify report hashing is deterministic, stable, and unique per input."""
    evidence = EnvironmentalEvidenceBundle(
        wetlands=[
            WetlandResult(
                id="WET-0001",
                classification="Estuarine",
                area_overlap_pct=15.0,
                severity=Severity.HIGH,
                quality=QualityMetadata(source_dataset="NWI", acquisition_date="2024", confidence=0.9, geometry_valid=True)
            )
        ],
        execution_summary=ExecutionSummary(
            tools_executed=["query_wetlands"],
            cache_hits=0,
            cache_misses=1,
            warnings=[],
            execution_duration_ms=50
        )
    )

    # 1. First run report build
    report1 = build_report(evidence, "t1", "w1", "s1")
    # 2. Second run report build (identical input)
    report2 = build_report(evidence, "t1", "w1", "s1")

    # Hashes must be identical
    assert report1.report_sha256 == report2.report_sha256
    assert len(report1.report_sha256) == 64

    # 3. Third run (different input)
    evidence.wetlands[0].area_overlap_pct = 25.0
    report3 = build_report(evidence, "t1", "w1", "s1")
    assert report1.report_sha256 != report3.report_sha256


def test_empty_evidence_bundle_handling():
    """Verify report builder executes correctly and outputs low severity when evidence bundle is empty."""
    empty_bundle = EnvironmentalEvidenceBundle()
    report = build_report(empty_bundle, "trace_empty", "wf_empty", "st_empty")

    assert pytest.approx(report.confidence_score) == 0.2  # Deductions: wetlands (0.3), habitats (0.3), permits (0.2)
    assert report.overall_severity == Severity.LOW
    assert len(report.permit_findings) == 0
    assert report.reasoning_summary.rules_evaluated == 4
    assert report.reasoning_summary.findings_generated == 0
