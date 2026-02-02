"""Manager for span lifecycle operations.

The SpanManager handles high-level operations for spans, converting user
calls into Operation objects that are queued for processing. It also manages
the span stack for automatic parent detection.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from ..context_stack import SpanContextStack
from ..models import Span
from ..operations import Operation, OperationType

if TYPE_CHECKING:
    from prefactor_http.client import PrefactorHttpClient


class SpanManager:
    """Manages span lifecycle operations.

    This class provides a high-level interface for span operations.
    All operations are converted to Operation objects and queued for
    async processing. The manager tracks span state and manages the
    span stack for automatic parent detection.

    Example:
        manager = SpanManager(http_client, enqueue_func)

        # Create a span (parent auto-detected from stack)
        span_id = await manager.create(
            instance_id="inst-123",
            schema_name="llm"
        )

        # Update span payload
        await manager.update_payload(span_id, {"model": "gpt-4"})

        # Finish the span
        await manager.finish(span_id)
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

    async def create(
        self,
        instance_id: str,
        schema_name: str,
        parent_span_id: str | None = None,
        payload: dict[str, Any] | None = None,
        span_id: str | None = None,
    ) -> str:
        """Create a new span.

        Creates an operation to create the span and queues it for
        processing. Returns immediately with the span ID.

        If parent_span_id is not provided, uses the current span from
        the SpanContextStack.

        Args:
            instance_id: ID of the agent instance this span belongs to.
            schema_name: Name of the schema for this span.
            parent_span_id: Optional parent span ID (auto-detected if None).
            payload: Optional initial payload data.
            span_id: Optional custom ID for the span.

        Returns:
            The span ID (generated or provided).
        """
        # Generate ID if not provided
        if span_id is None:
            import uuid

            span_id = str(uuid.uuid4())

        # Auto-detect parent from stack if not explicit
        if parent_span_id is None:
            parent_span_id = SpanContextStack.peek()

        # Create local span record
        span = Span(
            id=span_id,
            instance_id=instance_id,
            schema_name=schema_name,
            parent_span_id=parent_span_id,
            status="pending",
            payload=payload or {},
        )
        self._spans[span_id] = span

        # Push onto stack for automatic parent detection
        SpanContextStack.push(span_id)

        # Queue creation operation
        operation = Operation(
            type=OperationType.CREATE_SPAN,
            payload={
                "instance_id": instance_id,
                "schema_name": schema_name,
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "payload": payload or {},
            },
            timestamp=datetime.now(),
            idempotency_key=span_id,
        )

        await self._enqueue(operation)
        return span_id

    async def finish(self, span_id: str) -> None:
        """Mark a span as finished.

        Queues a finish operation and removes the span from the stack.

        Args:
            span_id: The ID of the span to finish.

        Raises:
            KeyError: If the span ID is not known.
        """
        if span_id not in self._spans:
            raise KeyError(f"Unknown span: {span_id}")

        # Update local state
        self._spans[span_id].status = "complete"
        self._spans[span_id].finished_at = datetime.now()

        # Pop from stack (if this span is on top)
        if SpanContextStack.peek() == span_id:
            SpanContextStack.pop()

        # Queue finish operation
        operation = Operation(
            type=OperationType.FINISH_SPAN,
            payload={"span_id": span_id},
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

        # Update local state
        self._spans[span_id].payload.update(payload)

        # Queue update operation
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
