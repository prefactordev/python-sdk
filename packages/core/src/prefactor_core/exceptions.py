"""Custom exceptions for prefactor-core."""

from __future__ import annotations


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


class PrefactorTelemetryFailureError(PrefactorCoreError):
    """Raised when telemetry enters a permanent failure state."""

    def __init__(
        self,
        message: str,
        *,
        cause: Exception,
        operation_type: str | None = None,
        dropped_operations: int = 0,
    ) -> None:
        super().__init__(message)
        self.cause = cause
        self.operation_type = operation_type
        self.dropped_operations = dropped_operations


class PrefactorTerminatedError(PrefactorCoreError):
    """Raised when the agent instance has been terminated by p2.

    Args:
        reason: Optional reason reported by p2 for the termination.
    """

    def __init__(self, reason: str | None = None) -> None:
        msg = (
            f"Agent instance terminated by p2: {reason}"
            if reason
            else "Agent instance terminated by p2"
        )
        super().__init__(msg)
        self.reason = reason


__all__ = [
    "PrefactorCoreError",
    "ClientNotInitializedError",
    "ClientAlreadyInitializedError",
    "OperationError",
    "InstanceNotFoundError",
    "SpanNotFoundError",
    "PrefactorTelemetryFailureError",
    "PrefactorTerminatedError",
]
