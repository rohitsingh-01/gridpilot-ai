"""Stub adapter for future PandaPower load flow integration."""
from __future__ import annotations

from agents.power_flow.solvers.base import BasePowerFlowSolver
from agents.power_flow.models import SimulationRequest, SimulationResult


class PandapowerSolver(BasePowerFlowSolver):
    """Future production solver integrating with the Pandapower library."""

    @property
    def name(self) -> str:
        return "pandapower"

    @property
    def version(self) -> str:
        return "2.13.0"

    def solve(self, request: SimulationRequest) -> SimulationResult:
        raise NotImplementedError("Pandapower solver is planned but not currently implemented.")
