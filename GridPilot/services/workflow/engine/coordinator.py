"""Workflow coordinator, DAG validator, and InMemoryWorkflowEngine execution implementation."""
from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.db.repositories.interfaces import IUserRepository, IProjectRepository, IStudyRepository
from services.semantic.storage.base import BaseSemanticStore
from services.workflow.interfaces.agent import BaseAgent, AgentInput, AgentOutput, AgentExecutionMetadata
from services.workflow.interfaces.task import WorkflowContext, WorkflowTask
from services.workflow.models.state import (
    WorkflowState,
    TaskState,
    WorkflowExecutionManifest,
    ManifestMetrics,
)
from services.workflow.engine.base import BaseWorkflowEngine


def validate_dag(tasks: Dict[str, WorkflowTask]) -> List[str]:
    """Perform topological sort on the task dependency graph, checking for cycles and missing tasks."""
    # Build adjacency list and compute in-degrees
    adj: Dict[str, List[str]] = {tid: [] for tid in tasks}
    in_degree: Dict[str, int] = {tid: 0 for tid in tasks}

    for tid, task in tasks.items():
        for dep in task.dependencies:
            if dep not in tasks:
                raise ValueError(f"Task '{tid}' depends on non-existent task '{dep}'")
            adj[dep].append(tid)
            in_degree[tid] += 1

    # Kahn's algorithm
    queue = [tid for tid, deg in in_degree.items() if deg == 0]
    execution_order = []

    while queue:
        u = queue.pop(0)
        execution_order.append(u)
        for v in adj[u]:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)

    if len(execution_order) != len(tasks):
        raise ValueError("Cyclic dependency detected in workflow task graph.")

    return execution_order


class InMemoryWorkflowEngine(BaseWorkflowEngine):
    """Executes a dependency DAG in-memory, supporting retries, skipping, and cancellation."""

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}
        self._cancellation_requested = False
        self._forced_cancellation = False

    def register_agent(self, name: str, agent: BaseAgent) -> None:
        """Register a concrete agent handler to handle specific task execution."""
        self._agents[name] = agent

    def request_graceful_cancellation(self) -> None:
        """Triggers graceful cancellation: active tasks complete, pending tasks skip."""
        self._cancellation_requested = True

    def request_forced_cancellation(self) -> None:
        """Triggers forced cancellation: immediately abort active and pending execution."""
        self._cancellation_requested = True
        self._forced_cancellation = True

    def _is_retryable(self, exception: Exception) -> bool:
        """Distinguish transient network/API issues from static configuration/validation issues."""
        if isinstance(exception, asyncio.TimeoutError):
            return True
        msg = str(exception).lower()
        # Retryable if it looks like connection, HTTP error, rate limit, or timeout
        retryable_keywords = ["timeout", "connection", "http", "rate limit", "503", "429", "request failed"]
        return any(keyword in msg for keyword in retryable_keywords)

    async def execute_workflow(
        self,
        context: WorkflowContext,
        tasks: Dict[str, WorkflowTask],
    ) -> WorkflowExecutionManifest:
        start_time = datetime.now(timezone.utc)
        start_time_str = start_time.isoformat()

        # Validate Graph
        try:
            execution_order = validate_dag(tasks)
        except ValueError as e:
            raise ValueError(f"DAG Validation failed: {str(e)}")

        tasks_completed = 0
        tasks_failed = 0
        tasks_skipped = 0
        total_retry_count = 0

        # Sequence execution based on dependency constraints
        for task_id in execution_order:
            task = tasks[task_id]

            # 1. Check Cancellation states
            if self._forced_cancellation:
                task.status = TaskState.CANCELLED
                task.error_message = "Forced cancellation triggered."
                tasks_skipped += 1
                continue
            
            if self._cancellation_requested:
                task.status = TaskState.CANCELLED
                task.error_message = "Graceful cancellation active."
                tasks_skipped += 1
                continue

            # 2. Check dependency status
            dep_failed = False
            for dep in task.dependencies:
                dep_task = tasks[dep]
                if dep_task.status in [TaskState.FAILED, TaskState.CANCELLED, TaskState.SKIPPED]:
                    dep_failed = True
                    break

            if dep_failed:
                task.status = TaskState.SKIPPED
                task.error_message = "Parent dependency failed or was skipped."
                tasks_skipped += 1
                continue

            # 3. Begin Task Execution Loop
            task.status = TaskState.RUNNING
            attempts = task.retry_policy.attempts
            backoff = task.retry_policy.backoff_seconds

            for attempt in range(attempts):
                if self._forced_cancellation:
                    task.status = TaskState.CANCELLED
                    task.error_message = "Forced cancellation triggered mid-execution."
                    break

                try:
                    task_start_time = time.time()
                    agent_name = task.name
                    agent = self._agents.get(agent_name)

                    if agent:
                        # Execute registered agent with timeout
                        agent_input = AgentInput(context=context, task_inputs=task.inputs)
                        agent_output = await asyncio.wait_for(
                            agent.execute(agent_input),
                            timeout=task.timeout_seconds
                        )
                        task.outputs = agent_output.model_dump()
                    else:
                        # Fallback to simulated execution if no agent is registered (mock run support)
                        await asyncio.wait_for(
                            asyncio.sleep(0.01),
                            timeout=task.timeout_seconds
                        )
                        task.outputs = {
                            "confidence": 1.0,
                            "sources": ["MockSource"],
                            "assumptions": ["Simulated run"],
                            "raw_model_output": "Mock success.",
                            "structured_data": {},
                            "execution_metadata": {
                                "execution_duration_ms": 10,
                                "retry_count": attempt,
                                "agent_version": "1.0.0",
                            },
                        }

                    task.status = TaskState.COMPLETED
                    tasks_completed += 1
                    break
                except Exception as exc:
                    is_retryable = self._is_retryable(exc)
                    if is_retryable and attempt < attempts - 1:
                        # Retryable error, sleep with backoff
                        task.retry_count += 1
                        total_retry_count += 1
                        await asyncio.sleep(backoff * (2**attempt))
                    else:
                        # Non-retryable or exhausted retries
                        task.status = TaskState.FAILED
                        task.error_message = str(exc)
                        tasks_failed += 1
                        # Request cancellation for downstream
                        self._cancellation_requested = True
                        break

        end_time = datetime.now(timezone.utc)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        # Write execution run manifest
        run_dir = os.path.join("data", "workflow", "runs")
        os.makedirs(run_dir, exist_ok=True)
        manifest_path = os.path.join(run_dir, f"{start_time.strftime('%Y%m%d_%H%M%S')}_{context.study_id}_manifest.json")

        manifest = WorkflowExecutionManifest(
            workflow_id=f"wf_{context.study_id}_{start_time.strftime('%Y%m%d')}",
            study_id=context.study_id,
            start_time=start_time_str,
            end_time=end_time.isoformat(),
            duration_ms=duration_ms,
            metrics=ManifestMetrics(
                tasks_completed=tasks_completed,
                tasks_failed=tasks_failed,
                tasks_skipped=tasks_skipped,
                retry_count=total_retry_count,
            ),
            manifest_path=manifest_path,
        )

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest.model_dump(), f, indent=2)

        return manifest


class WorkflowCoordinator:
    """Manages context creation, configuration parsing, and orchestrator dispatching."""

    def __init__(
        self,
        user_repository: IUserRepository,
        project_repository: IProjectRepository,
        study_repository: IStudyRepository,
        semantic_store: BaseSemanticStore,
        engine: Optional[BaseWorkflowEngine] = None,
    ) -> None:
        self.user_repo = user_repository
        self.project_repo = project_repository
        self.study_repo = study_repository
        self.semantic_store = semantic_store
        self.engine = engine or InMemoryWorkflowEngine()

    async def run_study(self, study_id: str, project_id: str, config: Dict[str, Any]) -> WorkflowExecutionManifest:
        """Run study workflow coordinator."""
        # 1. Initialize context
        context = WorkflowContext(
            study_id=study_id,
            project_id=project_id,
            config=config,
            user_repository=self.user_repo,
            project_repository=self.project_repo,
            study_repository=self.study_repo,
            semantic_store=self.semantic_store,
        )

        # 2. Build tasks map from config
        tasks = {}
        for task_id, t_cfg in config.get("workflow", {}).get("tasks", {}).items():
            tasks[task_id] = WorkflowTask(
                task_id=task_id,
                name=t_cfg.get("agent", "mock"),
                dependencies=t_cfg.get("dependencies", []),
                timeout_seconds=t_cfg.get("timeout_seconds", 300.0),
            )

        # 3. Dispatch to engine
        manifest = await self.engine.execute_workflow(context, tasks)
        return manifest
