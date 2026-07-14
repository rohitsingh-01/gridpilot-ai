"""Concrete repository for the immutable AuditLog table.

Aggregate boundary
------------------
``AuditLogRepository`` owns the ``AuditLog`` entity exclusively.

The AuditLog is **append-only**:

*   ``create_log()`` inserts new rows.
*   ``remove()`` is **not** exposed — audit rows must never be deleted.
*   ``update()`` is **not** exposed — audit rows must never be modified.
*   A PostgreSQL trigger (``trg_prevent_audit_log_modify``) enforces
    immutability at the database level.

This repository also provides **cursor-based pagination** for
high-volume audit streams, avoiding the performance degradation of
``OFFSET`` on ever-growing tables.

Design note
-----------
This class does **not** inherit from ``BaseRepository`` because:

*   ``remove()`` must be forbidden at the type level.
*   ``list_all()`` with offset pagination is inappropriate for an
    ever-growing table — cursor pagination is provided instead.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from services.db.models import AuditLog
from services.db.repositories.interfaces import IAuditLogRepository


class AuditLogRepository(IAuditLogRepository):
    """Append-only repository for ``AuditLog``.

    Transaction expectations
    ------------------------
    *   All methods call ``flush()`` only — never ``commit()``.
    *   The caller (service layer / ``get_db()``) owns the transaction.

    Immutability guarantee
    ----------------------
    *   No ``remove()`` method exists on this class.
    *   No ``update()`` method exists on this class.
    *   The PostgreSQL trigger ``trg_prevent_audit_log_modify`` blocks
        ``UPDATE`` and ``DELETE`` at the database level.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_log(
        self,
        actor_type: str,
        actor_name: str,
        action: str,
        detail_json: Dict[str, Any],
        study_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
    ) -> AuditLog:
        """Create and stage a new audit log entry.

        Parameters
        ----------
        actor_type : str
            One of: ``agent``, ``orchestrator``, ``human``, ``system``.
        actor_name : str
            Identifier of the actor (e.g. ``"power_flow"``).
        action : str
            The action being recorded (e.g. ``"study.started"``).
        detail_json : Dict[str, Any]
            Arbitrary JSON payload with action-specific details.
        study_id : Optional[uuid.UUID]
            FK to the related study, if applicable.
        project_id : Optional[uuid.UUID]
            FK to the related project, if applicable.

        Returns
        -------
        AuditLog
            The newly created log entry with its ``id`` populated.

        Raises
        ------
        EntityDuplicateError
            If a UNIQUE constraint is violated (unlikely for audit logs).
        ConstraintViolationError
            If ``actor_type`` violates the CHECK constraint, or if FKs
            are invalid.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound.
        """
        log = AuditLog(
            actor_type=actor_type,
            actor_name=actor_name,
            action=action,
            detail_json=detail_json,
            study_id=study_id,
            project_id=project_id,
        )
        try:
            self._session.add(log)
            await self._session.flush()
            return log
        except IntegrityError as exc:
            from services.db.exceptions import EntityDuplicateError
            raise EntityDuplicateError("AuditLog", str(exc)) from exc
        except DBAPIError as exc:
            from services.db.exceptions import ConstraintViolationError
            raise ConstraintViolationError(str(exc)) from exc

    # -- Offset pagination (simple) ----------------------------------------

    async def list_logs_for_study(
        self, study_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> List[AuditLog]:
        """Return audit entries for a study with basic offset pagination.

        Parameters
        ----------
        study_id : uuid.UUID
            The UUID of the study to filter by.
        limit : int
            Maximum number of rows to return (default ``100``).
        offset : int
            Number of rows to skip (default ``0``).

        Returns
        -------
        List[AuditLog]
            Audit entries ordered by ``created_at DESC``.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   Uses the ``idx_audit_log_study_id`` index for filtering.
        *   For high-volume studies, prefer ``list_logs_cursor()`` to
            avoid ``OFFSET`` performance degradation.
        *   The returned entities are session-bound.
        """
        try:
            result = await self._session.execute(
                select(AuditLog)
                .where(AuditLog.study_id == study_id)
                .order_by(AuditLog.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().all())
        except DBAPIError as exc:
            from services.db.exceptions import RepositoryError
            raise RepositoryError(str(exc)) from exc

    # -- Cursor-based seek pagination (high-volume) ------------------------

    async def list_logs_cursor(
        self,
        study_id: uuid.UUID,
        limit: int = 50,
        cursor_time: Optional[datetime] = None,
        cursor_id: Optional[uuid.UUID] = None,
    ) -> List[AuditLog]:
        """Cursor-based seek pagination for high-volume audit streams.

        Uses ``(created_at, id)`` as the compound cursor to guarantee
        deterministic ordering even when multiple rows share the same
        timestamp.

        Parameters
        ----------
        study_id : uuid.UUID
            The UUID of the study to filter by.
        limit : int
            Maximum number of rows to return (default ``50``).
        cursor_time : Optional[datetime]
            The ``created_at`` value of the **last** item from the
            previous page.  Pass ``None`` for the first page.
        cursor_id : Optional[uuid.UUID]
            The ``id`` value of the **last** item from the previous
            page.  Pass ``None`` for the first page.

        Returns
        -------
        List[AuditLog]
            Audit entries ordered by ``created_at DESC, id DESC``.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   Cursor pagination performs **O(1)** per page regardless of
            table size, compared to ``OFFSET`` which is **O(offset + limit)**.
        *   Both ``cursor_time`` and ``cursor_id`` must be provided
            together; if either is ``None``, the first page is returned.
        *   The returned entities are session-bound.
        """
        stmt = select(AuditLog).where(AuditLog.study_id == study_id)

        if cursor_time is not None and cursor_id is not None:
            stmt = stmt.where(
                (AuditLog.created_at < cursor_time)
                | (
                    (AuditLog.created_at == cursor_time)
                    & (AuditLog.id < cursor_id)
                )
            )

        stmt = stmt.order_by(
            AuditLog.created_at.desc(), AuditLog.id.desc()
        ).limit(limit)

        try:
            result = await self._session.execute(stmt)
            return list(result.scalars().all())
        except DBAPIError as exc:
            from services.db.exceptions import RepositoryError
            raise RepositoryError(str(exc)) from exc
