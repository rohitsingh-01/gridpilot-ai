"""
Generic base repository for GridPilot.

Provides shared CRUD primitives parameterised by the SQLAlchemy model
type ``T``.  Concrete repositories inherit from this *and* from the
corresponding interface in ``interfaces.py``.

Transaction rule
----------------
**``session.commit()`` and ``session.rollback()`` must NEVER be called
inside any repository method.**  The session lifecycle is owned by the
service-layer caller (via ``get_db()`` or an explicit context manager).
"""
from __future__ import annotations

import uuid
import logging
from typing import Any, Generic, List, Optional, Type, TypeVar

from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from services.db.exceptions import (
    ConstraintViolationError,
    EntityDuplicateError,
    EntityNotFoundError,
    RepositoryError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Async generic repository backed by SQLAlchemy 2.0.

    Provides the four CRUD primitives shared by every aggregate-root
    repository.  Concrete subclasses extend this class **and** the
    matching interface from ``interfaces.py``.

    Parameters
    ----------
    session : AsyncSession
        The *caller-managed* async session.  This class never commits or
        rolls back.
    model_class : Type[T]
        The SQLAlchemy declarative model this repository manages.

    Notes
    -----
    *   Returned entities remain **session-bound** — lazy-load access to
        relationships will work while the session is open.
    *   Every method calls ``flush()`` (not ``commit()``) so that
        generated IDs are available immediately without finalising the
        transaction.
    """

    def __init__(self, session: AsyncSession, model_class: Type[T]) -> None:
        self._session = session
        self._model_class = model_class

    # -- helpers -----------------------------------------------------------

    def _wrap_db_error(self, exc: Exception) -> RepositoryError:
        """Translate a raw database exception into a repository exception.

        Parameters
        ----------
        exc : Exception
            The original SQLAlchemy or asyncpg exception.

        Returns
        -------
        RepositoryError
            A domain-specific exception suitable for re-raising.
        """
        detail = str(exc)
        if isinstance(exc, IntegrityError):
            lower = detail.lower()
            if "unique" in lower or "duplicate" in lower:
                return EntityDuplicateError(
                    self._model_class.__name__, detail
                )
            return ConstraintViolationError(detail)
        if isinstance(exc, DBAPIError):
            return ConstraintViolationError(detail)
        return RepositoryError(detail)

    # -- CRUD primitives ---------------------------------------------------

    async def get_by_id(self, entity_id: uuid.UUID) -> Optional[T]:
        """Fetch a single entity by its primary key.

        Parameters
        ----------
        entity_id : uuid.UUID
            The UUID primary key of the entity.

        Returns
        -------
        Optional[T]
            The entity if found, otherwise ``None``.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   No eager loading is applied — relationships use the default
            lazy strategy.
        *   The returned entity is session-bound.
        """
        try:
            result = await self._session.execute(
                select(self._model_class).where(
                    self._model_class.id == entity_id  # type: ignore[attr-defined]
                )
            )
            return result.scalar_one_or_none()
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[T]:
        """Return an offset-paginated list of all entities.

        Parameters
        ----------
        limit : int
            Maximum number of rows to return (default ``100``).
        offset : int
            Number of rows to skip (default ``0``).

        Returns
        -------
        List[T]
            A list of session-bound entities.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   No ordering is applied — callers needing deterministic order
            should override this method or use a specialised query.
        *   For high-volume tables, prefer cursor-based pagination.
        """
        try:
            result = await self._session.execute(
                select(self._model_class).offset(offset).limit(limit)
            )
            return list(result.scalars().all())
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def add(self, entity: T) -> T:
        """Stage an entity for insertion.

        The entity is flushed (not committed) so that its server-generated
        ``id`` and ``created_at`` fields are populated immediately.

        Parameters
        ----------
        entity : T
            A fully-constructed model instance.

        Returns
        -------
        T
            The same instance, now with its ``id`` populated.

        Raises
        ------
        EntityDuplicateError
            If a UNIQUE constraint is violated.
        ConstraintViolationError
            If a CHECK, FK, or NOT-NULL constraint is violated.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The entity remains session-bound after return.
        """
        try:
            self._session.add(entity)
            await self._session.flush()
            return entity
        except IntegrityError as exc:
            raise self._wrap_db_error(exc) from exc
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def remove(self, entity_id: uuid.UUID) -> bool:
        """Stage an entity for deletion by its primary key.

        Parameters
        ----------
        entity_id : uuid.UUID
            The UUID primary key of the entity to delete.

        Returns
        -------
        bool
            ``True`` if the entity was found and staged for deletion,
            ``False`` if no entity with the given ID exists.

        Raises
        ------
        ConstraintViolationError
            If a FK constraint prevents deletion.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The entity is first loaded, then passed to ``session.delete()``
            so that cascade rules are honoured.
        """
        entity = await self.get_by_id(entity_id)
        if entity is None:
            return False
        try:
            await self._session.delete(entity)
            await self._session.flush()
            return True
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc
