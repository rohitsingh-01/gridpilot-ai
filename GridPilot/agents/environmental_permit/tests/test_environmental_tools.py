"""Unit and integration testing suite for Environmental Permit analysis tools."""
from __future__ import annotations

import asyncio
import pytest
from typing import List, Dict, Any, Tuple
from unittest.mock import MagicMock

from services.db.repositories.interfaces import IUserRepository, IProjectRepository, IStudyRepository, IUtilityRegionRepository
from agents.site_intelligence.interfaces import ToolContext, ISemanticService, IImageryService, IGeoService, BaseMapProvider
from agents.site_intelligence.models import ToolResult, PermissionDeniedError, Severity
from agents.site_intelligence.registry import ToolRegistry
from agents.site_intelligence.tests.test_tools import MockTelemetry, MockCache
from agents.environmental_permit.interfaces import IEnvironmentalAnalysisService
from agents.environmental_permit.models import (
    WetlandResult,
    HabitatResult,
    PermitResult,
    BufferResult,
    QualityMetadata,
    WetlandsQueryRequest,
    WetlandsBatchRequest,
    HabitatQueryRequest,
    HabitatBatchRequest,
    PermitQueryRequest,
    BufferAnalysisRequest,
    WetlandLookupError,
    HabitatLookupError,
    PermitLookupError,
)
import agents.environmental_permit.tools  # Trigger registration

pytestmark = pytest.mark.anyio


# --- Mock Environmental Analysis Service ---

class MockEnvironmentalService(IEnvironmentalAnalysisService):
    def __init__(self) -> None:
        self.wetland_calls = 0
        self.habitat_calls = 0
        self.permit_calls = 0
        self.buffer_calls = 0

    async def query_wetlands(self, aoi_geojson: Dict[str, Any]) -> List[WetlandResult]:
        self.wetland_calls += 1
        return [
            WetlandResult(
                id="WET-0002",
                classification="Estuarine",
                area_overlap_pct=10.0,
                severity=Severity.HIGH,
                quality=QualityMetadata(source_dataset="NWI", acquisition_date="2024", confidence=0.9, geometry_valid=True)
            ),
            WetlandResult(
                id="WET-0001",
                classification="Freshwater Forested",
                area_overlap_pct=30.0,
                severity=Severity.CRITICAL,
                quality=QualityMetadata(source_dataset="NWI", acquisition_date="2024", confidence=0.9, geometry_valid=True)
            ),
            WetlandResult(
                id="WET-0003",
                classification="Marine wetland",
                area_overlap_pct=5.0,
                severity=Severity.LOW,
                quality=QualityMetadata(source_dataset="EPA", acquisition_date="2023", confidence=0.85, geometry_valid=True)
            )
        ]

    async def query_critical_habitats(self, aoi_geojson: Dict[str, Any]) -> List[HabitatResult]:
        self.habitat_calls += 1
        return [
            HabitatResult(
                id="HAB-0001",
                species_name="Bog Turtle",
                status="Threatened",
                seasonal_restrictions=["April 1 - October 15"],
                severity=Severity.HIGH,
                quality=QualityMetadata(source_dataset="USFWS", acquisition_date="2024", confidence=0.95, geometry_valid=True)
            )
        ]

    async def query_permit_requirements(self, query: str) -> List[PermitResult]:
        self.permit_calls += 1
        return [
            PermitResult(
                id="PERMIT-0001",
                permit_name="Wetlands Protection Act Permit",
                issuing_agency="Conservation Commission",
                mitigation_requirements=["Replication area required"],
                severity=Severity.HIGH,
                quality=QualityMetadata(source_dataset="Code Corpus", acquisition_date="2026", confidence=1.0, geometry_valid=True)
            )
        ]

    def calculate_buffers(self, aoi_geojson: Dict[str, Any], buffer_m: float) -> BufferResult:
        self.buffer_calls += 1
        return BufferResult(
            setback_required_m=buffer_m,
            actual_setback_m=buffer_m - 15.0,
            violation_detected=True,
            references=[]
        )


@pytest.fixture
def env_tool_context() -> ToolContext:
    """Fixture supplying full context setup for environmental tests."""
    user_repo = MagicMock(spec=IUserRepository)
    project_repo = MagicMock(spec=IProjectRepository)
    study_repo = MagicMock(spec=IStudyRepository)
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
        user="environmental_reviewer",
        permissions=["read:environmental"],
        trace_id="env_trace_123"
    )


# --- Test Cases ---

def test_registry_lookup():
    """Verify environmental tools register correctly in the shared ToolRegistry."""
    query_wetlands_tool = ToolRegistry.get("query_wetlands")
    assert query_wetlands_tool is not None


async def test_permission_denied_environmental(env_tool_context):
    """Verify tool wrapper rejects calls when missing permissions."""
    env_tool_context.permissions = []
    query_wetlands_tool = ToolRegistry.get("query_wetlands")
    request = WetlandsQueryRequest(aoi_geojson={"type": "Polygon", "coordinates": []})

    with pytest.raises(PermissionDeniedError):
        await query_wetlands_tool(env_tool_context, request)


async def test_query_wetlands_deterministic_sorting(env_tool_context):
    """Verify that query_wetlands returns results sorted by Severity, Dataset name, then ID."""
    query_wetlands_tool = ToolRegistry.get("query_wetlands")
    request = WetlandsQueryRequest(aoi_geojson={"type": "Polygon", "coordinates": []})

    res = await query_wetlands_tool(env_tool_context, request)
    assert res.success is True
    assert isinstance(res, ToolResult)

    # Expected order: CRITICAL (WET-0001) > HIGH (WET-0002) > LOW (EPA source, WET-0003)
    assert res.data[0].id == "WET-0001"
    assert res.data[0].severity == Severity.CRITICAL
    assert res.data[1].id == "WET-0002"
    assert res.data[2].id == "WET-0003"


async def test_query_wetlands_batch_deduplication(env_tool_context):
    """Verify batch wetlands query removes duplicates and sorts results."""
    query_wetlands_batch_tool = ToolRegistry.get("query_wetlands_batch")
    request = WetlandsBatchRequest(aois=[
        {"type": "Polygon", "coordinates": [[[0,0], [0,1], [0,0]]]},
        {"type": "Polygon", "coordinates": [[[1,1], [1,2], [1,1]]]}
    ])

    res = await query_wetlands_batch_tool(env_tool_context, request)
    assert res.success is True
    # Verify duplicates are removed (should be exactly 3 unique wetlands, not 6)
    assert len(res.data) == 3
    assert res.data[0].id == "WET-0001"
    assert env_tool_context.environmental_service.wetland_calls == 2


async def test_query_critical_habitat(env_tool_context):
    """Verify protected species lookup and seasonal restrictions parameters."""
    query_habitat_tool = ToolRegistry.get("query_critical_habitat")
    request = HabitatQueryRequest(aoi_geojson={"type": "Polygon", "coordinates": []})

    res = await query_habitat_tool(env_tool_context, request)
    assert res.success is True
    assert res.data[0].id == "HAB-0001"
    assert res.data[0].species_name == "Bog Turtle"
    assert "April 1 - October 15" in res.data[0].seasonal_restrictions
    assert res.data[0].quality.source_dataset == "USFWS"


async def test_query_permit_requirements(env_tool_context):
    """Verify semantic permit lookups return issuing agencies and mitigation requirements."""
    query_permit_tool = ToolRegistry.get("query_permit_requirements")
    request = PermitQueryRequest(query="wetlands protection act compliance")

    res = await query_permit_tool(env_tool_context, request)
    assert res.success is True
    assert res.data[0].id == "PERMIT-0001"
    assert res.data[0].issuing_agency == "Conservation Commission"
    assert "Replication area required" in res.data[0].mitigation_requirements


async def test_calculate_buffers_violation(env_tool_context):
    """Verify buffer setback calculations correctly flags setback violations."""
    calculate_buffers_tool = ToolRegistry.get("calculate_environmental_buffers")
    request = BufferAnalysisRequest(aoi_geojson={"type": "Polygon", "coordinates": []}, buffer_m=100.0)

    res = await calculate_buffers_tool(env_tool_context, request)
    assert res.success is True
    assert res.data.setback_required_m == 100.0
    assert res.data.actual_setback_m == 85.0
    assert res.data.violation_detected is True


async def test_cancellation_during_execution(env_tool_context):
    """Verify environmental tools abort immediately when cancellation token triggers."""
    query_wetlands_tool = ToolRegistry.get("query_wetlands")
    request = WetlandsQueryRequest(aoi_geojson={"type": "Polygon", "coordinates": []})

    cancel_token = asyncio.Event()
    cancel_token.set()  # Cancel early

    with pytest.raises(asyncio.CancelledError):
        await query_wetlands_tool(env_tool_context, request, cancellation_token=cancel_token)


async def test_partial_success_fallback(env_tool_context):
    """Verify tools fallback gracefully (returning empty lists/results) when service layer is missing."""
    env_tool_context.environmental_service = None
    query_wetlands_tool = ToolRegistry.get("query_wetlands")
    request = WetlandsQueryRequest(aoi_geojson={"type": "Polygon", "coordinates": []})

    res = await query_wetlands_tool(env_tool_context, request)
    assert res.success is True
    assert len(res.data) == 0
    assert len(env_tool_context.telemetry_service.logs) == 2
    assert env_tool_context.telemetry_service.logs[0][0] == "WARNING"
