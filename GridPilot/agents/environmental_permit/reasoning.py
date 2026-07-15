"""Pure reasoning engine for the Environmental Permit Agent."""
from __future__ import annotations

from typing import List, Tuple
from agents.site_intelligence.models import Severity, FindingReference
from agents.environmental_permit.models import (
    EnvironmentalEvidenceBundle,
    ConfidenceBreakdown,
    PermitFinding,
    PermitRequirement,
    PermitRecommendation,
    Assumption,
)


def calculate_confidence(evidence: EnvironmentalEvidenceBundle) -> ConfidenceBreakdown:
    """Calculate structured confidence scoring deductions based on evidence completeness."""
    base_score = 1.0
    imagery_ded = 0.0
    habitat_ded = 0.0
    wetlands_ded = 0.0
    semantic_ded = 0.0
    geometry_ded = 0.0

    # 1. Evaluate missing datasets and warnings
    warnings_lower = [w.lower() for w in evidence.execution_summary.warnings]
    
    # Check if tools returned empty lists because service layer is missing
    service_missing = any("unavailable" in w for w in warnings_lower)

    if not evidence.wetlands or service_missing:
        wetlands_ded = 0.3
    if not evidence.habitats or service_missing:
        habitat_ded = 0.3
    if not evidence.permits or service_missing:
        semantic_ded = 0.2
    
    # Check if buffer warning is present or actual buffer setback is less than required
    if any(b.violation_detected for b in evidence.buffers) or "buffer" in warnings_lower:
        geometry_ded = 0.1

    # Check for missing imagery references (fallback)
    if "imagery" in warnings_lower:
        imagery_ded = 0.1

    final_score = max(0.0, min(1.0, base_score - (imagery_ded + habitat_ded + wetlands_ded + semantic_ded + geometry_ded)))

    return ConfidenceBreakdown(
        base_score=base_score,
        imagery_deduction=imagery_ded,
        habitat_deduction=habitat_ded,
        wetlands_deduction=wetlands_ded,
        semantic_deduction=semantic_ded,
        geometry_deduction=geometry_ded,
        final_score=final_score,
    )


def apply_escalation_rules(findings: List[PermitFinding]) -> Severity:
    """Determine overall severity level by escalating to the maximum finding severity."""
    if not findings:
        return Severity.LOW
    
    severity_rank = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
    }
    
    # Sort by rank ascending (lowest rank number = highest severity)
    sorted_findings = sorted(findings, key=lambda f: severity_rank.get(f.severity, 4))
    return sorted_findings[0].severity


def evaluate_environmental_constraints(evidence: EnvironmentalEvidenceBundle) -> List[PermitFinding]:
    """Synthesize evidence bundle into traceable PermitFindings."""
    findings: List[PermitFinding] = []

    # 1. Wetland Findings
    for idx, w in enumerate(evidence.wetlands):
        sev = Severity.HIGH
        if w.area_overlap_pct > 20.0:
            sev = Severity.CRITICAL
        
        # Build traceable finding references
        geom_refs = [
            FindingReference(
                tool="query_wetlands",
                source=w.quality.source_dataset,
                identifier=w.id
            )
        ]

        findings.append(
            PermitFinding(
                id=f"TEMP-WET-{idx}",
                title=f"Wetland Overlap Detected ({w.classification})",
                severity=sev,
                description=f"Direct overlap with mapped wetland. Affected area: {w.area_overlap_pct:.1f}%.",
                supporting_evidence=f"Overlap percentage is {w.area_overlap_pct}%.",
                citations=["USACE Wetland Delineation Manual"],
                geometry_references=geom_refs
            )
        )

    # 2. Critical Habitat Findings
    for idx, h in enumerate(evidence.habitats):
        sev = Severity.HIGH
        if h.status.lower() == "endangered":
            sev = Severity.CRITICAL
            
        geom_refs = [
            FindingReference(
                tool="query_critical_habitat",
                source=h.quality.source_dataset,
                identifier=h.id
            )
        ]

        findings.append(
            PermitFinding(
                id=f"TEMP-HAB-{idx}",
                title=f"Protected Habitat Overlap ({h.species_name})",
                severity=sev,
                description=f"Intersecting protected species habitat. Status: {h.status}.",
                supporting_evidence=f"Habitat species match for {h.species_name}. Seasonal constraints: {', '.join(h.seasonal_restrictions)}.",
                citations=["Endangered Species Act Section 7"],
                geometry_references=geom_refs
            )
        )

    # 3. Buffer Violation Findings
    for idx, b in enumerate(evidence.buffers):
        if b.violation_detected:
            findings.append(
                PermitFinding(
                    id=f"TEMP-BUF-{idx}",
                    title="Setback Buffer Violation",
                    severity=Severity.HIGH,
                    description=f"Calculated setback is {b.actual_setback_m}m, which is below the required {b.setback_required_m}m.",
                    supporting_evidence=f"Buffer margin violation of {b.setback_required_m - b.actual_setback_m}m.",
                    citations=["Local Zoning Setbacks"],
                    geometry_references=b.references or []
                )
            )

    return findings


def evaluate_permit_requirements(evidence: EnvironmentalEvidenceBundle) -> List[PermitRequirement]:
    """Parse permits evidence into PermitRequirement mappings."""
    requirements: List[PermitRequirement] = []
    
    for p in evidence.permits:
        requirements.append(
            PermitRequirement(
                agency=p.issuing_agency,
                requirement=p.permit_name,
                statutory_reference=f"Statute linked to {p.quality.source_dataset}",
                mitigation_requirement=", ".join(p.mitigation_requirements),
                deadline="Prior to Construction Start",
                source=p.quality.source_dataset
            )
        )
        
    return requirements


def generate_recommendations(findings: List[PermitFinding], evidence: EnvironmentalEvidenceBundle) -> List[PermitRecommendation]:
    """Compile recommendations based on generated findings and evidence."""
    recs: List[PermitRecommendation] = []

    # 1. Check for Critical Wetlands
    wetland_findings = [f for f in findings if "Wetland" in f.title]
    if wetland_findings:
        sev = apply_escalation_rules(wetland_findings)
        recs.append(
            PermitRecommendation(
                id="TEMP-REC-1",
                priority="CRITICAL" if sev == Severity.CRITICAL else "HIGH",
                category="wetland",
                action="Submit Notice of Intent (NOI)",
                rationale="Direct wetland intersections require an approved Order of Conditions.",
                related_findings=[f.id for f in wetland_findings]
            )
        )

    # 2. Check for Habitat constraints
    habitat_findings = [f for f in findings if "Habitat" in f.title]
    if habitat_findings:
        recs.append(
            PermitRecommendation(
                id="TEMP-REC-2",
                priority="HIGH",
                category="habitat",
                action="Initiate USFWS Section 7 Consultation",
                rationale="Intersections with endangered habitats require formal agency reviews.",
                related_findings=[f.id for f in habitat_findings]
            )
        )

    # 3. Check for Buffer Warnings
    buffer_findings = [f for f in findings if "Buffer" in f.title]
    if buffer_findings:
        recs.append(
            PermitRecommendation(
                id="TEMP-REC-3",
                priority="MEDIUM",
                category="geometry",
                action="Redesign Project Layout Setback",
                rationale="Alter boundary layout to respect setback requirements and avoid violation appeals.",
                related_findings=[f.id for f in buffer_findings]
            )
        )

    return recs


def assign_deterministic_ids(
    findings: List[PermitFinding],
    recommendations: List[PermitRecommendation]
) -> Tuple[List[PermitFinding], List[PermitRecommendation]]:
    """Sort constraints first, then assign stable, deterministic identifiers."""
    severity_order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
    }

    # 1. Deterministic sort of findings by severity, title, then citation
    findings.sort(
        key=lambda f: (
            severity_order.get(f.severity, 4),
            f.title,
            f.citations[0] if f.citations else ""
        )
    )
    for idx, f in enumerate(findings):
        f.id = f"PERMIT-{idx + 1:04d}"

    # 2. Deterministic sort of recommendations by priority rank, category, then action
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    recommendations.sort(
        key=lambda r: (
            priority_order.get(r.priority, 4),
            r.category,
            r.action
        )
    )
    for idx, r in enumerate(recommendations):
        r.id = f"REC-{idx + 1:04d}"

    return findings, recommendations
