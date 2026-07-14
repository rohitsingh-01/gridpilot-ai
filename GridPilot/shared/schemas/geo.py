from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator
from typing import List, Tuple, Dict, Any
import shapely.geometry
from shapely.validation import explain_validity

class Point(BaseModel):
    """
    Represents a GeoJSON Point geometry with validated [longitude, latitude] coordinates.
    """
    type: str = Field("Point", description="GeoJSON geometry type, must be 'Point'.")
    coordinates: Tuple[float, float] = Field(
        ..., 
        description="Coordinates in [longitude, latitude] order."
    )

    model_config = ConfigDict(
        str_strip_whitespace=True
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v != "Point":
            raise ValueError("Type must be exactly 'Point'.")
        return v

    @field_validator("coordinates")
    @classmethod
    def validate_coords(cls, v: Tuple[float, float]) -> Tuple[float, float]:
        lon, lat = v
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"Longitude {lon} must be between -180.0 and 180.0.")
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"Latitude {lat} must be between -90.0 and 90.0.")
        return v


class Polygon(BaseModel):
    """
    Represents a GeoJSON Polygon geometry. Enforces valid coordinate structures,
    closed rings, and invokes Shapely to reject self-intersecting or absurdly large shapes.
    """
    type: str = Field("Polygon", description="GeoJSON geometry type, must be 'Polygon'.")
    coordinates: List[List[Tuple[float, float]]] = Field(
        ..., 
        description="List of linear rings. The first ring is the exterior boundary; subsequent rings are holes."
    )

    model_config = ConfigDict(
        str_strip_whitespace=True
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v != "Polygon":
            raise ValueError("Type must be exactly 'Polygon'.")
        return v

    @field_validator("coordinates")
    @classmethod
    def validate_polygon_coordinates(cls, coords: List[List[Tuple[float, float]]]) -> List[List[Tuple[float, float]]]:
        if not coords:
            raise ValueError("Polygon must have at least one ring (the exterior boundary).")
        
        for ring_idx, ring in enumerate(coords):
            if len(ring) < 4:
                raise ValueError(f"Ring {ring_idx} must contain at least 4 coordinates (3 distinct vertices + 1 closing vertex).")
            
            # Verify coordinates are valid lon/lat
            for coord_idx, coord in enumerate(ring):
                lon, lat = coord
                if not (-180.0 <= lon <= 180.0):
                    raise ValueError(f"Ring {ring_idx}, coordinate {coord_idx}: Longitude {lon} must be between -180.0 and 180.0.")
                if not (-90.0 <= lat <= 90.0):
                    raise ValueError(f"Ring {ring_idx}, coordinate {coord_idx}: Latitude {lat} must be between -90.0 and 90.0.")
            
            # Verify the ring is closed
            if ring[0] != ring[-1]:
                raise ValueError(f"Ring {ring_idx} is not closed. The first coordinate {ring[0]} must match the last coordinate {ring[-1]}.")
                
        return coords

    @model_validator(mode="after")
    def validate_geometry_safety(self) -> 'Polygon':
        # Convert model data to raw dict format for shapely to load
        geojson_dict = self.model_dump()
        try:
            geom = shapely.geometry.shape(geojson_dict)
        except Exception as e:
            raise ValueError(f"Shapely failed to parse the geometry: {e}")
            
        # 1. Check if geometry is valid (not self-intersecting)
        if not geom.is_valid:
            validity_reason = explain_validity(geom)
            raise ValueError(f"Invalid polygon geometry (self-intersecting or invalid boundary): {validity_reason}")
            
        # 2. Check if geometry is empty
        if geom.is_empty:
            raise ValueError("Polygon geometry cannot be empty.")
            
        # 3. Prevent absurdly large shapes to protect against runaway computational load.
        # An area limit of 1.0 square degree corresponds to roughly 100km x 100km (approx. 10,000 sq km),
        # which is extremely large for any standard renewable energy site (which are typically a few thousand acres).
        max_area_sq_degrees = 1.0
        if geom.area > max_area_sq_degrees:
            raise ValueError(
                f"Polygon area ({geom.area:.4f} sq degrees) exceeds the maximum safety limit "
                f"of {max_area_sq_degrees} sq degrees. Please upload a smaller area of interest."
            )
            
        return self


class Feature(BaseModel):
    """
    Represents a standard GeoJSON Feature containing a geometry and metadata properties.
    """
    type: str = Field("Feature", description="GeoJSON type, must be 'Feature'.")
    geometry: Polygon = Field(..., description="The geometry of the feature.")
    properties: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Key-value properties associated with this feature."
    )

    model_config = ConfigDict(
        str_strip_whitespace=True
    )

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v != "Feature":
            raise ValueError("Type must be exactly 'Feature'.")
        return v
