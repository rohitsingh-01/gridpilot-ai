import uuid
from datetime import datetime, timedelta
from sqlalchemy import inspect
from services.db.models import (
    Base,
    User,
    Session,
    UtilityRegion,
    GridNode,
    GridEdge,
    Project,
    Study,
    AgentRun,
    PowerFlowResult,
    CostAllocationResult,
    EnvironmentalFlag,
    RegulatoryCitation,
    HumanReview,
    AuditLog,
    Document,
)

def test_metadata_tables_count():
    """Verify that all 15 tables are declared in SQLAlchemy metadata."""
    expected_tables = {
        "gridpilot.users",
        "gridpilot.sessions",
        "gridpilot.utility_regions",
        "gridpilot.grid_nodes",
        "gridpilot.grid_edges",
        "gridpilot.projects",
        "gridpilot.studies",
        "gridpilot.agent_runs",
        "gridpilot.power_flow_results",
        "gridpilot.cost_allocation_results",
        "gridpilot.environmental_flags",
        "gridpilot.regulatory_citations",
        "gridpilot.human_reviews",
        "gridpilot.audit_log",
        "gridpilot.documents",
    }
    actual_tables = set(Base.metadata.tables.keys())
    assert expected_tables.issubset(actual_tables) or actual_tables == expected_tables
    assert len(actual_tables) == 15

def test_user_model_attributes():
    """Verify Column mapping, default roles, and primary keys on the User model."""
    user = User(
        email="test@gridpilot.com",
        display_name="Test Engineer",
        password_hash="hashed_password"
    )
    assert user.email == "test@gridpilot.com"
    assert user.display_name == "Test Engineer"
    assert User.role.default.arg == "engineer"
    assert User.id.default.arg.__name__ == "uuid4"

def test_session_model_attributes():
    """Verify column mapping and relationships on the Session model."""
    user_id = uuid.uuid4()
    expires = datetime.utcnow() + timedelta(days=1)
    session = Session(
        user_id=user_id,
        token_hash="session_token_hash",
        expires_at=expires
    )
    assert session.user_id == user_id
    assert session.token_hash == "session_token_hash"
    assert session.expires_at == expires

def test_utility_region_model_attributes():
    """Verify boundary_geojson storage on the UtilityRegion model."""
    boundary = {"type": "Polygon", "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]]}
    region = UtilityRegion(
        name="ERCOT-North",
        description="ERCOT Northern region synthetic boundary",
        boundary_geojson=boundary
    )
    assert region.name == "ERCOT-North"
    assert region.boundary_geojson == boundary

def test_grid_node_model_attributes():
    """Verify coordinate and voltage properties on the GridNode model."""
    node = GridNode(
        region_id=uuid.uuid4(),
        node_key="BUS-01",
        node_type="substation",
        voltage_kv=138.0,
        latitude=32.7767,
        longitude=-96.7970,
        thermal_limit_mva=500.0
    )
    assert node.node_key == "BUS-01"
    assert node.voltage_kv == 138.0
    assert node.latitude == 32.7767
    assert node.longitude == -96.7970

def test_grid_edge_model_attributes():
    """Verify edge specs on the GridEdge model."""
    edge = GridEdge(
        region_id=uuid.uuid4(),
        from_node_id=uuid.uuid4(),
        to_node_id=uuid.uuid4(),
        edge_type="line",
        reactance_pu=0.0125,
        thermal_limit_mva=250.0
    )
    assert edge.edge_type == "line"
    assert edge.reactance_pu == 0.0125
    assert edge.thermal_limit_mva == 250.0

def test_project_model_attributes():
    """Verify projects fields and status on the Project model."""
    proj = Project(
        region_id=uuid.uuid4(),
        poi_node_id=uuid.uuid4(),
        name="Sagebrush Solar",
        technology="solar_plus_storage",
        capacity_mw=150.0,
        storage_capacity_mw=50.0,
        aoi_geojson={"type": "Polygon", "coordinates": []}
    )
    assert proj.name == "Sagebrush Solar"
    assert Project.status.default.arg == "submitted"

def test_study_model_attributes():
    """Verify study parameters on the Study model."""
    study = Study(
        project_id=uuid.uuid4(),
        status="running",
        state_snapshot={"active_agent": "site_intelligence"}
    )
    assert study.status == "running"
    assert study.state_snapshot == {"active_agent": "site_intelligence"}

def test_agent_run_model_attributes():
    """Verify run performance logging on the AgentRun model."""
    run = AgentRun(
        study_id=uuid.uuid4(),
        agent_name="site_intelligence",
        status="succeeded",
        input_json={"test_param": True},
        confidence=0.92,
        duration_ms=4500
    )
    assert run.agent_name == "site_intelligence"
    assert run.confidence == 0.92
    assert run.duration_ms == 4500

def test_read_models_attributes():
    """Verify read-models (power_flow, cost, environmental, regulatory)."""
    study_id = uuid.uuid4()
    
    pf = PowerFlowResult(
        study_id=study_id,
        scenarios_run=1000,
        violation_probability=0.025,
        raw_results_json={}
    )
    assert pf.scenarios_run == 1000
    assert pf.violation_probability == 0.025

    cost = CostAllocationResult(
        study_id=study_id,
        total_estimated_cost_usd=1250000.0,
        upgrades_json={}
    )
    assert cost.total_estimated_cost_usd == 1250000.0

    env = EnvironmentalFlag(
        study_id=study_id,
        flag_type="wetland",
        severity="review_required",
        distance_m=45.2,
        description="Intersects NWI Wetland",
        source_dataset="USFWS NWI"
    )
    assert env.flag_type == "wetland"
    assert env.severity == "review_required"

    reg = RegulatoryCitation(
        study_id=study_id,
        section_name="Attachment Y",
        citation_text="Interconnection procedures...",
        source_document="MISO Tariff",
        chroma_chunk_id="chunk-abc-123"
    )
    assert reg.section_name == "Attachment Y"
    assert reg.chroma_chunk_id == "chunk-abc-123"

def test_reviews_logs_and_docs_attributes():
    """Verify human review, append-only logs, and document references mapping."""
    study_id = uuid.uuid4()
    
    hr = HumanReview(
        study_id=study_id,
        reviewer_id=uuid.uuid4(),
        decision="approved",
        comment="Looks solid"
    )
    assert hr.decision == "approved"

    audit = AuditLog(
        study_id=study_id,
        project_id=uuid.uuid4(),
        actor_type="agent",
        actor_name="regulatory",
        action="parse_citation",
        detail_json={"chunk_id": 4}
    )
    assert audit.actor_type == "agent"

    doc = Document(
        study_id=study_id,
        doc_type="study_pdf",
        oss_key="studies/sagebrush_solar.pdf",
        content_type="application/pdf",
        size_bytes=4523000
    )
    assert doc.doc_type == "study_pdf"
    assert doc.oss_key == "studies/sagebrush_solar.pdf"
