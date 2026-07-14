"""Main orchestrator for the GridPilot database seed system."""
from __future__ import annotations

from typing import Any, List
import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
import networkx as nx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.db.session import AsyncSessionLocal
from services.db.seed.config_models import (
    ProjectSeedConfig,
    RegionSeedConfig,
    TopologySeedConfig,
    UserSeedConfig,
)
from services.db.seed.helpers import (
    StructuredLogger,
    get_node_id,
    get_region_id,
)
from services.db.seed.projects import seed_projects
from services.db.seed.regions import seed_regions
from services.db.seed.studies import seed_studies
from services.db.seed.users import seed_users

SEED_VERSION = "1.0.0"
logger = StructuredLogger()


def load_config_file(profile_path: str, filename: str) -> Any:
    """Load JSON config file from a profile path."""
    filepath = os.path.join(profile_path, filename)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Required seed configuration file missing: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_topology(
    topology_config: TopologySeedConfig, projects_config: List[ProjectSeedConfig], region_name: str
) -> None:
    """Perform topological validation using NetworkX (islands, cycles, nominal voltages)."""
    # 1. Construct network graph
    G = nx.Graph()
    region_id = get_region_id(region_name)

    node_keys = set()
    for n in topology_config.nodes:
        node_id = get_node_id(region_id, n.node_key)
        G.add_node(n.node_key, id=node_id, voltage_kv=n.voltage_kv, type=n.node_type)
        node_keys.add(n.node_key)

    for e in topology_config.edges:
        if e.from_node not in node_keys or e.to_node not in node_keys:
            raise ValueError(
                f"Topology edge references missing node: {e.from_node} -> {e.to_node}"
            )
        G.add_edge(e.from_node, e.to_node, edge_type=e.edge_type)

    # 2. POI existence checks
    for proj in projects_config:
        if proj.poi_node_key not in node_keys:
            raise ValueError(
                f"Project POI node key '{proj.poi_node_key}' is not part of the seeded topology."
            )

    # 3. Connectedness (Island check)
    if not nx.is_connected(G):
        islands = list(nx.connected_components(G))
        raise ValueError(
            f"Topology validation failed: Graph is disconnected. "
            f"Found {len(islands)} isolated sub-graphs: {islands}"
        )

    # 4. Cycle / Loop Permissibility Check (Info level)
    cycles = nx.cycle_basis(G)
    logger.info(
        "seed.validation",
        f"Topology verification: Found {len(cycles)} expected loops/cycles in ring bus network.",
        cycles=cycles,
    )

    # 5. Voltage Level Consistency Checks
    for u, v, data in G.edges(data=True):
        u_kv = G.nodes[u]["voltage_kv"]
        v_kv = G.nodes[v]["voltage_kv"]
        edge_type = data["edge_type"]

        if edge_type == "line":
            if u_kv != v_kv:
                raise ValueError(
                    f"Topology validation failed: Line connects nodes with mismatched voltage levels. "
                    f"Nodes: {u} ({u_kv}kV) <-> {v} ({v_kv}kV)"
                )
        elif edge_type == "transformer":
            logger.info(
                "seed.validation",
                f"Transformer coupling nominal voltages: {u} ({u_kv}kV) <-> {v} ({v_kv}kV)",
            )


async def run_seed(profile: str = "demo", dry_run: bool = False) -> Dict[str, Any]:
    """Execute the transactional seeding process."""
    start_time = time.perf_counter()
    logger.info("seed.init", "Starting GridPilot database seeding.", profile=profile, dry_run=dry_run)

    # 1. Resolve and Load Profiles
    base_dir = os.path.dirname(os.path.abspath(__file__))
    profile_path = os.path.join(base_dir, "data", profile)

    try:
        users_raw = load_config_file(profile_path, "users.json")
        regions_raw = load_config_file(profile_path, "regions.json")
        topology_raw = load_config_file(profile_path, "topology.json")
        projects_raw = load_config_file(profile_path, "projects.json")
    except FileNotFoundError as e:
        logger.error("seed.init", str(e))
        raise

    # 2. Strong Schema Validation (Pydantic)
    try:
        users_list = [UserSeedConfig.model_validate(u) for u in users_raw]
        regions_list = [RegionSeedConfig.model_validate(r) for r in regions_raw]
        topology_config = TopologySeedConfig.model_validate(topology_raw)
        projects_list = [ProjectSeedConfig.model_validate(p) for p in projects_raw]
    except Exception as e:
        logger.error("seed.validation", f"Pydantic config model validation failed: {str(e)}")
        raise

    # 3. Topology Validation
    region_name = regions_list[0].name if regions_list else "ERCOT West Zone"
    try:
        validate_topology(topology_config, projects_list, region_name)
    except ValueError as e:
        logger.error("seed.validation", str(e))
        raise

    # 4. Database Transaction
    alembic_version = "unknown"
    counts = {}
    entities = {}

    async with AsyncSessionLocal() as session:
        # Begin transactional context
        txn = await session.begin()
        # Fetch current Alembic schema version
        try:
            res = await session.execute(text("SELECT version_num FROM gridpilot.alembic_version"))
            alembic_version = res.scalar() or "unknown"
        except Exception:
            logger.warning("seed.init", "Alembic schema version table not found.")

        try:
            logger.info("seed.users", "Seeding User records.")
            user_mapping = await seed_users(session, users_list)
            entities["users"] = {email: str(uid) for email, uid in user_mapping.items()}
            counts["users"] = len(users_list)

            logger.info("seed.topology", "Seeding UtilityRegion and Grid topology (Nodes + Edges).")
            region_mapping, node_mapping, n_count, e_count = await seed_regions(
                session, regions_list, topology_config
            )
            entities["regions"] = {name: str(uid) for name, uid in region_mapping.items()}
            counts["regions"] = len(regions_list)
            counts["nodes"] = n_count
            counts["edges"] = e_count

            logger.info("seed.projects", "Seeding Project records.")
            project_mapping = await seed_projects(
                session, projects_list, region_mapping, node_mapping
            )
            counts["projects"] = len(projects_list)

            logger.info("seed.studies", "Seeding initial Study runs.")
            studies_count = await seed_studies(session, project_mapping)
            counts["studies"] = studies_count

            # Trigger constraints in Postgres without finalising
            await session.flush()

            # Transaction resolution
            if dry_run:
                await txn.rollback()
                logger.info("seed.complete", "Dry run active: all database insertions rolled back.")
            else:
                await txn.commit()
                logger.info("seed.complete", "Seeding transaction committed successfully.")

                # Write manifest to artifacts
                manifest = {
                    "seed_version": SEED_VERSION,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "alembic_version": alembic_version,
                    "counts": counts,
                    "entities": entities,
                }
                os.makedirs("artifacts", exist_ok=True)
                manifest_path = "artifacts/seed_manifest.json"
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2)

        except Exception as exc:
            await txn.rollback()
            logger.error("seed.error", f"Transactional seed execution rolled back due to error: {str(exc)}")
            raise

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    # 5. Output Concise Execution Summary
    summary = f"""
=========================================
GRIDPILOT SEED SUCCESSFUL
=========================================
Seed Version:      {SEED_VERSION}
Alembic Version:   {alembic_version}
Dry Run:           {"Yes" if dry_run else "No"}
Elapsed Time:      {elapsed_ms} ms
-----------------------------------------
Users Seeded:      {counts.get("users", 0)}
Regions Seeded:    {counts.get("regions", 0)}
Nodes Seeded:      {counts.get("nodes", 0)}
Edges Seeded:      {counts.get("edges", 0)}
Projects Seeded:   {counts.get("projects", 0)}
Studies Seeded:    {counts.get("studies", 0)}
-----------------------------------------
Manifest Path:     {"N/A (Dry Run)" if dry_run else "artifacts/seed_manifest.json"}
=========================================
"""
    print(summary)

    return {
        "seed_version": SEED_VERSION,
        "alembic_version": alembic_version,
        "counts": counts,
        "elapsed_ms": elapsed_ms,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GridPilot database seeder.")
    parser.add_argument(
        "--profile", default="demo", help="Seeding dataset profile name (default: 'demo')."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate configurations and stage without committing."
    )
    args = parser.parse_args()

    asyncio.run(run_seed(profile=args.profile, dry_run=args.dry_run))
