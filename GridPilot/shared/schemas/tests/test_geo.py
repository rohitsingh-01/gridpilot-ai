import pytest
from unittest.mock import patch
from pydantic import ValidationError
from shared.schemas.geo import Point, Polygon, Feature
import shapely.geometry

def test_point_valid():
    """Verify that a valid Point parses correctly."""
    pt = Point(type="Point", coordinates=(-115.5, 42.3))
    assert pt.type == "Point"
    assert pt.coordinates == (-115.5, 42.3)

def test_point_invalid_type():
    """Verify that invalid geometry type raises validation error."""
    with pytest.raises(ValidationError) as exc_info:
        Point(type="InvalidType", coordinates=(-115.5, 42.3))
    assert "Type must be exactly 'Point'" in str(exc_info.value)

def test_point_invalid_coordinates():
    """Verify that coordinates outside valid ranges are rejected."""
    # Longitude out of bounds
    with pytest.raises(ValidationError) as exc_info:
        Point(type="Point", coordinates=(-181.0, 42.3))
    assert "Longitude -181.0 must be between -180.0 and 180.0" in str(exc_info.value)

    # Latitude out of bounds
    with pytest.raises(ValidationError) as exc_info:
        Point(type="Point", coordinates=(-115.5, 91.0))
    assert "Latitude 91.0 must be between -90.0 and 90.0" in str(exc_info.value)

def test_polygon_valid():
    """Verify that a valid, simple closed Polygon parses successfully."""
    # A small square polygon (0.01 x 0.01 degrees)
    poly = Polygon(
        type="Polygon",
        coordinates=[[
            (-115.0, 42.0),
            (-115.01, 42.0),
            (-115.01, 42.01),
            (-115.0, 42.01),
            (-115.0, 42.0)
        ]]
    )
    assert poly.type == "Polygon"
    assert len(poly.coordinates[0]) == 5

def test_polygon_invalid_type():
    """Verify that invalid geometry type raises validation error for Polygon."""
    with pytest.raises(ValidationError) as exc_info:
        Polygon(
            type="NotAPolygon",
            coordinates=[[
                (-115.0, 42.0),
                (-115.01, 42.0),
                (-115.01, 42.01),
                (-115.0, 42.01),
                (-115.0, 42.0)
            ]]
        )
    assert "Type must be exactly 'Polygon'" in str(exc_info.value)

def test_polygon_empty_coordinates():
    """Verify that empty coordinates list raises validation error."""
    with pytest.raises(ValidationError) as exc_info:
        Polygon(type="Polygon", coordinates=[])
    assert "must have at least one ring" in str(exc_info.value)

def test_polygon_invalid_coordinate_ranges():
    """Verify that coordinates outside valid ranges are rejected in Polygon."""
    # Longitude out of bounds
    with pytest.raises(ValidationError) as exc_info:
        Polygon(
            type="Polygon",
            coordinates=[[
                (-185.0, 42.0),
                (-115.01, 42.0),
                (-115.01, 42.01),
                (-115.0, 42.01),
                (-185.0, 42.0)
            ]]
        )
    assert "Longitude -185.0 must be between -180.0 and 180.0" in str(exc_info.value)

    # Latitude out of bounds
    with pytest.raises(ValidationError) as exc_info:
        Polygon(
            type="Polygon",
            coordinates=[[
                (-115.0, 95.0),
                (-115.01, 42.0),
                (-115.01, 42.01),
                (-115.0, 42.01),
                (-115.0, 95.0)
            ]]
        )
    assert "Latitude 95.0 must be between -90.0 and 90.0" in str(exc_info.value)

def test_polygon_unclosed_ring():
    """Verify that unclosed linear rings are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Polygon(
            type="Polygon",
            coordinates=[[
                (-115.0, 42.0),
                (-115.01, 42.0),
                (-115.01, 42.01),
                (-115.0, 42.01),
                (-115.0, 42.05) # First (-115.0, 42.0) and last don't match
            ]]
        )
    assert "is not closed" in str(exc_info.value)

def test_polygon_insufficient_points():
    """Verify that rings with fewer than 4 coordinates are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        Polygon(
            type="Polygon",
            coordinates=[[
                (-115.0, 42.0),
                (-115.01, 42.0),
                (-115.0, 42.0)
            ]]
        )
    assert "must contain at least 4 coordinates" in str(exc_info.value)

def test_polygon_self_intersecting():
    """Verify that self-intersecting (figure-eight) polygons are rejected by Shapely validation."""
    with pytest.raises(ValidationError) as exc_info:
        Polygon(
            type="Polygon",
            coordinates=[[
                (0.0, 0.0),
                (2.0, 2.0),
                (2.0, 0.0),
                (0.0, 2.0),
                (0.0, 0.0)
            ]]
        )
    assert "self-intersecting" in str(exc_info.value).lower()

def test_polygon_absurdly_large():
    """Verify that polygons exceeding the safety area limit (1.0 sq degree) are rejected."""
    # A 2.0 x 2.0 degree square (area = 4.0 sq degrees)
    with pytest.raises(ValidationError) as exc_info:
        Polygon(
            type="Polygon",
            coordinates=[[
                (-115.0, 42.0),
                (-117.0, 42.0),
                (-117.0, 44.0),
                (-115.0, 44.0),
                (-115.0, 42.0)
            ]]
        )
    assert "exceeds the maximum safety limit" in str(exc_info.value)

def test_polygon_shapely_parse_error():
    """Verify that a shapely parse failure is handled gracefully."""
    with patch("shapely.geometry.shape", side_effect=ValueError("Parse failed")):
        with pytest.raises(ValidationError) as exc_info:
            Polygon(
                type="Polygon",
                coordinates=[[
                    (-115.0, 42.0),
                    (-115.01, 42.0),
                    (-115.01, 42.01),
                    (-115.0, 42.01),
                    (-115.0, 42.0)
                ]]
            )
        assert "Shapely failed to parse the geometry" in str(exc_info.value)

def test_polygon_empty_geometry():
    """Verify that an empty geometry is rejected."""
    # Create a dummy geometry that returns is_empty = True
    mock_geom = shapely.geometry.Polygon()
    with patch("shapely.geometry.shape", return_value=mock_geom):
        with pytest.raises(ValidationError) as exc_info:
            Polygon(
                type="Polygon",
                coordinates=[[
                    (-115.0, 42.0),
                    (-115.01, 42.0),
                    (-115.01, 42.01),
                    (-115.0, 42.01),
                    (-115.0, 42.0)
                ]]
            )
        assert "Polygon geometry cannot be empty" in str(exc_info.value)

def test_feature_valid():
    """Verify that a valid Feature with geometry and properties parses successfully."""
    poly = Polygon(
        type="Polygon",
        coordinates=[[
            (-115.0, 42.0),
            (-115.01, 42.0),
            (-115.01, 42.01),
            (-115.0, 42.01),
            (-115.0, 42.0)
        ]]
    )
    feature = Feature(
        type="Feature",
        geometry=poly,
        properties={"site_name": "Sagebrush Solar", "capacity_mw": 150}
    )
    assert feature.type == "Feature"
    assert feature.properties["site_name"] == "Sagebrush Solar"
    assert feature.geometry.type == "Polygon"

def test_feature_invalid_type():
    """Verify that a Feature with an invalid type is rejected."""
    poly = Polygon(
        type="Polygon",
        coordinates=[[
            (-115.0, 42.0),
            (-115.01, 42.0),
            (-115.01, 42.01),
            (-115.0, 42.01),
            (-115.0, 42.0)
        ]]
    )
    with pytest.raises(ValidationError) as exc_info:
        Feature(
            type="NotAFeature",
            geometry=poly,
            properties={}
        )
    assert "Type must be exactly 'Feature'" in str(exc_info.value)
