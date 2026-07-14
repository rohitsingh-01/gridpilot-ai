"""Concrete repository for the UtilityRegion / GridNode / GridEdge aggregate.

Aggregate boundary
------------------
``UtilityRegionRepository`` owns the ``UtilityRegion`` entity and its
child ``GridNode`` / ``GridEdge`` entities that form the synthetic grid
topology.  All topology lookups are accessed through this single
repository.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.db.models import UtilityRegion, GridNode
from services.db.repositories.base import BaseRepository
from services.db.repositories.interfaces import IUtilityRegionRepository


class UtilityRegionRepository(BaseRepository[UtilityRegion], IUtilityRegionRepository):
    """Manages persistence for ``UtilityRegion`` and its child
    ``GridNode`` / ``GridEdge`` entities.

    Transaction expectations
    ------------------------
    *   All methods call ``flush()`` only — never ``commit()``.
    *   The caller (service layer / ``get_db()``) owns the transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UtilityRegion)

    async def get_with_network(
        self, region_id: uuid.UUID
    ) -> Optional[UtilityRegion]:
        """Eagerly load nodes and edges for the given region.

        Parameters
        ----------
        region_id : uuid.UUID
            The UUID primary key of the region.

        Returns
        -------
        Optional[UtilityRegion]
            The region with ``nodes`` and ``edges`` collections populated
            (via ``selectinload``), or ``None`` if not found.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   Eager loading: ``UtilityRegion.nodes`` and
            ``UtilityRegion.edges`` are loaded in two additional
            ``SELECT … WHERE region_id IN (…)`` queries.
        *   The returned entity is session-bound.
        """
        try:
            result = await self._session.execute(
                select(UtilityRegion)
                .where(UtilityRegion.id == region_id)
                .options(
                    selectinload(UtilityRegion.nodes),
                    selectinload(UtilityRegion.edges),
                )
            )
            return result.scalar_one_or_none()
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def get_node_by_key(
        self, region_id: uuid.UUID, node_key: str
    ) -> Optional[GridNode]:
        """Find a single grid node by its composite natural key.

        Parameters
        ----------
        region_id : uuid.UUID
            The UUID of the region the node belongs to.
        node_key : str
            The unique node identifier within the region (e.g. ``"SUB_1"``).

        Returns
        -------
        Optional[GridNode]
            The matching node, or ``None``.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   Uses the UNIQUE constraint ``uq_grid_nodes_region_node`` for
            efficient lookup.
        *   No eager loading — the returned node is session-bound.
        """
        try:
            result = await self._session.execute(
                select(GridNode).where(
                    GridNode.region_id == region_id,
                    GridNode.node_key == node_key,
                )
            )
            return result.scalar_one_or_none()
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def list_regions(
        self, limit: int = 100, offset: int = 0
    ) -> List[UtilityRegion]:
        """Return a paginated list of regions without child collections.

        Parameters
        ----------
        limit : int
            Maximum number of rows to return (default ``100``).
        offset : int
            Number of rows to skip (default ``0``).

        Returns
        -------
        List[UtilityRegion]
            A list of session-bound region entities (no nodes or edges).

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   Delegates to ``BaseRepository.list_all()``.
        *   No eager loading — child collections are not populated.
        """
        return await self.list_all(limit=limit, offset=offset)
