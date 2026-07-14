"""Concrete repository for the User / Session aggregate.

Aggregate boundary
------------------
``UserRepository`` owns both the ``User`` entity and its child
``Session`` (authentication token) entities.  All session-token
operations are accessed through this single repository.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, delete, func
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.db.models import User, Session
from services.db.repositories.base import BaseRepository
from services.db.repositories.interfaces import IUserRepository


class UserRepository(BaseRepository[User], IUserRepository):
    """Manages persistence for ``User`` and its child ``Session`` entities.

    Transaction expectations
    ------------------------
    *   All methods call ``flush()`` only — never ``commit()``.
    *   The caller (service layer / ``get_db()``) owns the transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, User)

    # -- User queries ------------------------------------------------------

    async def get_by_email(self, email: str) -> Optional[User]:
        """Return a user by their unique email address.

        Parameters
        ----------
        email : str
            The email address to look up (case-sensitive).

        Returns
        -------
        Optional[User]
            The matching ``User`` entity, or ``None`` if not found.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   No eager loading — relationships use the default lazy strategy.
        *   The returned entity is session-bound.
        """
        try:
            result = await self._session.execute(
                select(User).where(User.email == email)
            )
            return result.scalar_one_or_none()
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    # -- Session (child entity) management ---------------------------------

    async def create_session(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> Session:
        """Create and stage a new authentication session for a user.

        Parameters
        ----------
        user_id : uuid.UUID
            FK to the owning ``User``.
        token_hash : str
            A pre-hashed session token (never store plaintext tokens).
        expires_at : datetime
            The expiration timestamp for this session (timezone-aware).

        Returns
        -------
        Session
            The newly created ``Session`` entity with its ``id`` populated.

        Raises
        ------
        EntityDuplicateError
            If the ``token_hash`` already exists (UNIQUE violation).
        ConstraintViolationError
            If the ``user_id`` FK is invalid.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound.
        """
        sess = Session(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        try:
            self._session.add(sess)
            await self._session.flush()
            return sess
        except IntegrityError as exc:
            raise self._wrap_db_error(exc) from exc
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def get_session_by_token(self, token_hash: str) -> Optional[Session]:
        """Look up a session by its hashed token value.

        Parameters
        ----------
        token_hash : str
            The hashed token to search for.

        Returns
        -------
        Optional[Session]
            The matching ``Session`` with its ``user`` relationship
            **eagerly loaded** via ``selectinload``, or ``None``.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   Eager loading: ``Session.user`` is loaded in the same query.
        *   The returned entity is session-bound.
        """
        try:
            result = await self._session.execute(
                select(Session)
                .where(Session.token_hash == token_hash)
                .options(selectinload(Session.user))
            )
            return result.scalar_one_or_none()
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def delete_expired_sessions(self) -> int:
        """Delete all sessions whose ``expires_at`` is in the past.

        Returns
        -------
        int
            The number of rows deleted.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   Uses ``DELETE … WHERE expires_at < now()`` — a single
            round-trip bulk delete.
        *   Does **not** call ``session.commit()``.
        """
        try:
            result = await self._session.execute(
                delete(Session).where(
                    Session.expires_at < func.now()
                )
            )
            await self._session.flush()
            return result.rowcount  # type: ignore[return-value]
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc
