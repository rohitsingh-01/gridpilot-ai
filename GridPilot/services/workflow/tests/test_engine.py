"""Unit and integration tests for the AI workflow orchestration engine."""
from __future__ import annotations

import json
import os
import shutil
import pytest
from unittest.mock import MagicMock

from services.db.repositories.interfaces import IUserRepository, IProjectRepository, IStudyRepository
from services.semantic.storage.base import BaseSemanticStore
from services.workflow.models.state import TaskState, WorkflowExecutionManifest
from services.workflow.interfaces.task import WorkflowContext, WorkflowTask
from services.workflow.interfaces.agent import BaseAgent, AgentInput, AgentOutput, AgentExecutionMetadata
from services.workflow.engine.coordinator import validate_dag, InMemoryWorkflowEngine, WorkflowCoordinator

pytestmark = pytest.mark.anyio

TEST_RUNS_DIR = os.path.join("data", "workflow", "runs")


@pytest.fixture(autouse=True)
def clean_test_runs():
    """Ensure runs directory is clean before and after tests."""
    if os.path.exists(TEST_RUNS_DIR):
        shutil.rmtree(TEST_RUNS_DIR)
    yield
    if os.path.exists(TEST_RUNS_DIR):
        shutil.rmtree(TEST_RUNS_DIR)


def test_dag_validation_success():
    """Verify that a valid DAG passes validation and returns topological sort order."""
    tasks = {
        "site_assessment": WorkflowTask(task_id="site_assessment", name="site_agent", dependencies=[]),
        "grid_simulation": WorkflowTask(task_id="grid_simulation", name="grid_agent", dependencies=["site_assessment"]),
        "costing": WorkflowTask(task_id="costing", name="cost_agent", dependencies=["grid_simulation"])
    }
    order = validate_dag(tasks)
    assert order == ["site_assessment", "grid_simulation", "costing"]


def test_dag_validation_cycle():
    """Verify that a cyclical task graph configuration raises a ValueError."""
    tasks = {
        "site_assessment": WorkflowTask(task_id="site_assessment", name="site_agent", dependencies=["costing"]),
        "grid_simulation": WorkflowTask(task_id="grid_simulation", name="grid_agent", dependencies=["site_assessment"]),
        "costing": WorkflowTask(task_id="costing", name="cost_agent", dependencies=["grid_simulation"])
    }
    with pytest.raises(ValueError, match="Cyclic dependency detected"):
        validate_dag(tasks)


def test_dag_validation_missing_dependency():
    """Verify that depending on a non-existent task raises a ValueError."""
    tasks = {
        "site_assessment": WorkflowTask(task_id="site_assessment", name="site_agent", dependencies=["non_existent"])
    }
    with pytest.raises(ValueError, match="depends on non-existent task"):
        validate_dag(tasks)


async def test_workflow_state_transitions_and_manifest():
    """Verify in-memory execution workflow runs tasks, sets states, and writes manifest."""
    # 1. Initialize mocked repository dependencies
    user_repo = MagicMock(spec=IUserRepository)
    project_repo = MagicMock(spec=IProjectRepository)
    study_repo = MagicMock(spec=IStudyRepository)
    semantic_store = MagicMock(spec=BaseSemanticStore)

    coordinator = WorkflowCoordinator(
        user_repository=user_repo,
        project_repository=project_repo,
        study_repository=study_repo,
        semantic_store=semantic_store,
    )

    # 2. Configure mock study execution config
    config = {
        "version": "1.0.0",
        "workflow": {
            "tasks": {
                "task1": {"agent": "mock", "dependencies": []},
                "task2": {"agent": "mock", "dependencies": ["task1"]}
            }
        }
    }

    # 3. Execute
    manifest = await coordinator.run_study("study_abc", "project_123", config)
    assert isinstance(manifest, WorkflowExecutionManifest)
    assert manifest.metrics.tasks_completed == 2
    assert manifest.metrics.tasks_failed == 0
    assert manifest.metrics.tasks_skipped == 0
    assert manifest.metrics.retry_count == 0

    # 4. Verify manifest file exists on disk
    assert os.path.exists(manifest.manifest_path)
    with open(manifest.manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["study_id"] == "study_abc"
    assert data["metrics"]["tasks_completed"] == 2


class RetryableFailAgent(BaseAgent):
    """Agent that fails initially with a retryable error and succeeds on second attempt."""
    def __init__(self) -> None:
        self.call_count = 0

    async def execute(self, inputs: AgentInput) -> AgentOutput:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("Temporary HTTP connection timeout error.")
        return AgentOutput(
            confidence=0.9,
            sources=["RetryDoc"],
            assumptions=["Retried successfully"],
            raw_model_output="Success after retry.",
            structured_data={},
            execution_metadata=AgentExecutionMetadata(
                execution_duration_ms=5,
                retry_count=1,
            )
        )


async def test_workflow_retry_policy():
    """Verify that retryable failures trigger task retries and eventual success."""
    user_repo = MagicMock(spec=IUserRepository)
    project_repo = MagicMock(spec=IProjectRepository)
    study_repo = MagicMock(spec=IStudyRepository)
    semantic_store = MagicMock(spec=BaseSemanticStore)

    engine = InMemoryWorkflowEngine()
    # Register failing/retrying agent
    retry_agent = RetryableFailAgent()
    engine.register_agent("retry_agent", retry_agent)

    coordinator = WorkflowCoordinator(
        user_repository=user_repo,
        project_repository=project_repo,
        study_repository=study_repo,
        semantic_store=semantic_store,
        engine=engine,
    )

    config = {
        "version": "1.0.0",
        "workflow": {
            "tasks": {
                "retry_task": {
                    "agent": "retry_agent",
                    "dependencies": []
                }
            }
        }
    }

    manifest = await coordinator.run_study("study_retry", "project_123", config)
    assert manifest.metrics.tasks_completed == 1
    assert manifest.metrics.retry_count == 1
    assert retry_agent.call_count == 2


async def test_graceful_cancellation_skips_downstream():
    """Verify that cancelling a workflow skips downstream tasks."""
    user_repo = MagicMock(spec=IUserRepository)
    project_repo = MagicMock(spec=IProjectRepository)
    study_repo = MagicMock(spec=IStudyRepository)
    semantic_store = MagicMock(spec=BaseSemanticStore)

    engine = InMemoryWorkflowEngine()
    
    # Define an agent that triggers graceful cancellation on run
    class CancellingAgent(BaseAgent):
        async def execute(self, inputs: AgentInput) -> AgentOutput:
            engine.request_graceful_cancellation()
            return AgentOutput(
                raw_model_output="Cancelled",
                execution_metadata=AgentExecutionMetadata(execution_duration_ms=1, retry_count=0)
            )

    engine.register_agent("canceller", CancellingAgent())

    coordinator = WorkflowCoordinator(
        user_repository=user_repo,
        project_repository=project_repo,
        study_repository=study_repo,
        semantic_store=semantic_store,
        engine=engine,
    )

    config = {
        "version": "1.0.0",
        "workflow": {
            "tasks": {
                "task1": {"agent": "canceller", "dependencies": []},
                "task2": {"agent": "mock", "dependencies": ["task1"]}
            }
        }
    }

    manifest = await coordinator.run_study("study_cancel", "project_123", config)
    assert manifest.metrics.tasks_completed == 1
    assert manifest.metrics.tasks_skipped == 1  # task2 is skipped (marked CANCELLED)
