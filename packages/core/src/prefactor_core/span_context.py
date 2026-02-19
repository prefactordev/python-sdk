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

    Spans follow a three-phase lifecycle:

    1. **Enter context** — span is prepared locally (no HTTP call yet).
    2. **``await span.start(payload)``** — POSTs the span to the API as
       ``pending`` with the given params payload.
    3. **``await span.complete(result)``** (or ``.fail()`` / ``.cancel()``)
       — finishes the span with the appropriate terminal status.

    Because spans are created as ``pending``, all three terminal statuses
    are valid transitions — including ``cancelled``, which the API only
    accepts from ``pending``.

    If ``start()`` or a finish method is omitted, the context manager calls
    them automatically on exit (auto-start uses ``default_payload``; the
    default finish status is ``complete``), so explicit calls are opt-in.

    Example::

        async with instance.span("agent:llm_call") as span:
            await span.start({"model": "claude-3-5-sonnet", "prompt": "Hi"})
            try:
                response = await call_llm(...)
                await span.complete({"response": response, "tokens": 42})
            except Exception as exc:
                await span.fail({"error": str(exc)})

        # Skip start entirely to cancel before any work begins:
        async with instance.span("agent:retrieval") as span:
            if not needed:
                await span.cancel()
            else:
                await span.start({"query": "..."})
                ...
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
                called (i.e. the context manager auto-starts on exit).
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
        """Post the span to the API as ``pending`` with the given params payload.

        This triggers ``POST /api/v1/agent_spans``. The span is created as
        ``pending`` so that any terminal status (``complete``, ``failed``,
        ``cancelled``) is a valid transition via the finish endpoint. Must be
        called at most once; subsequent calls are no-ops.

        Args:
            payload: Optional params/inputs for the span (e.g. model name,
                prompt text, tool input). Stored as the span's ``payload``
                field in the API.
        """
        if self._started:
            return

        api_id = await self._span_manager.start(self._span_id, payload=payload)
        self._span_id = api_id
        self._started = True

    def set_result(self, data: dict[str, Any]) -> None:
        """Store result data to be sent when the span finishes.

        The data is merged and sent as ``result_payload`` when the span
        finishes. Calling this does **not** finish the span.

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
        """Finish the span with ``cancelled`` status.

        Can be called before or after ``start()``. If ``start()`` has not
        been called yet, the span is posted as ``pending`` then immediately
        cancelled — the API only accepts cancellation from the ``pending``
        state, so this is always a valid sequence.
        """
        self._finish_status = "cancelled"
        await self._finish()

    async def finish(self) -> None:
        """Finish the span using whichever status was last set (default: ``complete``).

        Called automatically when exiting the context manager. Can also be
        called manually; subsequent calls are no-ops.
        """
        await self._finish()

    async def _finish(self) -> None:
        """Internal finish — idempotent.

        API state machine constraints:
          - ``active``  → complete / failed / cancelled  (via finish endpoint)
          - ``pending`` → cancelled                       (via finish endpoint)

        If ``start()`` was never called and the status is ``cancelled``, the
        span is posted as ``pending`` then immediately cancelled — the only
        valid pre-active cancellation path.  For all other statuses the span
        is auto-started as ``active`` first.
        """
        if self._finished:
            return

        self._finished = True

        if not self._started and self._finish_status == "cancelled":
            await self._span_manager.cancel_unstarted(self._span_id)
            return

        if not self._started:
            await self.start(self._default_payload)

        await self._span_manager.finish(
            self._span_id,
            result_payload=self._result_payload or None,
            status=self._finish_status,  # type: ignore[arg-type]
        )


__all__ = ["SpanContext"]
