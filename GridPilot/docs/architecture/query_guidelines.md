# Query Performance Guidelines

> **Audience**: All GridPilot developers writing repository methods.
> **Scope**: SQLAlchemy 2.0 async ORM queries.

---

## 1. Query Construction

### `select()` — Fetching Entities

```python
# Full entity (session-bound, all columns)
result = await session.execute(select(User).where(User.id == user_id))
user = result.scalar_one_or_none()
```

Use `select(Model)` when the caller needs the full ORM entity for
subsequent mutations or relationship traversal.

### Projection Queries — Lightweight Reads

```python
# Select only the columns you need
result = await session.execute(
    select(Project.id, Project.name, Project.status)
    .where(Project.id == project_id)
)
row = result.first()  # Returns a Row, NOT an ORM entity
summary = {"id": row.id, "name": row.name, "status": row.status}
```

Use projections when:
- The caller only needs a subset of columns
- The result is serialised to JSON immediately
- No mutations or relationship access is needed
- Performance is critical (avoids loading unused JSONB blobs)

---

## 2. Eager Loading Strategies

### `selectinload()` — Recommended Default

```python
select(Study)
    .options(selectinload(Study.agent_runs))
```

**How it works**: Issues a second `SELECT ... WHERE study_id IN (...)` query.

| Pros | Cons |
|---|---|
| No Cartesian product explosion | Extra query per collection |
| Works well with all relationship types | Slight overhead for single-entity loads |
| Predictable query count | |

**When to use**: Most one-to-many relationships.

### `joinedload()` — Use Sparingly

```python
select(Session)
    .options(joinedload(Session.user))
```

**How it works**: Issues a single `JOIN` in the original query.

| Pros | Cons |
|---|---|
| Single query | Cartesian product with multiple collections |
| Lowest latency for single relationships | Row duplication with one-to-many |
| | Harder to debug with complex joins |

**When to use**: Many-to-one and one-to-one relationships only.

### Lazy Loading — Avoid in Async

```python
# ❌ DANGEROUS — will raise MissingGreenlet in async context
user = await session.execute(select(User).where(...))
user.sessions  # Attempts lazy load → FAILS in async
```

In async SQLAlchemy, lazy loading raises `MissingGreenlet` because
lazy loads require a synchronous database call.  Always use explicit
eager-loading options.

---

## 3. Pagination Strategies

### Offset Pagination

```python
select(Project)
    .order_by(Project.created_at.desc())
    .offset(offset)
    .limit(limit)
```

| Pros | Cons |
|---|---|
| Simple to implement | O(offset + limit) performance |
| Supports "jump to page N" | Inconsistent results on concurrent writes |
| Familiar API | Degrades on large tables |

**When to use**: Tables with bounded size (users, regions, projects).

### Cursor-Based (Seek) Pagination

```python
stmt = select(AuditLog).where(AuditLog.study_id == study_id)

if cursor_time and cursor_id:
    stmt = stmt.where(
        (AuditLog.created_at < cursor_time) |
        ((AuditLog.created_at == cursor_time) & (AuditLog.id < cursor_id))
    )

stmt = stmt.order_by(
    AuditLog.created_at.desc(), AuditLog.id.desc()
).limit(limit)
```

| Pros | Cons |
|---|---|
| O(1) per page regardless of table size | Cannot "jump to page N" |
| Consistent results on concurrent writes | Requires compound cursor |
| Ideal for ever-growing tables | Slightly more complex API |

**When to use**: Audit logs, agent runs, any append-only table.

---

## 4. Bulk Operations

### Bulk Insert

```python
# ✅ Single round-trip — O(1) queries regardless of batch size
payload = [{"study_id": sid, "flag_type": "wetland", ...} for ...]
await session.execute(insert(EnvironmentalFlag), payload)
await session.flush()
```

**When to use**: Inserting 10+ rows at once (e.g. environmental flags
from a GIS analysis).

### Bulk Update

```python
# ✅ Single UPDATE statement
await session.execute(
    update(AgentRun)
    .where(AgentRun.study_id == study_id, AgentRun.status == "running")
    .values(status="cancelled")
)
```

**When to use**: Updating multiple rows with the same value change
(e.g. cancelling all running agents in a study).

---

## 5. Anti-Patterns

### ❌ N+1 Queries

```python
# BAD — issues 1 query for studies + N queries for agent_runs
studies = await repo.list_all()
for study in studies:
    runs = study.agent_runs  # lazy load → N+1

# GOOD — eager-load in the original query
studies = await session.execute(
    select(Study).options(selectinload(Study.agent_runs))
)
```

### ❌ SELECT * When Only a Few Columns Are Needed

```python
# BAD — loads the entire Study including large JSONB columns
study = await repo.get_by_id(study_id)
return {"id": study.id, "status": study.status}

# GOOD — projection query avoids loading state_snapshot JSONB
result = await session.execute(
    select(Study.id, Study.status).where(Study.id == study_id)
)
```

### ❌ Unnecessary Eager Loading

```python
# BAD — loads 7 child collections when only agent_runs are needed
study = await repo.get_full_study_state(study_id)
return study.agent_runs

# GOOD — load only what you need
result = await session.execute(
    select(Study)
    .where(Study.id == study_id)
    .options(selectinload(Study.agent_runs))
)
```

### ❌ Offset Pagination on Large Tables

```python
# BAD — page 10000 requires scanning 500,000 rows
logs = await repo.list_logs_for_study(study_id, limit=50, offset=500_000)

# GOOD — cursor pagination is O(1) regardless of page number
logs = await repo.list_logs_cursor(study_id, limit=50, cursor_time=..., cursor_id=...)
```

### ❌ Loading Entities Just to Delete Them

```python
# BAD — fetches the entity, then deletes it (2 queries)
entity = await session.execute(select(Session).where(Session.id == sid))
await session.delete(entity.scalar_one())

# GOOD — single DELETE statement (1 query)
await session.execute(delete(Session).where(Session.id == sid))
```

---

## 6. Index Usage Reference

| Table | Index | Used By |
|---|---|---|
| `users` | `users_email_key` (UNIQUE) | `get_by_email()` |
| `sessions` | `idx_sessions_user_id` | Session FK lookups |
| `sessions` | `idx_sessions_expires_at` | `delete_expired_sessions()` |
| `grid_nodes` | `idx_grid_nodes_region_id` | `get_with_network()` |
| `grid_nodes` | `uq_grid_nodes_region_node` (UNIQUE) | `get_node_by_key()` |
| `projects` | `idx_projects_status` | `list_by_status()` |
| `studies` | `idx_studies_project_id` | Study FK lookups |
| `studies` | `idx_studies_state_snapshot_gin` | JSONB queries (future) |
| `agent_runs` | `idx_agent_runs_study_id` | Agent run lookups |
| `audit_log` | `idx_audit_log_study_id` | `list_logs_for_study()` |
| `audit_log` | `idx_audit_log_created_at` | `list_logs_cursor()` |
