class DatabaseError(Exception):
    """Base exception for all persistence errors."""


class MigrationError(DatabaseError):
    """Raised when a versioned database migration cannot be applied."""


class RepositoryError(DatabaseError):
    """Raised when a repository operation fails."""


class EntityNotFoundError(RepositoryError):
    """Raised when a requested domain record does not exist."""


class PersistenceError(DatabaseError):
    """Raised when an inspection result cannot be persisted atomically."""
