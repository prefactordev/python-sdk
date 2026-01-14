"""Abstract base class for span transport."""

from abc import ABC, abstractmethod

from prefactor_sdk.tracing.span import Span


class Transport(ABC):
    """Abstract base class for transporting spans."""

    @abstractmethod
    def emit(self, span: Span) -> None:
        """
        Emit a span to the transport destination.

        Args:
            span: The span to emit.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the transport and cleanup resources."""
        pass
