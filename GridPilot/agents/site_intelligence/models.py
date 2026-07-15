"""Strongly typed tool requests, generic results, and domain exceptions."""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Generic, TypeVar
from pydantic import BaseModel, Field, ConfigDict

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
