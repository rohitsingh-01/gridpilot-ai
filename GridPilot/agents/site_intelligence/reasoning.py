"""Core deterministic reasoning engine (confidence scoring, findings synthesis, and recommendations)."""
from __future__ import annotations

import hashlib
from typing import List, Dict, Any

from agents.site_intelligence.models import (
    EvidenceBundle,
    EnvironmentalFinding,
    InfrastructureFinding,
    RegulatoryFinding,
    Recommendation,
    Severity,
    FindingReference,
    ConfidenceBreakdown,
)


def calculate_confidence(evidence: EvidenceBundle) -> ConfidenceBreakdown:
    """Calculate structured confidence breakdown details based on evidence completeness."""
    base_score = 1.0
    imagery_penalty = 0.0
    osm_penalty = 0.0
    semantic_penalty = 0.0
    geometry_penalty = 0.0

    # 1. Missing satellite imagery tile references
    if evidence.imagery is None:
        imagery_penalty = 0.30

    # 2. No OpenStreetMap infrastructure features
    if not evidence.osm_features:
        osm_penalty = 0.10

    # 3. No semantic regulations matched
    if not evidence.semantic_chunks:
        semantic_penalty = 0.15

    # 4. Repaired geometry warning check
    if evidence.geometry_results.get("warnings") or "repaired" in evidence.geometry_results.get("status", ""):
        geometry_penalty = 0.05

    final_score = max(0.0, min(1.0, base_score - (imagery_penalty + osm_penalty + semantic_penalty + geometry_penalty)))

    return ConfidenceBreakdown(
        base_score=base_score,
        imagery_penalty=imagery_penalty,
        osm_penalty=osm_penalty,
        semantic_penalty=semantic_penalty,
        geometry_penalty=geometry_penalty,
        final_score=final_score
    )


def synthesize_findings(evidence: EvidenceBundle) -> Dict[str, List[Any]]:
    """Analyze the evidence bundle and construct deterministically ordered and identified findings."""
    env_findings: List[EnvironmentalFinding] = []
    infra_findings: List[InfrastructureFinding] = []
    reg_findings: List[RegulatoryFinding] = []
    max_severity = Severity.LOW

    # 1. Evaluate Geometry & Wetlands Overlaps
    intersects = evidence.geometry_results.get("intersects", False)
    dist = evidence.geometry_results.get("distance_m", 0.0)

    if intersects:
        max_severity = Severity.CRITICAL
        env_findings.append(
            EnvironmentalFinding(
                id="ENV-0001",
                label="Wetland Intersection Detected",
                description="Project Area of Interest directly overlaps with NWI-mapped wetlands.",
                severity=Severity.CRITICAL,
                references=[
                    FindingReference(
                        tool="calculate_intersection",
                        source="NWI Wetlands Dataset",
                        identifier="aoi_overlap"
                    )
                ]
            )
        )
    elif dist > 0 and dist < 100:
        if max_severity != Severity.CRITICAL:
            max_severity = Severity.HIGH
        env_findings.append(
            EnvironmentalFinding(
                id="ENV-0001",
                label="Wetland Proximity Buffer Warning",
                description=f"Project AOI is situated {dist:.1f}m from a mapped wetland buffer zone.",
                severity=Severity.HIGH,
                references=[
                    FindingReference(
                        tool="calculate_intersection",
                        source="NWI Wetlands Dataset",
                        identifier="aoi_buffer_distance"
                    )
                ]
            )
        )

    # 2. Evaluate OSM features (Sort by ID to keep deterministic)
    sorted_osm_features = sorted(evidence.osm_features, key=lambda f: f.id)
    for idx, feature in enumerate(sorted_osm_features):
        tags = feature.tags
        feat_type = tags.get("power", "infrastructure")
        label = f"OSM Power {feat_type.capitalize()} Found"
        
        proximity_m = 120.0
        severity = Severity.LOW
        if feat_type == "line":
            severity = Severity.MEDIUM
        
        finding_id = f"GRID-{idx + 1:04d}"
        
        # Sort references deterministically
        references = sorted(
            [
                FindingReference(
                    tool="query_osm",
                    source="OpenStreetMap Overpass API",
                    identifier=str(feature.id)
                )
            ],
            key=lambda r: (r.tool, r.source, r.identifier)
        )

        infra_findings.append(
            InfrastructureFinding(
                id=finding_id,
                label=label,
                description=f"Found nearby OSM grid node {feature.id} tagged with tags: {tags}",
                severity=severity,
                proximity_m=proximity_m,
                references=references
            )
        )

    # 3. Evaluate Semantic Tariffs chunks (Sort by chunk_id to keep deterministic)
    sorted_semantic_chunks = sorted(evidence.semantic_chunks, key=lambda c: c.chunk_id)
    for idx, chunk in enumerate(sorted_semantic_chunks):
        doc_id = chunk.document_id
        citation = chunk.metadata.get("source_document", f"{doc_id}.md")
        
        severity = Severity.LOW
        content_lower = chunk.content.lower()
        if "warning" in content_lower or "penalty" in content_lower:
            severity = Severity.MEDIUM
        if "critical" in content_lower or "no-disturb" in content_lower:
            severity = Severity.HIGH
            
        finding_id = f"REG-{idx + 1:04d}"
        
        references = sorted(
            [
                FindingReference(
                    tool="semantic_search",
                    source=f"ChromaDB - {chunk.document_id}",
                    identifier=chunk.chunk_id
                )
            ],
            key=lambda r: (r.tool, r.source, r.identifier)
        )

        reg_findings.append(
            RegulatoryFinding(
                id=finding_id,
                citation=citation,
                text_chunk=chunk.content,
                severity=severity,
                references=references
            )
        )

    # If imagery was completely missing, raise risk level to at least MEDIUM
    if evidence.imagery is None and max_severity == Severity.LOW:
        max_severity = Severity.MEDIUM

    # Deterministic sorting of final findings
    env_findings.sort(key=lambda f: f.id)
    infra_findings.sort(key=lambda f: f.id)
    reg_findings.sort(key=lambda f: f.id)

    return {
        "environmental": env_findings,
        "infrastructure": infra_findings,
        "regulatory": reg_findings,
        "overall_risk": [max_severity],
    }


def generate_recommendations(evidence: EvidenceBundle) -> List[Recommendation]:
    """Generate actionable priority recommendations categorized and sorted deterministically."""
    recs: List[Recommendation] = []

    # 1. Missing imagery tiles
    if evidence.imagery is None:
        recs.append(
            Recommendation(
                title="Manually Inspect Terrain",
                description="Sentinel-2 satellite imagery was unavailable. Schedule a physical field survey to check for unmapped terrain hazards.",
                priority="HIGH",
                category="environmental",
                related_findings=["imagery_missing"]
            )
        )

    # 2. Wetlands overlap or buffer warnings
    intersects = evidence.geometry_results.get("intersects", False)
    dist = evidence.geometry_results.get("distance_m", 0.0)
    if intersects or (dist > 0 and dist < 100):
        recs.append(
            Recommendation(
                title="Conduct Local Wetland Delineations",
                description="The project boundary is within or adjacent to wetlands. Apply for aDEP Wetlands Protection Act Order of Conditions.",
                priority="CRITICAL",
                category="environmental",
                related_findings=["wetland_intersection", "wetland_proximity"]
            )
        )

    # 3. OSM features
    if evidence.osm_features:
        recs.append(
            Recommendation(
                title="Conduct Interconnection Intersect Analysis",
                description="Examine nearby transmission lines and design optimal corridor routing paths to the grid interconnection nodes.",
                priority="MEDIUM",
                category="grid",
                related_findings=["osm_grid_features"]
            )
        )

    # Sort recommendations deterministically by Priority first, then by Title to guarantee identical lists
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    recs.sort(key=lambda r: (priority_order.get(r.priority, 4), r.title))

    return recs
