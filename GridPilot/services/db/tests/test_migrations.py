import pytest
import uuid
from sqlalchemy import text, inspect
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import ProgrammingError, InternalError
from sqlalchemy.ext.asyncio import create_async_engine
from services.db.session import DATABASE_URL

@pytest.fixture
async def test_engine():
    """Fixture providing a clean async engine with NullPool to avoid event loop sharing bugs."""
    eng = create_async_engine(DATABASE_URL, poolclass=NullPool)
    yield eng
    await eng.dispose()

@pytest.mark.anyio
async def test_tables_and_schema_exist(test_engine):
    """Verify that the gridpilot schema and all 15 expected tables exist."""
    async with test_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'gridpilot';")
        )
        tables = {row[0] for row in result.fetchall()}
        
        expected_tables = {
            "users",
            "sessions",
            "utility_regions",
            "grid_nodes",
            "grid_edges",
            "projects",
            "studies",
            "agent_runs",
            "power_flow_results",
            "cost_allocation_results",
            "environmental_flags",
            "regulatory_citations",
            "human_reviews",
            "audit_log",
            "documents",
            "alembic_version"
        }
        assert expected_tables.issubset(tables) or tables == expected_tables

@pytest.mark.anyio
async def test_indexes_exist(test_engine):
    """Verify that key indexes specified in the Database Design section exist."""
    def inspect_indexes(sync_conn):
        inspector = inspect(sync_conn)
        indexes_by_table = {
            "users": ["users_email_key"],
            "sessions": ["idx_sessions_user_id", "idx_sessions_expires_at"],
            "grid_nodes": ["idx_grid_nodes_region_id"],
            "grid_edges": ["idx_grid_edges_region_id", "idx_grid_edges_from_node", "idx_grid_edges_to_node"],
            "projects": ["idx_projects_region_id", "idx_projects_status"],
            "studies": ["idx_studies_project_id", "idx_studies_status"],
            "agent_runs": ["idx_agent_runs_study_id", "idx_agent_runs_agent_name"],
            "audit_log": ["idx_audit_log_study_id", "idx_audit_log_created_at"],
        }
        
        for table, expected_idxs in indexes_by_table.items():
            indexes = inspector.get_indexes(table, schema="gridpilot")
            idx_names = {idx["name"] for idx in indexes}
            
            # Also check unique constraints
            unique_constrs = inspector.get_unique_constraints(table, schema="gridpilot")
            for uc in unique_constrs:
                if uc["name"]:
                    idx_names.add(uc["name"])
                    
            for exp in expected_idxs:
                assert exp in idx_names or any(exp in name for name in idx_names), f"Missing index {exp} on table {table}"

    async with test_engine.connect() as conn:
        await conn.run_sync(inspect_indexes)

@pytest.mark.anyio
async def test_constraints_exist(test_engine):
    """Verify check constraints and foreign keys exist on tables."""
    def inspect_constraints(sync_conn):
        inspector = inspect(sync_conn)
        fks_projects = inspector.get_foreign_keys("projects", schema="gridpilot")
        fk_targets = {fk["referred_table"] for fk in fks_projects}
        assert "utility_regions" in fk_targets
        assert "grid_nodes" in fk_targets

        fks_studies = inspector.get_foreign_keys("studies", schema="gridpilot")
        fk_targets_studies = {fk["referred_table"] for fk in fks_studies}
        assert "projects" in fk_targets_studies

    async with test_engine.connect() as conn:
        await conn.run_sync(inspect_constraints)

@pytest.mark.anyio
async def test_audit_log_trigger_exists(test_engine):
    """Verify that trg_prevent_audit_log_modify is active on audit_log table."""
    async with test_engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT trigger_name 
            FROM information_schema.triggers 
            WHERE event_object_schema = 'gridpilot' 
              AND event_object_table = 'audit_log' 
              AND trigger_name = 'trg_prevent_audit_log_modify';
        """))
        row = result.fetchone()
        assert row is not None
        assert row[0] == "trg_prevent_audit_log_modify"

@pytest.mark.anyio
async def test_audit_log_trigger_immutability(test_engine):
    """Verify that UPDATE and DELETE on audit_log are blocked by trigger."""
    async with test_engine.begin() as conn:
        # 1. Insert dummy record into audit_log
        log_id = uuid.uuid4()
        await conn.execute(text(f"""
            INSERT INTO gridpilot.audit_log (id, actor_type, actor_name, action, detail_json)
            VALUES ('{log_id}', 'system', 'test_runner', 'test_trigger', '{{}}'::jsonb);
        """))
        
        # 2. Attempt to UPDATE the record (should fail)
        try:
            async with conn.begin_nested():
                await conn.execute(text(f"UPDATE gridpilot.audit_log SET actor_name = 'hacker' WHERE id = '{log_id}';"))
                pytest.fail("UPDATE on audit_log should have failed")
        except Exception as exc_info:
            assert "prevent_audit_log_modification" in str(exc_info) or "immutable" in str(exc_info)

        # 3. Attempt to DELETE the record (should fail)
        try:
            async with conn.begin_nested():
                await conn.execute(text(f"DELETE FROM gridpilot.audit_log WHERE id = '{log_id}';"))
                pytest.fail("DELETE on audit_log should have failed")
        except Exception as exc_info_del:
            assert "prevent_audit_log_modification" in str(exc_info_del) or "immutable" in str(exc_info_del)

@pytest.mark.anyio
async def test_gridpilot_runtime_privilege_enforcement(test_engine):
    """Verify gridpilot_runtime user exists and can only SELECT/INSERT on audit_log."""
    async with test_engine.connect() as conn:
        res = await conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'gridpilot_runtime';"))
        role_exists = res.fetchone() is not None
        
    if not role_exists:
        pytest.skip("gridpilot_runtime role does not exist on this environment")
        
    # Build connection URL for the runtime user
    runtime_url = DATABASE_URL.replace("gridpilot_app", "gridpilot_runtime", 1)
    if "postgres_dev_password_change_me" not in runtime_url:
        runtime_url = runtime_url.replace("@", ":postgres_dev_password_change_me@", 1)
        
    runtime_engine = create_async_engine(runtime_url, poolclass=NullPool)
    
    async with runtime_engine.begin() as conn:
        # 1. Verify runtime role has SELECT/INSERT/UPDATE/DELETE on standard tables (e.g. utility_regions)
        region_id = uuid.uuid4()
        await conn.execute(text(f"""
            INSERT INTO gridpilot.utility_regions (id, name, boundary_geojson)
            VALUES ('{region_id}', 'Runtime Region', '{{}}'::jsonb);
        """))
        res = await conn.execute(text(f"SELECT name FROM gridpilot.utility_regions WHERE id = '{region_id}';"))
        assert res.fetchone()[0] == "Runtime Region"
        
        # Verify can UPDATE utility_regions
        await conn.execute(text(f"UPDATE gridpilot.utility_regions SET name = 'Updated Region' WHERE id = '{region_id}';"))
        
        # 2. Verify runtime role has SELECT/INSERT on audit_log
        log_id = uuid.uuid4()
        await conn.execute(text(f"""
            INSERT INTO gridpilot.audit_log (id, actor_type, actor_name, action, detail_json)
            VALUES ('{log_id}', 'system', 'runtime_runner', 'runtime_test', '{{}}'::jsonb);
        """))
        res = await conn.execute(text(f"SELECT actor_name FROM gridpilot.audit_log WHERE id = '{log_id}';"))
        assert res.fetchone()[0] == "runtime_runner"
        
        # 3. Verify runtime role CANNOT UPDATE audit_log
        try:
            async with conn.begin_nested():
                await conn.execute(text(f"UPDATE gridpilot.audit_log SET actor_name = 'hacker' WHERE id = '{log_id}';"))
                pytest.fail("UPDATE on audit_log by runtime role should have failed")
        except Exception as exc_info:
            assert any(term in str(exc_info).lower() for term in ["permission denied", "prevent_audit_log_modification", "immutable"])
        
        # 4. Verify runtime role CANNOT DELETE audit_log
        try:
            async with conn.begin_nested():
                await conn.execute(text(f"DELETE FROM gridpilot.audit_log WHERE id = '{log_id}';"))
                pytest.fail("DELETE on audit_log by runtime role should have failed")
        except Exception as exc_info_del:
            assert any(term in str(exc_info_del).lower() for term in ["permission denied", "prevent_audit_log_modification", "immutable"])
        
    await runtime_engine.dispose()
