"""Span context for automatic lifecycle management.

The SpanContext provides an interface for updating span data during execution
and ensures proper cleanup when the span completes.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .managers.span import SpanManager


class SpanContext:
    """Context for an active span.

    Returned by ``instance.span()`` / ``client.span()`` context managers.
    Call ``await span.start(payload)`` to explicitly POST the span to the
    API with its params payload. If ``start()`` is not called before the
    context exits, the context manager calls it automatically (with no
    payload) so the span is always flushed.

    Use the status-based finish methods before the context exits to control
    the final span status:

    - ``await span.complete(result)`` — mark as successfully completed
    - ``await span.fail(result)``     — mark as failed
    - ``await span.cancel()``         — mark as cancelled

    ``set_result()`` stores result data that is sent when the context
    manager auto-finishes the span (using ``complete`` status by default).

    Example::

        async with instance.span("agent:llm_call") as span:
            await span.start({"model": "claude-3-5-sonnet", "prompt": "Hi"})
            response = await call_llm(...)
            await span.complete({"response": response, "tokens": 42})

        # Or let the context manager handle finish automatically:
        async with instance.span("agent:llm_call") as span:
            await span.start({"model": "claude-3-5-sonnet", "prompt": "Hi"})
            response = await call_llm(...)
            span.set_result({"response": response, "tokens": 42})
        # span.complete() called automatically on exit
    """

    def __init__(
        self,
        temp_id: str,
        span_manager: "SpanManager",
        default_payload: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the span context.

        Args:
            temp_id: The temporary local ID returned by SpanManager.prepare().
            span_manager: The manager for span operations.
            default_payload: Payload to use if ``start()`` is never explicitly
                called (i.e. the context manager calls ``start()`` on exit).
        """
        self._span_id = temp_id  # replaced by API ID after start()
        self._span_manager = span_manager
        self._default_payload = default_payload
        self._result_payload: dict[str, Any] = {}
        self._finish_status: str = "complete"
        self._started = False
        self._finished = False

    @property
    def id(self) -> str:
        """Get the span ID.

        Before ``start()`` is called this returns the temporary local ID.
        After ``start()`` it returns the API-generated ID.

        Returns:
            The span identifier.
        """
        return self._span_id

    async def start(self, payload: dict[str, Any] | None = None) -> None:
        """Post the span to the API with the given params payload.

        This triggers the HTTP ``POST /api/v1/agent_spans`` request. Must be
        called at most once. Subsequent calls are no-ops.

        Args:
            payload: Optional params/inputs for the span (e.g. model name,
                prompt text, tool input). These are stored as the span's
                ``payload`` field in the API.
        """
        if self._started:
            return

        api_id = await self._span_manager.start(self._span_id, payload=payload)
        self._span_id = api_id
        self._started = True

    def set_result(self, data: dict[str, Any]) -> None:
        """Store result data to be sent when the span finishes.

        The data is merged and sent as ``result_payload`` when the span
        completes. Calling this does **not** finish the span — the finish
        happens when the context exits or when an explicit status method is
        called.

        Args:
            data: Dictionary of result data for the span.
        """
        self._result_payload.update(data)

    async def complete(self, result: dict[str, Any] | None = None) -> None:
        """Finish the span with ``complete`` status.

        Args:
            result: Optional result payload to attach to the span.
        """
        if result:
            self.set_result(result)
        self._finish_status = "complete"
        await self._finish()

    async def fail(self, result: dict[str, Any] | None = None) -> None:
        """Finish the span with ``failed`` status.

        Args:
            result: Optional result payload (e.g. error details).
        """
        if result:
            self.set_result(result)
        self._finish_status = "failed"
        await self._finish()

    async def cancel(self) -> None:
        """Finish the span with ``cancelled`` status."""
        self._finish_status = "cancelled"
        await self._finish()

    async def finish(self) -> None:
        """Finish the span using whichever status was last set (default: ``complete``).

        Called automatically when exiting the context manager. Can also be
        called manually; subsequent calls are no-ops.
        """
        await self._finish()

    async def _finish(self) -> None:
        """Internal finish — idempotent, auto-starts with default payload if needed."""
        if self._finished:
            return

        if not self._started:
            await self.start(self._default_payload)

        self._finished = True
        await self._span_manager.finish(
            self._span_id,
            result_payload=self._result_payload or None,
            status=self._finish_status,  # type: ignore[arg-type]
        )


__all__ = ["SpanContext"]
