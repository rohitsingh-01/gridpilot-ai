# Repository Naming Conventions

> **Audience**: All GridPilot developers.
> **Scope**: Method and class naming within `services/db/repositories/`.

---

## 1. Class Naming

| Pattern | Example | Rule |
|---|---|---|
| Interface | `I{Entity}Repository` | Prefix with `I`, suffix with `Repository` |
| Concrete | `{Entity}Repository` | No prefix, suffix with `Repository` |
| Base | `BaseRepository[T]` | Generic type parameter |

---

## 2. Method Naming Standards

### Read Operations

| Pattern | Signature | Semantics |
|---|---|---|
| `get_by_id()` | `(entity_id: UUID) -> Optional[T]` | PK lookup, returns `None` if not found |
| `get_by_{field}()` | `({field}: type) -> Optional[T]` | Unique-field lookup |
| `get_with_{children}()` | `(id: UUID) -> Optional[T]` | Eager-loads named children |
| `get_full_{aggregate}_state()` | `(id: UUID) -> Optional[T]` | Eager-loads ALL children |
| `get_{entity}_summary()` | `(id: UUID) -> Optional[Dict]` | Lightweight projection (not session-bound) |
| `list_all()` | `(limit, offset) -> List[T]` | Offset-paginated full list |
| `list_{collection}()` | `(limit, offset) -> List[T]` | Named convenience for `list_all()` |
| `list_by_{filter}()` | `({filter}, limit, offset) -> List[T]` | Filtered offset-paginated list |
| `list_{collection}_cursor()` | `(id, limit, cursor_*) -> List[T]` | Cursor-paginated list |

**Rules**:
- `get_*` returns a **single entity** or `None`
- `list_*` returns a **list** (possibly empty)
- Never return bare `Row` objects — return typed entities or `Dict`

### Write Operations

| Pattern | Signature | Semantics |
|---|---|---|
| `add()` | `(entity: T) -> T` | Insert pre-constructed entity (flush, no commit) |
| `add_{child}()` | `(parent_id, **fields) -> Child` | Insert child entity with field arguments |
| `create_{child}()` | `(parent_id, **fields) -> Child` | Factory-style child creation (synonym of `add_*`) |
| `create_log()` | `(**fields) -> AuditLog` | Append-only insert |
| `save_{result}()` | `(parent_id, **fields) -> Result` | Persist a read-model / denormalised result |
| `update_{field}()` | `(id, current, new) -> T` | Targeted field update (may use optimistic guard) |
| `remove()` | `(entity_id: UUID) -> bool` | Soft-or-hard delete by PK |

**Rules**:
- `add_*` and `create_*` both mean "insert" — use `create_*` when the
  method constructs the entity internally from scalar arguments
- `save_*` is used for read-model results (PowerFlowResult, etc.)
- `update_*` is used for targeted field mutations

### Delete Operations

| Pattern | Signature | Semantics |
|---|---|---|
| `remove()` | `(entity_id: UUID) -> bool` | Delete single entity by PK |
| `delete_{criteria}()` | `(**criteria) -> int` | Bulk conditional delete, returns count |

**Rules**:
- `remove()` returns `bool` (found or not)
- `delete_*` returns `int` (count deleted)
- Audit logs have **no** delete methods

### Bulk Operations

| Pattern | Signature | Semantics |
|---|---|---|
| `bulk_add_{children}()` | `(parent_id, items: List[Dict]) -> int` | Batch insert, returns count |
| `bulk_update_{field}()` | `(criteria, new_value) -> int` | Batch update, returns count |
| `bulk_delete_{criteria}()` | `(criteria) -> int` | Batch delete, returns count |

**Rules**:
- Bulk methods accept `List[Dict]` for inserts (not ORM entities)
- Always return the count of affected rows

---

## 3. Parameter Naming

| Parameter | Convention | Example |
|---|---|---|
| Primary key | `entity_id`, `{entity}_id` | `study_id`, `user_id` |
| Pagination | `limit`, `offset` | `limit=50, offset=0` |
| Cursor | `cursor_time`, `cursor_id` | Compound cursor components |
| Status filter | `status` | `status="submitted"` |
| Optimistic guard | `current_status`, `new_status` | Used in `update_status()` |

---

## 4. Return Type Conventions

| Method Type | Return Type | Session-Bound? |
|---|---|---|
| Single entity | `Optional[T]` | Yes |
| Entity list | `List[T]` | Yes |
| Projection | `Optional[Dict[str, Any]]` | **No** |
| Insert / update | `T` or `ChildEntity` | Yes |
| Delete | `bool` (single) or `int` (bulk) | N/A |

---

## 5. Exception Naming

| Exception | When Raised |
|---|---|
| `EntityNotFoundError` | Entity does not exist (in methods that require it) |
| `EntityDuplicateError` | UNIQUE constraint violation |
| `ConstraintViolationError` | CHECK, FK, or NOT-NULL violation |
| `ConcurrencyError` | Optimistic locking guard failed |
| `RepositoryError` | Catch-all for unexpected database errors |

---

## 6. File Naming

| File | Contains |
|---|---|
| `interfaces.py` | All abstract interfaces |
| `base.py` | `BaseRepository[T]` |
| `{aggregate}.py` | Concrete repository for that aggregate |
| `__init__.py` | Public API re-exports |

**Aggregate file names** use the primary entity's short name:
- `user.py` (not `user_repository.py`)
- `region.py` (not `utility_region_repository.py`)
- `study.py` (not `study_repository.py`)
- `audit.py` (not `audit_log_repository.py`)
- `project.py` (not `project_repository.py`)
