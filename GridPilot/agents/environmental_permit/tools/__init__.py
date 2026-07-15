"""Dynamic registration of all environmental permit analysis tools in ToolRegistry."""
from __future__ import annotations

from agents.site_intelligence.registry import ToolRegistry
from agents.environmental_permit.tools.wetlands import query_wetlands, query_wetlands_batch
from agents.environmental_permit.tools.habitat import query_critical_habitat, query_critical_habitat_batch
from agents.environmental_permit.tools.permitting import query_permit_requirements
from agents.environmental_permit.tools.geometry import calculate_environmental_buffers

# Explicit, deterministic registration of environmental tools
ToolRegistry.register("query_wetlands", query_wetlands)
ToolRegistry.register("query_wetlands_batch", query_wetlands_batch)
ToolRegistry.register("query_critical_habitat", query_critical_habitat)
ToolRegistry.register("query_critical_habitat_batch", query_critical_habitat_batch)
ToolRegistry.register("query_permit_requirements", query_permit_requirements)
ToolRegistry.register("calculate_environmental_buffers", calculate_environmental_buffers)

__all__ = [
    "query_wetlands",
    "query_wetlands_batch",
    "query_critical_habitat",
    "query_critical_habitat_batch",
    "query_permit_requirements",
    "calculate_environmental_buffers",
]
