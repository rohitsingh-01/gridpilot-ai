"""Workflow and task state enums, policies, and manifest schemas."""
from __future__ import annotations

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class WorkflowState(str, Enum):
    """Governs the overall execution state of a study workflow."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskState(str, Enum):
    """Governs the state of an individual task node in the execution graph."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class RetryPolicyConfig(BaseModel):
    """Defines limits and backoffs for task retries on failure."""
    attempts: int = Field(default=3, ge=1)
    backoff_seconds: float = Field(default=2.0, gt=0)


class ManifestMetrics(BaseModel):
    """Ingestion statistics metrics for a workflow execution."""
    tasks_completed: int
    tasks_failed: int
    tasks_skipped: int
    retry_count: int


class WorkflowExecutionManifest(BaseModel):
    """Run summary execution manifest schema for observability and tracing."""
    workflow_id: str
    study_id: str
    start_time: str
    end_time: str
    duration_ms: int
    metrics: ManifestMetrics
    workflow_version: str = "1.0.0"
    configuration_version: str = "1.0.0"
    software_version: str = "GridPilot Orchestrator 1.0.0"
    manifest_path: str
