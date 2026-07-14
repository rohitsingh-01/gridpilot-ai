"""Abstract base class interface for workflow orchestration engines."""
from __future__ import annotations

import abc
from typing import Dict, List

from services.workflow.interfaces.task import WorkflowContext, WorkflowTask
from services.workflow.models.state import WorkflowExecutionManifest


class BaseWorkflowEngine(abc.ABC):
    """Decoupled interface wrapping workflow execution DAG engines."""

    @abc.abstractmethod
    async def execute_workflow(
        self,
        context: WorkflowContext,
        tasks: Dict[str, WorkflowTask],
    ) -> WorkflowExecutionManifest:
        """Coordinate execution of a dependency validated task map."""
        pass
