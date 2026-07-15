"""Base reasoning agent orchestration layer for GridPilot agents."""
from __future__ import annotations

import abc
import asyncio
import time
from typing import Any, List, Optional

from services.workflow.interfaces.agent import BaseAgent, AgentInput, AgentOutput, AgentExecutionMetadata
from agents.site_intelligence.interfaces import ToolContext, ITelemetryService
from agents.site_intelligence.models import (
    EvidenceBundle,
    ToolExecutionSummary,
    ToolDomainError,
    ToolExecutionError,
    ToolTimeoutError,
)
from agents.site_intelligence.registry import ToolRegistry


class BaseReasoningAgent(BaseAgent, abc.ABC):
    """Abstract Mixin and Base class orchestrating execution, cancellation, and metrics lifecycles."""

    def __init__(self, telemetry_service: ITelemetryService) -> None:
        self.telemetry_srv = telemetry_service

    @abc.abstractmethod
    async def gather_evidence(
        self,
        tool_context: ToolContext,
        inputs: AgentInput,
        tool_metrics: List[ToolExecutionSummary],
    ) -> EvidenceBundle:
        """Retrieve domain specific evidence using tools, logging executed summaries."""
        pass

    @abc.abstractmethod
    def compile_report(
        self,
        evidence: EvidenceBundle,
        tool_context: ToolContext,
        workflow_id: str,
        tool_metrics: List[ToolExecutionSummary],
    ) -> Any:
        """Transform gathered evidence bundle into a validated output report."""
        pass

    async def execute(self, inputs: AgentInput) -> AgentOutput:
        """Unified orchestrator workflow handling timeouts, cancellations, and telemetry logs."""
        start_time = time.perf_counter()
        trace_id = inputs.context.metadata.get("trace_id", f"trace_{int(time.time())}")
        workflow_id = inputs.context.metadata.get("workflow_id", f"wf_{inputs.context.study_id}")
        
        # 1. Initialize tool context
        tool_context = self.build_tool_context(inputs, trace_id)
        tool_metrics: List[ToolExecutionSummary] = []

        try:
            # 2. Check workflow cancellation early
            cancellation_token = inputs.context.metadata.get("cancellation_token")
            if cancellation_token and cancellation_token.is_set():
                raise asyncio.CancelledError("Workflow was cancelled before agent execution.")

            # 3. Call abstract evidence gathering phase
            evidence = await self.gather_evidence(tool_context, inputs, tool_metrics)

            # 4. Compile and validate final report
            report = self.compile_report(evidence, tool_context, workflow_id, tool_metrics)
            
            dur_ms = int((time.perf_counter() - start_time) * 1000)
            self.telemetry_srv.record_metric(
                "agent.execution_duration_ms", dur_ms, {"agent": self.__class__.__name__, "status": "success"}
            )

            return AgentOutput(
                confidence=getattr(report, "confidence_score", 1.0),
                sources=[f"Tool: {m.tool_name}" for m in tool_metrics],
                assumptions=[getattr(a, "description", str(a)) for a in getattr(report, "assumptions", [])],
                raw_model_output=f"Agent report generated successfully. Risk: {getattr(report, 'overall_risk', 'LOW')}.",
                structured_data=report.model_dump(),
                execution_metadata=AgentExecutionMetadata(
                    execution_duration_ms=dur_ms,
                    retry_count=0,
                    warnings=getattr(report, "warnings", []),
                    agent_version="1.0.0"
                )
            )

        except asyncio.TimeoutError as exc:
            dur_ms = int((time.perf_counter() - start_time) * 1000)
            self.telemetry_srv.record_metric(
                "agent.execution_duration_ms", dur_ms, {"agent": self.__class__.__name__, "status": "timeout"}
            )
            raise ToolTimeoutError(f"Agent timed out during orchestration: {str(exc)}")
        except asyncio.CancelledError:
            dur_ms = int((time.perf_counter() - start_time) * 1000)
            self.telemetry_srv.record_metric(
                "agent.execution_duration_ms", dur_ms, {"agent": self.__class__.__name__, "status": "cancelled"}
            )
            raise
        except Exception as exc:
            dur_ms = int((time.perf_counter() - start_time) * 1000)
            self.telemetry_srv.record_metric(
                "agent.execution_duration_ms", dur_ms, {"agent": self.__class__.__name__, "status": "error"}
            )
            if isinstance(exc, ToolDomainError):
                raise exc
            raise ToolExecutionError(f"Agent failed during orchestration: {str(exc)}")

    @abc.abstractmethod
    def build_tool_context(self, inputs: AgentInput, trace_id: str) -> ToolContext:
        """Construct the concrete ToolContext container from inputs."""
        pass
