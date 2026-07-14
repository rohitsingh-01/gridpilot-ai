# Technical Debt Register

> **Last updated**: Milestone 6 Engineering Hardening
>
> This document tracks all known technical debt in the GridPilot project.
> Each item includes priority, reason, expected milestone for resolution,
> and estimated impact.

---

## Active Technical Debt

### TD-001: `datetime.utcnow()` Deprecation Warnings

| Field | Value |
|---|---|
| **Priority** | Medium |
| **Location** | `services/db/models.py` — all 15 model classes |
| **Reason** | SQLAlchemy model `default=datetime.utcnow` triggers Python 3.12+ deprecation warnings. `datetime.utcnow()` is scheduled for removal in a future Python version. |
| **Impact** | 132 deprecation warnings per test run. No functional impact currently, but will break when Python removes `utcnow()`. |
| **Resolution** | Replace `default=datetime.utcnow` with `default=lambda: datetime.now(timezone.utc)` across all models. |
| **Expected Milestone** | Milestone 7 or dedicated cleanup sprint |
| **Estimated Effort** | 1 hour |

---

### TD-002: Module-Level Engine Instantiation in `session.py`

| Field | Value |
|---|---|
| **Priority** | Low |
| **Location** | `services/db/session.py` |
| **Reason** | `engine` and `AsyncSessionLocal` are created at import time. This means importing `session.py` anywhere (including tests) immediately creates a connection pool to the production database URL. |
| **Impact** | Test isolation requires overriding `DATABASE_URL` via environment variables before import. Difficult to use multiple databases in the same process. |
| **Resolution** | Move to a factory function (`get_engine(url)`) or use FastAPI's dependency injection with `Depends()`. |
| **Expected Milestone** | Milestone 8 (FastAPI integration) |
| **Estimated Effort** | 2 hours |

---

### TD-003: No `updated_at` Auto-Update on `Project`

| Field | Value |
|---|---|
| **Priority** | Medium |
| **Location** | `services/db/models.py` — `Project.updated_at` |
| **Reason** | The `updated_at` column has `default=datetime.utcnow` but no `onupdate` trigger or SQLAlchemy event listener to auto-update it on modification. |
| **Impact** | `updated_at` reflects creation time, not last modification time, unless explicitly set by callers. |
| **Resolution** | Add `onupdate=lambda: datetime.now(timezone.utc)` to the column definition, or create a PostgreSQL trigger. |
| **Expected Milestone** | Milestone 7 |
| **Estimated Effort** | 30 minutes |

---

### TD-004: Lazy Imports in `AuditLogRepository`

| Field | Value |
|---|---|
| **Priority** | Low |
| **Location** | `services/db/repositories/audit.py` — exception handlers |
| **Reason** | Exception classes are imported inside `except` blocks (`from services.db.exceptions import ...`) rather than at module level. This was done to avoid circular imports that don't actually exist. |
| **Impact** | Minor performance overhead on every exception. Inconsistent with other repositories. |
| **Resolution** | Move imports to module level, consistent with `base.py`. |
| **Expected Milestone** | Next cleanup sprint |
| **Estimated Effort** | 15 minutes |

---

### TD-005: No Connection Pool Monitoring

| Field | Value |
|---|---|
| **Priority** | Low |
| **Location** | `services/db/session.py` |
| **Reason** | No metrics are collected on connection pool utilisation, wait times, or overflow events. |
| **Impact** | In production, connection exhaustion would be invisible until queries start timing out. |
| **Resolution** | Add SQLAlchemy pool event listeners that emit metrics to OpenTelemetry. |
| **Expected Milestone** | Milestone 10+ (production hardening) |
| **Estimated Effort** | 4 hours |

---

## Future Improvements

### FI-001: Repository Metrics & OpenTelemetry

| Field | Value |
|---|---|
| **Priority** | Medium |
| **Reason** | Repository operations have no observability. In production, slow queries, high error rates, and throughput degradation are invisible. |
| **Expected Milestone** | Milestone 10+ |
| **Estimated Impact** | Enables proactive performance monitoring, SLO tracking, and alert-based incident response. |

**Planned capabilities**:
- Per-method latency histograms
- Error rate counters by exception type
- Query count per request
- Connection pool saturation gauge

---

### FI-002: Repository Query Timing

| Field | Value |
|---|---|
| **Priority** | Medium |
| **Reason** | Individual query execution times are not measured. Slow queries can only be detected via PostgreSQL `pg_stat_statements`. |
| **Expected Milestone** | Milestone 10+ |
| **Estimated Impact** | Enables application-level slow query detection and alerting. |

**Planned approach**: Decorator-based timing on repository methods that logs queries exceeding a configurable threshold.

---

### FI-003: Distributed Tracing

| Field | Value |
|---|---|
| **Priority** | Low |
| **Reason** | Repository calls are not linked to upstream HTTP requests or LangGraph agent steps. |
| **Expected Milestone** | Milestone 11+ |
| **Estimated Impact** | Enables end-to-end request tracing from API → service → repository → database. |

---

### FI-004: Query Specification Pattern

| Field | Value |
|---|---|
| **Priority** | Low |
| **Reason** | Complex filtering logic (e.g. "find all projects in region X with status Y and technology Z") currently requires adding new repository methods for each combination. |
| **Expected Milestone** | Milestone 9+ |
| **Estimated Impact** | Enables composable, reusable query filters without method explosion. |

---

### FI-005: Unit of Work Abstraction

| Field | Value |
|---|---|
| **Priority** | Low |
| **Reason** | Currently, services manually instantiate repositories with the same session. A Unit of Work would provide a single entry point that guarantees all repositories share the same transaction. |
| **Expected Milestone** | Milestone 9+ |
| **Estimated Impact** | Simplifies service-layer code and eliminates the risk of accidentally using different sessions for cross-aggregate operations. |

---

### FI-006: Read-Replica Routing

| Field | Value |
|---|---|
| **Priority** | Low |
| **Reason** | All queries currently hit the primary database. Read-heavy operations (list queries, projections) could be routed to read replicas. |
| **Expected Milestone** | Post-hackathon (production scaling) |
| **Estimated Impact** | Reduces primary database load by 60–80% in read-heavy workloads. |
