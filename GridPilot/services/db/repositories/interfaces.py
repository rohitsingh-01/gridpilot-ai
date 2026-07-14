"""
Abstract repository interfaces for GridPilot.

These ABCs define the contracts that application services, agents, and
API layers depend on.  Concrete implementations live in the sibling
modules and are the *only* classes that touch SQLAlchemy.

Design rules
------------
* Interfaces never reference ``AsyncSession``, ``select()``, or any
  other SQLAlchemy construct.
* All methods are ``async``.
* No method may call ``session.commit()`` or ``session.rollback()``.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Generic read helpers shared by every aggregate-root repository
# ---------------------------------------------------------------------------

class IBaseRepository(ABC):
    """Minimal contract every repository exposes."""

    @abstractmethod
    async def get_by_id(self, entity_id: uuid.UUID) -> Optional[Any]:
        """Return a single entity by primary-key, or ``None``."""
        ...

    @abstractmethod
    async def add(self, entity: Any) -> Any:
        """Stage an entity for insertion (no commit)."""
        ...

    @abstractmethod
    async def remove(self, entity_id: uuid.UUID) -> bool:
        """Stage an entity for deletion.  Returns ``True`` if found."""
        ...


# ---------------------------------------------------------------------------
# User aggregate
# ---------------------------------------------------------------------------

class IUserRepository(IBaseRepository):
    """Persistence contract for the User / Session aggregate."""

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[Any]:
        ...

    @abstractmethod
    async def create_session(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> Any:
        ...

    @abstractmethod
    async def get_session_by_token(self, token_hash: str) -> Optional[Any]:
        ...

    @abstractmethod
    async def delete_expired_sessions(self) -> int:
        """Remove all expired sessions.  Returns count deleted."""
        ...


# ---------------------------------------------------------------------------
# UtilityRegion aggregate
# ---------------------------------------------------------------------------

class IUtilityRegionRepository(IBaseRepository):
    """Persistence contract for the UtilityRegion / GridNode / GridEdge aggregate."""

    @abstractmethod
    async def get_with_network(self, region_id: uuid.UUID) -> Optional[Any]:
        """Eagerly load nodes and edges."""
        ...

    @abstractmethod
    async def get_node_by_key(
        self, region_id: uuid.UUID, node_key: str
    ) -> Optional[Any]:
        ...

    @abstractmethod
    async def list_regions(
        self, limit: int = 100, offset: int = 0
    ) -> List[Any]:
        ...


# ---------------------------------------------------------------------------
# Project aggregate
# ---------------------------------------------------------------------------

class IProjectRepository(IBaseRepository):
    """Persistence contract for the Project aggregate."""

    @abstractmethod
    async def get_with_studies(self, project_id: uuid.UUID) -> Optional[Any]:
        ...

    @abstractmethod
    async def list_by_status(
        self, status: str, limit: int = 50, offset: int = 0
    ) -> List[Any]:
        ...

    @abstractmethod
    async def update_status(
        self,
        project_id: uuid.UUID,
        current_status: str,
        new_status: str,
    ) -> Any:
        """Optimistic status transition.  Raises ``ConcurrencyError`` on conflict."""
        ...

    @abstractmethod
    async def get_project_summary(
        self, project_id: uuid.UUID
    ) -> Optional[Dict[str, Any]]:
        """Lightweight projection returning id, name, status only."""
        ...


# ---------------------------------------------------------------------------
# Study aggregate  (richest — manages 8 child entity types)
# ---------------------------------------------------------------------------

class IStudyRepository(IBaseRepository):
    """Persistence contract for the Study aggregate and all its children."""

    @abstractmethod
    async def get_full_study_state(self, study_id: uuid.UUID) -> Optional[Any]:
        """Eagerly load every child collection."""
        ...

    # -- Agent runs --------------------------------------------------------
    @abstractmethod
    async def add_agent_run(
        self,
        study_id: uuid.UUID,
        agent_name: str,
        input_json: Dict[str, Any],
        status: str,
    ) -> Any:
        ...

    @abstractmethod
    async def update_agent_run(
        self,
        run_id: uuid.UUID,
        status: str,
        output_json: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        confidence: Optional[float] = None,
        duration_ms: Optional[int] = None,
    ) -> Any:
        ...

    # -- Read-model results ------------------------------------------------
    @abstractmethod
    async def save_power_flow_result(
        self,
        study_id: uuid.UUID,
        scenarios_run: int,
        violation_probability: float,
        raw_results_json: Dict[str, Any],
        worst_case_line_id: Optional[uuid.UUID] = None,
        worst_case_loading_pct: Optional[float] = None,
        worst_case_bus_voltage_pu: Optional[float] = None,
    ) -> Any:
        ...

    @abstractmethod
    async def save_cost_allocation_result(
        self,
        study_id: uuid.UUID,
        total_estimated_cost_usd: float,
        upgrades_json: Dict[str, Any],
    ) -> Any:
        ...

    @abstractmethod
    async def add_environmental_flag(
        self,
        study_id: uuid.UUID,
        flag_type: str,
        severity: str,
        description: str,
        source_dataset: str,
        distance_m: Optional[float] = None,
        geometry_geojson: Optional[Dict[str, Any]] = None,
    ) -> Any:
        ...

    @abstractmethod
    async def add_regulatory_citation(
        self,
        study_id: uuid.UUID,
        section_name: str,
        citation_text: str,
        source_document: str,
        chroma_chunk_id: str,
    ) -> Any:
        ...

    @abstractmethod
    async def add_human_review(
        self,
        study_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        decision: str,
        comment: Optional[str] = None,
        affected_section: Optional[str] = None,
    ) -> Any:
        ...

    @abstractmethod
    async def add_document(
        self,
        study_id: uuid.UUID,
        doc_type: str,
        oss_key: str,
        content_type: str,
        size_bytes: Optional[int] = None,
    ) -> Any:
        ...

    # -- Bulk operations ---------------------------------------------------
    @abstractmethod
    async def bulk_add_environmental_flags(
        self,
        study_id: uuid.UUID,
        flags: List[Dict[str, Any]],
    ) -> int:
        """Insert many flags in a single round-trip.  Returns count inserted."""
        ...


# ---------------------------------------------------------------------------
# AuditLog (append-only aggregate)
# ---------------------------------------------------------------------------

class IAuditLogRepository(ABC):
    """Persistence contract for the immutable AuditLog table.

    ``remove`` is deliberately absent — audit logs cannot be deleted.
    """

    @abstractmethod
    async def create_log(
        self,
        actor_type: str,
        actor_name: str,
        action: str,
        detail_json: Dict[str, Any],
        study_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
    ) -> Any:
        ...

    @abstractmethod
    async def list_logs_for_study(
        self, study_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> List[Any]:
        ...

    @abstractmethod
    async def list_logs_cursor(
        self,
        study_id: uuid.UUID,
        limit: int = 50,
        cursor_time: Optional[datetime] = None,
        cursor_id: Optional[uuid.UUID] = None,
    ) -> List[Any]:
        """Cursor-based seek pagination for high-volume audit streams."""
        ...
