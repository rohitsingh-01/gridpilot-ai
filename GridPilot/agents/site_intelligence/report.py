"""Report builder converting evidence bundles and reasoning outputs into standard SiteIntelligenceReports."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Dict, Any

from agents.site_intelligence.models import (
    EvidenceBundle,
    SiteIntelligenceReport,
    ToolExecutionSummary,
    Severity,
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
    """Build and serialize a standardized SiteIntelligenceReport from an EvidenceBundle."""
    generated_at_str = datetime.now(timezone.utc).isoformat()
    
    # 1. Determine execution status
    # If project or study details are empty (which shouldn't pass request validation, but just in case)
    if not evidence.project.id or not evidence.study.id:
        status = "failed"
    elif evidence.imagery is None or not evidence.osm_features:
        status = "partial"
    else:
        status = "complete"

    # 2. Run reasoning calculations
    confidence = calculate_confidence(evidence)
    findings = synthesize_findings(evidence)
    recommendations = generate_recommendations(evidence)

    # 3. Assemble assumptions and limitations
    assumptions = ["Project boundary is represented accurately by the input AOI geometry."]
    limitations = ["OSM features are dependent on Overpass community voluntary update frequencies."]

    if evidence.imagery is None:
        assumptions.append("Satellite imagery cache was missing; fell back to OSM-only validation.")
        limitations.append("Analysis lacks true-color Sentinel-2 visual confirmation.")
    else:
        assumptions.append(f"Scene date parsed from imagery cache: {evidence.imagery.cache_path}")

    report = SiteIntelligenceReport(
        report_version="1.0.0",
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
        tool_metrics=tool_metrics or [],
        confidence_score=confidence,
        assumptions=assumptions,
        limitations=limitations,
        warnings=[
            w for w in [
                "Missing imagery cache reference" if evidence.imagery is None else "",
                "Empty OSM feature dataset" if not evidence.osm_features else "",
            ] if w
        ],
    )

    return report
