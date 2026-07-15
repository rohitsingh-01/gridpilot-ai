"""Validator and main simulation engine for GridPilot Power Flow calculation layer."""
from __future__ import annotations

import os
import yaml
import time
import json
import hashlib
from typing import Dict, Any, List, Optional

from agents.power_flow.models import (
    SimulationRequest,
    SimulationResult,
    SimulationValidationError,
    TopologyError,
    NetworkConfigurationError,
    Bus,
    TransmissionLine,
    Transformer,
    Generator,
)
from agents.power_flow.solvers.base import BasePowerFlowSolver
from agents.power_flow.solvers.mock_solver import MockPowerFlowSolver


# --- Topology and Constraints Validator ---

class NetworkValidator:
    """Performs topology integrity and boundary constraint validation checks on requests."""

    @staticmethod
    def validate(request: SimulationRequest) -> None:
        """Run validation rules over the network topography."""
        # 1. Duplicate Bus Check
        bus_ids = set()
        for bus in request.buses:
            if bus.id in bus_ids:
                raise SimulationValidationError(f"Duplicate bus identifier detected: {bus.id}")
            bus_ids.add(bus.id)

        # 2. Duplicate Line Check
        line_ids = set()
        for line in request.lines:
            if line.id in line_ids:
                raise SimulationValidationError(f"Duplicate transmission line identifier detected: {line.id}")
            line_ids.add(line.id)

        # 3. Parameter bounds checks (negative/zero bounds)
        for bus in request.buses:
            if bus.voltage_kv <= 0.0:
                raise SimulationValidationError(f"Bus {bus.id} voltage_kv must be greater than 0.")

        for line in request.lines:
            if line.impedance <= 0.0:
                raise SimulationValidationError(f"Line {line.id} impedance must be greater than 0.")
            if line.thermal_limit_mva <= 0.0:
                raise SimulationValidationError(f"Line {line.id} thermal_limit_mva must be greater than 0.")
            if line.length_km <= 0.0:
                raise SimulationValidationError(f"Line {line.id} length_km must be greater than 0.")

        for trans in request.transformers:
            if trans.rating_mva <= 0.0:
                raise SimulationValidationError(f"Transformer {trans.id} rating_mva must be greater than 0.")

        for gen in request.generators:
            if gen.max_generation_mw <= 0.0:
                raise SimulationValidationError(f"Generator {gen.id} max_generation_mw must be greater than 0.")

        # 4. Bus reference validation
        for line in request.lines:
            if line.from_bus not in bus_ids:
                raise TopologyError(f"Line {line.id} references missing from_bus: {line.from_bus}")
            if line.to_bus not in bus_ids:
                raise TopologyError(f"Line {line.id} references missing to_bus: {line.to_bus}")

        for trans in request.transformers:
            if trans.primary_bus not in bus_ids:
                raise TopologyError(f"Transformer {trans.id} references missing primary_bus: {trans.primary_bus}")
            if trans.secondary_bus not in bus_ids:
                raise TopologyError(f"Transformer {trans.id} references missing secondary_bus: {trans.secondary_bus}")

        for gen in request.generators:
            if gen.bus not in bus_ids:
                raise TopologyError(f"Generator {gen.id} references missing bus: {gen.bus}")

        # 5. Configuration rules
        allow_islands = request.configuration.get("validation", {}).get("allow_islands", False)
        require_slack = request.configuration.get("validation", {}).get("require_slack_bus", True)

        if require_slack:
            has_slack = any(b.type == "slack" for b in request.buses)
            if not has_slack:
                raise TopologyError("Network topology lacks a required slack/swing bus configuration.")

        if not allow_islands and request.buses:
            adj = {b_id: [] for b_id in bus_ids}
            for line in request.lines:
                if line.from_bus in adj and line.to_bus in adj:
                    adj[line.from_bus].append(line.to_bus)
                    adj[line.to_bus].append(line.from_bus)
            for trans in request.transformers:
                if trans.primary_bus in adj and trans.secondary_bus in adj:
                    adj[trans.primary_bus].append(trans.secondary_bus)
                    adj[trans.secondary_bus].append(trans.primary_bus)

            # BFS from first bus to verify connectivity
            visited = set()
            start_node = request.buses[0].id
            queue = [start_node]
            visited.add(start_node)
            while queue:
                node = queue.pop(0)
                for neighbor in adj[node]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            if len(visited) < len(request.buses):
                raise TopologyError("Network topology contains isolated nodes or separate islands.")


# --- Main Engine Runner Class ---

class PowerFlowEngine:
    """Runner orchestration engine that executes validations, solves network flow, and persists manifests."""

    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_default_config(config_path)

    def _load_default_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """Load default configuration from config directory."""
        if not config_path:
            # Fallback path logic
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            config_path = os.path.join(base_dir, "config", "power_flow.yaml")

        if not os.path.exists(config_path):
            return {
                "version": "1.0.0",
                "solver": {"default": "mock"},
                "limits": {"voltage_min_pu": 0.95, "voltage_max_pu": 1.05, "thermal_limit_percentage": 100},
                "loss_model": {"percentage": 2.0},
                "validation": {"allow_islands": False, "require_slack_bus": True}
            }

        try:
            with open(config_path, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as exc:
            raise NetworkConfigurationError(f"Failed to read yaml configuration at {config_path}: {str(exc)}")

    def run(self, request: SimulationRequest, solver: Optional[BasePowerFlowSolver] = None) -> SimulationResult:
        """Pipeline orchestration runner."""
        engine_start = time.perf_counter()

        # Merges configuration defaults
        cfg = self.config.copy()
        if request.configuration:
            cfg.update(request.configuration)
        request.configuration = cfg

        # 1. Validation phase
        val_start = time.perf_counter()
        NetworkValidator.validate(request)
        val_duration_ms = int((time.perf_counter() - val_start) * 1000)

        # 2. Compute network topology stable SHA-256 hash
        network_hash = self.compute_network_hash(request)

        # 3. Solver resolution
        if not solver:
            solver = MockPowerFlowSolver()

        sim_start = time.perf_counter()
        result = solver.solve(request)
        sim_duration_ms = int((time.perf_counter() - sim_start) * 1000)

        # 4. Finalize result telemetry summaries
        engine_duration_ms = int((time.perf_counter() - engine_start) * 1000)
        result.network_sha256 = network_hash
        result.summary.validation_time_ms = val_duration_ms
        result.summary.simulation_time_ms = sim_duration_ms
        result.summary.execution_time_ms = engine_duration_ms

        # 5. Persist execution manifest
        self._write_manifest(request, result)

        return result

    @staticmethod
    def compute_network_hash(request: SimulationRequest) -> str:
        """Construct a stable, deterministic hash from network topology parameters."""
        # Sort collections by stable identifiers to eliminate ordering discrepancies
        buses_serialized = sorted([b.model_dump() for b in request.buses], key=lambda x: x["id"])
        lines_serialized = sorted([l.model_dump() for l in request.lines], key=lambda x: x["id"])
        trans_serialized = sorted([t.model_dump() for t in request.transformers], key=lambda x: x["id"])
        gens_serialized = sorted([g.model_dump() for g in request.generators], key=lambda x: x["id"])

        payload = {
            "buses": buses_serialized,
            "lines": lines_serialized,
            "transformers": trans_serialized,
            "generators": gens_serialized,
        }

        serialized_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized_str.encode("utf-8")).hexdigest()

    def _write_manifest(self, request: SimulationRequest, result: SimulationResult) -> None:
        """Write execution manifest records to file."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        manifest_dir = os.path.join(base_dir, "data", "power_flow", "manifests")
        os.makedirs(manifest_dir, exist_ok=True)

        manifest_path = os.path.join(manifest_dir, f"{request.study_id}_{request.project_id}.json")

        manifest_data = {
            "study_id": request.study_id,
            "project_id": request.project_id,
            "solver": result.solver_name,
            "solver_version": result.solver_version,
            "execution_duration_ms": result.summary.execution_time_ms,
            "warnings": result.summary.warnings,
            "topology_summary": {
                "buses": result.summary.network_statistics.number_of_buses,
                "lines": result.summary.network_statistics.number_of_lines,
                "transformers": result.summary.network_statistics.number_of_transformers,
                "generators": result.summary.network_statistics.number_of_generators,
            },
            "convergence": result.convergence_status,
            "validation_results": "success" if result.convergence_status == "converged" else "failure",
            "network_sha256": result.network_sha256,
        }

        try:
            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f, indent=2)
        except Exception:
            # Silence logging file errors during background unit tests if workspace is sandboxed
            pass
