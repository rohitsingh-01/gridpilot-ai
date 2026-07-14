"""
Custom repository exception hierarchy for GridPilot.

All database-layer exceptions are translated into these domain-specific
exceptions so that SQLAlchemy implementation details never leak into
application services, agents, or API layers.
"""


class RepositoryError(Exception):
    """Base exception for all repository operations.

    Services should catch this as the broadest persistence error.
    """

    def __init__(self, message: str = "A repository error occurred.") -> None:
        self.message = message
        super().__init__(self.message)


class EntityNotFoundError(RepositoryError):
    """Raised when a requested entity does not exist in the database."""

    def __init__(self, entity_type: str, entity_id: object) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with id '{entity_id}' not found.")


class EntityDuplicateError(RepositoryError):
    """Raised when an insert or update violates a UNIQUE constraint."""

    def __init__(self, entity_type: str, detail: str = "") -> None:
        self.entity_type = entity_type
        msg = f"Duplicate {entity_type}."
        if detail:
            msg += f" Detail: {detail}"
        super().__init__(msg)


class ConstraintViolationError(RepositoryError):
    """Raised when a CHECK, FK, or NOT-NULL constraint is violated."""

    def __init__(self, detail: str = "") -> None:
        msg = "Database constraint violation."
        if detail:
            msg += f" Detail: {detail}"
        super().__init__(msg)


class ConcurrencyError(RepositoryError):
    """Raised when an optimistic-concurrency check fails (zero rows updated)."""

    def __init__(self, entity_type: str, entity_id: object) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(
            f"Concurrent modification detected on {entity_type} "
            f"with id '{entity_id}'. The row was modified by another transaction."
        )
