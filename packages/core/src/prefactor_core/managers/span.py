"""Manager for span lifecycle operations.

The SpanManager handles high-level operations for spans, converting user
calls into Operation objects that are queued for processing. It also manages
the span stack for automatic parent detection.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from ..context_stack import SpanContextStack
from ..models import Span
from ..operations import Operation, OperationType
from ..utils import generate_idempotency_key

if TYPE_CHECKING:
    from prefactor_http.client import PrefactorHttpClient
    from prefactor_http.models.types import FinishStatus


class SpanManager:
    """Manages span lifecycle operations.

    Spans follow a three-phase lifecycle that maps to the API's state machine:

    1. ``prepare()``  — synchronous; allocates a local temp ID and pushes it
       onto the SpanContextStack so nested spans can auto-detect their parent.
       No HTTP call is made.
    2. ``start()``    — async; POSTs the span to the API with status
       ``"active"`` and the params payload, then re-keys local state under
       the API-generated ID. The span is now running.
    3. ``finish()``   — async; queues a ``FINISH_SPAN`` operation that calls
       ``POST /agent_spans/{id}/finish`` with the desired terminal status
       (``complete``, ``failed``, or ``cancelled``).

    API state machine:
      pending  → cancelled            (cancel_unstarted: POST pending, finish cancelled)
      active   → complete / failed / cancelled  (start then finish)

    ``cancel_unstarted()`` handles the case where the span is cancelled
    before ``start()`` is ever called — it POSTs the span as ``pending``
    then immediately cancels it, which is the only valid pre-active
    cancellation path the API supports.

    Example:
        manager = SpanManager(http_client, enqueue_func)

        temp_id = manager.prepare(instance_id="inst-123", schema_name="agent:llm")
        api_id  = await manager.start(temp_id, payload={"model": "gpt-4"})
        await manager.finish(api_id, status="complete", result_payload={...})
    """

    def __init__(
        self,
        http_client: "PrefactorHttpClient",
        enqueue: Callable[[Operation], Awaitable[None]],
    ) -> None:
        """Initialize the manager.

        Args:
            http_client: HTTP client for API calls.
            enqueue: Function to queue operations for processing.
        """
        self._http = http_client
        self._enqueue = enqueue
        self._spans: dict[str, Span] = {}

    def prepare(
        self,
        instance_id: str,
        schema_name: str,
        parent_span_id: str | None = None,
    ) -> str:
        """Reserve a local span slot and push it onto the context stack.

        Allocates a temporary local ID and pushes it onto the
        SpanContextStack so that nested ``prepare()`` calls can auto-detect
        their parent. The actual HTTP POST is deferred to ``start()``.

        Args:
            instance_id: ID of the agent instance this span belongs to.
            schema_name: Name of the schema for this span.
            parent_span_id: Optional parent span ID (auto-detected from
                stack if None).

        Returns:
            A temporary span ID (replaced by the API-generated ID in
            ``start()``).
        """
        if parent_span_id is None:
            parent_span_id = SpanContextStack.peek()

        temp_id = generate_idempotency_key()

        span = Span(
            id=temp_id,
            instance_id=instance_id,
            schema_name=schema_name,
            parent_span_id=parent_span_id,
            status="pending",
        )
        self._spans[temp_id] = span

        SpanContextStack.push(temp_id)

        return temp_id

    async def start(
        self,
        temp_id: str,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """Post the span to the API as ``active`` and return the API-generated ID.

        POSTs the span with ``status="active"``, which allows it to be
        finished via the finish endpoint with any terminal status
        (``complete``, ``failed``, or ``cancelled``). Replaces the temporary
        local ID with the API-generated ID in local state and on the context
        stack.

        Args:
            temp_id: The temporary ID returned by ``prepare()``.
            payload: Optional params/inputs to send with the span.

        Returns:
            The API-generated span ID.

        Raises:
            KeyError: If temp_id is not a known pending span.
        """
        if temp_id not in self._spans:
            raise KeyError(f"Unknown span: {temp_id}")

        span = self._spans[temp_id]

        result = await self._http.agent_spans.create(
            agent_instance_id=span.instance_id,
            schema_name=span.schema_name,
            status="active",
            payload=payload or {},
            parent_span_id=span.parent_span_id,
            idempotency_key=generate_idempotency_key(),
        )

        api_id = result.id

        # Re-key local state under the API-generated ID
        span.id = api_id
        span.payload = payload or {}
        span.status = "active"
        del self._spans[temp_id]
        self._spans[api_id] = span

        # Replace temp ID on the context stack
        stack = SpanContextStack.get_stack()
        new_stack = [api_id if s == temp_id else s for s in stack]

        from ..context_stack import _current_span_stack

        _current_span_stack.set(new_stack)

        return api_id

    async def cancel_unstarted(self, temp_id: str) -> None:
        """Cancel a span that was never started.

        When ``cancel()`` is called before ``start()``, the span has not yet
        been posted to the API. The API state machine only allows
        ``pending → cancelled``, so this method creates the span as
        ``pending`` then immediately cancels it via the finish endpoint.

        Args:
            temp_id: The temporary ID returned by ``prepare()``.

        Raises:
            KeyError: If temp_id is not a known pending span.
        """
        if temp_id not in self._spans:
            raise KeyError(f"Unknown span: {temp_id}")

        span = self._spans[temp_id]

        result = await self._http.agent_spans.create(
            agent_instance_id=span.instance_id,
            schema_name=span.schema_name,
            status="pending",
            payload={},
            parent_span_id=span.parent_span_id,
            idempotency_key=generate_idempotency_key(),
        )
        api_id = result.id

        await self._http.agent_spans.finish(
            agent_span_id=api_id,
            status="cancelled",
            idempotency_key=generate_idempotency_key(),
        )

        span.status = "cancelled"
        span.finished_at = datetime.now(timezone.utc)

        stack = SpanContextStack.get_stack()
        if temp_id in stack:
            from ..context_stack import _current_span_stack

            _current_span_stack.set([s for s in stack if s != temp_id])

        del self._spans[temp_id]

    async def create(
        self,
        instance_id: str,
        schema_name: str,
        parent_span_id: str | None = None,
        payload: dict[str, Any] | None = None,
        span_id: str | None = None,
    ) -> str:
        """Create a span in one step (prepare + start).

        Convenience method that combines ``prepare()`` and ``start()`` for
        callers that don't need the two-phase lifecycle.

        Args:
            instance_id: ID of the agent instance this span belongs to.
            schema_name: Name of the schema for this span.
            parent_span_id: Optional parent span ID (auto-detected if None).
            payload: Optional initial payload data.
            span_id: Ignored (API generates IDs).

        Returns:
            The API-generated span ID.
        """
        temp_id = self.prepare(
            instance_id=instance_id,
            schema_name=schema_name,
            parent_span_id=parent_span_id,
        )
        return await self.start(temp_id, payload=payload)

    async def finish(
        self,
        span_id: str,
        result_payload: dict[str, Any] | None = None,
        status: "FinishStatus" = "complete",
    ) -> None:
        """Mark a span as finished.

        Queues a finish operation and removes the span from the stack.

        Args:
            span_id: The ID of the span to finish.
            result_payload: Optional result data to store on the span.
            status: Terminal status — ``"complete"``, ``"failed"``, or
                ``"cancelled"`` (default: ``"complete"``). The span must be
                ``active`` for this to succeed; use ``cancel_unstarted()``
                to cancel a span that was never started.

        Raises:
            KeyError: If the span ID is not known.
        """
        if span_id not in self._spans:
            raise KeyError(f"Unknown span: {span_id}")

        self._spans[span_id].status = status
        self._spans[span_id].finished_at = datetime.now(timezone.utc)

        stack = SpanContextStack.get_stack()
        if span_id in stack:
            from ..context_stack import _current_span_stack

            _current_span_stack.set([s for s in stack if s != span_id])

        op_payload: dict[str, Any] = {
            "span_id": span_id,
            "status": status,
            "idempotency_key": generate_idempotency_key(),
        }
        if result_payload is not None:
            op_payload["result_payload"] = result_payload

        operation = Operation(
            type=OperationType.FINISH_SPAN,
            payload=op_payload,
            timestamp=datetime.now(timezone.utc),
        )

        await self._enqueue(operation)

    def get_span(self, span_id: str) -> Span | None:
        """Get a span by ID.

        Args:
            span_id: The span ID to look up.

        Returns:
            The span if known, None otherwise.
        """
        return self._spans.get(span_id)


__all__ = ["SpanManager"]
