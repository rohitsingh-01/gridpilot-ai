"""Report assembler for the Environmental Permit Agent."""
from __future__ import annotations

import hashlib
import time
from typing import List
from datetime import datetime

from agents.site_intelligence.models import Severity
from agents.environmental_permit.models import (
    EnvironmentalEvidenceBundle,
    EnvironmentalPermitReport,
    ReasoningSummary,
    Assumption,
)
from agents.environmental_permit.reasoning import (
    calculate_confidence,
    evaluate_environmental_constraints,
    evaluate_permit_requirements,
    generate_recommendations,
    assign_deterministic_ids,
    apply_escalation_rules,
)


def build_report(
    evidence: EnvironmentalEvidenceBundle,
    trace_id: str,
    workflow_id: str,
    study_id: str,
    execution_duration_ms: int = 0,
) -> EnvironmentalPermitReport:
    """Compile, reason, hash, and validate the final EnvironmentalPermitReport."""
    reasoning_start = time.perf_counter()

    # 1. Run reasoning evaluations
    findings = evaluate_environmental_constraints(evidence)
    permit_reqs = evaluate_permit_requirements(evidence)
    recs = generate_recommendations(findings, evidence)
    
    # Assign deterministic IDs
    findings, recs = assign_deterministic_ids(findings, recs)
    
    overall_sev = apply_escalation_rules(findings)
    confidence_breakdown = calculate_confidence(evidence)

    # 2. Compile assumptions
    assumptions: List[Assumption] = []
    warnings_lower = [w.lower() for w in evidence.execution_summary.warnings]
    
    if any("wetland" in w or "unavailable" in w for w in warnings_lower):
        assumptions.append(
            Assumption(
                id="ASM-WET-01",
                description="Wetland dataset unavailable. Assumed no critical wetland constraints within standard boundaries.",
                severity=Severity.HIGH,
                source="System Fallback"
            )
        )
    if any("habitat" in w or "unavailable" in w for w in warnings_lower):
        assumptions.append(
            Assumption(
                id="ASM-HAB-01",
                description="Critical habitat dataset unavailable. Assumed no endangered species conflicts.",
                severity=Severity.HIGH,
                source="System Fallback"
            )
        )

    # 3. Assemble ReasoningSummary
    reasoning_duration = int((time.perf_counter() - reasoning_start) * 1000)
    summary = ReasoningSummary(
        rules_evaluated=4,  # wetlands, habitats, permits, buffers
        findings_generated=len(findings),
        recommendations_generated=len(recs),
        assumptions_used=len(assumptions),
        execution_duration_ms=reasoning_duration
    )

    # 4. Status policy
    status = "success"
    if len(assumptions) > 0:
        status = "partial"

    # Assemble preliminary report
    report = EnvironmentalPermitReport(
        workflow_id=workflow_id,
        study_id=study_id,
        trace_id=trace_id,
        execution_status=status,
        confidence_score=confidence_breakdown.final_score,
        confidence_breakdown=confidence_breakdown,
        overall_severity=overall_sev,
        permit_findings=findings,
        permit_requirements=permit_reqs,
        recommendations=recs,
        assumptions=assumptions,
        warnings=evidence.execution_summary.warnings,
        reasoning_summary=summary,
        report_sha256=""
    )

    # 5. Compute SHA-256 hash (excluding report_sha256 field itself)
    report_json = report.model_dump_json(exclude={"report_sha256", "generated_at"})
    sha256_hash = hashlib.sha256(report_json.encode("utf-8")).hexdigest()
    report.report_sha256 = sha256_hash

    # Validate model
    return EnvironmentalPermitReport.model_validate(report)
