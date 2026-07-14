"""WorkflowContext and WorkflowTask interface models."""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

from services.db.repositories.interfaces import IUserRepository, IProjectRepository, IStudyRepository
from services.semantic.storage.base import BaseSemanticStore
from services.workflow.models.state import RetryPolicyConfig, TaskState


class WorkflowContext(BaseModel):
    """Shared, immutable context passed to every task and agent during execution."""
    study_id: str
    project_id: str
    config: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    # Injected strong repository & storage interfaces
    user_repository: IUserRepository = Field(exclude=True)
    project_repository: IProjectRepository = Field(exclude=True)
    study_repository: IStudyRepository = Field(exclude=True)
    semantic_store: BaseSemanticStore = Field(exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class WorkflowTask(BaseModel):
    """Model representing an execution task node in a workflow DAG."""
    task_id: str
    name: str
    dependencies: List[str] = Field(default_factory=list)
    retry_policy: RetryPolicyConfig = Field(default_factory=RetryPolicyConfig)
    timeout_seconds: float = 300.0
    status: TaskState = TaskState.PENDING
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    retry_count: int = 0
