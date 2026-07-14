from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UserSeedConfig(BaseModel):
    """Seed data configuration schema for User."""
    email: str = Field(pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    display_name: str
    role: str = Field(pattern="^(engineer|admin)$")
    password_hash: str


class RegionSeedConfig(BaseModel):
    """Seed data configuration schema for UtilityRegion."""
    name: str
    boundary_geojson: Dict[str, Any]


class NodeSeedConfig(BaseModel):
    """Seed data configuration schema for GridNode."""
    node_key: str
    node_type: str = Field(pattern="^(substation|generator_bus|load_bus)$")
    voltage_kv: float = Field(gt=0)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    thermal_limit_mva: Optional[float] = Field(default=None, gt=0)


class EdgeSeedConfig(BaseModel):
    """Seed data configuration schema for GridEdge."""
    from_node: str
    to_node: str
    edge_type: str = Field(pattern="^(line|transformer)$")
    reactance_pu: float = Field(gt=0)
    thermal_limit_mva: float = Field(gt=0)
    length_miles: Optional[float] = Field(default=None, gt=0)


class TopologySeedConfig(BaseModel):
    """Composite seed configuration schema for GridNode and GridEdge."""
    nodes: List[NodeSeedConfig]
    edges: List[EdgeSeedConfig]


class ProjectSeedConfig(BaseModel):
    """Seed data configuration schema for Project."""
    name: str
    technology: str = Field(pattern="^(solar|storage|solar_plus_storage|wind)$")
    capacity_mw: float = Field(gt=0)
    storage_capacity_mw: Optional[float] = Field(default=None, gt=0)
    poi_node_key: str
    aoi_geojson: Dict[str, Any]
    submitted_by: Optional[str] = None
    status: str = "submitted"
