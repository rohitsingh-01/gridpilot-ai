"""Offline unit and integration testing suite for Power Flow simulation engine."""
from __future__ import annotations

import os
import json
import pytest
from typing import Dict, Any

from agents.power_flow.models import (
    Bus,
    TransmissionLine,
    Transformer,
    Generator,
    SimulationRequest,
    SimulationResult,
    SimulationValidationError,
    TopologyError,
)
from agents.power_flow.simulation import PowerFlowEngine, NetworkValidator
from agents.power_flow.solvers.base import BasePowerFlowSolver
from agents.power_flow.solvers.mock_solver import MockPowerFlowSolver
from agents.power_flow.solvers.future_pandapower import PandapowerSolver


# --- Test Network Topologies ---

def get_base_request() -> SimulationRequest:
    """Helper creating a healthy, simple 3-bus network request."""
    return SimulationRequest(
        study_id="study_test_789",
        project_id="proj_test_789",
        buses=[
            Bus(id="B1", name="Slack Bus", voltage_kv=115.0, type="slack", load_mw=0.0, generation_mw=50.0),
            Bus(id="B2", name="Load Bus A", voltage_kv=115.0, type="PQ", load_mw=20.0, generation_mw=0.0),
            Bus(id="B3", name="Load Bus B", voltage_kv=115.0, type="PQ", load_mw=15.0, generation_mw=0.0),
        ],
        lines=[
            TransmissionLine(id="L1", from_bus="B1", to_bus="B2", impedance=0.5, thermal_limit_mva=100.0, length_km=10.0),
            TransmissionLine(id="L2", from_bus="B2", to_bus="B3", impedance=0.4, thermal_limit_mva=80.0, length_km=8.0),
        ],
        transformers=[],
        generators=[
            Generator(id="G1", bus="B1", max_generation_mw=100.0)
        ],
        configuration={
            "limits": {"voltage_min_pu": 0.95, "voltage_max_pu": 1.05},
            "loss_model": {"percentage": 2.0},
            "validation": {"allow_islands": False, "require_slack_bus": True}
        }
    )


# --- Tests ---

def test_solver_inheritance():
    """Verify that solvers correctly subclass BasePowerFlowSolver abstract interface."""
    mock_solver = MockPowerFlowSolver()
    future_solver = PandapowerSolver()
    
    assert isinstance(mock_solver, BasePowerFlowSolver)
    assert isinstance(future_solver, BasePowerFlowSolver)
    
    with pytest.raises(NotImplementedError):
        future_solver.solve(get_base_request())


def test_validator_happy_path():
    """Verify healthy topology validates without errors."""
    req = get_base_request()
    # Should not raise exception
    NetworkValidator.validate(req)


def test_validation_duplicate_buses():
    """Verify that duplicate bus IDs raise a SimulationValidationError."""
    req = get_base_request()
    req.buses.append(Bus(id="B1", name="Duplicate Slack", voltage_kv=115.0, type="PQ"))
    
    with pytest.raises(SimulationValidationError, match="Duplicate bus identifier"):
        NetworkValidator.validate(req)


def test_validation_duplicate_lines():
    """Verify that duplicate line IDs raise a SimulationValidationError."""
    req = get_base_request()
    req.lines.append(TransmissionLine(id="L1", from_bus="B1", to_bus="B3", impedance=0.2, thermal_limit_mva=50.0, length_km=5.0))
    
    with pytest.raises(SimulationValidationError, match="Duplicate transmission line"):
        NetworkValidator.validate(req)


def test_validation_negative_impedance():
    """Verify that negative parameter values raise validation errors."""
    req = get_base_request()
    req.lines[0].impedance = -0.5
    
    with pytest.raises(SimulationValidationError, match="impedance must be greater than 0"):
        NetworkValidator.validate(req)


def test_validation_negative_thermal_limit():
    """Verify that non-positive thermal limits raise validation errors."""
    req = get_base_request()
    req.lines[0].thermal_limit_mva = 0.0
    
    with pytest.raises(SimulationValidationError, match="thermal_limit_mva must be greater than 0"):
        NetworkValidator.validate(req)


def test_validation_missing_bus_references():
    """Verify topology checks catch line references to non-existent buses."""
    req = get_base_request()
    req.lines[0].to_bus = "B99"  # Non-existent bus
    
    with pytest.raises(TopologyError, match="references missing to_bus"):
        NetworkValidator.validate(req)


def test_validation_invalid_generator_reference():
    """Verify validation detects generator reference to a missing bus."""
    req = get_base_request()
    req.generators.append(Generator(id="G2", bus="B99", max_generation_mw=50.0))
    
    with pytest.raises(TopologyError, match="references missing bus"):
        NetworkValidator.validate(req)


def test_validation_invalid_transformer_reference():
    """Verify validation detects transformer reference to a missing bus."""
    req = get_base_request()
    req.transformers.append(Transformer(id="T1", primary_bus="B1", secondary_bus="B99", rating_mva=40.0))
    
    with pytest.raises(TopologyError, match="references missing secondary_bus"):
        NetworkValidator.validate(req)


def test_validation_missing_slack_bus():
    """Verify topology validation flags networks missing a slack bus when required."""
    req = get_base_request()
    # Change slack bus to PV
    req.buses[0].type = "PV"
    
    with pytest.raises(TopologyError, match="lacks a required slack"):
        NetworkValidator.validate(req)


def test_validation_islanded_topology():
    """Verify isolated buses are flagged as islanded topology violations."""
    req = get_base_request()
    # Add an isolated bus
    req.buses.append(Bus(id="B4", name="Isolated Bus", voltage_kv=115.0, type="PQ"))
    
    with pytest.raises(TopologyError, match="isolated nodes or separate islands"):
        NetworkValidator.validate(req)


def test_engine_runs_with_dependency_injection():
    """Verify engine runs using injected solvers and populates summaries."""
    class CustomSolver(BasePowerFlowSolver):
        @property
        def name(self) -> str:
            return "custom"
        @property
        def version(self) -> str:
            return "0.0.1"
        def solve(self, request: SimulationRequest) -> SimulationResult:
            mock = MockPowerFlowSolver().solve(request)
            mock.solver_name = self.name
            mock.solver_version = self.version
            return mock

    engine = PowerFlowEngine()
    req = get_base_request()
    result = engine.run(req, solver=CustomSolver())
    
    assert result.solver_name == "custom"
    assert result.solver_version == "0.0.1"


def test_mock_solver_constraint_violations():
    """Verify mock solver detects thermal limits overload and voltage drops."""
    req = get_base_request()
    
    # 1. Trigger voltage drop by placing extremely high load on PQ bus
    req.buses[1].load_mw = 100.0
    # 2. Trigger line overload by restricting thermal limit
    req.lines[0].thermal_limit_mva = 5.0
    
    engine = PowerFlowEngine()
    result = engine.run(req)
    
    # Check violations detected
    assert "L1" in result.overloaded_lines
    assert "B2" in result.voltage_violations
    assert result.convergence_status == "converged"
    assert len(result.summary.warnings) > 0


def test_statistics_calculation():
    """Verify network stats contain correct element counts and component counts."""
    req = get_base_request()
    # Add a transformer
    req.transformers.append(Transformer(id="TR1", primary_bus="B1", secondary_bus="B2", rating_mva=50.0))
    
    engine = PowerFlowEngine()
    result = engine.run(req)
    stats = result.summary.network_statistics
    
    assert stats.number_of_buses == 3
    assert stats.number_of_lines == 2
    assert stats.number_of_transformers == 1
    assert stats.number_of_generators == 1
    assert stats.total_load == 35.0
    assert stats.total_capacity == 100.0


def test_network_hash_stability():
    """Verify network hash is stable, reproducible, and independent of workspace timestamps."""
    req1 = get_base_request()
    req2 = get_base_request()
    
    # Ensure independent run hash evaluations are identical
    hash1 = PowerFlowEngine.compute_network_hash(req1)
    hash2 = PowerFlowEngine.compute_network_hash(req2)
    assert hash1 == hash2
    
    # Modify generation capacity on second layout
    req2.generators[0].max_generation_mw = 150.0
    hash3 = PowerFlowEngine.compute_network_hash(req2)
    assert hash1 != hash3


def test_execution_manifest_generation():
    """Verify execution manifest files populate correct performance and run metadata."""
    req = get_base_request()
    engine = PowerFlowEngine()
    result = engine.run(req)
    
    # Check manifest file creation
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    manifest_path = os.path.join(base_dir, "data", "power_flow", "manifests", f"{req.study_id}_{req.project_id}.json")
    
    assert os.path.exists(manifest_path)
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    assert manifest["study_id"] == req.study_id
    assert manifest["project_id"] == req.project_id
    assert manifest["solver"] == "mock"
    assert manifest["network_sha256"] == result.network_sha256
    assert manifest["convergence"] == "converged"
    assert manifest["topology_summary"]["buses"] == 3


def test_result_serialization_roundtrip():
    """Verify SimulationResult Pydantic models serialize and deserialize without loss."""
    req = get_base_request()
    engine = PowerFlowEngine()
    result = engine.run(req)
    
    dumped = result.model_dump_json()
    loaded = SimulationResult.model_validate_json(dumped)
    
    assert loaded.network_sha256 == result.network_sha256
    assert loaded.total_load == result.total_load
    assert loaded.summary.network_statistics.number_of_buses == 3
