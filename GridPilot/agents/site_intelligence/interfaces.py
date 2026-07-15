"""Abstract interfaces and schema models for Site Intelligence tools."""
from __future__ import annotations

import abc
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

from services.db.repositories.interfaces import (
    IUserRepository,
    IProjectRepository,
    IStudyRepository,
    IUtilityRegionRepository,
)


# --- Strongly Typed Interface Output Models ---

class ImageryMetadata(BaseModel):
    """Metadata representing a cached imagery tile resource."""
    cache_path: str
    mime_type: str
    checksum: str
    height: int
    width: int


class OSMFeature(BaseModel):
    """Model representing an OpenStreetMap infrastructure feature."""
    id: int
    type: str  # e.g., "node", "way", "relation"
    tags: Dict[str, str] = Field(default_factory=dict)
    geometry: Dict[str, Any] = Field(
        default_factory=dict,
        description="GeoJSON geometry representing the feature."
    )


class SearchChunk(BaseModel):
    """Model representing a retrieved semantic memory text segment."""
    chunk_id: str
    document_id: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


# --- Abstract Service Interfaces ---

class ISemanticService(abc.ABC):
    """Decoupled interface wrapping ChromaDB query vector searches."""

    @abc.abstractmethod
    async def search(self, collection: str, query: str, limit: int = 5) -> List[SearchChunk]:
        """Perform semantic retrieval from the specified vector store collection."""
        pass


class IImageryService(abc.ABC):
    """Decoupled interface wrapping Alibaba Cloud OSS cached imagery lookups."""

    @abc.abstractmethod
    async def get_metadata(self, region_id: str, scene_date: str) -> ImageryMetadata:
        """Fetch pre-cached tile metadata for the given region and timestamp."""
        pass


class IGeoService(abc.ABC):
    """Decoupled interface wrapping GIS geometry calculations via Shapely."""

    @abc.abstractmethod
    def buffer(self, aoi_geojson: Dict[str, Any], buffer_m: float) -> Dict[str, Any]:
        """Calculate buffer boundary geometry for a target AOI."""
        pass

    @abc.abstractmethod
    def intersects(self, geom1: Dict[str, Any], geom2: Dict[str, Any]) -> bool:
        """Evaluate if two geometries overlap."""
        pass

    @abc.abstractmethod
    def distance(self, geom1: Dict[str, Any], geom2: Dict[str, Any]) -> float:
        """Compute the minimum distance in meters between two geometries."""
        pass


class BaseMapProvider(abc.ABC):
    """Decoupled interface wrapping third-party map data search providers."""

    @abc.abstractmethod
    async def query_features(self, bbox: List[float], tags: List[str]) -> List[OSMFeature]:
        """Query physical infrastructure features matching the given bounding box and tags."""
        pass


class ICacheService(abc.ABC):
    """Decoupled cache client wrapper."""

    @abc.abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """Read string value from cache store."""
        pass

    @abc.abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int = 86400) -> None:
        """Write string value to cache store with expiration TTL."""
        pass


class ITelemetryService(abc.ABC):
    """Decoupled execution logger and telemetry recorder."""

    @abc.abstractmethod
    def record_metric(self, name: str, value: float, tags: Dict[str, str]) -> None:
        """Emit numeric telemetry metrics."""
        pass

    @abc.abstractmethod
    def log_structured(self, level: str, message: str, extra: Dict[str, Any]) -> None:
        """Publish structured execution run JSON logs."""
        pass


class ToolContext(BaseModel):
    """Injected execution context representing the active session runtime."""
    user_repository: IUserRepository
    project_repository: IProjectRepository
    study_repository: IStudyRepository
    region_repository: IUtilityRegionRepository

    semantic_service: ISemanticService
    imagery_service: IImageryService
    geo_service: IGeoService
    osm_service: BaseMapProvider
    cache_service: ICacheService
    telemetry_service: ITelemetryService

    user: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)
    trace_id: str

    model_config = ConfigDict(arbitrary_types_allowed=True)

