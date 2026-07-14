import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Column,
    ForeignKey,
    String,
    Integer,
    Numeric,
    DateTime,
    Text,
    UniqueConstraint,
    CheckConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models in the GridPilot application."""
    pass

class User(Base):
    """
    Represents an authorized human user or engineer in the GridPilot system.
    """
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('engineer', 'admin')", name="chk_user_role"),
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="engineer", server_default="engineer")
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    sessions: Mapped[List["Session"]] = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    human_reviews: Mapped[List["HumanReview"]] = relationship("HumanReview", back_populates="reviewer")


class Session(Base):
    """
    Represents an active user session token for authentication.
    """
    __tablename__ = "sessions"
    __table_args__ = (
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.users.id", ondelete="CASCADE"), 
        nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")


class UtilityRegion(Base):
    """
    Represents a geographic utility region or ISO territory with a boundary.
    """
    __tablename__ = "utility_regions"
    __table_args__ = (
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    boundary_geojson: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    nodes: Mapped[List["GridNode"]] = relationship("GridNode", back_populates="region", cascade="all, delete-orphan")
    edges: Mapped[List["GridEdge"]] = relationship("GridEdge", back_populates="region", cascade="all, delete-orphan")
    projects: Mapped[List["Project"]] = relationship("Project", back_populates="region")


class GridNode(Base):
    """
    Represents a bus, substation, or connection point within a synthetic utility region.
    """
    __tablename__ = "grid_nodes"
    __table_args__ = (
        UniqueConstraint("region_id", "node_key", name="uq_grid_nodes_region_node"),
        CheckConstraint("node_type IN ('substation', 'generator_bus', 'load_bus')", name="chk_grid_node_type"),
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.utility_regions.id", ondelete="CASCADE"), 
        nullable=False
    )
    node_key: Mapped[str] = mapped_column(String, nullable=False)
    node_type: Mapped[str] = mapped_column(String, nullable=False)
    voltage_kv: Mapped[float] = mapped_column(Numeric(precision=6, scale=2), nullable=False)
    latitude: Mapped[float] = mapped_column(Numeric(precision=9, scale=6), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(precision=9, scale=6), nullable=False)
    thermal_limit_mva: Mapped[Optional[float]] = mapped_column(Numeric(precision=8, scale=2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    region: Mapped["UtilityRegion"] = relationship("UtilityRegion", back_populates="nodes")
    projects: Mapped[List["Project"]] = relationship("Project", back_populates="poi_node")


class GridEdge(Base):
    """
    Represents a transmission line or transformer connecting two grid nodes.
    """
    __tablename__ = "grid_edges"
    __table_args__ = (
        CheckConstraint("edge_type IN ('line', 'transformer')", name="chk_grid_edge_type"),
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.utility_regions.id", ondelete="CASCADE"), 
        nullable=False
    )
    from_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.grid_nodes.id", ondelete="CASCADE"), 
        nullable=False
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.grid_nodes.id", ondelete="CASCADE"), 
        nullable=False
    )
    edge_type: Mapped[str] = mapped_column(String, nullable=False)
    length_miles: Mapped[Optional[float]] = mapped_column(Numeric(precision=6, scale=2), nullable=True)
    reactance_pu: Mapped[float] = mapped_column(Numeric(precision=8, scale=5), nullable=False)
    thermal_limit_mva: Mapped[float] = mapped_column(Numeric(precision=8, scale=2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    region: Mapped["UtilityRegion"] = relationship("UtilityRegion", back_populates="edges")
    from_node: Mapped["GridNode"] = relationship("GridNode", foreign_keys=[from_node_id])
    to_node: Mapped["GridNode"] = relationship("GridNode", foreign_keys=[to_node_id])
    power_flow_results: Mapped[List["PowerFlowResult"]] = relationship("PowerFlowResult", back_populates="worst_case_line")


class Project(Base):
    """
    Represents a renewable energy project submitted for interconnection study.
    """
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("technology IN ('solar', 'storage', 'solar_plus_storage', 'wind')", name="chk_project_technology"),
        CheckConstraint("status IN ('submitted', 'in_study', 'pending_review', 'approved', 'rejected')", name="chk_project_status"),
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.utility_regions.id"), 
        nullable=False
    )
    poi_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.grid_nodes.id"), 
        nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    technology: Mapped[str] = mapped_column(String, nullable=False)
    capacity_mw: Mapped[float] = mapped_column(Numeric(precision=7, scale=2), nullable=False)
    storage_capacity_mw: Mapped[Optional[float]] = mapped_column(Numeric(precision=7, scale=2), nullable=True)
    aoi_geojson: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    submitted_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String, 
        nullable=False, 
        default="submitted", 
        server_default="submitted"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    region: Mapped["UtilityRegion"] = relationship("UtilityRegion", back_populates="projects")
    poi_node: Mapped["GridNode"] = relationship("GridNode", back_populates="projects")
    studies: Mapped[List["Study"]] = relationship("Study", back_populates="project", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="project")


class Study(Base):
    """
    Represents an active or completed swarm execution run analyzing a project.
    """
    __tablename__ = "studies"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'pending_review', 'revision_requested', 'approved', 'rejected', 'failed')", name="chk_study_status"),
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.projects.id", ondelete="CASCADE"), 
        nullable=False
    )
    status: Mapped[str] = mapped_column(
        String, 
        nullable=False, 
        default="running", 
        server_default="running"
    )
    state_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, 
        nullable=False, 
        default=dict, 
        server_default=text("'{}'::jsonb")
    )
    overall_confidence: Mapped[Optional[float]] = mapped_column(Numeric(precision=4, scale=3), nullable=True)
    study_document_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    pdf_oss_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="studies")
    agent_runs: Mapped[List["AgentRun"]] = relationship("AgentRun", back_populates="study", cascade="all, delete-orphan")
    power_flow_results: Mapped[List["PowerFlowResult"]] = relationship("PowerFlowResult", back_populates="study", cascade="all, delete-orphan")
    cost_allocation_results: Mapped[List["CostAllocationResult"]] = relationship("CostAllocationResult", back_populates="study", cascade="all, delete-orphan")
    environmental_flags: Mapped[List["EnvironmentalFlag"]] = relationship("EnvironmentalFlag", back_populates="study", cascade="all, delete-orphan")
    regulatory_citations: Mapped[List["RegulatoryCitation"]] = relationship("RegulatoryCitation", back_populates="study", cascade="all, delete-orphan")
    human_reviews: Mapped[List["HumanReview"]] = relationship("HumanReview", back_populates="study", cascade="all, delete-orphan")
    audit_logs: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="study", cascade="all, delete-orphan")
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="study", cascade="all, delete-orphan")


class AgentRun(Base):
    """
    Represents the execution details of an individual agent within a study run.
    """
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint("agent_name IN ('site_intelligence', 'environmental_permit', 'power_flow', 'cost_allocation', 'regulatory', 'orchestrator')", name="chk_agent_run_name"),
        CheckConstraint("status IN ('running', 'succeeded', 'failed', 'escalated')", name="chk_agent_run_status"),
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.studies.id", ondelete="CASCADE"), 
        nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String, nullable=False)
    input_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Numeric(precision=4, scale=3), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    qwen_model_used: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    qwen_input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    qwen_output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    study: Mapped["Study"] = relationship("Study", back_populates="agent_runs")


class PowerFlowResult(Base):
    """
    Read-model storing denormalized results of the power flow analysis agent.
    """
    __tablename__ = "power_flow_results"
    __table_args__ = (
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.studies.id", ondelete="CASCADE"), 
        nullable=False
    )
    scenarios_run: Mapped[int] = mapped_column(Integer, nullable=False)
    violation_probability: Mapped[float] = mapped_column(Numeric(precision=4, scale=3), nullable=False)
    worst_case_line_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.grid_edges.id"), 
        nullable=True
    )
    worst_case_loading_pct: Mapped[Optional[float]] = mapped_column(Numeric(precision=6, scale=2), nullable=True)
    worst_case_bus_voltage_pu: Mapped[Optional[float]] = mapped_column(Numeric(precision=5, scale=3), nullable=True)
    raw_results_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    study: Mapped["Study"] = relationship("Study", back_populates="power_flow_results")
    worst_case_line: Mapped[Optional["GridEdge"]] = relationship("GridEdge", back_populates="power_flow_results")


class CostAllocationResult(Base):
    """
    Read-model storing denormalized results of the cost allocation agent.
    """
    __tablename__ = "cost_allocation_results"
    __table_args__ = (
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.studies.id", ondelete="CASCADE"), 
        nullable=False
    )
    total_estimated_cost_usd: Mapped[float] = mapped_column(Numeric(precision=12, scale=2), nullable=False)
    upgrades_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    study: Mapped["Study"] = relationship("Study", back_populates="cost_allocation_results")


class EnvironmentalFlag(Base):
    """
    Read-model storing environmental conflicts detected by the permit agent.
    """
    __tablename__ = "environmental_flags"
    __table_args__ = (
        CheckConstraint("flag_type IN ('wetland', 'habitat', 'other')", name="chk_env_flag_type"),
        CheckConstraint("severity IN ('info', 'review_required', 'blocking')", name="chk_env_flag_severity"),
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.studies.id", ondelete="CASCADE"), 
        nullable=False
    )
    flag_type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    distance_m: Mapped[Optional[float]] = mapped_column(Numeric(precision=10, scale=2), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_dataset: Mapped[str] = mapped_column(String, nullable=False)
    geometry_geojson: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    study: Mapped["Study"] = relationship("Study", back_populates="environmental_flags")


class RegulatoryCitation(Base):
    """
    Read-model storing citations from regulatory tariffs mapped to this study.
    """
    __tablename__ = "regulatory_citations"
    __table_args__ = (
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.studies.id", ondelete="CASCADE"), 
        nullable=False
    )
    section_name: Mapped[str] = mapped_column(String, nullable=False)
    citation_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_document: Mapped[str] = mapped_column(String, nullable=False)
    chroma_chunk_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    study: Mapped["Study"] = relationship("Study", back_populates="regulatory_citations")


class HumanReview(Base):
    """
    Represents human review actions, decisions, and comments on study milestones.
    """
    __tablename__ = "human_reviews"
    __table_args__ = (
        CheckConstraint("decision IN ('approved', 'rejected', 'revision_requested', 'comment')", name="chk_human_review_decision"),
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    study_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.studies.id", ondelete="CASCADE"), 
        nullable=False
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.users.id"), 
        nullable=False
    )
    decision: Mapped[str] = mapped_column(String, nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    affected_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    study: Mapped["Study"] = relationship("Study", back_populates="human_reviews")
    reviewer: Mapped["User"] = relationship("User", back_populates="human_reviews")


class AuditLog(Base):
    """
    Append-only log record for capturing and reconstructing all actions inside the system.
    """
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("actor_type IN ('agent', 'orchestrator', 'human', 'system')", name="chk_audit_actor_type"),
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.studies.id", ondelete="CASCADE"), 
        nullable=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.projects.id"), 
        nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String, nullable=False)
    actor_name: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    detail_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    study: Mapped[Optional["Study"]] = relationship("Study", back_populates="audit_logs")
    project: Mapped[Optional["Project"]] = relationship("Project", back_populates="audit_logs")


class Document(Base):
    """
    Represents references to objects stored in the versioned Alibaba OSS bucket.
    """
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("doc_type IN ('satellite_tile', 'study_pdf', 'audit_export')", name="chk_document_doc_type"),
        {"schema": "gridpilot"}
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        server_default=text("gen_random_uuid()")
    )
    study_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("gridpilot.studies.id", ondelete="CASCADE"), 
        nullable=True
    )
    doc_type: Mapped[str] = mapped_column(String, nullable=False)
    oss_key: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=datetime.utcnow, 
        server_default=text("now()")
    )

    # Relationships
    study: Mapped[Optional["Study"]] = relationship("Study", back_populates="documents")
