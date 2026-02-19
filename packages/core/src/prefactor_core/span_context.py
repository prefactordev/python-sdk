"""Span context for automatic lifecycle management.

The SpanContext provides an interface for updating span data during execution
and ensures proper cleanup when the span completes.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .managers.span import SpanManager


class SpanContext:
    """Context for an active span.

    This class provides methods to set span result data during execution.
    When used as a context manager (via PrefactorCoreClient.span()), the span
    is automatically finished when exiting the context, sending any stored
    result payload.

    Example:
        async with instance.span("langchain:llm") as span:
            result = await call_llm()
            span.set_result({"response": result, "status": "completed"})
        # Span automatically finished with result_payload here
    """

    def __init__(
        self,
        span_id: str,
        span_manager: "SpanManager",
    ) -> None:
        """Initialize the span context.

        Args:
            span_id: The ID of the span this context represents.
            span_manager: The manager for span operations.
        """
        self._span_id = span_id
        self._span_manager = span_manager
        self._result_payload: dict[str, Any] = {}

    @property
    def id(self) -> str:
        """Get the span ID.

        Returns:
            The unique identifier for this span.
        """
        return self._span_id

    def set_result(self, data: dict[str, Any]) -> None:
        """Set the span result payload.

        The result is stored locally and sent as ``result_payload`` when the
        span is finished via the context manager.

        Args:
            data: Dictionary of result data for the span.
        """
        self._result_payload.update(data)

    async def finish(self) -> None:
        """Finish the span, sending any stored result payload.

        This is called automatically when exiting a context manager,
        but can be called manually if needed.
        """
        await self._span_manager.finish(
            self._span_id,
            result_payload=self._result_payload or None,
        )


__all__ = ["SpanContext"]
