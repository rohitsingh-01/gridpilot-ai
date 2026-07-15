"""Unit and integration testing suite for Site Intelligence tools."""
from __future__ import annotations

import asyncio
import pytest
from typing import List, Tuple, Dict, Any, Optional
from unittest.mock import MagicMock

from services.db.repositories.interfaces import IUserRepository, IProjectRepository, IStudyRepository, IUtilityRegionRepository
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
    ToolResult,
    ProjectRequest,
    StudyRequest,
    RegionRequest,
    TileRequest,
    OSMRequest,
    SearchRequest,
    BufferRequest,
    IntersectionRequest,
    PermissionDeniedError,
    ToolTimeoutError,
    ToolValidationError,
)
from agents.site_intelligence.registry import ToolRegistry
import agents.site_intelligence.tools  # Trigger explicit tool registration

pytestmark = pytest.mark.anyio


# --- Mock Service Implementations ---

class MockTelemetry(ITelemetryService):
    def __init__(self) -> None:
        self.metrics: List[Tuple[str, float, Dict[str, str]]] = []
        self.logs: List[Tuple[str, str, Dict[str, Any]]] = []

    def record_metric(self, name: str, value: float, tags: Dict[str, str]) -> None:
        self.metrics.append((name, value, tags))

    def log_structured(self, level: str, message: str, extra: Dict[str, Any]) -> None:
        self.logs.append((level, message, extra))


class MockCache(ICacheService):
    def __init__(self) -> None:
        self.store: Dict[str, str] = {}
        self.get_calls = 0
        self.set_calls = 0

    async def get(self, key: str) -> Optional[str]:
        self.get_calls += 1
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int = 86400) -> None:
        self.set_calls += 1
        self.store[key] = value


class MockSemantic(ISemanticService):
    async def search(self, collection: str, query: str, limit: int = 5) -> List[SearchChunk]:
        return [
            SearchChunk(
                chunk_id="chunk_1",
                document_id="doc_1",
                content=f"Synthetic chunk from {collection} for query '{query}'",
                metadata={"source_document": "rules.md"}
            )
        ]


class MockImagery(IImageryService):
    async def get_metadata(self, region_id: str, scene_date: str) -> ImageryMetadata:
        return ImageryMetadata(
            cache_path=f"data/imagery/{region_id}_{scene_date}.png",
            mime_type="image/png",
            checksum="abc123sha256",
            height=512,
            width=512
        )


class MockGeo(IGeoService):
    def buffer(self, aoi_geojson: Dict[str, Any], buffer_m: float) -> Dict[str, Any]:
        return {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}

    def intersects(self, geom1: Dict[str, Any], geom2: Dict[str, Any]) -> bool:
        return True

    def distance(self, geom1: Dict[str, Any], geom2: Dict[str, Any]) -> float:
        return 45.2


class MockMapProvider(BaseMapProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def query_features(self, bbox: List[float], tags: List[str]) -> List[OSMFeature]:
        self.calls += 1
        return [
            OSMFeature(
                id=999888,
                type="way",
                tags={"power": "line", "voltage": "115000"},
                geometry={"type": "LineString", "coordinates": [[0.5, 0.5], [0.6, 0.6]]}
            )
        ]


@pytest.fixture
def test_context() -> ToolContext:
    """Fixture supplying full context with mocked repository and service layers."""
    user_repo = MagicMock(spec=IUserRepository)
    project_repo = MagicMock(spec=IProjectRepository)
    study_repo = MagicMock(spec=IStudyRepository)
    region_repo = MagicMock(spec=IUtilityRegionRepository)

    return ToolContext(
        user_repository=user_repo,
        project_repository=project_repo,
        study_repository=study_repo,
        region_repository=region_repo,
        semantic_service=MockSemantic(),
        imagery_service=MockImagery(),
        geo_service=MockGeo(),
        osm_service=MockMapProvider(),
        cache_service=MockCache(),
        telemetry_service=MockTelemetry(),
        user="test_engineer",
        permissions=["read:project", "read:study", "read:region", "read:imagery", "read:osm", "read:spatial", "read:semantic"],
        trace_id="trace_test_run_123"
    )


# --- Test Cases ---

def test_registry_lookup():
    """Verify registered tools can be dynamically located in ToolRegistry."""
    query_osm_tool = ToolRegistry.get("query_osm")
    assert query_osm_tool is not None
    
    with pytest.raises(KeyError):
        ToolRegistry.get("non_existent_tool")


async def test_permission_denied(test_context):
    """Verify that calling a tool without correct permissions raises PermissionDeniedError."""
    # Strip permissions from context
    test_context.permissions = []
    
    get_project_tool = ToolRegistry.get("get_project")
    request = ProjectRequest(project_id="c0a80101-0000-0000-0000-000000000001")
    
    with pytest.raises(PermissionDeniedError, match="missing permission 'read:project'"):
        await get_project_tool(test_context, request)


async def test_validation_failure(test_context):
    """Verify validation checking raises ToolValidationError on bad arguments."""
    get_project_tool = ToolRegistry.get("get_project")
    request = ProjectRequest(project_id="invalid-uuid-string")
    
    with pytest.raises(ToolValidationError, match="Invalid UUID format"):
        await get_project_tool(test_context, request)


async def test_get_project_happy_path(test_context):
    """Verify project lookup executes successfully and returns wrapped ToolResult."""
    # Setup mock repository returns
    proj_id = "c0a80101-0000-0000-0000-000000000001"
    mock_project = MagicMock()
    mock_project.id = proj_id
    mock_project.name = "Demo Wind Farm"
    mock_project.status = "active"
    
    test_context.project_repository.get_by_id.return_value = mock_project
    
    get_project_tool = ToolRegistry.get("get_project")
    request = ProjectRequest(project_id=proj_id)
    
    res = await get_project_tool(test_context, request)
    assert isinstance(res, ToolResult)
    assert res.success is True
    assert res.data["name"] == "Demo Wind Farm"
    assert res.data["status"] == "active"
    assert res.trace_id == test_context.trace_id


async def test_imagery_metadata_metadata_only(test_context):
    """Verify satellite tool returns metadata only to keep memory footprint light."""
    fetch_imagery = ToolRegistry.get("fetch_satellite_tile_metadata")
    request = TileRequest(region_id="reg_12", scene_date="2026-07-15")
    
    res = await fetch_imagery(test_context, request)
    assert res.success is True
    assert res.data.mime_type == "image/png"
    assert res.data.height == 512
    assert res.data.width == 512


async def test_osm_caching_happy_path(test_context):
    """Verify repeated query_osm calls hit the ICacheService instead of making multiple API calls."""
    query_osm_tool = ToolRegistry.get("query_osm")
    request = OSMRequest(bbox=[42.0, -71.5, 42.1, -71.4], tags=["power=line"])

    # First call (cache miss)
    res1 = await query_osm_tool(test_context, request)
    assert res1.success is True
    assert len(res1.data) == 1
    assert res1.data[0].id == 999888
    
    # Second call (cache hit)
    res2 = await query_osm_tool(test_context, request)
    assert res2.success is True
    assert len(res2.data) == 1
    assert res2.data[0].id == 999888

    # Assert cache calls
    assert test_context.cache_service.get_calls == 2
    assert test_context.cache_service.set_calls == 1
    assert test_context.osm_service.calls == 1  # Only queried the provider once!


async def test_osm_cancellation_during_execution(test_context):
    """Verify query_osm aborts immediately when cancellation token is flagged."""
    query_osm_tool = ToolRegistry.get("query_osm")
    request = OSMRequest(bbox=[42.0, -71.5, 42.1, -71.4], tags=["power=line"])
    
    cancel_token = asyncio.Event()
    cancel_token.set()  # Cancel early
    
    with pytest.raises(asyncio.CancelledError):
        await query_osm_tool(test_context, request, cancellation_token=cancel_token)


async def test_semantic_search_generalization(test_context):
    """Verify semantic_search can query both regulatory and environmental collections."""
    search_tool = ToolRegistry.get("semantic_search")
    
    req_reg = SearchRequest(query=" FERC cost", collection="regulatory", limit=3)
    res_reg = await search_tool(test_context, req_reg)
    assert res_reg.success is True
    assert "regulatory" in res_reg.data[0].content

    req_env = SearchRequest(query="NWI buffer", collection="environmental", limit=3)
    res_env = await search_tool(test_context, req_env)
    assert res_env.success is True
    assert "environmental" in res_env.data[0].content


async def test_telemetry_recorded_on_failures(test_context):
    """Verify timing and metrics telemetry are recorded even on tool errors (finally blocks)."""
    # Cause a validation exception by passing a bad UUID
    get_project_tool = ToolRegistry.get("get_project")
    request = ProjectRequest(project_id="not-a-uuid")
    
    with pytest.raises(ToolValidationError):
        await get_project_tool(test_context, request)
        
    # Telemetry should still be logged and recorded
    assert len(test_context.telemetry_service.metrics) == 1
    assert test_context.telemetry_service.metrics[0][0] == "tool.duration_ms"
    assert test_context.telemetry_service.metrics[0][2]["success"] == "False"
    
    assert len(test_context.telemetry_service.logs) == 1
    assert test_context.telemetry_service.logs[0][0] == "ERROR"
