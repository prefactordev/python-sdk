"""Custom exceptions for prefactor-next."""


class PrefactorNextError(Exception):
    """Base exception for all prefactor-next errors."""

    pass


class ClientNotInitializedError(PrefactorNextError):
    """Raised when attempting to use a client that hasn't been initialized."""

    pass


class ClientAlreadyInitializedError(PrefactorNextError):
    """Raised when attempting to initialize a client that's already initialized."""

    pass


class OperationError(PrefactorNextError):
    """Raised when an operation fails to process."""

    def __init__(self, message: str, operation_type: str | None = None) -> None:
        super().__init__(message)
        self.operation_type = operation_type


class InstanceNotFoundError(PrefactorNextError):
    """Raised when an agent instance is not found."""

    pass


class SpanNotFoundError(PrefactorNextError):
    """Raised when a span is not found."""

    pass


__all__ = [
    "PrefactorNextError",
    "ClientNotInitializedError",
    "ClientAlreadyInitializedError",
    "OperationError",
    "InstanceNotFoundError",
    "SpanNotFoundError",
]
