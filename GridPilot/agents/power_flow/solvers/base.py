"""Base abstract power flow solver class."""
from __future__ import annotations

import abc
from agents.power_flow.models import SimulationRequest, SimulationResult


class BasePowerFlowSolver(abc.ABC):
    """Abstract base class that all power flow solvers must inherit from."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """The identifier name of the solver."""
        pass

    @property
    @abc.abstractmethod
    def version(self) -> str:
        """The version code of the solver."""
        pass

    @abc.abstractmethod
    def solve(self, request: SimulationRequest) -> SimulationResult:
        """Execute the load flow simulation computations and check violations."""
        pass
