"""
Comprehensive integration tests for the GridPilot repository layer.

Requirements
------------
* A running PostgreSQL database with the GridPilot schema applied
  (``alembic upgrade head``).
* ``DATABASE_URL`` env-var pointing at it (or the defaults in ``session.py``).

Design
------
Every test uses a **transactional session** that is rolled back at the end
of the test, so tests never leave artefacts in the database.

``session.commit()`` is **never** called inside repositories; the tests
verify this by rolling back after each assertion phase.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from services.db.exceptions import (
    ConcurrencyError,
    ConstraintViolationError,
    EntityDuplicateError,
    EntityNotFoundError,
    RepositoryError,
)
from services.db.models import (
    AuditLog,
    GridEdge,
    GridNode,
    Project,
    Session as UserSession,
    Study,
    User,
    UtilityRegion,
)
from services.db.repositories import (
    AuditLogRepository,
    ProjectRepository,
    StudyRepository,
    UserRepository,
    UtilityRegionRepository,
)
from services.db.session import DATABASE_URL


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_engine():
    """Engine with NullPool to avoid event-loop sharing issues in tests."""
    eng = create_async_engine(DATABASE_URL, poolclass=NullPool)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(test_engine):
    """Yield a session wrapped in a **transaction that is always rolled back**.

    This guarantees tests never persist data.
    """
    async with test_engine.connect() as conn:
        txn = await conn.begin()
        # bind the session to the connection that owns the transaction
        session_factory = sessionmaker(
            bind=conn, class_=AsyncSession, expire_on_commit=False
        )
        async with session_factory() as session:
            yield session
        # Roll back *everything* the test did
        await txn.rollback()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email: str = "test@gridpilot.dev", display_name: str = "Tester") -> User:
    return User(
        email=email,
        display_name=display_name,
        role="engineer",
        password_hash="fakehash_not_real",
    )


def _make_region(name: str = "Test Region") -> UtilityRegion:
    return UtilityRegion(
        name=name,
        boundary_geojson={"type": "Polygon", "coordinates": []},
    )


def _make_node(region_id: uuid.UUID, key: str = "BUS_1") -> GridNode:
    return GridNode(
        region_id=region_id,
        node_key=key,
        node_type="substation",
        voltage_kv=138.00,
        latitude=33.123456,
        longitude=-97.654321,
    )


def _make_edge(
    region_id: uuid.UUID, from_node_id: uuid.UUID, to_node_id: uuid.UUID
) -> GridEdge:
    return GridEdge(
        region_id=region_id,
        from_node_id=from_node_id,
        to_node_id=to_node_id,
        edge_type="line",
        reactance_pu=0.05000,
        thermal_limit_mva=250.00,
    )


def _make_project(region_id: uuid.UUID, poi_node_id: uuid.UUID) -> Project:
    return Project(
        region_id=region_id,
        poi_node_id=poi_node_id,
        name="Solar Farm Alpha",
        technology="solar",
        capacity_mw=100.00,
        aoi_geojson={"type": "Polygon", "coordinates": []},
        status="submitted",
    )


def _make_study(project_id: uuid.UUID) -> Study:
    return Study(
        project_id=project_id,
        status="running",
        state_snapshot={},
    )


# ═══════════════════════════════════════════════════════════════════════════
# Exception hierarchy tests
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptionHierarchy:
    """Verify the custom exception classes behave as expected."""

    def test_repository_error_is_base(self):
        with pytest.raises(RepositoryError):
            raise EntityNotFoundError("User", uuid.uuid4())

    def test_entity_not_found_message(self):
        uid = uuid.uuid4()
        err = EntityNotFoundError("User", uid)
        assert "User" in str(err)
        assert str(uid) in str(err)

    def test_entity_duplicate_message(self):
        err = EntityDuplicateError("User", "email already exists")
        assert "Duplicate" in str(err)
        assert "email already exists" in str(err)

    def test_constraint_violation(self):
        err = ConstraintViolationError("FK violation")
        assert "constraint" in str(err).lower()

    def test_concurrency_error(self):
        uid = uuid.uuid4()
        err = ConcurrencyError("Project", uid)
        assert "concurrent" in str(err).lower() or "Concurrent" in str(err)


# ═══════════════════════════════════════════════════════════════════════════
# UserRepository tests
# ═══════════════════════════════════════════════════════════════════════════


class TestUserRepository:

    @pytest.mark.anyio
    async def test_add_and_get_by_id(self, db_session):
        repo = UserRepository(db_session)
        user = _make_user()
        created = await repo.add(user)
        assert created.id is not None

        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.email == "test@gridpilot.dev"

    @pytest.mark.anyio
    async def test_get_by_email(self, db_session):
        repo = UserRepository(db_session)
        user = _make_user(email="lookup@gridpilot.dev")
        await repo.add(user)

        found = await repo.get_by_email("lookup@gridpilot.dev")
        assert found is not None
        assert found.display_name == "Tester"

    @pytest.mark.anyio
    async def test_get_by_email_not_found(self, db_session):
        repo = UserRepository(db_session)
        result = await repo.get_by_email("nonexistent@gridpilot.dev")
        assert result is None

    @pytest.mark.anyio
    async def test_get_by_id_not_found(self, db_session):
        repo = UserRepository(db_session)
        result = await repo.get_by_id(uuid.uuid4())
        assert result is None

    @pytest.mark.anyio
    async def test_remove_user(self, db_session):
        repo = UserRepository(db_session)
        user = _make_user(email="removable@gridpilot.dev")
        await repo.add(user)

        deleted = await repo.remove(user.id)
        assert deleted is True

        gone = await repo.get_by_id(user.id)
        assert gone is None

    @pytest.mark.anyio
    async def test_remove_nonexistent_returns_false(self, db_session):
        repo = UserRepository(db_session)
        deleted = await repo.remove(uuid.uuid4())
        assert deleted is False

    @pytest.mark.anyio
    async def test_create_and_get_session(self, db_session):
        repo = UserRepository(db_session)
        user = _make_user(email="session_user@gridpilot.dev")
        await repo.add(user)

        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        sess = await repo.create_session(user.id, "hash_abc123", expires)
        assert sess.id is not None
        assert sess.user_id == user.id

        found = await repo.get_session_by_token("hash_abc123")
        assert found is not None
        assert found.user_id == user.id

    @pytest.mark.anyio
    async def test_delete_expired_sessions(self, db_session):
        repo = UserRepository(db_session)
        user = _make_user(email="expired_test@gridpilot.dev")
        await repo.add(user)

        # Create an expired session
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        await repo.create_session(user.id, "expired_hash", past)

        # Create a valid session
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        await repo.create_session(user.id, "valid_hash", future)

        count = await repo.delete_expired_sessions()
        assert count >= 1

        # Expired session should be gone
        assert await repo.get_session_by_token("expired_hash") is None
        # Valid session should remain
        assert await repo.get_session_by_token("valid_hash") is not None


# ═══════════════════════════════════════════════════════════════════════════
# UtilityRegionRepository tests
# ═══════════════════════════════════════════════════════════════════════════


class TestUtilityRegionRepository:

    @pytest.mark.anyio
    async def test_add_and_list_regions(self, db_session):
        repo = UtilityRegionRepository(db_session)
        r1 = _make_region("Region A")
        r2 = _make_region("Region B")
        await repo.add(r1)
        await repo.add(r2)

        regions = await repo.list_regions(limit=10)
        assert len(regions) >= 2

    @pytest.mark.anyio
    async def test_get_with_network(self, db_session):
        repo = UtilityRegionRepository(db_session)
        region = _make_region("Network Region")
        await repo.add(region)

        n1 = _make_node(region.id, "SUB_1")
        n2 = _make_node(region.id, "SUB_2")
        db_session.add_all([n1, n2])
        await db_session.flush()

        edge = _make_edge(region.id, n1.id, n2.id)
        db_session.add(edge)
        await db_session.flush()

        loaded = await repo.get_with_network(region.id)
        assert loaded is not None
        assert len(loaded.nodes) == 2
        assert len(loaded.edges) == 1

    @pytest.mark.anyio
    async def test_get_node_by_key(self, db_session):
        repo = UtilityRegionRepository(db_session)
        region = _make_region("Key Lookup Region")
        await repo.add(region)

        node = _make_node(region.id, "UNIQUE_KEY_42")
        db_session.add(node)
        await db_session.flush()

        found = await repo.get_node_by_key(region.id, "UNIQUE_KEY_42")
        assert found is not None
        assert found.node_key == "UNIQUE_KEY_42"

    @pytest.mark.anyio
    async def test_get_node_by_key_not_found(self, db_session):
        repo = UtilityRegionRepository(db_session)
        result = await repo.get_node_by_key(uuid.uuid4(), "NOKEY")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# ProjectRepository tests
# ═══════════════════════════════════════════════════════════════════════════


class TestProjectRepository:

    async def _seed_project(self, db_session) -> Project:
        """Create prerequisite region + node and return a flushed project."""
        region = _make_region("Project Region")
        db_session.add(region)
        await db_session.flush()

        node = _make_node(region.id, "POI_1")
        db_session.add(node)
        await db_session.flush()

        repo = ProjectRepository(db_session)
        proj = _make_project(region.id, node.id)
        await repo.add(proj)
        return proj

    @pytest.mark.anyio
    async def test_add_and_get(self, db_session):
        proj = await self._seed_project(db_session)
        repo = ProjectRepository(db_session)

        fetched = await repo.get_by_id(proj.id)
        assert fetched is not None
        assert fetched.name == "Solar Farm Alpha"

    @pytest.mark.anyio
    async def test_list_by_status(self, db_session):
        await self._seed_project(db_session)
        repo = ProjectRepository(db_session)

        results = await repo.list_by_status("submitted")
        assert len(results) >= 1

    @pytest.mark.anyio
    async def test_update_status_optimistic(self, db_session):
        proj = await self._seed_project(db_session)
        repo = ProjectRepository(db_session)

        updated = await repo.update_status(proj.id, "submitted", "in_study")
        assert updated.status == "in_study"

    @pytest.mark.anyio
    async def test_update_status_concurrency_error(self, db_session):
        proj = await self._seed_project(db_session)
        repo = ProjectRepository(db_session)

        with pytest.raises(ConcurrencyError):
            await repo.update_status(proj.id, "in_study", "approved")

    @pytest.mark.anyio
    async def test_update_status_entity_not_found(self, db_session):
        repo = ProjectRepository(db_session)
        with pytest.raises(EntityNotFoundError):
            await repo.update_status(uuid.uuid4(), "submitted", "in_study")

    @pytest.mark.anyio
    async def test_get_project_summary(self, db_session):
        proj = await self._seed_project(db_session)
        repo = ProjectRepository(db_session)

        summary = await repo.get_project_summary(proj.id)
        assert summary is not None
        assert summary["id"] == proj.id
        assert summary["name"] == "Solar Farm Alpha"
        assert summary["status"] == "submitted"

    @pytest.mark.anyio
    async def test_get_project_summary_not_found(self, db_session):
        repo = ProjectRepository(db_session)
        assert await repo.get_project_summary(uuid.uuid4()) is None

    @pytest.mark.anyio
    async def test_get_with_studies(self, db_session):
        proj = await self._seed_project(db_session)
        study = _make_study(proj.id)
        db_session.add(study)
        await db_session.flush()

        repo = ProjectRepository(db_session)
        loaded = await repo.get_with_studies(proj.id)
        assert loaded is not None
        assert len(loaded.studies) == 1


# ═══════════════════════════════════════════════════════════════════════════
# StudyRepository tests
# ═══════════════════════════════════════════════════════════════════════════


class TestStudyRepository:

    async def _seed_study(self, db_session) -> tuple:
        """Create prerequisite region -> node -> project -> study.

        Returns (user, region, node, project, study).
        """
        user = _make_user(email=f"study_user_{uuid.uuid4().hex[:8]}@gridpilot.dev")
        db_session.add(user)
        await db_session.flush()

        region = _make_region(f"Study Region {uuid.uuid4().hex[:6]}")
        db_session.add(region)
        await db_session.flush()

        node = _make_node(region.id, f"N_{uuid.uuid4().hex[:6]}")
        db_session.add(node)
        await db_session.flush()

        proj = _make_project(region.id, node.id)
        db_session.add(proj)
        await db_session.flush()

        repo = StudyRepository(db_session)
        study = _make_study(proj.id)
        await repo.add(study)
        return user, region, node, proj, study

    @pytest.mark.anyio
    async def test_add_and_get(self, db_session):
        _, _, _, _, study = await self._seed_study(db_session)
        repo = StudyRepository(db_session)
        fetched = await repo.get_by_id(study.id)
        assert fetched is not None
        assert fetched.status == "running"

    @pytest.mark.anyio
    async def test_get_full_study_state(self, db_session):
        _, _, _, _, study = await self._seed_study(db_session)
        repo = StudyRepository(db_session)
        full = await repo.get_full_study_state(study.id)
        assert full is not None
        assert isinstance(full.agent_runs, list)
        assert isinstance(full.power_flow_results, list)

    # -- Agent runs --------------------------------------------------------

    @pytest.mark.anyio
    async def test_add_and_update_agent_run(self, db_session):
        _, _, _, _, study = await self._seed_study(db_session)
        repo = StudyRepository(db_session)

        run = await repo.add_agent_run(
            study.id, "power_flow", {"grid_model": "5bus"}, "running"
        )
        assert run.id is not None
        assert run.agent_name == "power_flow"

        updated = await repo.update_agent_run(
            run.id,
            status="succeeded",
            output_json={"violations": 0},
            confidence=0.95,
            duration_ms=1200,
        )
        assert updated.status == "succeeded"
        assert updated.confidence == pytest.approx(0.95, abs=0.001)
        assert updated.duration_ms == 1200

    @pytest.mark.anyio
    async def test_update_agent_run_not_found(self, db_session):
        repo = StudyRepository(db_session)
        with pytest.raises(EntityNotFoundError):
            await repo.update_agent_run(uuid.uuid4(), "failed")

    # -- Power flow --------------------------------------------------------

    @pytest.mark.anyio
    async def test_save_power_flow_result(self, db_session):
        _, _, _, _, study = await self._seed_study(db_session)
        repo = StudyRepository(db_session)

        pf = await repo.save_power_flow_result(
            study_id=study.id,
            scenarios_run=100,
            violation_probability=0.023,
            raw_results_json={"scenario_1": {}},
        )
        assert pf.id is not None
        assert pf.scenarios_run == 100

    # -- Cost allocation ---------------------------------------------------

    @pytest.mark.anyio
    async def test_save_cost_allocation_result(self, db_session):
        _, _, _, _, study = await self._seed_study(db_session)
        repo = StudyRepository(db_session)

        ca = await repo.save_cost_allocation_result(
            study_id=study.id,
            total_estimated_cost_usd=1_500_000.00,
            upgrades_json={"upgrade_1": {"cost": 500000}},
        )
        assert ca.id is not None
        assert ca.total_estimated_cost_usd == pytest.approx(1_500_000.00)

    # -- Environmental flags -----------------------------------------------

    @pytest.mark.anyio
    async def test_add_environmental_flag(self, db_session):
        _, _, _, _, study = await self._seed_study(db_session)
        repo = StudyRepository(db_session)

        flag = await repo.add_environmental_flag(
            study_id=study.id,
            flag_type="wetland",
            severity="review_required",
            description="Adjacent wetland detected",
            source_dataset="NWI",
            distance_m=150.0,
        )
        assert flag.id is not None
        assert flag.flag_type == "wetland"

    @pytest.mark.anyio
    async def test_bulk_add_environmental_flags(self, db_session):
        _, _, _, _, study = await self._seed_study(db_session)
        repo = StudyRepository(db_session)

        flags = [
            {
                "flag_type": "wetland",
                "severity": "info",
                "description": f"Flag {i}",
                "source_dataset": "NWI",
            }
            for i in range(5)
        ]
        count = await repo.bulk_add_environmental_flags(study.id, flags)
        assert count == 5

    @pytest.mark.anyio
    async def test_bulk_add_empty_list(self, db_session):
        repo = StudyRepository(db_session)
        count = await repo.bulk_add_environmental_flags(uuid.uuid4(), [])
        assert count == 0

    # -- Regulatory citations ----------------------------------------------

    @pytest.mark.anyio
    async def test_add_regulatory_citation(self, db_session):
        _, _, _, _, study = await self._seed_study(db_session)
        repo = StudyRepository(db_session)

        cit = await repo.add_regulatory_citation(
            study_id=study.id,
            section_name="FERC Order 2023",
            citation_text="Section 3.1.2 …",
            source_document="ferc_order_2023.pdf",
            chroma_chunk_id="chunk_abc123",
        )
        assert cit.id is not None

    # -- Human reviews -----------------------------------------------------

    @pytest.mark.anyio
    async def test_add_human_review(self, db_session):
        user, _, _, _, study = await self._seed_study(db_session)
        repo = StudyRepository(db_session)

        rev = await repo.add_human_review(
            study_id=study.id,
            reviewer_id=user.id,
            decision="approved",
            comment="Looks good",
        )
        assert rev.id is not None
        assert rev.decision == "approved"

    # -- Documents ---------------------------------------------------------

    @pytest.mark.anyio
    async def test_add_document(self, db_session):
        _, _, _, _, study = await self._seed_study(db_session)
        repo = StudyRepository(db_session)

        doc = await repo.add_document(
            study_id=study.id,
            doc_type="study_pdf",
            oss_key="studies/123/report.pdf",
            content_type="application/pdf",
            size_bytes=204800,
        )
        assert doc.id is not None
        assert doc.oss_key == "studies/123/report.pdf"


# ═══════════════════════════════════════════════════════════════════════════
# AuditLogRepository tests
# ═══════════════════════════════════════════════════════════════════════════


class TestAuditLogRepository:

    @pytest.mark.anyio
    async def test_create_log(self, db_session):
        repo = AuditLogRepository(db_session)
        log = await repo.create_log(
            actor_type="system",
            actor_name="test_runner",
            action="test.create_log",
            detail_json={"test": True},
        )
        assert log.id is not None
        assert log.actor_type == "system"

    @pytest.mark.anyio
    async def test_list_logs_for_study(self, db_session):
        # Seed a study first
        region = _make_region("Audit Region")
        db_session.add(region)
        await db_session.flush()

        node = _make_node(region.id, "AUDIT_NODE")
        db_session.add(node)
        await db_session.flush()

        proj = _make_project(region.id, node.id)
        db_session.add(proj)
        await db_session.flush()

        study = _make_study(proj.id)
        db_session.add(study)
        await db_session.flush()

        repo = AuditLogRepository(db_session)
        # Insert several logs
        for i in range(3):
            await repo.create_log(
                actor_type="agent",
                actor_name=f"agent_{i}",
                action=f"action_{i}",
                detail_json={"step": i},
                study_id=study.id,
            )

        logs = await repo.list_logs_for_study(study.id, limit=10)
        assert len(logs) == 3

    @pytest.mark.anyio
    async def test_list_logs_cursor_pagination(self, db_session):
        # Seed study
        region = _make_region("Cursor Region")
        db_session.add(region)
        await db_session.flush()

        node = _make_node(region.id, "CUR_NODE")
        db_session.add(node)
        await db_session.flush()

        proj = _make_project(region.id, node.id)
        db_session.add(proj)
        await db_session.flush()

        study = _make_study(proj.id)
        db_session.add(study)
        await db_session.flush()

        repo = AuditLogRepository(db_session)
        for i in range(5):
            await repo.create_log(
                actor_type="orchestrator",
                actor_name="orch",
                action=f"step_{i}",
                detail_json={"i": i},
                study_id=study.id,
            )

        # First page
        page1 = await repo.list_logs_cursor(study.id, limit=3)
        assert len(page1) == 3

        # Second page using last item as cursor
        last = page1[-1]
        page2 = await repo.list_logs_cursor(
            study.id, limit=3,
            cursor_time=last.created_at,
            cursor_id=last.id,
        )
        assert len(page2) == 2  # remaining items

    @pytest.mark.anyio
    async def test_audit_log_has_no_remove_method(self, db_session):
        """Verify AuditLogRepository does NOT expose remove()."""
        repo = AuditLogRepository(db_session)
        assert not hasattr(repo, "remove"), (
            "AuditLogRepository must NOT expose remove() "
            "— audit rows are immutable"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Cross-cutting: commit prohibition static test
# ═══════════════════════════════════════════════════════════════════════════


class TestCommitProhibition:
    """Verify that no repository module contains session.commit()."""

    def test_no_commit_in_repository_source(self):
        """Static analysis: check executable lines for session.commit()."""
        import ast
        import pathlib

        repo_dir = pathlib.Path(__file__).resolve().parent.parent / "repositories"
        for py_file in repo_dir.glob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            # Strip docstrings and comments: check only executable lines
            executable_lines: list[str] = []
            for line in source.splitlines():
                stripped = line.strip()
                # Skip comment-only lines
                if stripped.startswith("#"):
                    continue
                executable_lines.append(line)

            executable_text = "\n".join(executable_lines)

            # Remove triple-quoted docstrings via AST
            try:
                tree = ast.parse(source)
                docstring_lines: set[int] = set()
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                        if (
                            node.body
                            and isinstance(node.body[0], ast.Expr)
                            and isinstance(node.body[0].value, ast.Constant)
                            and isinstance(node.body[0].value.value, str)
                        ):
                            ds = node.body[0]
                            for ln in range(ds.lineno, ds.end_lineno + 1):  # type: ignore[union-attr]
                                docstring_lines.add(ln)

                lines_numbered = source.splitlines()
                code_only = "\n".join(
                    l for i, l in enumerate(lines_numbered, 1)
                    if i not in docstring_lines and not l.strip().startswith("#")
                )
            except SyntaxError:
                code_only = executable_text

            assert "session.commit()" not in code_only, (
                f"{py_file.name} contains session.commit() in executable code — "
                f"repositories must never commit"
            )
            assert "session.rollback()" not in code_only, (
                f"{py_file.name} contains session.rollback() in executable code — "
                f"repositories must never rollback"
            )
