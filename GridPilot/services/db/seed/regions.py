"""Seeder handler for UtilityRegion, GridNode, and GridEdge aggregates."""
from __future__ import annotations

import uuid
from typing import Dict, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from services.db.models import GridEdge, GridNode, UtilityRegion
from services.db.repositories.region import UtilityRegionRepository
from services.db.seed.config_models import RegionSeedConfig, TopologySeedConfig
from services.db.seed.helpers import (
    get_edge_id,
    get_node_id,
    get_region_id,
)


async def seed_regions(
    session: AsyncSession,
    regions_config: List[RegionSeedConfig],
    topology_config: TopologySeedConfig,
) -> Tuple[Dict[str, uuid.UUID], int, int]:
    """Seed regions, nodes, and edges deterministically and return stats.

    Returns:
        (region_id_mapping, nodes_seeded_count, edges_seeded_count)
    """
    repo = UtilityRegionRepository(session)
    region_mapping = {}
    total_nodes = 0
    total_edges = 0

    for reg_cfg in regions_config:
        derived_region_id = get_region_id(reg_cfg.name)
        region = await repo.get_with_network(derived_region_id)

        if region is None:
            # Check by list scan in case of ID mismatch
            existing_regions = await repo.list_regions(limit=100)
            for r in existing_regions:
                if r.name == reg_cfg.name:
                    region = await repo.get_with_network(r.id)
                    break

        if region is None:
            # Create new region with pre-initialized empty collections to avoid lazy-loading
            region = UtilityRegion(
                id=derived_region_id,
                name=reg_cfg.name,
                boundary_geojson=reg_cfg.boundary_geojson,
                nodes=[],
                edges=[],
            )
            await repo.add(region)

        region_mapping[reg_cfg.name] = region.id

        # Track existing nodes by key
        existing_nodes = {node.node_key: node for node in region.nodes}

        # Seed Nodes
        for node_cfg in topology_config.nodes:
            derived_node_id = get_node_id(region.id, node_cfg.node_key)
            if node_cfg.node_key in existing_nodes:
                node = existing_nodes[node_cfg.node_key]
                node.node_type = node_cfg.node_type
                node.voltage_kv = node_cfg.voltage_kv
                node.latitude = node_cfg.latitude
                node.longitude = node_cfg.longitude
                node.thermal_limit_mva = node_cfg.thermal_limit_mva
            else:
                node = GridNode(
                    id=derived_node_id,
                    region_id=region.id,
                    node_key=node_cfg.node_key,
                    node_type=node_cfg.node_type,
                    voltage_kv=node_cfg.voltage_kv,
                    latitude=node_cfg.latitude,
                    longitude=node_cfg.longitude,
                    thermal_limit_mva=node_cfg.thermal_limit_mva,
                )
                region.nodes.append(node)
                existing_nodes[node_cfg.node_key] = node
            total_nodes += 1

        # Flush to ensure node IDs are generated in session for foreign keys
        await session.flush()

        # Track existing edges by deterministic from-to pair key
        existing_edges = {}
        for edge in region.edges:
            # Lookup node keys
            from_node = next((n.node_key for n in region.nodes if n.id == edge.from_node_id), None)
            to_node = next((n.node_key for n in region.nodes if n.id == edge.to_node_id), None)
            if from_node and to_node:
                n1, n2 = sorted([from_node, to_node])
                existing_edges[(n1, n2)] = edge

        # Seed Edges
        for edge_cfg in topology_config.edges:
            n1, n2 = sorted([edge_cfg.from_node, edge_cfg.to_node])
            derived_edge_id = get_edge_id(region.id, n1, n2)

            from_node_obj = existing_nodes.get(edge_cfg.from_node)
            to_node_obj = existing_nodes.get(edge_cfg.to_node)

            if not from_node_obj or not to_node_obj:
                raise ValueError(
                    f"Topology edge refers to missing node: {edge_cfg.from_node} -> {edge_cfg.to_node}"
                )

            if (n1, n2) in existing_edges:
                edge = existing_edges[(n1, n2)]
                edge.edge_type = edge_cfg.edge_type
                edge.reactance_pu = edge_cfg.reactance_pu
                edge.thermal_limit_mva = edge_cfg.thermal_limit_mva
                edge.length_miles = edge_cfg.length_miles
            else:
                edge = GridEdge(
                    id=derived_edge_id,
                    region_id=region.id,
                    from_node_id=from_node_obj.id,
                    to_node_id=to_node_obj.id,
                    edge_type=edge_cfg.edge_type,
                    reactance_pu=edge_cfg.reactance_pu,
                    thermal_limit_mva=edge_cfg.thermal_limit_mva,
                    length_miles=edge_cfg.length_miles,
                )
                region.edges.append(edge)
            total_edges += 1

    # Construct node mapping
    node_mapping = {}
    for region_name, reg_id in region_mapping.items():
        region = await repo.get_with_network(reg_id)
        if region:
            for node in region.nodes:
                node_mapping[node.node_key] = node.id

    return region_mapping, node_mapping, total_nodes, total_edges
