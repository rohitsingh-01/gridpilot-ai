"""Deterministic Mock solver implementation for Power Flow calculations."""
from __future__ import annotations

import time
from typing import Dict, Any, List

from agents.power_flow.solvers.base import BasePowerFlowSolver
from agents.power_flow.models import (
    SimulationRequest,
    SimulationResult,
    SimulationSummary,
    NetworkStatistics,
    Bus,
    TransmissionLine,
)


class MockPowerFlowSolver(BasePowerFlowSolver):
    """Deterministic mock load flow solver."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def version(self) -> str:
        return "1.0.0"

    def solve(self, request: SimulationRequest) -> SimulationResult:
        solve_start = time.perf_counter()

        # Load limits from configuration
        cfg_limits = request.configuration.get("limits", {})
        voltage_min = cfg_limits.get("voltage_min_pu", 0.95)
        voltage_max = cfg_limits.get("voltage_max_pu", 1.05)
        loss_pct = request.configuration.get("loss_model", {}).get("percentage", 2.0) / 100.0

        total_load = sum(b.load_mw for b in request.buses)
        total_gen_scheduled = sum(b.generation_mw for b in request.buses)
        total_losses = total_load * loss_pct

        # Slack bus balancing logic
        slack_bus = next((b for b in request.buses if b.type == "slack"), None)
        slack_addition = max(0.0, (total_load + total_losses) - total_gen_scheduled)
        total_generation = total_gen_scheduled + slack_addition

        # Estimate line loadings deterministically
        overloaded_lines: List[str] = []
        num_lines = len(request.lines)
        for line in request.lines:
            # Flow is proportional to total load, inversely proportional to impedance
            flow = (total_load * 0.8) / (line.impedance * num_lines)
            if flow > line.thermal_limit_mva:
                overloaded_lines.append(line.id)

        # Estimate bus voltages deterministically
        voltage_violations: List[str] = []
        for bus in request.buses:
            # Drop voltage based on load, boost based on generation
            v_pu = 1.0 - (bus.load_mw * 0.002) + (bus.generation_mw * 0.001)
            if bus.type == "slack":
                v_pu = 1.0
            if v_pu < voltage_min or v_pu > voltage_max:
                voltage_violations.append(bus.id)

        # Sort violation lists for determinism
        overloaded_lines.sort()
        voltage_violations.sort()

        # Build execution summary statistics
        duration_ms = int((time.perf_counter() - solve_start) * 1000)

        # Basic connected component estimate (mocked as 1 unless disconnected buses exist)
        connected_components = 1
        bus_ids = {b.id for b in request.buses}
        line_buses = {l.from_bus for l in request.lines}.union({l.to_bus for l in request.lines})
        disconnected_count = len(bus_ids - line_buses)
        if disconnected_count > 0:
            connected_components += disconnected_count

        total_capacity = sum(g.max_generation_mw for g in request.generators)

        stats = NetworkStatistics(
            number_of_buses=len(request.buses),
            number_of_lines=len(request.lines),
            number_of_transformers=len(request.transformers),
            number_of_generators=len(request.generators),
            connected_components=connected_components,
            total_capacity=total_capacity,
            total_load=total_load,
        )

        summary = SimulationSummary(
            execution_time_ms=duration_ms,
            validation_time_ms=0,  # Populated by Engine
            simulation_time_ms=duration_ms,
            solver_name=self.name,
            solver_version=self.version,
            warnings=["Mock simulation completed. Localized flow is estimated."] if overloaded_lines or voltage_violations else [],
            network_statistics=stats,
            converged=True,
        )

        # Generate stable network hash from sorted items
        # To avoid timestamp discrepancies, this is handled in the Engine
        
        return SimulationResult(
            convergence_status="converged",
            convergence_iterations=1,
            total_generation=total_generation,
            total_load=total_load,
            total_losses=total_losses,
            overloaded_lines=overloaded_lines,
            voltage_violations=voltage_violations,
            summary=summary,
            solver_name=self.name,
            solver_version=self.version,
            network_sha256="",  # Set by Engine
        )
