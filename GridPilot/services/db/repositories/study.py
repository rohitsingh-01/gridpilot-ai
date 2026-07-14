"""Concrete repository for the Study aggregate (richest aggregate root).

Aggregate boundary
------------------
``StudyRepository`` owns the ``Study`` entity and manages persistence
for its 8 child entity types:

*   ``AgentRun``
*   ``PowerFlowResult``
*   ``CostAllocationResult``
*   ``EnvironmentalFlag``
*   ``RegulatoryCitation``
*   ``HumanReview``
*   ``Document``
*   ``AuditLog`` (read-only via ``get_full_study_state`` — writes
    are handled by ``AuditLogRepository``)

This is the richest aggregate in the system because a single study
execution produces outputs from every agent in the swarm.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.db.exceptions import EntityNotFoundError
from services.db.models import (
    AgentRun,
    CostAllocationResult,
    Document,
    EnvironmentalFlag,
    HumanReview,
    PowerFlowResult,
    RegulatoryCitation,
    Study,
)
from services.db.repositories.base import BaseRepository
from services.db.repositories.interfaces import IStudyRepository


class StudyRepository(BaseRepository[Study], IStudyRepository):
    """Manages persistence for the ``Study`` aggregate and its 8 child types.

    Transaction expectations
    ------------------------
    *   All methods call ``flush()`` only — never ``commit()``.
    *   The caller (service layer / ``get_db()``) owns the transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Study)

    # -- Eager-load helpers ------------------------------------------------

    async def get_full_study_state(
        self, study_id: uuid.UUID
    ) -> Optional[Study]:
        """Eagerly load every child collection on a study.

        Parameters
        ----------
        study_id : uuid.UUID
            The UUID primary key of the study.

        Returns
        -------
        Optional[Study]
            The study with **all** child collections populated via
            ``selectinload``, or ``None`` if not found.

        Raises
        ------
        RepositoryError
            On any unexpected database error.

        Notes
        -----
        *   Eager loading: 7 ``selectinload`` options issue one
            ``SELECT … WHERE study_id IN (…)`` per child table.
        *   Use this method when you need the complete study state
            (e.g. for the orchestrator agent or PDF generation).
        *   The returned entity is session-bound.
        """
        try:
            result = await self._session.execute(
                select(Study)
                .where(Study.id == study_id)
                .options(
                    selectinload(Study.agent_runs),
                    selectinload(Study.power_flow_results),
                    selectinload(Study.cost_allocation_results),
                    selectinload(Study.environmental_flags),
                    selectinload(Study.regulatory_citations),
                    selectinload(Study.human_reviews),
                    selectinload(Study.documents),
                )
            )
            return result.scalar_one_or_none()
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    # -- Agent runs --------------------------------------------------------

    async def add_agent_run(
        self,
        study_id: uuid.UUID,
        agent_name: str,
        input_json: Dict[str, Any],
        status: str,
    ) -> AgentRun:
        """Create and stage a new agent run record.

        Parameters
        ----------
        study_id : uuid.UUID
            FK to the parent study.
        agent_name : str
            One of: ``site_intelligence``, ``environmental_permit``,
            ``power_flow``, ``cost_allocation``, ``regulatory``,
            ``orchestrator``.
        input_json : Dict[str, Any]
            The serialised input payload sent to the agent.
        status : str
            Initial status — typically ``"running"``.

        Returns
        -------
        AgentRun
            The newly created agent run with its ``id`` populated.

        Raises
        ------
        ConstraintViolationError
            If ``agent_name`` or ``status`` violates a CHECK constraint,
            or if ``study_id`` is an invalid FK.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound.
        """
        run = AgentRun(
            study_id=study_id,
            agent_name=agent_name,
            input_json=input_json,
            status=status,
        )
        try:
            self._session.add(run)
            await self._session.flush()
            return run
        except IntegrityError as exc:
            raise self._wrap_db_error(exc) from exc
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def update_agent_run(
        self,
        run_id: uuid.UUID,
        status: str,
        output_json: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        confidence: Optional[float] = None,
        duration_ms: Optional[int] = None,
    ) -> AgentRun:
        """Update an existing agent run with completion data.

        Parameters
        ----------
        run_id : uuid.UUID
            The UUID primary key of the agent run.
        status : str
            New status (e.g. ``"succeeded"``, ``"failed"``, ``"escalated"``).
        output_json : Optional[Dict[str, Any]]
            Serialised output from the agent (set on success).
        error_message : Optional[str]
            Error description (set on failure).
        confidence : Optional[float]
            Agent confidence score, range ``[0.000, 1.000]``.
        duration_ms : Optional[int]
            Wall-clock execution time in milliseconds.

        Returns
        -------
        AgentRun
            The updated agent run entity.

        Raises
        ------
        EntityNotFoundError
            If no agent run with ``run_id`` exists.
        ConstraintViolationError
            If ``status`` violates a CHECK constraint.

        Notes
        -----
        *   Only non-``None`` optional parameters are written.
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound.
        """
        try:
            result = await self._session.execute(
                select(AgentRun).where(AgentRun.id == run_id)
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise EntityNotFoundError("AgentRun", run_id)
            run.status = status
            if output_json is not None:
                run.output_json = output_json
            if error_message is not None:
                run.error_message = error_message
            if confidence is not None:
                run.confidence = confidence
            if duration_ms is not None:
                run.duration_ms = duration_ms
            await self._session.flush()
            return run
        except EntityNotFoundError:
            raise
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    # -- Power flow --------------------------------------------------------

    async def save_power_flow_result(
        self,
        study_id: uuid.UUID,
        scenarios_run: int,
        violation_probability: float,
        raw_results_json: Dict[str, Any],
        worst_case_line_id: Optional[uuid.UUID] = None,
        worst_case_loading_pct: Optional[float] = None,
        worst_case_bus_voltage_pu: Optional[float] = None,
    ) -> PowerFlowResult:
        """Persist the denormalised result of a power flow analysis.

        Parameters
        ----------
        study_id : uuid.UUID
            FK to the parent study.
        scenarios_run : int
            Number of Monte-Carlo or contingency scenarios executed.
        violation_probability : float
            Probability of a thermal or voltage violation, ``[0.000, 1.000]``.
        raw_results_json : Dict[str, Any]
            Full JSON blob of scenario-level results.
        worst_case_line_id : Optional[uuid.UUID]
            FK to the ``GridEdge`` with the worst loading.
        worst_case_loading_pct : Optional[float]
            Peak loading percentage on the worst-case line.
        worst_case_bus_voltage_pu : Optional[float]
            Worst-case bus voltage in per-unit.

        Returns
        -------
        PowerFlowResult
            The newly created entity.

        Raises
        ------
        ConstraintViolationError
            If FKs are invalid.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound.
        """
        entity = PowerFlowResult(
            study_id=study_id,
            scenarios_run=scenarios_run,
            violation_probability=violation_probability,
            raw_results_json=raw_results_json,
            worst_case_line_id=worst_case_line_id,
            worst_case_loading_pct=worst_case_loading_pct,
            worst_case_bus_voltage_pu=worst_case_bus_voltage_pu,
        )
        try:
            self._session.add(entity)
            await self._session.flush()
            return entity
        except IntegrityError as exc:
            raise self._wrap_db_error(exc) from exc
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    # -- Cost allocation ---------------------------------------------------

    async def save_cost_allocation_result(
        self,
        study_id: uuid.UUID,
        total_estimated_cost_usd: float,
        upgrades_json: Dict[str, Any],
    ) -> CostAllocationResult:
        """Persist the denormalised result of cost allocation analysis.

        Parameters
        ----------
        study_id : uuid.UUID
            FK to the parent study.
        total_estimated_cost_usd : float
            Total estimated interconnection cost in USD.
        upgrades_json : Dict[str, Any]
            Itemised breakdown of required grid upgrades.

        Returns
        -------
        CostAllocationResult
            The newly created entity.

        Raises
        ------
        ConstraintViolationError
            If ``study_id`` is an invalid FK.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound.
        """
        entity = CostAllocationResult(
            study_id=study_id,
            total_estimated_cost_usd=total_estimated_cost_usd,
            upgrades_json=upgrades_json,
        )
        try:
            self._session.add(entity)
            await self._session.flush()
            return entity
        except IntegrityError as exc:
            raise self._wrap_db_error(exc) from exc
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    # -- Environmental flags -----------------------------------------------

    async def add_environmental_flag(
        self,
        study_id: uuid.UUID,
        flag_type: str,
        severity: str,
        description: str,
        source_dataset: str,
        distance_m: Optional[float] = None,
        geometry_geojson: Optional[Dict[str, Any]] = None,
    ) -> EnvironmentalFlag:
        """Add a single environmental conflict flag to a study.

        Parameters
        ----------
        study_id : uuid.UUID
            FK to the parent study.
        flag_type : str
            One of: ``wetland``, ``habitat``, ``other``.
        severity : str
            One of: ``info``, ``review_required``, ``blocking``.
        description : str
            Human-readable description of the conflict.
        source_dataset : str
            Name of the GIS dataset that detected the conflict.
        distance_m : Optional[float]
            Distance to the project boundary in metres.
        geometry_geojson : Optional[Dict[str, Any]]
            GeoJSON geometry of the conflicting feature.

        Returns
        -------
        EnvironmentalFlag
            The newly created entity.

        Raises
        ------
        ConstraintViolationError
            If ``flag_type`` or ``severity`` violates a CHECK constraint.

        Notes
        -----
        *   For inserting many flags at once, prefer
            ``bulk_add_environmental_flags()``.
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound.
        """
        entity = EnvironmentalFlag(
            study_id=study_id,
            flag_type=flag_type,
            severity=severity,
            description=description,
            source_dataset=source_dataset,
            distance_m=distance_m,
            geometry_geojson=geometry_geojson,
        )
        try:
            self._session.add(entity)
            await self._session.flush()
            return entity
        except IntegrityError as exc:
            raise self._wrap_db_error(exc) from exc
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    async def bulk_add_environmental_flags(
        self,
        study_id: uuid.UUID,
        flags: List[Dict[str, Any]],
    ) -> int:
        """Bulk-insert environmental flags in a single database round-trip.

        Parameters
        ----------
        study_id : uuid.UUID
            FK to the parent study.  Injected into every row.
        flags : List[Dict[str, Any]]
            List of dictionaries matching ``EnvironmentalFlag`` columns.
            Required keys: ``flag_type``, ``severity``, ``description``,
            ``source_dataset``.

        Returns
        -------
        int
            Number of rows inserted.  Returns ``0`` if ``flags`` is empty.

        Raises
        ------
        ConstraintViolationError
            If any flag violates a CHECK or FK constraint.

        Notes
        -----
        *   Uses ``INSERT … VALUES (…), (…), …`` via
            ``session.execute(insert(Model), payload)``.
        *   UUIDs are auto-generated for each row if not provided.
        *   Does **not** call ``session.commit()``.
        """
        if not flags:
            return 0
        payload = [
            {**f, "study_id": study_id, "id": f.get("id", uuid.uuid4())}
            for f in flags
        ]
        try:
            await self._session.execute(insert(EnvironmentalFlag), payload)
            await self._session.flush()
            return len(payload)
        except IntegrityError as exc:
            raise self._wrap_db_error(exc) from exc
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    # -- Regulatory citations ----------------------------------------------

    async def add_regulatory_citation(
        self,
        study_id: uuid.UUID,
        section_name: str,
        citation_text: str,
        source_document: str,
        chroma_chunk_id: str,
    ) -> RegulatoryCitation:
        """Add a regulatory citation linked to a Chroma vector chunk.

        Parameters
        ----------
        study_id : uuid.UUID
            FK to the parent study.
        section_name : str
            Section of the regulatory tariff being cited.
        citation_text : str
            The full citation text.
        source_document : str
            Filename or identifier of the source document.
        chroma_chunk_id : str
            ID of the corresponding chunk in ChromaDB.

        Returns
        -------
        RegulatoryCitation
            The newly created entity.

        Raises
        ------
        ConstraintViolationError
            If ``study_id`` is an invalid FK.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound.
        """
        entity = RegulatoryCitation(
            study_id=study_id,
            section_name=section_name,
            citation_text=citation_text,
            source_document=source_document,
            chroma_chunk_id=chroma_chunk_id,
        )
        try:
            self._session.add(entity)
            await self._session.flush()
            return entity
        except IntegrityError as exc:
            raise self._wrap_db_error(exc) from exc
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    # -- Human reviews -----------------------------------------------------

    async def add_human_review(
        self,
        study_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        decision: str,
        comment: Optional[str] = None,
        affected_section: Optional[str] = None,
    ) -> HumanReview:
        """Record a human review decision on a study.

        Parameters
        ----------
        study_id : uuid.UUID
            FK to the parent study.
        reviewer_id : uuid.UUID
            FK to the reviewing ``User``.
        decision : str
            One of: ``approved``, ``rejected``, ``revision_requested``,
            ``comment``.
        comment : Optional[str]
            Free-text review comment.
        affected_section : Optional[str]
            Section of the study affected by this review.

        Returns
        -------
        HumanReview
            The newly created entity.

        Raises
        ------
        ConstraintViolationError
            If ``decision`` violates the CHECK constraint, or if FKs
            are invalid.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound.
        """
        entity = HumanReview(
            study_id=study_id,
            reviewer_id=reviewer_id,
            decision=decision,
            comment=comment,
            affected_section=affected_section,
        )
        try:
            self._session.add(entity)
            await self._session.flush()
            return entity
        except IntegrityError as exc:
            raise self._wrap_db_error(exc) from exc
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc

    # -- Documents ---------------------------------------------------------

    async def add_document(
        self,
        study_id: uuid.UUID,
        doc_type: str,
        oss_key: str,
        content_type: str,
        size_bytes: Optional[int] = None,
    ) -> Document:
        """Register an object-storage document reference for a study.

        Parameters
        ----------
        study_id : uuid.UUID
            FK to the parent study.
        doc_type : str
            One of: ``satellite_tile``, ``study_pdf``, ``audit_export``.
        oss_key : str
            Alibaba OSS object key (path within the bucket).
        content_type : str
            MIME type of the document (e.g. ``application/pdf``).
        size_bytes : Optional[int]
            File size in bytes (may be ``None`` if unknown at write time).

        Returns
        -------
        Document
            The newly created entity.

        Raises
        ------
        ConstraintViolationError
            If ``doc_type`` violates the CHECK constraint, or if FKs
            are invalid.

        Notes
        -----
        *   Does **not** call ``session.commit()``.
        *   The returned entity is session-bound.
        """
        entity = Document(
            study_id=study_id,
            doc_type=doc_type,
            oss_key=oss_key,
            content_type=content_type,
            size_bytes=size_bytes,
        )
        try:
            self._session.add(entity)
            await self._session.flush()
            return entity
        except IntegrityError as exc:
            raise self._wrap_db_error(exc) from exc
        except DBAPIError as exc:
            raise self._wrap_db_error(exc) from exc
