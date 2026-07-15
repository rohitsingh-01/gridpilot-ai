"""Models, requests, results, and domain exceptions for the Environmental Permit Agent tools."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from agents.site_intelligence.models import FindingReference, Severity, BaseToolRequest


# --- Domain Exceptions ---

class EnvironmentalToolError(Exception):
    """Base domain exception for all environmental analysis tools."""
    pass


class PermitLookupError(EnvironmentalToolError):
    """Exception raised when permit requirements search fails."""
    pass


class HabitatLookupError(EnvironmentalToolError):
    """Exception raised when critical habitat search fails."""
    pass


class WetlandLookupError(EnvironmentalToolError):
    """Exception raised when wetlands geometry query fails."""
    pass


# --- Structured Output Schema Elements ---

class QualityMetadata(BaseModel):
    """Quality assurance and dataset tracking metadata."""
    source_dataset: str
    acquisition_date: str
    confidence: float = Field(ge=0.0, le=1.0)
    geometry_valid: bool


class EnvironmentalConstraint(BaseModel):
    """Describes a specific environmental constraint or warning evaluated by tools."""
    severity: Severity
    category: str  # e.g., "wetland", "habitat", "regulatory"
    distance: float
    affected_area: float
    citation: str
    recommendation: str


class WetlandResult(BaseModel):
    """Details of a matching wetland intersection."""
    id: str
    classification: str
    area_overlap_pct: float
    severity: Severity
    references: List[FindingReference] = Field(default_factory=list)
    quality: QualityMetadata


class HabitatResult(BaseModel):
    """Details of a matching protected critical habitat overlap."""
    id: str
    species_name: str
    status: str
    seasonal_restrictions: List[str] = Field(default_factory=list)
    severity: Severity
    references: List[FindingReference] = Field(default_factory=list)
    quality: QualityMetadata


class PermitResult(BaseModel):
    """Details of a regulatory permit requirement matching the location context."""
    id: str
    permit_name: str
    issuing_agency: str
    mitigation_requirements: List[str] = Field(default_factory=list)
    severity: Severity
    references: List[FindingReference] = Field(default_factory=list)
    quality: QualityMetadata


class BufferResult(BaseModel):
    """Calculated buffer setbacks and violations."""
    setback_required_m: float
    actual_setback_m: float
    violation_detected: bool
    references: List[FindingReference] = Field(default_factory=list)


# --- Consolidated Environmental Evidence Bundle ---

class EnvironmentalEvidenceBundle(BaseModel):
    """Unified container consolidating all retrieved environmental data outputs."""
    bundle_version: str = "1.0.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    wetlands: List[WetlandResult] = Field(default_factory=list)
    habitats: List[HabitatResult] = Field(default_factory=list)
    permits: List[PermitResult] = Field(default_factory=list)
    buffers: List[BufferResult] = Field(default_factory=list)
    constraints: List[EnvironmentalConstraint] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# --- Request Models ---

class WetlandsQueryRequest(BaseToolRequest):
    """Request arguments to query wetlands intersection."""
    aoi_geojson: Dict[str, Any]


class WetlandsBatchRequest(BaseToolRequest):
    """Request arguments to query wetlands intersections in batch."""
    aois: List[Dict[str, Any]]


class HabitatQueryRequest(BaseToolRequest):
    """Request arguments to query critical habitats."""
    aoi_geojson: Dict[str, Any]


class HabitatBatchRequest(BaseToolRequest):
    """Request arguments to query critical habitats in batch."""
    aois: List[Dict[str, Any]]


class PermitQueryRequest(BaseToolRequest):
    """Request arguments to query permit requirements."""
    query: str


class BufferAnalysisRequest(BaseToolRequest):
    """Request arguments to analyze environmental buffer setbacks."""
    aoi_geojson: Dict[str, Any]
    buffer_m: float
