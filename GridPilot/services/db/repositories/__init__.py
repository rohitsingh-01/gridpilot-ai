"""Public API for the repository layer.

Import repositories from this package rather than from individual modules::

    from services.db.repositories import (
        UserRepository,
        UtilityRegionRepository,
        ProjectRepository,
        StudyRepository,
        AuditLogRepository,
    )
"""
from services.db.repositories.audit import AuditLogRepository
from services.db.repositories.base import BaseRepository
from services.db.repositories.interfaces import (
    IAuditLogRepository,
    IProjectRepository,
    IStudyRepository,
    IUserRepository,
    IUtilityRegionRepository,
)
from services.db.repositories.project import ProjectRepository
from services.db.repositories.region import UtilityRegionRepository
from services.db.repositories.study import StudyRepository
from services.db.repositories.user import UserRepository

__all__ = [
    # Base
    "BaseRepository",
    # Interfaces
    "IAuditLogRepository",
    "IProjectRepository",
    "IStudyRepository",
    "IUserRepository",
    "IUtilityRegionRepository",
    # Concrete
    "AuditLogRepository",
    "ProjectRepository",
    "StudyRepository",
    "UserRepository",
    "UtilityRegionRepository",
]
