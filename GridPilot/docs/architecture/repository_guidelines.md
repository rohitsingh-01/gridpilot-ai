# Repository Development Guidelines

> **Audience**: All GridPilot developers.
> **Scope**: Persistence layer only (`services/db/repositories/`).

---

## 1. What Is a Repository?

A repository is the **single access point** for persisting and retrieving
a specific **aggregate root** and its child entities.  It translates between
the application's domain language and SQLAlchemy's ORM.

```
┌──────────────────────┐
│  Service / Agent      │   ← uses IStudyRepository (interface)
├──────────────────────┤
│  Repository           │   ← uses AsyncSession, SQLAlchemy ORM
├──────────────────────┤
│  Database (Postgres)  │
└──────────────────────┘
```

---

## 2. Repository Responsibilities

### ✅ Repositories MUST

| Responsibility | Example |
|---|---|
| Execute queries using `select()`, `update()`, `delete()`, `insert()` | `await self._session.execute(select(User).where(...))` |
| Map ORM entities to/from the database | `self._session.add(entity)` |
| Translate SQLAlchemy exceptions into domain exceptions | `raise EntityNotFoundError(...)` |
| Call `flush()` to populate server-generated values (IDs, timestamps) | `await self._session.flush()` |
| Use eager-loading strategies (`selectinload`, `joinedload`) | `.options(selectinload(Study.agent_runs))` |
| Return typed entities or `None` | `-> Optional[User]` |
| Be fully async | `async def get_by_id(...)` |
| Be fully type-hinted | Every parameter and return value |
| Have comprehensive docstrings | Parameters, returns, raises, notes |
| Implement their corresponding interface | `class UserRepository(BaseRepository[User], IUserRepository)` |

### ❌ Repositories must NEVER

| Prohibition | Reason |
|---|---|
| Call `session.commit()` | Transaction lifecycle is owned by the service layer / `get_db()` |
| Call `session.rollback()` | Transaction lifecycle is owned by the service layer / `get_db()` |
| Create sessions (`AsyncSessionLocal()`) | Session creation is a cross-cutting concern |
| Close sessions (`session.close()`) | Session lifecycle is managed externally |
| Contain business logic | Repositories are persistence-only; business rules belong in services |
| Validate business rules | Validation belongs in Pydantic schemas or service-layer validators |
| Import FastAPI | No HTTP concerns in persistence layer |
| Import LangGraph | No AI workflow concerns in persistence layer |
| Import AI model clients | No API call logic in persistence layer |
| Contain HTTP request/response logic | Repositories have no knowledge of HTTP |
| Emit events or notifications | Event dispatching belongs in the service layer |
| Access environment variables | Configuration belongs in `session.py` or settings modules |
| Import from other repositories | Repositories must not cross aggregate boundaries |

---

## 3. Transaction Boundaries

```python
# ✅ CORRECT — service layer owns the transaction
async def approve_study(study_id: uuid.UUID, reviewer_id: uuid.UUID):
    async with get_db() as session:  # commits on success, rolls back on error
        study_repo = StudyRepository(session)
        audit_repo = AuditLogRepository(session)

        study = await study_repo.get_by_id(study_id)
        study.status = "approved"
        await session.flush()

        await audit_repo.create_log(
            actor_type="human",
            actor_name=str(reviewer_id),
            action="study.approved",
            detail_json={"study_id": str(study_id)},
            study_id=study_id,
        )
        # get_db() commits here if no exception was raised

# ❌ WRONG — repository commits internally
class BadRepository:
    async def save(self, entity):
        self._session.add(entity)
        await self._session.commit()  # FORBIDDEN
```

---

## 4. Error Handling Contract

All SQLAlchemy exceptions must be caught and translated:

| SQLAlchemy Exception | Domain Exception |
|---|---|
| `IntegrityError` (UNIQUE) | `EntityDuplicateError` |
| `IntegrityError` (CHECK/FK/NOT-NULL) | `ConstraintViolationError` |
| `DBAPIError` | `ConstraintViolationError` or `RepositoryError` |
| Not found (zero rows) | `EntityNotFoundError` or return `None` |

Use `_wrap_db_error()` from `BaseRepository` for consistent translation.

---

## 5. Interface-Driven Design

Every aggregate-root repository has a corresponding interface (ABC):

| Interface | Concrete | File |
|---|---|---|
| `IUserRepository` | `UserRepository` | `user.py` |
| `IUtilityRegionRepository` | `UtilityRegionRepository` | `region.py` |
| `IProjectRepository` | `ProjectRepository` | `project.py` |
| `IStudyRepository` | `StudyRepository` | `study.py` |
| `IAuditLogRepository` | `AuditLogRepository` | `audit.py` |

Services and agents depend on **interfaces only**, never on concrete classes.
This enables testing with mock repositories.

---

## 6. Adding a New Repository

1. Identify the aggregate root and its children.
2. Add the interface to `interfaces.py`.
3. Create the concrete class inheriting `BaseRepository[T]` and the interface.
4. Register it in `__init__.py`.
5. Write integration tests in `test_repositories.py`.
6. Verify commit prohibition test still passes.

---

## 7. Session-Binding Rules

| Method Type | Session-Bound? | Notes |
|---|---|---|
| `get_by_id()` | Yes | Lazy-load access works while session is open |
| `get_with_*()` (eager) | Yes | Children are pre-loaded |
| `add()` | Yes | Entity has populated ID after flush |
| Projection queries | **No** | Returns `Dict`, not ORM entity |
| `remove()` | N/A | Entity is deleted from session |

---

## 8. File Organisation

```
services/db/
├── exceptions.py          # Domain exception hierarchy
├── models.py              # SQLAlchemy models (15 tables)
├── session.py             # AsyncEngine + session factory
├── repositories/
│   ├── __init__.py        # Public API re-exports
│   ├── interfaces.py      # Abstract interfaces (ABCs)
│   ├── base.py            # BaseRepository[T]
│   ├── user.py            # UserRepository
│   ├── region.py          # UtilityRegionRepository
│   ├── project.py         # ProjectRepository
│   ├── study.py           # StudyRepository
│   └── audit.py           # AuditLogRepository
└── tests/
    ├── test_models.py
    ├── test_migrations.py
    └── test_repositories.py
```
