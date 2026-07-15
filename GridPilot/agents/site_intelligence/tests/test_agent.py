"""Unit and integration testing suite for Site Intelligence Agent."""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock

from services.workflow.interfaces.agent import AgentInput, AgentOutput
from services.workflow.interfaces.task import WorkflowContext
from services.db.repositories.interfaces import IUserRepository, IProjectRepository, IStudyRepository, IUtilityRegionRepository
from services.semantic.storage.base import BaseSemanticStore
from agents.site_intelligence.interfaces import (
    ToolContext,
    ISemanticService,
    IImageryService,
    IGeoService,
    BaseMapProvider,
    ICacheService,
    ITelemetryService,
    ImageryMetadata,
    OSMFeature,
    SearchChunk,
)
from agents.site_intelligence.models import (
    Severity,
    SiteIntelligenceReport,
)
from agents.site_intelligence.agent import SiteIntelligenceAgent
from agents.site_intelligence.tests.test_tools import (
    MockSemantic,
    MockImagery,
    MockGeo,
    MockMapProvider,
    MockCache,
    MockTelemetry,
)

pytestmark = pytest.mark.anyio


# --- Test Cases ---

async def test_agent_execution_success():
    """Verify end-to-end execution of SiteIntelligenceAgent returning a complete report."""
    # 1. Mock repositories
    user_repo = MagicMock(spec=IUserRepository)
    project_repo = MagicMock(spec=IProjectRepository)
    study_repo = MagicMock(spec=IStudyRepository)
    region_repo = MagicMock(spec=IUtilityRegionRepository)

    # Setup project mock return
    proj_id = "c0a80101-0000-0000-0000-000000000001"
    mock_project = MagicMock()
    mock_project.id = proj_id
    mock_project.name = "GridPilot Site Study"
    mock_project.status = "active"
    project_repo.get_by_id.return_value = mock_project

    # Setup study mock return
    study_id = "c0a80101-0000-0000-0000-000000000002"
    mock_study = MagicMock()
    mock_study.id = study_id
    mock_study.project_id = proj_id
    mock_study.status = "running"
    mock_study.region_id = "c0a80101-0000-0000-0000-000000000003"
    study_repo.get_by_id.return_value = mock_study

    # Setup region mock return
    mock_region = MagicMock()
    mock_region.id = "c0a80101-0000-0000-0000-000000000003"
    mock_region.name = "Northeast Region"
    mock_region.code = "NE"
    region_repo.get_by_id.return_value = mock_region

    # 2. Instantiate agent with mock services
    telemetry = MockTelemetry()
    agent = SiteIntelligenceAgent(
        region_repository=region_repo,
        semantic_service=MockSemantic(),
        imagery_service=MockImagery(),
        geo_service=MockGeo(),
        osm_service=MockMapProvider(),
        cache_service=MockCache(),
        telemetry_service=telemetry,
    )

    # 3. Create context and execute
    workflow_ctx = WorkflowContext(
        study_id=study_id,
        project_id=proj_id,
        user_repository=user_repo,
        project_repository=project_repo,
        study_repository=study_repo,
        semantic_store=MagicMock(spec=BaseSemanticStore),  # Satisfies Pydantic context
    )
    
    # Injected metadata
    workflow_ctx.metadata["trace_id"] = "trace_abc"
    workflow_ctx.metadata["workflow_id"] = "wf_123"

    inputs = AgentInput(context=workflow_ctx)
    output = await agent.execute(inputs)

    # 4. Verify outputs
    assert isinstance(output, AgentOutput)
    # The default mock data should be complete (caching is setup, semantic works, etc.)
    # Wetland intersection is mocked to return True in MockGeo -> max severity is CRITICAL
    assert output.confidence == 1.0
    assert any(m["tool_name"] == "calculate_intersection" for m in output.structured_data["tool_metrics"])

    report = SiteIntelligenceReport.model_validate(output.structured_data)
    assert report.status == "complete"
    assert report.overall_risk == Severity.CRITICAL
    assert len(report.environmental_findings) == 1
    assert len(report.infrastructure_findings) == 1
    assert len(report.recommendations) >= 2


async def test_agent_missing_imagery_fallback():
    """Verify that agent continues running with partial status and reduced confidence when imagery is missing."""
    # 1. Setup repos and mocks
    user_repo = MagicMock(spec=IUserRepository)
    project_repo = MagicMock(spec=IProjectRepository)
    study_repo = MagicMock(spec=IStudyRepository)
    region_repo = MagicMock(spec=IUtilityRegionRepository)

    proj_id = "c0a80101-0000-0000-0000-000000000001"
    mock_project = MagicMock()
    mock_project.id = proj_id
    mock_project.name = "GridPilot Site Study"
    mock_project.status = "active"
    project_repo.get_by_id.return_value = mock_project

    study_id = "c0a80101-0000-0000-0000-000000000002"
    mock_study = MagicMock()
    mock_study.id = study_id
    mock_study.project_id = proj_id
    mock_study.status = "running"
    mock_study.region_id = "c0a80101-0000-0000-0000-000000000003"
    study_repo.get_by_id.return_value = mock_study

    mock_region = MagicMock()
    mock_region.id = "c0a80101-0000-0000-0000-000000000003"
    mock_region.name = "Northeast Region"
    mock_region.code = "NE"
    region_repo.get_by_id.return_value = mock_region

    # Mock imagery service to throw connection error
    failing_imagery = MagicMock(spec=IImageryService)
    failing_imagery.get_metadata.side_effect = ConnectionError("OSS timeout connecting to bucket.")

    agent = SiteIntelligenceAgent(
        region_repository=region_repo,
        semantic_service=MockSemantic(),
        imagery_service=failing_imagery,
        geo_service=MockGeo(),
        osm_service=MockMapProvider(),
        cache_service=MockCache(),
        telemetry_service=MockTelemetry(),
    )

    workflow_ctx = WorkflowContext(
        study_id=study_id,
        project_id=proj_id,
        user_repository=user_repo,
        project_repository=project_repo,
        study_repository=study_repo,
        semantic_store=MagicMock(spec=BaseSemanticStore),
    )

    inputs = AgentInput(context=workflow_ctx)
    output = await agent.execute(inputs)

    # 2. Assert fallback metrics
    report = SiteIntelligenceReport.model_validate(output.structured_data)
    assert report.status == "partial"
    # Imagery deduction is 0.3 -> confidence should drop to 0.7
    assert pytest.approx(output.confidence) == 0.7
    assert any("imagery_missing" in r.related_findings for r in report.recommendations)
    assert any("Satellite imagery cache was missing" in a for a in report.assumptions)


async def test_agent_empty_osm_reasoning():
    """Verify that agent runs with empty OSM lists and adjusts confidence score."""
    user_repo = MagicMock(spec=IUserRepository)
    project_repo = MagicMock(spec=IProjectRepository)
    study_repo = MagicMock(spec=IStudyRepository)
    region_repo = MagicMock(spec=IUtilityRegionRepository)

    proj_id = "c0a80101-0000-0000-0000-000000000001"
    mock_project = MagicMock()
    mock_project.id = proj_id
    mock_project.name = "GridPilot Site Study"
    mock_project.status = "active"
    project_repo.get_by_id.return_value = mock_project

    study_id = "c0a80101-0000-0000-0000-000000000002"
    mock_study = MagicMock()
    mock_study.id = study_id
    mock_study.project_id = proj_id
    mock_study.status = "running"
    mock_study.region_id = "c0a80101-0000-0000-0000-000000000003"
    study_repo.get_by_id.return_value = mock_study

    mock_region = MagicMock()
    mock_region.id = "c0a80101-0000-0000-0000-000000000003"
    mock_region.name = "Northeast Region"
    mock_region.code = "NE"
    region_repo.get_by_id.return_value = mock_region

    # Mock OSM service to return empty features
    empty_osm = MagicMock(spec=BaseMapProvider)
    empty_osm.query_features.return_value = []

    agent = SiteIntelligenceAgent(
        region_repository=region_repo,
        semantic_service=MockSemantic(),
        imagery_service=MockImagery(),
        geo_service=MockGeo(),
        osm_service=empty_osm,
        cache_service=MockCache(),
        telemetry_service=MockTelemetry(),
    )

    workflow_ctx = WorkflowContext(
        study_id=study_id,
        project_id=proj_id,
        user_repository=user_repo,
        project_repository=project_repo,
        study_repository=study_repo,
        semantic_store=MagicMock(spec=BaseSemanticStore),
    )

    inputs = AgentInput(context=workflow_ctx)
    output = await agent.execute(inputs)

    report = SiteIntelligenceReport.model_validate(output.structured_data)
    assert report.status == "partial"
    # OSM deduction is 0.1 -> confidence should drop to 0.9
    assert pytest.approx(output.confidence) == 0.9
    assert len(report.infrastructure_findings) == 0


async def test_agent_determinism_identical_runs():
    """Verify that running the agent twice with identical inputs produces identical reports (reproducibility)."""
    user_repo = MagicMock(spec=IUserRepository)
    project_repo = MagicMock(spec=IProjectRepository)
    study_repo = MagicMock(spec=IStudyRepository)
    region_repo = MagicMock(spec=IUtilityRegionRepository)

    proj_id = "c0a80101-0000-0000-0000-000000000001"
    mock_project = MagicMock()
    mock_project.id = proj_id
    mock_project.name = "GridPilot Site Study"
    mock_project.status = "active"
    project_repo.get_by_id.return_value = mock_project

    study_id = "c0a80101-0000-0000-0000-000000000002"
    mock_study = MagicMock()
    mock_study.id = study_id
    mock_study.project_id = proj_id
    mock_study.status = "running"
    mock_study.region_id = "c0a80101-0000-0000-0000-000000000003"
    study_repo.get_by_id.return_value = mock_study

    mock_region = MagicMock()
    mock_region.id = "c0a80101-0000-0000-0000-000000000003"
    mock_region.name = "Northeast Region"
    mock_region.code = "NE"
    region_repo.get_by_id.return_value = mock_region

    agent = SiteIntelligenceAgent(
        region_repository=region_repo,
        semantic_service=MockSemantic(),
        imagery_service=MockImagery(),
        geo_service=MockGeo(),
        osm_service=MockMapProvider(),
        cache_service=MockCache(),
        telemetry_service=MockTelemetry(),
    )

    workflow_ctx = WorkflowContext(
        study_id=study_id,
        project_id=proj_id,
        user_repository=user_repo,
        project_repository=project_repo,
        study_repository=study_repo,
        semantic_store=MagicMock(spec=BaseSemanticStore),
    )

    inputs = AgentInput(context=workflow_ctx)
    output1 = await agent.execute(inputs)
    output2 = await agent.execute(inputs)

    report1 = SiteIntelligenceReport.model_validate(output1.structured_data)
    report2 = SiteIntelligenceReport.model_validate(output2.structured_data)

    # Verify identical findings and overall metrics
    assert report1.confidence_score == report2.confidence_score
    assert report1.status == report2.status
    assert report1.overall_risk == report2.overall_risk
    assert len(report1.environmental_findings) == len(report2.environmental_findings)
    assert len(report1.recommendations) == len(report2.recommendations)
