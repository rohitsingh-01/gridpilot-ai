# Repository Code Review Checklist

> **Use this checklist** when reviewing any PR that creates or modifies
> a repository class in `services/db/repositories/`.

---

## Architecture & Design

- [ ] **No business logic** — Repository contains only persistence
      operations; business rules belong in the service layer.
- [ ] **Uses repository interface** — Concrete class implements the
      corresponding ABC from `interfaces.py`.
- [ ] **Single aggregate responsibility** — Repository manages one
      aggregate root and its children only.
- [ ] **No cross-aggregate imports** — Repository does not import
      from other repositories.

---

## Transaction Boundaries

- [ ] **No `commit()`** — Repository never calls `session.commit()`.
- [ ] **No `rollback()`** — Repository never calls `session.rollback()`.
- [ ] **No session creation** — Repository does not call
      `AsyncSessionLocal()` or `sessionmaker()`.
- [ ] **No session closure** — Repository does not call
      `session.close()`.
- [ ] **Uses `flush()` for ID population** — After `session.add()`,
      calls `flush()` to populate server-generated values.

---

## Error Handling

- [ ] **SQLAlchemy exceptions wrapped** — All `IntegrityError` and
      `DBAPIError` exceptions are caught and translated into domain
      exceptions (`EntityNotFoundError`, `EntityDuplicateError`,
      `ConstraintViolationError`, `RepositoryError`).
- [ ] **Uses `_wrap_db_error()`** — Consistent translation via the
      base class helper method.
- [ ] **No bare `except`** — Only specific exception types are caught.
- [ ] **Domain exceptions re-raised** — `EntityNotFoundError`,
      `ConcurrencyError`, etc. are not wrapped again.

---

## Query Quality

- [ ] **Proper loading strategy** — Uses `selectinload()` for
      one-to-many, `joinedload()` for many-to-one (never lazy load).
- [ ] **No N+1 queries** — Collections accessed by the caller are
      eagerly loaded in the repository query.
- [ ] **Projection used where appropriate** — Lightweight read methods
      return `Dict` instead of full ORM entities.
- [ ] **Pagination implemented** — List methods accept `limit`/`offset`
      or cursor parameters.
- [ ] **Cursor pagination for high-volume tables** — Audit logs and
      other append-only tables use seek pagination.
- [ ] **Bulk operations for batch inserts** — 10+ rows use
      `session.execute(insert(Model), payload)`.

---

## Performance Reviewed

- [ ] **Indexes exist** — Queries filter/sort on indexed columns.
- [ ] **No SELECT * in projections** — Only needed columns are selected.
- [ ] **No unnecessary eager loading** — Only required relationships
      are loaded.
- [ ] **Large JSONB columns avoided in list queries** — Use projections
      to skip heavy columns when not needed.

---

## Code Quality

- [ ] **Async only** — All public methods are `async def`.
- [ ] **Fully type-hinted** — Every parameter, return type, and
      optional field is typed.
- [ ] **Documentation complete** — Every public method has a docstring
      specifying: purpose, parameters, return value, possible exceptions,
      transaction expectations, eager-loading behaviour, and whether
      returned entities remain session-bound.
- [ ] **Consistent naming** — Methods follow the naming standard
      (see `naming_conventions` below).

---

## Testing

- [ ] **Integration tests exist** — Every public method has at least
      one test in `test_repositories.py`.
- [ ] **Happy path tested** — Standard CRUD operations work correctly.
- [ ] **Error paths tested** — Not-found, duplicate, and constraint
      violations are tested.
- [ ] **Transaction isolation** — Tests use rollback-wrapped sessions
      so they leave no artefacts.
- [ ] **Commit prohibition verified** — The static analysis test in
      `TestCommitProhibition` passes.

---

## Naming Conventions

| Pattern | Example | When To Use |
|---|---|---|
| `get_by_{field}()` | `get_by_email()` | Single-entity lookup by unique field |
| `get_by_id()` | `get_by_id()` | Primary key lookup |
| `get_with_{children}()` | `get_with_studies()` | Eager-loaded fetch |
| `get_full_{aggregate}_state()` | `get_full_study_state()` | Load all children |
| `get_{entity}_summary()` | `get_project_summary()` | Lightweight projection |
| `list_{collection}()` | `list_regions()` | Paginated list (all) |
| `list_by_{filter}()` | `list_by_status()` | Paginated filtered list |
| `list_{collection}_cursor()` | `list_logs_cursor()` | Cursor-paginated list |
| `add()` | `add(entity)` | Insert new entity |
| `add_{child}()` | `add_agent_run()` | Insert child entity |
| `save_{result}()` | `save_power_flow_result()` | Persist read-model result |
| `update_{field}()` | `update_status()` | Targeted field update |
| `remove()` | `remove(entity_id)` | Delete by ID |
| `delete_{criteria}()` | `delete_expired_sessions()` | Bulk conditional delete |
| `bulk_add_{children}()` | `bulk_add_environmental_flags()` | Batch insert |
| `create_{child}()` | `create_session()` | Factory-style child insert |
| `create_log()` | `create_log()` | Append-only insert |

---

## Final Sign-Off

- [ ] **All checks above pass**
- [ ] **42/42 existing tests still pass**
- [ ] **No project behaviour changed**
