"""Consolidated abstract interface contract for Environmental Analysis Services."""
from __future__ import annotations

import abc
from typing import Any, Dict, List

from agents.environmental_permit.models import (
    WetlandResult,
    HabitatResult,
    PermitResult,
    BufferResult,
)


class IEnvironmentalAnalysisService(abc.ABC):
    """Abstract interface governing all environmental queries and calculations."""

    @abc.abstractmethod
    async def query_wetlands(self, aoi_geojson: Dict[str, Any]) -> List[WetlandResult]:
        """Intersect input AOI boundary with national wetlands datasets."""
        pass

    @abc.abstractmethod
    async def query_critical_habitats(self, aoi_geojson: Dict[str, Any]) -> List[HabitatResult]:
        """Intersect input AOI boundary with critical habitats datasets."""
        pass

    @abc.abstractmethod
    async def query_permit_requirements(self, query: str) -> List[PermitResult]:
        """Perform semantic regulatory check to list permitting requirements."""
        pass

    @abc.abstractmethod
    async def query_permit_requirements_batch(self, queries: List[str]) -> List[PermitResult]:
        """Batch query semantic regulatory memory for multiple permit requests."""
        pass

    @abc.abstractmethod
    def calculate_buffers(self, aoi_geojson: Dict[str, Any], buffer_m: float) -> BufferResult:
        """Evaluate buffer setback bounds and identify setback compliance."""
        pass
