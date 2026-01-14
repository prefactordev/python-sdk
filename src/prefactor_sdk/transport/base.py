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

    def start_agent_instance(self) -> None:
        """
        Mark the agent instance as started.

        This is called when the agent begins execution. The default
        implementation does nothing - transports that need to track
        agent instance lifecycle should override this method.
        """
        pass

    def finish_agent_instance(self) -> None:
        """
        Mark the agent instance as finished.

        This is called when the agent execution completes. The default
        implementation does nothing - transports that need to track
        agent instance lifecycle should override this method.
        """
        pass
