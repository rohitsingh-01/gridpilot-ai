"""Models, requests, results, and reporting schemas for the Environmental Permit Agent."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator

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


class ConfigurationValidationError(EnvironmentalToolError):
    """Exception raised when config validation checks fail."""
    pass


# --- Structured Output Schema Elements ---

class QualityMetadata(BaseModel):
    """Quality assurance and dataset tracking metadata."""
    source_dataset: str
    acquisition_date: str
    confidence: float = Field(ge=0.0, le=1.0)
    geometry_valid: bool
    dataset_version: str = "1.0.0"
    dataset_license: str = "public-domain"
    processing_version: str = "1.0.0"
    last_updated: str = "2026-01-01"


class EnvironmentalConstraint(BaseModel):
    """Describes a specific environmental constraint or warning evaluated by tools."""
    id: str  # Deterministic e.g. ENV-CONSTRAINT-0001
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
    tool_version: str = "1.0.0"
    schema_version: str = "1.0.0"


class HabitatResult(BaseModel):
    """Details of a matching protected critical habitat overlap."""
    id: str
    species_name: str
    status: str
    seasonal_restrictions: List[str] = Field(default_factory=list)
    severity: Severity
    references: List[FindingReference] = Field(default_factory=list)
    quality: QualityMetadata
    tool_version: str = "1.0.0"
    schema_version: str = "1.0.0"


class PermitResult(BaseModel):
    """Details of a regulatory permit requirement matching the location context."""
    id: str
    permit_name: str
    issuing_agency: str
    mitigation_requirements: List[str] = Field(default_factory=list)
    severity: Severity
    references: List[FindingReference] = Field(default_factory=list)
    quality: QualityMetadata
    tool_version: str = "1.0.0"
    schema_version: str = "1.0.0"


class BufferResult(BaseModel):
    """Calculated buffer setbacks and violations."""
    setback_required_m: float
    actual_setback_m: float
    violation_detected: bool
    references: List[FindingReference] = Field(default_factory=list)
    tool_version: str = "1.0.0"
    schema_version: str = "1.0.0"


class ExecutionSummary(BaseModel):
    """Telemetry summary for tools executed in the gathering lifecycle."""
    tools_executed: List[str] = Field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    warnings: List[str] = Field(default_factory=list)
    execution_duration_ms: int = 0


# --- Consolidated Environmental Evidence Bundle ---

class EnvironmentalEvidenceBundle(BaseModel):
    """Unified container consolidating all retrieved environmental data outputs."""
    bundle_version: str = "1.0.0"
    schema_version: str = "1.0.0"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    wetlands: List[WetlandResult] = Field(default_factory=list)
    habitats: List[HabitatResult] = Field(default_factory=list)
    permits: List[PermitResult] = Field(default_factory=list)
    buffers: List[BufferResult] = Field(default_factory=list)
    constraints: List[EnvironmentalConstraint] = Field(default_factory=list)
    execution_summary: ExecutionSummary = Field(default_factory=ExecutionSummary)
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


class PermitBatchRequest(BaseToolRequest):
    """Request arguments to query permit requirements in batch."""
    queries: List[str]


class BufferAnalysisRequest(BaseToolRequest):
    """Request arguments to analyze environmental buffer setbacks."""
    aoi_geojson: Dict[str, Any]
    buffer_m: float


# --- Config Validator Schema ---

class EnvironmentalConfigValidator(BaseModel):
    """Configuration validator checking path existence, uniqueness, and versions."""
    version: str
    environmental_tools: Dict[str, Dict[str, Any]]
    processing: Dict[str, Any]
    cache: Dict[str, Any]

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if not v or v != "1.0.0":
            raise ValueError("Invalid configuration version. Must be '1.0.0'.")
        return v

    @field_validator("environmental_tools")
    @classmethod
    def validate_tools(cls, v: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        priorities = []
        layer_names = []
        for name, config in v.items():
            p = config.get("priority")
            if p in priorities:
                raise ValueError(f"Duplicate priority '{p}' found in environmental tools config.")
            priorities.append(p)

            layer = config.get("layer_name")
            if layer:
                if layer in layer_names:
                    raise ValueError(f"Duplicate layer name '{layer}' found in config.")
                layer_names.append(layer)

        return v


# --- Agent Specific Reporting Models ---

class ReasoningSummary(BaseModel):
    """Structured summary of the reasoning decisions and performance statistics."""
    rules_evaluated: int
    findings_generated: int
    recommendations_generated: int
    assumptions_used: int
    execution_duration_ms: int


class PermitFinding(BaseModel):
    """Environmental constraint finding including full traceability references."""
    id: str  # Deterministic PERMIT-0001 format
    title: str
    severity: Severity
    description: str
    supporting_evidence: str
    citations: List[str] = Field(default_factory=list)
    geometry_references: List[FindingReference] = Field(default_factory=list)


class PermitRequirement(BaseModel):
    """Mandatory permitting process details mapped by the reasoning engine."""
    agency: str
    requirement: str
    statutory_reference: str
    mitigation_requirement: str
    deadline: str
    source: str


class PermitRecommendation(BaseModel):
    """Prioritized mitigation recommended for permitting success."""
    id: str  # Deterministic REC-0001 format
    priority: str
    category: str
    action: str
    rationale: str
    related_findings: List[str] = Field(default_factory=list)


class ConfidenceBreakdown(BaseModel):
    """Breakdown of confidence scoring calculations."""
    base_score: float = 1.0
    imagery_deduction: float = 0.0
    habitat_deduction: float = 0.0
    wetlands_deduction: float = 0.0
    semantic_deduction: float = 0.0
    geometry_deduction: float = 0.0
    final_score: float = 1.0


class Assumption(BaseModel):
    """Assumptions used when data gaps or warnings are encountered."""
    id: str
    description: str
    severity: Severity
    source: str


class EnvironmentalPermitReport(BaseModel):
    """The canonical validated report output from the Environmental Permit Agent."""
    report_version: str = "1.0.0"
    schema_version: str = "1.0.0"
    agent_name: str = "EnvironmentalPermitAgent"
    agent_version: str = "1.0.0"
    reasoning_version: str = "1.0.0"
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    workflow_id: str
    study_id: str
    trace_id: str
    execution_status: str  # "success" or "partial"
    confidence_score: float
    confidence_breakdown: ConfidenceBreakdown
    overall_severity: Severity
    permit_findings: List[PermitFinding] = Field(default_factory=list)
    permit_requirements: List[PermitRequirement] = Field(default_factory=list)
    recommendations: List[PermitRecommendation] = Field(default_factory=list)
    assumptions: List[Assumption] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    reasoning_summary: ReasoningSummary
    report_sha256: str = ""

    model_config = ConfigDict(arbitrary_types_allowed=True)
