"""Abstract base class for span transport."""

from abc import ABC, abstractmethod

from prefactor_core.tracing.span import Span


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

    def finish_span(self, span_id: str, end_time: float) -> None:
        """
        Finish a previously emitted span.

        This is called for long-running spans that were emitted with end_time=None.
        The default implementation does nothing - transports that support the
        two-step span lifecycle should override this method.

        Args:
            span_id: The span ID.
            end_time: The end time (perf_counter value).
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
