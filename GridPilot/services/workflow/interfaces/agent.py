"""Base agent execution interfaces and Pydantic communication schemas."""
from __future__ import annotations

import abc
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from services.workflow.interfaces.task import WorkflowContext


class AgentExecutionMetadata(BaseModel):
    """Metadata tracking agent execution performance for observability."""
    execution_duration_ms: int
    retry_count: int
    warnings: List[str] = Field(default_factory=list)
    agent_version: str = "1.0.0"


class AgentInput(BaseModel):
    """Encapsulates input variables required for agent execution."""
    context: WorkflowContext
    task_inputs: Dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    """Standardized output structure every agent must return."""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    sources: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    raw_model_output: str
    structured_data: Dict[str, Any] = Field(default_factory=dict)
    execution_metadata: AgentExecutionMetadata


class BaseAgent(abc.ABC):
    """Abstract interface defining the execution contract for all AI agents."""

    @abc.abstractmethod
    async def execute(self, inputs: AgentInput) -> AgentOutput:
        """Run the agent logic using injected context and inputs, returning standard output."""
        pass
