"""Site Intelligence Agent models including Pydantic data schemas, requests, result envelopes, severity enums, and result containers."""
from __future__ import annotations

from enum import Enum
from typing import List, Dict, Any, Optional, Generic, TypeVar
from pydantic import BaseModel, Field, ConfigDict

from agents.site_intelligence.interfaces import ImageryMetadata, OSMFeature, SearchChunk

T = TypeVar("T")


# --- Domain Exception Hierarchy ---

class ToolDomainError(Exception):
    """Base domain exception for all tool operations."""
    pass


class ToolExecutionError(ToolDomainError):
    """Exception raised when tool business logic execution fails."""
    pass


class PermissionDeniedError(ToolDomainError):
    """Exception raised when user does not possess required permission claims."""
    pass


class ToolTimeoutError(ToolDomainError):
    """Exception raised when tool execution times out."""
    pass


class ToolValidationError(ToolDomainError):
    """Exception raised when request arguments fail validation."""
    pass


class ExternalServiceUnavailableError(ToolDomainError):
    """Exception raised when an external API or vector store is unreachable."""
    pass


# --- Tool Result Wrapper ---

class ToolResult(BaseModel, Generic[T]):
    """Standardized output wrapper returned by all execution tool nodes."""
    success: bool
    data: Optional[T] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)
    trace_id: str


# --- Request Models ---

class BaseToolRequest(BaseModel):
    """Abstract base request class for all tools."""
    pass


class ProjectRequest(BaseToolRequest):
    """Request arguments for loading project details."""
    project_id: str


class StudyRequest(BaseToolRequest):
    """Request arguments for loading study details."""
    study_id: str


class RegionRequest(BaseToolRequest):
    """Request arguments for loading region details."""
    region_id: str


class TileRequest(BaseToolRequest):
    """Request arguments for locating satellite tile metadata."""
    region_id: str
    scene_date: str


class OSMRequest(BaseToolRequest):
    """Request arguments for querying OpenStreetMap features."""
    bbox: List[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Bounding box [min_lat, min_lon, max_lat, max_lon]."
    )
    tags: List[str] = Field(
        ...,
        description="OSM tags to filter by (e.g. ['power=line', 'power=substation'])."
    )


class SearchRequest(BaseToolRequest):
    """Request arguments for running a semantic text query."""
    query: str
    collection: str  # e.g., "regulatory", "environmental"
    limit: int = 5


class BufferRequest(BaseToolRequest):
    """Request arguments for calculating a planar distance buffer."""
    aoi_geojson: Dict[str, Any]
    buffer_m: float


class IntersectionRequest(BaseToolRequest):
    """Request arguments for calculating geometric intersections."""
    aoi_geojson: Dict[str, Any]
    target_geojson: Dict[str, Any]


# --- Severity & Domain Analysis Models ---

class Severity(str, Enum):
    """Exposes risk severity classification levels for findings."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ProjectModel(BaseModel):
    """Representation of project database entity details."""
    id: str
    name: str
    status: str


class StudyModel(BaseModel):
    """Representation of study database entity details."""
    id: str
    project_id: str
    status: str
    region_id: Optional[str] = None


class RegionModel(BaseModel):
    """Representation of region database entity details."""
    id: str
    name: str
    code: str


class FindingReference(BaseModel):
    """Links a reasoning finding to its supporting source tool or identifier."""
    tool: str
    source: str
    identifier: str


class EnvironmentalFinding(BaseModel):
    """Results of wetlands and habitat overlap spatial calculations."""
    label: str
    description: str
    severity: Severity
    references: List[FindingReference] = Field(default_factory=list)


class InfrastructureFinding(BaseModel):
    """Results of physical infrastructure (lines, substations) proximity lookups."""
    label: str
    description: str
    severity: Severity
    proximity_m: float
    references: List[FindingReference] = Field(default_factory=list)


class RegulatoryFinding(BaseModel):
    """Grounded citation results from semantic tarification memory search."""
    citation: str
    text_chunk: str
    severity: Severity
    references: List[FindingReference] = Field(default_factory=list)


class Recommendation(BaseModel):
    """Actionable mitigation suggestion generated from evidence analysis."""
    title: str
    description: str
    priority: str  # e.g., "HIGH", "MEDIUM", "LOW"
    related_findings: List[str] = Field(default_factory=list)


class ToolExecutionSummary(BaseModel):
    """Telemetry metrics recording tool duration, cache hit, and status outcomes."""
    tool_name: str
    duration_ms: int
    success: bool
    cached: bool
    warning_count: int = 0


class EvidenceBundle(BaseModel):
    """Consolidated strongly-typed data package passed to the reasoning engine."""
    project: ProjectModel
    study: StudyModel
    region: RegionModel
    imagery: Optional[ImageryMetadata] = None
    osm_features: List[OSMFeature] = Field(default_factory=list)
    semantic_chunks: List[SearchChunk] = Field(default_factory=list)
    geometry_results: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SiteIntelligenceReport(BaseModel):
    """Production-grade structured output report for auditing and persistence."""
    report_version: str = "1.0.0"
    generated_at: str
    workflow_id: str
    study_id: str
    trace_id: str
    status: str  # "complete", "partial", "failed"
    
    environmental_findings: List[EnvironmentalFinding] = Field(default_factory=list)
    infrastructure_findings: List[InfrastructureFinding] = Field(default_factory=list)
    regulatory_findings: List[RegulatoryFinding] = Field(default_factory=list)
    
    overall_risk: Severity
    recommendations: List[Recommendation] = Field(default_factory=list)
    tool_metrics: List[ToolExecutionSummary] = Field(default_factory=list)
    
    confidence_score: float = Field(ge=0.0, le=1.0)
    assumptions: List[str] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
