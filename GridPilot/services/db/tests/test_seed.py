"""Integration tests for the GridPilot database seeder."""
from __future__ import annotations

import json
import os
import uuid
import pytest
from sqlalchemy import select, delete
from pydantic import ValidationError

from services.db.models import (
    User,
    UtilityRegion,
    GridNode,
    GridEdge,
    Project,
    Study,
)
from services.db.session import AsyncSessionLocal
from services.db.seed.seed import run_seed, validate_topology
from services.db.seed.config_models import (
    TopologySeedConfig,
    ProjectSeedConfig,
    UserSeedConfig,
)
from services.db.seed.helpers import (
    get_user_id,
    get_region_id,
    get_project_id,
    get_study_id,
)

# Remove module-level anyio marker to prevent applying it to sync tests


async def cleanup_seed_data():
    """Manually delete all seeded data using their deterministic UUIDs."""
    user_id = get_user_id("priya@gridpilot.dev")
    region_id = get_region_id("ERCOT West Zone")
    project_id = get_project_id("Sagebrush Solar + Storage")
    study_id = get_study_id(project_id)

    async with AsyncSessionLocal() as session:
        # Delete dependencies first to respect foreign keys
        await session.execute(delete(Study).where(Study.id == study_id))
        await session.execute(delete(Project).where(Project.id == project_id))
        await session.execute(delete(GridEdge).where(GridEdge.region_id == region_id))
        await session.execute(delete(GridNode).where(GridNode.region_id == region_id))
        await session.execute(delete(UtilityRegion).where(UtilityRegion.id == region_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


@pytest.fixture
async def seed_cleanup():
    """Ensure database is clean before and after each seeding test."""
    await cleanup_seed_data()
    yield
    await cleanup_seed_data()
    # Clean up manifest file if generated
    manifest_path = "artifacts/seed_manifest.json"
    if os.path.exists(manifest_path):
        try:
            os.remove(manifest_path)
        except OSError:
            pass
    # Dispose the global engine to release connection pool resources
    from services.db.session import engine
    await engine.dispose()


@pytest.mark.anyio
async def test_dry_run_does_not_persist(seed_cleanup):
    """Verify that --dry-run validates everything but does not persist database records."""
    # 1. Run seeder in dry-run mode
    result = await run_seed(profile="demo", dry_run=True)
    assert result["counts"]["users"] == 1
    assert result["counts"]["regions"] == 1
    assert result["counts"]["nodes"] == 9
    assert result["counts"]["edges"] == 12

    # 2. Assert no data is stored in the database
    async with AsyncSessionLocal() as session:
        user_id = get_user_id("priya@gridpilot.dev")
        region_id = get_region_id("ERCOT West Zone")
        project_id = get_project_id("Sagebrush Solar + Storage")

        user = await session.get(User, user_id)
        region = await session.get(UtilityRegion, region_id)
        proj = await session.get(Project, project_id)

        assert user is None, "Dry run persisted User!"
        assert region is None, "Dry run persisted UtilityRegion!"
        assert proj is None, "Dry run persisted Project!"

    # 3. Verify no manifest was written
    assert not os.path.exists("artifacts/seed_manifest.json")


@pytest.mark.anyio
async def test_successful_seeding_and_idempotency(seed_cleanup):
    """Verify successful seeding, manifest generation, and idempotency on duplicate runs."""
    # 1. Run first time (fresh seed)
    result = await run_seed(profile="demo", dry_run=False)
    assert result["counts"]["users"] == 1
    assert result["counts"]["regions"] == 1
    assert result["counts"]["nodes"] == 9
    assert result["counts"]["edges"] == 12

    # 2. Verify records exist in database
    async with AsyncSessionLocal() as session:
        user_id = get_user_id("priya@gridpilot.dev")
        region_id = get_region_id("ERCOT West Zone")
        project_id = get_project_id("Sagebrush Solar + Storage")

        user = await session.get(User, user_id)
        region = await session.get(UtilityRegion, region_id)
        proj = await session.get(Project, project_id)

        assert user is not None
        assert user.email == "priya@gridpilot.dev"
        assert region is not None
        assert region.name == "ERCOT West Zone"
        assert proj is not None
        assert proj.name == "Sagebrush Solar + Storage"

    # 3. Verify manifest was generated correctly
    manifest_path = "artifacts/seed_manifest.json"
    assert os.path.exists(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["seed_version"] == "1.0.0"
    assert manifest["counts"]["users"] == 1
    assert manifest["counts"]["nodes"] == 9
    assert manifest["counts"]["edges"] == 12
    assert manifest["entities"]["users"]["priya@gridpilot.dev"] == str(user_id)

    # 4. Run second time (duplicate run) to verify idempotency
    result2 = await run_seed(profile="demo", dry_run=False)
    assert result2["counts"]["users"] == 1
    assert result2["counts"]["regions"] == 1
    assert result2["counts"]["nodes"] == 9
    assert result2["counts"]["edges"] == 12

    # Verify counts in database didn't double
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User).where(User.email == "priya@gridpilot.dev"))).scalars().all()
        regions = (await session.execute(select(UtilityRegion).where(UtilityRegion.name == "ERCOT West Zone"))).scalars().all()
        projects = (await session.execute(select(Project).where(Project.name == "Sagebrush Solar + Storage"))).scalars().all()

        assert len(users) == 1, "Duplicate seeding created multiple users!"
        assert len(regions) == 1, "Duplicate seeding created multiple regions!"
        assert len(projects) == 1, "Duplicate seeding created multiple projects!"


def test_topology_validation_poi_missing():
    """Verify that topology validation catches missing POI node references."""
    topology = TopologySeedConfig(
        nodes=[
            {
                "node_key": "BUS_1",
                "node_type": "substation",
                "voltage_kv": 138.0,
                "latitude": 30.9,
                "longitude": -102.6,
            }
        ],
        edges=[]
    )
    projects = [
        ProjectSeedConfig(
            name="Test Solar",
            technology="solar",
            capacity_mw=10.0,
            poi_node_key="BUS_MISSING",  # Missing in nodes list
            aoi_geojson={"type": "Polygon", "coordinates": []}
        )
    ]

    with pytest.raises(ValueError, match="POI node key.*is not part of the seeded topology"):
        validate_topology(topology, projects, "Test Region")


def test_topology_validation_islands():
    """Verify that topology validation catches islanded/disconnected sub-graphs."""
    topology = TopologySeedConfig(
        nodes=[
            {
                "node_key": "BUS_1",
                "node_type": "substation",
                "voltage_kv": 138.0,
                "latitude": 30.9,
                "longitude": -102.6,
            },
            {
                "node_key": "BUS_2",
                "node_type": "substation",
                "voltage_kv": 138.0,
                "latitude": 30.9,
                "longitude": -102.5,
            }
        ],
        edges=[]  # No connection between BUS_1 and BUS_2 -> disconnected
    )
    projects = [
        ProjectSeedConfig(
            name="Test Solar",
            technology="solar",
            capacity_mw=10.0,
            poi_node_key="BUS_1",
            aoi_geojson={"type": "Polygon", "coordinates": []}
        )
    ]

    with pytest.raises(ValueError, match="Graph is disconnected"):
        validate_topology(topology, projects, "Test Region")


def test_topology_validation_voltage_mismatch():
    """Verify that topology validation catches line voltage mismatches."""
    topology = TopologySeedConfig(
        nodes=[
            {
                "node_key": "BUS_1",
                "node_type": "substation",
                "voltage_kv": 138.0,
                "latitude": 30.9,
                "longitude": -102.6,
            },
            {
                "node_key": "BUS_2",
                "node_type": "substation",
                "voltage_kv": 34.5,  # Mismatched voltage
                "latitude": 30.9,
                "longitude": -102.5,
            }
        ],
        edges=[
            {
                "from_node": "BUS_1",
                "to_node": "BUS_2",
                "edge_type": "line",  # Line requires consistent voltage levels
                "reactance_pu": 0.05,
                "thermal_limit_mva": 100.0,
            }
        ]
    )
    projects = [
        ProjectSeedConfig(
            name="Test Solar",
            technology="solar",
            capacity_mw=10.0,
            poi_node_key="BUS_1",
            aoi_geojson={"type": "Polygon", "coordinates": []}
        )
    ]

    with pytest.raises(ValueError, match="Line connects nodes with mismatched voltage levels"):
        validate_topology(topology, projects, "Test Region")
