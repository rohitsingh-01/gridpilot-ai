"""Concrete repository for the Project aggregate.

Aggregate boundary
------------------
``ProjectRepository`` owns the ``Project`` entity.  Child ``Study``
entities are accessible through ``get_with_studies()`` but their
lifecycle is managed by ``StudyRepository``.

The repository provides an **optimistic concurrency** mechanism for
status transitions to prevent lost-update race conditions.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.db.exceptions import ConcurrencyError, EntityNotFoundError
from services.db.models import Project
from services.db.repositories.base import BaseRepository
from services.db.repositories.interfaces import IProjectRepository


class ProjectRepository(BaseRepository[Project], IProjectRepository):
    """Manages persistence for the ``Project`` aggregate root.

    Transaction expectations
    ------------------------
    *   All methods call ``flush()`` only — never ``commit()``.
    *   The caller (service layer / ``get_db()``) owns the transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Project)

    async def get_with_studies(
        self, project_id: uuid.UUID
    ) -> Optional[Project]:
        """Return a project with its studies eagerly loaded.

        Parameters
        ----------
        project_id : uuid.UUID
            The UUID primary key of the project.

        Returns
        -------
        Optional[Project]
            The project with ``studies`` populated via ``selectinload``,
            or ``None`` if not found.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   Eager loading: ``Project.studies`` is loaded in one
            additional ``SELECT … WHERE project_id IN (…)`` query.
        *   The returned entity is session-bound.
        """
        try:
            result = await self._session.execute(
                select(Project)
                .where(Project.id == project_id)
                .options(selectinload(Project.studies))
            )
            return result.scalar_one_or_none()
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def list_by_status(
        self, status: str, limit: int = 50, offset: int = 0
    ) -> List[Project]:
        """Return projects filtered by status with offset pagination.

        Parameters
        ----------
        status : str
            One of: ``submitted``, ``in_study``, ``pending_review``,
            ``approved``, ``rejected``.
        limit : int
            Maximum number of rows to return (default ``50``).
        offset : int
            Number of rows to skip (default ``0``).

        Returns
        -------
        List[Project]
            Projects ordered by ``created_at DESC``.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   Uses the ``idx_projects_status`` index for efficient filtering.
        *   No eager loading — child collections are not populated.
        """
        try:
            result = await self._session.execute(
                select(Project)
                .where(Project.status == status)
                .order_by(Project.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def update_status(
        self,
        project_id: uuid.UUID,
        current_status: str,
        new_status: str,
    ) -> Project:
        """Optimistic status transition.

        Issues ``UPDATE … WHERE id = :id AND status = :current`` so that
        a concurrent modification causes zero rows updated, which we
        translate into a ``ConcurrencyError``.

        Parameters
        ----------
        project_id : uuid.UUID
            The UUID primary key of the project.
        current_status : str
            The expected current status (optimistic guard).
        new_status : str
            The target status to transition to.

        Returns
        -------
        Project
            The refreshed project entity after the transition.

        Raises
        ------
        EntityNotFoundError
            If no project with ``project_id`` exists.
        ConcurrencyError
            If the current status does not match ``current_status``
            (another transaction modified it).
        ConstraintViolationError
            If ``new_status`` violates the CHECK constraint.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound and re-fetched after
            the update.
        """
        try:
            result = await self._session.execute(
                update(Project)
                .where(
                    Project.id == project_id,
                    Project.status == current_status,
                )
                .values(status=new_status)
                .returning(Project.id)
            )
            row = result.scalar_one_or_none()
            if row is None:
                # Either the entity doesn't exist or the status guard failed
                existing = await self.get_by_id(project_id)
                if existing is None:
                    raise EntityNotFoundError("Project", project_id)
                raise ConcurrencyError("Project", project_id)
            await self._session.flush()
            # Re-fetch the refreshed entity
            return await self.get_by_id(project_id)  # type: ignore[return-value]
        except (ConcurrencyError, EntityNotFoundError):
            raise
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    # -- Projection / read-model -------------------------------------------

    async def get_project_summary(
        self, project_id: uuid.UUID
    ) -> Optional[Dict[str, Any]]:
        """Lightweight projection returning only id, name, and status.

        Parameters
        ----------
        project_id : uuid.UUID
            The UUID primary key of the project.

        Returns
        -------
        Optional[Dict[str, Any]]
            A dictionary with keys ``id``, ``name``, ``status``,
            or ``None`` if the project does not exist.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   This is a **projection query** — it selects only three
            columns rather than loading the full ORM entity.
        *   The returned dictionary is **not** session-bound.
        """
        try:
            result = await self._session.execute(
                select(Project.id, Project.name, Project.status).where(
                    Project.id == project_id
                )
            )
            row = result.first()
            if row is None:
                return None
            return {"id": row.id, "name": row.name, "status": row.status}
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc
