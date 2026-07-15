"""Models, requests, results, and domain exceptions for the Power Flow simulation engine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


# --- Domain Exceptions ---

class PowerFlowError(Exception):
    """Base exception for all power flow simulation engine errors."""
    pass


class SimulationValidationError(PowerFlowError):
    """Exception raised when request arguments fail boundary validations."""
    pass


class TopologyError(PowerFlowError):
    """Exception raised when network topology validation fails."""
    pass


class ConvergenceError(PowerFlowError):
    """Exception raised when solver fails to converge."""
    pass


class PowerBalanceError(PowerFlowError):
    """Exception raised when network generation cannot meet load deficits."""
    pass


class NetworkConfigurationError(PowerFlowError):
    """Exception raised when loading configuration yaml values fails."""
    pass


# --- Topology Data Schema Elements ---

class Bus(BaseModel):
    """A bus (node) in the transmission/distribution network topology."""
    id: str
    name: str
    voltage_kv: float = Field(gt=0.0)
    type: str = "PQ"  # "slack", "PV", or "PQ"
    load_mw: float = Field(default=0.0, ge=0.0)
    generation_mw: float = Field(default=0.0, ge=0.0)


class TransmissionLine(BaseModel):
    """A line connecting two buses in the network."""
    id: str
    from_bus: str
    to_bus: str
    impedance: float = Field(gt=0.0)
    thermal_limit_mva: float = Field(gt=0.0)
    length_km: float = Field(gt=0.0)


class Transformer(BaseModel):
    """A transformer connecting two buses with step-up/down voltages."""
    id: str
    primary_bus: str
    secondary_bus: str
    rating_mva: float = Field(gt=0.0)


class Generator(BaseModel):
    """A generator connected to a specific bus supplying power capacity."""
    id: str
    bus: str
    max_generation_mw: float = Field(gt=0.0)


# --- Simulation Request ---

class SimulationRequest(BaseModel):
    """Input parameters defining the network configuration to run simulation."""
    study_id: str
    project_id: str
    buses: List[Bus]
    lines: List[TransmissionLine]
    transformers: List[Transformer]
    generators: List[Generator]
    configuration: Dict[str, Any] = Field(default_factory=dict)


# --- Nested Result Elements ---

class NetworkStatistics(BaseModel):
    """Aggregate statistics representing the analyzed network topology size."""
    number_of_buses: int
    number_of_lines: int
    number_of_transformers: int
    number_of_generators: int
    connected_components: int
    total_capacity: float
    total_load: float


class SimulationSummary(BaseModel):
    """Performance telemetry and basic convergence state of the simulation."""
    execution_time_ms: int
    validation_time_ms: int
    simulation_time_ms: int
    solver_name: str
    solver_version: str
    warnings: List[str] = Field(default_factory=list)
    network_statistics: NetworkStatistics
    converged: bool


# --- Simulation Result ---

class SimulationResult(BaseModel):
    """The canonical output payload containing solved power flows and violation alerts."""
    convergence_status: str  # "converged" or "diverged"
    convergence_iterations: int
    total_generation: float
    total_load: float
    total_losses: float
    overloaded_lines: List[str] = Field(default_factory=list)  # Sorted line IDs
    voltage_violations: List[str] = Field(default_factory=list)  # Sorted bus IDs
    summary: SimulationSummary
    solver_name: str = "mock"
    solver_version: str = "1.0.0"
    schema_version: str = "1.0.0"
    network_sha256: str
