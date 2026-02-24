"""Custom exceptions for prefactor-core."""


class PrefactorCoreError(Exception):
    """Base exception for all prefactor-core errors."""

    pass


class ClientNotInitializedError(PrefactorCoreError):
    """Raised when attempting to use a client that hasn't been initialized."""

    pass


class ClientAlreadyInitializedError(PrefactorCoreError):
    """Raised when attempting to initialize a client that's already initialized."""

    pass


class OperationError(PrefactorCoreError):
    """Raised when an operation fails to process."""

    def __init__(self, message: str, operation_type: str | None = None) -> None:
        super().__init__(message)
        self.operation_type = operation_type


class InstanceNotFoundError(PrefactorCoreError):
    """Raised when an agent instance is not found."""

    pass


class SpanNotFoundError(PrefactorCoreError):
    """Raised when a span is not found."""

    pass


__all__ = [
    "PrefactorCoreError",
    "ClientNotInitializedError",
    "ClientAlreadyInitializedError",
    "OperationError",
    "InstanceNotFoundError",
    "SpanNotFoundError",
]
