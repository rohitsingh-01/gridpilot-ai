"""Seeder handler for User aggregates."""
from __future__ import annotations

import uuid
from typing import Dict, List
from sqlalchemy.ext.asyncio import AsyncSession

from services.db.models import User
from services.db.repositories.user import UserRepository
from services.db.seed.config_models import UserSeedConfig
from services.db.seed.helpers import get_user_id


async def seed_users(
    session: AsyncSession, config_list: List[UserSeedConfig]
) -> Dict[str, uuid.UUID]:
    """Seed users from configuration using the UserRepository.

    Returns a mapping of user email to their derived UUID.
    """
    repo = UserRepository(session)
    mapping = {}

    for cfg in config_list:
        derived_id = get_user_id(cfg.email)
        existing = await repo.get_by_id(derived_id)
        if existing is None:
            existing = await repo.get_by_email(cfg.email)

        if existing is not None:
            # Update details if changed
            existing.display_name = cfg.display_name
            existing.role = cfg.role
            existing.password_hash = cfg.password_hash
            mapping[cfg.email] = existing.id
        else:
            new_user = User(
                id=derived_id,
                email=cfg.email,
                display_name=cfg.display_name,
                role=cfg.role,
                password_hash=cfg.password_hash,
            )
            await repo.add(new_user)
            mapping[cfg.email] = derived_id

    return mapping
