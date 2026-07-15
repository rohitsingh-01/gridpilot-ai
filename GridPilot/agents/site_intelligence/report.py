"""Report builder converting evidence bundles and reasoning outputs into standard SiteIntelligenceReports."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any

from agents.site_intelligence.models import (
    EvidenceBundle,
    SiteIntelligenceReport,
    ToolExecutionSummary,
    Severity,
    Assumption,
    ConfidenceBreakdown,
)
from agents.site_intelligence.reasoning import (
    calculate_confidence,
    synthesize_findings,
    generate_recommendations,
)


def build_report(
    evidence: EvidenceBundle,
    trace_id: str,
    workflow_id: str,
    tool_metrics: List[ToolExecutionSummary] = None,
) -> SiteIntelligenceReport:
    """Build, hash, and validate a standardized SiteIntelligenceReport from an EvidenceBundle."""
    generated_at_str = datetime.now(timezone.utc).isoformat()
    
    # 1. Determine execution status
    if not evidence.project.id or not evidence.study.id:
        status = "failed"
    elif evidence.imagery is None or not evidence.osm_features:
        status = "partial"
    else:
        status = "complete"

    # 2. Run reasoning calculations
    breakdown = calculate_confidence(evidence)
    findings = synthesize_findings(evidence)
    recommendations = generate_recommendations(evidence)

    # 3. Assemble structured assumptions and limitations
    assumptions: List[Assumption] = [
        Assumption(
            id="ASM-0001",
            description="Project boundary is represented accurately by the input AOI geometry.",
            severity=Severity.LOW,
            source="Project Input Geometry"
        )
    ]
    
    limitations = [
        "OSM features are dependent on Overpass community voluntary update frequencies."
    ]

    if evidence.imagery is None:
        assumptions.append(
            Assumption(
                id="ASM-0002",
                description="Satellite imagery cache was missing; fell back to OSM-only validation.",
                severity=Severity.MEDIUM,
                source="Imagery Service"
            )
        )
        limitations.append("Analysis lacks true-color Sentinel-2 visual confirmation.")
    else:
        assumptions.append(
            Assumption(
                id="ASM-0002",
                description=f"Scene date parsed from imagery cache: {evidence.imagery.cache_path}",
                severity=Severity.LOW,
                source="Imagery Service"
            )
        )

    # 4. Construct initial report (without hash)
    # Ensure tool metrics are sorted deterministically
    sorted_tool_metrics = sorted(tool_metrics or [], key=lambda m: m.tool_name)

    report = SiteIntelligenceReport(
        report_version="1.0.0",
        report_sha256="",
        generated_at=generated_at_str,
        workflow_id=workflow_id,
        study_id=evidence.study.id,
        trace_id=trace_id,
        status=status,
        environmental_findings=findings.get("environmental") or [],
        infrastructure_findings=findings.get("infrastructure") or [],
        regulatory_findings=findings.get("regulatory") or [],
        overall_risk=findings.get("overall_risk")[0] if findings.get("overall_risk") else Severity.LOW,
        recommendations=recommendations,
        tool_metrics=sorted_tool_metrics,
        confidence_score=breakdown.final_score,
        confidence_breakdown=breakdown,
        assumptions=assumptions,
        limitations=limitations,
        warnings=[
            w for w in [
                "Missing imagery cache reference" if evidence.imagery is None else "",
                "Empty OSM feature dataset" if not evidence.osm_features else "",
            ] if w
        ],
    )

    # 5. Generate deterministic SHA-256 hash of report data
    # Dump model to json excluding report_sha256 to ensure stability
    serialized_json = report.model_dump_json(exclude={"report_sha256"})
    report.report_sha256 = hashlib.sha256(serialized_json.encode("utf-8")).hexdigest()

    # 6. Structured validation step
    SiteIntelligenceReport.model_validate(report.model_dump())

    return report
