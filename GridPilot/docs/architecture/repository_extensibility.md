# Repository Extensibility Strategy

> **Status**: Design document — do NOT implement.
> **Audience**: Architecture team.

This document describes future extension patterns for the GridPilot
repository layer.  Each pattern is described with motivation, API design,
and migration path.  None of these should be implemented until the
corresponding milestone approves them.

---

## 1. Specification Pattern

### Motivation

As query complexity grows, the repository layer accumulates methods like
`list_by_status()`, `list_by_region()`, `list_by_status_and_region()`,
etc.  The Specification pattern composes filter predicates without
method explosion.

### Proposed API

```python
from services.db.repositories.specs import Spec, StatusSpec, RegionSpec

# Composable specifications
spec = StatusSpec("submitted") & RegionSpec(region_id)
projects = await project_repo.find(spec, limit=50)
```

### Implementation Sketch

```python
class Spec(ABC):
    @abstractmethod
    def to_clause(self) -> ClauseElement:
        ...

    def __and__(self, other: "Spec") -> "AndSpec":
        return AndSpec(self, other)

    def __or__(self, other: "Spec") -> "OrSpec":
        return OrSpec(self, other)

class StatusSpec(Spec):
    def __init__(self, status: str):
        self._status = status
    def to_clause(self):
        return Project.status == self._status
```

### Migration Path

1. Add `find(spec, limit, offset)` to `BaseRepository`.
2. Create `specs.py` module with common specifications.
3. Existing methods (`list_by_status`) delegate to `find()` internally.
4. No breaking changes to existing interfaces.

---

## 2. Query Objects

### Motivation

For complex, multi-criteria queries that go beyond the Specification
pattern (e.g. joins, aggregations, subqueries), a Query Object
encapsulates the entire query construction.

### Proposed API

```python
query = StudySummaryQuery(
    project_id=project_id,
    status_filter=["running", "pending_review"],
    include_agent_stats=True,
)
results = await study_repo.execute_query(query)
```

### Migration Path

1. Define `Query[TResult]` base class.
2. Add `execute_query(query)` to `BaseRepository`.
3. Query objects live in `services/db/queries/`.
4. Existing methods remain unchanged.

---

## 3. Read Models (Projections)

### Motivation

`get_project_summary()` returns a `Dict`.  As the number of projections
grows, type-safe read models provide better documentation and IDE
support.

### Proposed API

```python
@dataclass(frozen=True)
class ProjectSummary:
    id: uuid.UUID
    name: str
    status: str
    study_count: int

summary: Optional[ProjectSummary] = await project_repo.get_summary(pid)
```

### Migration Path

1. Define read-model dataclasses in `services/db/read_models/`.
2. Update projection methods to return typed read models.
3. Dict-based methods are deprecated but remain for backward compat.

---

## 4. CQRS Compatibility

### Motivation

As the system scales, separating read and write paths enables
independent optimisation.  The current repository design already
supports this partially through projection methods.

### Current CQRS-Ready Patterns

```
┌───────────────────────────────────────────────┐
│                Current Design                  │
├───────────────────────────────────────────────┤
│ Write Path:                                    │
│   add(), remove(), update_status()             │
│   → Hits primary database                      │
│   → Returns session-bound entities             │
│                                                │
│ Read Path:                                     │
│   get_project_summary(), list_by_status()      │
│   → Could hit read replica                     │
│   → Returns Dict or lightweight projection     │
└───────────────────────────────────────────────┘
```

### Future CQRS Evolution

```
┌────────────────────┐     ┌────────────────────┐
│  Command Repository │     │   Query Repository  │
│  (Write-optimised)  │     │  (Read-optimised)   │
│  Primary DB         │     │  Read Replica / View │
│  Full ORM entities  │     │  Projections only    │
└────────────────────┘     └────────────────────┘
```

### Migration Path

1. Split interfaces: `IProjectCommandRepo` / `IProjectQueryRepo`.
2. Query repo connects to read replica.
3. Command repo connects to primary.
4. Service layer uses both through dependency injection.

---

## 5. Repository Metrics

### Motivation

Production observability requires per-repository, per-method metrics.

### Proposed Design

```python
class InstrumentedRepository(BaseRepository[T]):
    """Decorator that wraps repository methods with OpenTelemetry spans."""

    async def get_by_id(self, entity_id: uuid.UUID) -> Optional[T]:
        with tracer.start_as_current_span("repo.get_by_id") as span:
            span.set_attribute("entity.type", self._model_class.__name__)
            return await super().get_by_id(entity_id)
```

### Metrics to Collect

| Metric | Type | Labels |
|---|---|---|
| `repo.operation.duration` | Histogram | `method`, `entity`, `status` |
| `repo.operation.count` | Counter | `method`, `entity`, `status` |
| `repo.error.count` | Counter | `method`, `entity`, `error_type` |
| `db.pool.active_connections` | Gauge | `pool_name` |

### Migration Path

1. Add `opentelemetry-api` dependency.
2. Create `InstrumentedRepository` mixin.
3. Apply via composition in dependency injection.

---

## 6. Streaming APIs (Async Iterators)

### Motivation

For large result sets (e.g. exporting all audit logs for a study),
loading everything into memory is wasteful.  Async iterators enable
streaming processing.

### Proposed API

```python
async for log in audit_repo.stream_logs(study_id):
    await export_service.write_log(log)
```

### Implementation Sketch

```python
async def stream_logs(
    self, study_id: uuid.UUID, batch_size: int = 100
) -> AsyncIterator[AuditLog]:
    cursor_time = None
    cursor_id = None
    while True:
        batch = await self.list_logs_cursor(
            study_id, limit=batch_size,
            cursor_time=cursor_time, cursor_id=cursor_id,
        )
        if not batch:
            break
        for log in batch:
            yield log
        cursor_time = batch[-1].created_at
        cursor_id = batch[-1].id
```

### Migration Path

1. Add `stream_*()` methods to repositories that manage large collections.
2. Underlying cursor pagination already exists.
3. No database schema changes required.

---

## 7. Naming Conventions for Extensions

| Pattern | Convention | Example |
|---|---|---|
| Specification | `{Field}Spec` | `StatusSpec`, `RegionSpec` |
| Query Object | `{Entity}{Purpose}Query` | `StudySummaryQuery` |
| Read Model | `{Entity}{View}` | `ProjectSummary`, `StudyOverview` |
| Metric | `repo.{method}.{metric}` | `repo.get_by_id.duration` |
| Stream | `stream_{collection}()` | `stream_logs()` |
