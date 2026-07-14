# Shared Schemas Library Documentation

This document describes the shared Pydantic v2 schemas located in `shared/schemas/` used by the GridPilot swarm agents and APIs. 

These schemas form the cross-cutting typed contracts of the project. They enforce strict field validation, error-handling distinction, and geometric constraints.

---

## 1. Common Schemas (`shared/schemas/common.py`)

### `Source`
Represents a citation or a reference to a data source used by an agent to substantiate its claims.
* **Fields:**
  * `document_name` (`str`): The name of the source document or dataset (required).
  * `section` (`str`, optional): The specific section, clause, paragraph, or page.
  * `snippet` (`str`, optional): The exact text snippet or data retrieved.
  * `uri` (`str`, optional): A URI or link pointing directly to the source.

### `Confidence`
Represents a numeric confidence score for a claim along with its qualitative reasoning.
* **Fields:**
  * `score` (`float`): The confidence score, strictly between `0.0` and `1.0` inclusive (required). Enforced via custom `@field_validator`.
  * `rationale` (`str`): Explanation or justification for the score (required).

### `AgentError`
Represents a structured error encountered during agent execution. Used to distinguish system execution failures (e.g., API timeouts) from low-confidence findings (which are valid outcomes, not exceptions).
* **Fields:**
  * `agent_name` (`str`): The name of the agent encountering the error (required).
  * `error_code` (`str`): Unique error identifier (e.g., `API_TIMEOUT`, `PARSING_ERROR`) (required).
  * `message` (`str`): A detailed human-readable description of the error (required).
  * `details` (`dict`, optional): Extra troubleshooting metadata.

### `AgentInput`
Base class for inputs passed to all GridPilot agents.
* **Fields:**
  * `project_id` (`str`): Unique UUID of the project (required).
  * `study_id` (`str`): Unique UUID of the study run (required).
* **Behavior:** Enforces strict spelling discipline by forbidding extra fields (`extra="forbid"`).

### `AgentOutput`
Base class for outputs returned by all GridPilot agents.
* **Fields:**
  * `confidence` (`float`): Score between `0.0` and `1.0` indicating agent certainty (required). Enforced via custom `@field_validator`.
  * `sources` (`list[Source]`): Citations or references supporting findings.
  * `assumptions` (`list[str]`): List of explicit assumptions made during execution.
  * `raw_model_output` (`str`): Raw LLM completion string stored for auditing (required).
* **Behavior:** Permits downstream agent models to add their own custom fields (`extra="ignore"`).

---

## 2. Geospatial Schemas (`shared/schemas/geo.py`)

All coordinates in these models are represented as `[longitude, latitude]` tuples/lists in accordance with RFC 7946 (GeoJSON).

### `Point`
Represents a GeoJSON Point geometry.
* **Fields:**
  * `type` (`str`): Must be exactly `"Point"`.
  * `coordinates` (`tuple[float, float]`): Order: `(longitude, latitude)`.
* **Validation:** Longitude must be in `[-180.0, 180.0]` and latitude in `[-90.0, 90.0]`.

### `Polygon`
Represents a GeoJSON Polygon geometry.
* **Fields:**
  * `type` (`str`): Must be exactly `"Polygon"`.
  * `coordinates` (`list[list[tuple[float, float]]]`): A list of rings (the first is the exterior boundary, subsequent are holes).
* **Validation & Constraints:**
  * **Closed Rings:** First and last coordinate in each ring must be identical.
  * **Vertices count:** Each ring must contain at least 4 coordinates (3 distinct vertices + 1 closing vertex).
  * **Coordinate Limits:** All coordinates must lie within valid longitude/latitude ranges.
  * **Shapely Integration:** The polygon is loaded into a `shapely` shape to verify:
    * **Validity:** Geometries must be topologically valid (no self-intersections or self-tangencies).
    * **Empty:** Geometries must contain points/area.
    * **Safety Area Limit:** To protect against runaway computational loads during spatial intersections, the polygon area is capped at a maximum of `1.0` square degree (approx. 100km x 100km, or ~10,000 square km).

### `Feature`
Represents a standard GeoJSON Feature wrapping a geometry and properties dictionary.
* **Fields:**
  * `type` (`str`): Must be exactly `"Feature"`.
  * `geometry` (`Polygon`): The polygon geometry.
  * `properties` (`dict`): Arbitrary metadata properties.

---

## 3. Usage Examples

### Importing Schemas
Import schemas directly from the `shared.schemas` namespace:
```python
from shared.schemas import Source, Confidence, Polygon, AgentOutput
```

### Instantiating Common Models
```python
# Validating confidence score
try:
    confidence = Confidence(score=0.85, rationale="Matched tariff text exactly.")
except ValidationError as e:
    print(f"Validation failed: {e}")
```

### Instantiating and Validating GeoJSON
```python
# Valid GeoJSON Polygon
valid_polygon = Polygon(
    type="Polygon",
    coordinates=[[
        (-115.0, 42.0),
        (-115.01, 42.0),
        (-115.01, 42.01),
        (-115.0, 42.01),
        (-115.0, 42.0)
    ]]
)

# Invalid Polygon (Self-intersecting figure-8, rejected by Shapely validator)
try:
    invalid_polygon = Polygon(
        type="Polygon",
        coordinates=[[
            (0.0, 0.0),
            (2.0, 2.0),
            (2.0, 0.0),
            (0.0, 2.0),
            (0.0, 0.0)
        ]]
    )
except ValidationError as e:
    print(e)
    # Output includes: "Invalid polygon geometry (self-intersecting or invalid boundary)"
```
