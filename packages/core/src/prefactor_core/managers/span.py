"""Manager for span lifecycle operations.

The SpanManager handles high-level operations for spans, converting user
calls into Operation objects that are queued for processing. It also manages
the span stack for automatic parent detection.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from ..context_stack import SpanContextStack
from ..models import Span
from ..operations import Operation, OperationType

if TYPE_CHECKING:
    from prefactor_http.client import PrefactorHttpClient
    from prefactor_http.models.types import FinishStatus


class SpanManager:
    """Manages span lifecycle operations.

    This class provides a high-level interface for span operations.
    Span preparation is synchronous (local state + stack push), while the
    HTTP POST (start) and finish/update operations are queued for async
    processing. The manager tracks span state and manages the span stack
    for automatic parent detection.

    Example:
        manager = SpanManager(http_client, enqueue_func)

        # Prepare a span (local state + stack push, no HTTP)
        span_id = manager.prepare(
            instance_id="inst-123",
            schema_name="agent:llm",
            parent_span_id=None,
        )

        # Start the span (HTTP POST)
        await manager.start(span_id, payload={"model": "gpt-4"})

        # Finish the span
        await manager.finish(span_id, status="complete")
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

        temp_id = str(uuid.uuid4())

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
        """Post the span to the API and return the API-generated ID.

        Replaces the temporary local ID with the API-generated ID in local
        state and on the context stack.

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
        from contextvars import copy_context  # noqa: F401 — set via internal API

        from ..context_stack import _current_span_stack

        _current_span_stack.set(new_stack)

        return api_id

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
            status: Finish status — ``"complete"``, ``"failed"``, or
                ``"cancelled"`` (default: ``"complete"``).

        Raises:
            KeyError: If the span ID is not known.
        """
        if span_id not in self._spans:
            raise KeyError(f"Unknown span: {span_id}")

        self._spans[span_id].status = status
        self._spans[span_id].finished_at = datetime.now()

        if SpanContextStack.peek() == span_id:
            SpanContextStack.pop()

        op_payload: dict[str, Any] = {"span_id": span_id, "status": status}
        if result_payload is not None:
            op_payload["result_payload"] = result_payload

        operation = Operation(
            type=OperationType.FINISH_SPAN,
            payload=op_payload,
            timestamp=datetime.now(),
        )

        await self._enqueue(operation)

    async def update_payload(
        self,
        span_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Update a span's payload.

        Queues an update operation for the span payload.

        Args:
            span_id: The ID of the span to update.
            payload: Payload data to merge with existing data.

        Raises:
            KeyError: If the span ID is not known.
        """
        if span_id not in self._spans:
            raise KeyError(f"Unknown span: {span_id}")

        self._spans[span_id].payload.update(payload)

        operation = Operation(
            type=OperationType.UPDATE_SPAN_PAYLOAD,
            payload={
                "span_id": span_id,
                "payload": payload,
            },
            timestamp=datetime.now(),
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
