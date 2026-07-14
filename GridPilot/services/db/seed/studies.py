"""Seeder handler for Study aggregates."""
from __future__ import annotations

import uuid
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession

from services.db.models import Study
from services.db.repositories.study import StudyRepository
from services.db.seed.helpers import get_study_id


async def seed_studies(
    session: AsyncSession, project_mapping: Dict[str, uuid.UUID]
) -> int:
    """Seed initial running studies for all seeded projects using StudyRepository.

    Returns the count of studies seeded.
    """
    repo = StudyRepository(session)
    seeded_count = 0

    for proj_name, proj_id in project_mapping.items():
        derived_id = get_study_id(proj_id)
        existing = await repo.get_by_id(derived_id)

        if existing is not None:
            # Idempotently reset study status and clear state snapshot
            existing.status = "running"
            existing.state_snapshot = {}
            existing.overall_confidence = None
            existing.study_document_json = None
            existing.pdf_oss_key = None
            existing.completed_at = None
        else:
            new_study = Study(
                id=derived_id,
                project_id=proj_id,
                status="running",
                state_snapshot={},
            )
            await repo.add(new_study)

        seeded_count += 1

    return seeded_count
