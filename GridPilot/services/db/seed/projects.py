"""Seeder handler for Project aggregates."""
from __future__ import annotations

import uuid
from typing import Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

from services.db.models import Project
from services.db.repositories.project import ProjectRepository
from services.db.seed.config_models import ProjectSeedConfig
from services.db.seed.helpers import get_project_id


async def seed_projects(
    session: AsyncSession,
    config_list: List[ProjectSeedConfig],
    region_mapping: Dict[str, uuid.UUID],
    node_mapping: Dict[str, uuid.UUID],
) -> Dict[str, uuid.UUID]:
    """Seed projects from configuration using ProjectRepository.

    Returns a mapping of project name to their derived UUID.
    """
    repo = ProjectRepository(session)
    mapping = {}

    for cfg in config_list:
        derived_id = get_project_id(cfg.name)

        # Retrieve mapped region and node IDs
        # Default to a placeholder if not found (validation checks run separately)
        region_id = region_mapping.get("ERCOT West Zone")
        poi_node_id = node_mapping.get(cfg.poi_node_key)

        if region_id is None:
            # Fallback in case of region config variations
            region_id = list(region_mapping.values())[0]

        if poi_node_id is None:
            raise ValueError(
                f"POI node key '{cfg.poi_node_key}' for project '{cfg.name}' "
                f"not found in seeded grid topology."
            )

        existing = await repo.get_by_id(derived_id)

        if existing is not None:
            # Idempotently update project details
            existing.name = cfg.name
            existing.technology = cfg.technology
            existing.capacity_mw = cfg.capacity_mw
            existing.storage_capacity_mw = cfg.storage_capacity_mw
            existing.region_id = region_id
            existing.poi_node_id = poi_node_id
            existing.aoi_geojson = cfg.aoi_geojson
            existing.status = cfg.status
            existing.submitted_by = cfg.submitted_by
            mapping[cfg.name] = existing.id
        else:
            new_proj = Project(
                id=derived_id,
                region_id=region_id,
                poi_node_id=poi_node_id,
                name=cfg.name,
                technology=cfg.technology,
                capacity_mw=cfg.capacity_mw,
                storage_capacity_mw=cfg.storage_capacity_mw,
                aoi_geojson=cfg.aoi_geojson,
                status=cfg.status,
                submitted_by=cfg.submitted_by,
            )
            await repo.add(new_proj)
            mapping[cfg.name] = derived_id

    return mapping
