"""Span context for automatic lifecycle management.

The SpanContext provides an interface for updating span data during execution
and ensures proper cleanup when the span completes.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .managers.span import SpanManager


class SpanContext:
    """Context for an active span.

    This class provides methods to update span payload data during execution.
    When used as a context manager (via PrefactorNextClient.span()), the span
    is automatically finished when exiting the context.

    Example:
        async with client.span(instance_id, "llm") as span:
            span.set_payload({"model": "gpt-4"})
            result = await call_llm()
            span.set_payload({"response": result})
        # Span automatically finished here
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
        self._payload: dict[str, Any] = {}

    @property
    def id(self) -> str:
        """Get the span ID.

        Returns:
            The unique identifier for this span.
        """
        return self._span_id

    def set_payload(self, data: dict[str, Any]) -> None:
        """Update the span payload.

        This merges the provided data with any existing payload data.
        The updates are queued for async processing.

        Args:
            data: Dictionary of data to add to the span payload.
        """
        self._payload.update(data)
        # Queue async update
        # Note: We don't await here - updates are best-effort
        import asyncio

        asyncio.create_task(self._span_manager.update_payload(self._span_id, data))

    def get_payload(self) -> dict[str, Any]:
        """Get the current payload data.

        Returns:
            Copy of the current payload dictionary.
        """
        return self._payload.copy()

    async def finish(self) -> None:
        """Finish the span early.

        This is called automatically when exiting a context manager,
        but can be called manually if needed.
        """
        await self._span_manager.finish(self._span_id)


__all__ = ["SpanContext"]
