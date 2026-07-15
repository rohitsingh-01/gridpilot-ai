"""Database entity lookup tools (projects, studies, regions)."""
from __future__ import annotations

import uuid
from typing import Optional, Any
import asyncio

from agents.site_intelligence.interfaces import ToolContext
from agents.site_intelligence.models import (
    ProjectRequest,
    StudyRequest,
    RegionRequest,
    ToolValidationError,
    ToolExecutionError,
)
from agents.site_intelligence.tools.decorators import tool_wrapper


@tool_wrapper(required_permissions=["read:project"])
async def get_project(
    context: ToolContext,
    request: ProjectRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> Any:
    """Lookup a project by unique ID using project_repository."""
    try:
        project_uuid = uuid.UUID(request.project_id)
    except ValueError as exc:
        raise ToolValidationError(f"Invalid UUID format for project_id: {str(exc)}")

    project = await context.project_repository.get_by_id(project_uuid)
    if project is None:
        raise ToolExecutionError(f"Project with ID '{request.project_id}' not found.")
    
    # Return serializable summary or direct entity projection
    return {
        "id": str(project.id),
        "name": project.name,
        "status": project.status,
    }


@tool_wrapper(required_permissions=["read:study"])
async def get_study(
    context: ToolContext,
    request: StudyRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> Any:
    """Lookup a study by unique ID using study_repository."""
    try:
        study_uuid = uuid.UUID(request.study_id)
    except ValueError as exc:
        raise ToolValidationError(f"Invalid UUID format for study_id: {str(exc)}")

    study = await context.study_repository.get_by_id(study_uuid)
    if study is None:
        raise ToolExecutionError(f"Study with ID '{request.study_id}' not found.")

    return {
        "id": str(study.id),
        "project_id": str(study.project_id),
        "status": study.status,
        "region_id": str(study.region_id) if study.region_id else None,
    }


@tool_wrapper(required_permissions=["read:region"])
async def get_region(
    context: ToolContext,
    request: RegionRequest,
    cancellation_token: Optional[asyncio.Event] = None,
) -> Any:
    """Lookup a utility region by unique ID using region_repository."""
    try:
        region_uuid = uuid.UUID(request.region_id)
    except ValueError as exc:
        raise ToolValidationError(f"Invalid UUID format for region_id: {str(exc)}")

    region = await context.region_repository.get_by_id(region_uuid)
    if region is None:
        raise ToolExecutionError(f"Utility Region with ID '{request.region_id}' not found.")

    return {
        "id": str(region.id),
        "name": region.name,
        "code": region.code,
    }
