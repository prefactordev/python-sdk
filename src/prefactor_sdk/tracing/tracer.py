"""Tracer for managing span lifecycle."""

import time
import traceback
import uuid
from typing import Any, Optional

from prefactor_sdk.tracing.span import ErrorInfo, Span, SpanStatus, SpanType, TokenUsage
from prefactor_sdk.transport.base import Transport
from prefactor_sdk.utils.logging import get_logger

logger = get_logger("tracing.tracer")


class Tracer:
    """Manages span lifecycle and delegates to transport."""

    def __init__(self, transport: Transport):
        """
        Initialize the tracer.

        Args:
            transport: The transport to use for emitting spans.
        """
        self._transport = transport

    def start_span(
        self,
        name: str,
        span_type: SpanType,
        inputs: dict[str, Any],
        parent_span_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ) -> Span:
        """
        Start a new span.

        Args:
            name: The name of the span.
            span_type: The type of the span.
            inputs: The inputs to the span.
            parent_span_id: Optional parent span ID.
            trace_id: Optional trace ID (will be generated if not provided).
            metadata: Optional metadata dict.
            tags: Optional list of tags.

        Returns:
            The created span.
        """
        span_id = str(uuid.uuid4())

        # Use provided trace_id or generate a new one
        if trace_id is None:
            trace_id = str(uuid.uuid4())

        span = Span(
            span_id=span_id,
            parent_span_id=parent_span_id,
            trace_id=trace_id,
            name=name,
            span_type=span_type,
            start_time=time.perf_counter(),
            end_time=None,
            status=SpanStatus.RUNNING,
            inputs=inputs,
            outputs=None,
            token_usage=None,
            error=None,
            metadata=metadata or {},
            tags=tags or [],
        )

        logger.debug(f"Started span: {span_id} ({name})")
        return span

    def end_span(
        self,
        span: Span,
        outputs: Optional[dict[str, Any]] = None,
        error: Optional[Exception] = None,
        token_usage: Optional[TokenUsage] = None,
    ) -> None:
        """
        End a span and emit it to the transport.

        Args:
            span: The span to end.
            outputs: Optional outputs from the span.
            error: Optional error that occurred.
            token_usage: Optional token usage information.
        """
        span.end_time = time.perf_counter()
        span.outputs = outputs
        span.token_usage = token_usage

        if error:
            span.status = SpanStatus.ERROR
            span.error = ErrorInfo(
                error_type=type(error).__name__,
                message=str(error),
                stacktrace=traceback.format_exc(),
            )
        else:
            span.status = SpanStatus.SUCCESS

        logger.debug(f"Ended span: {span.span_id} ({span.name}) - {span.status}")

        # Emit the span
        try:
            self._transport.emit(span)
        except Exception as e:
            logger.error(f"Failed to emit span: {e}", exc_info=True)

    def start_agent_instance(self) -> None:
        """Mark the agent instance as started."""
        logger.debug("Starting agent instance")
        try:
            self._transport.start_agent_instance()
        except Exception as e:
            logger.error(f"Failed to start agent instance: {e}", exc_info=True)

    def finish_agent_instance(self) -> None:
        """Mark the agent instance as finished."""
        logger.debug("Finishing agent instance")
        try:
            self._transport.finish_agent_instance()
        except Exception as e:
            logger.error(f"Failed to finish agent instance: {e}", exc_info=True)

    def close(self) -> None:
        """Close the tracer and cleanup resources."""
        logger.debug("Closing tracer")
        try:
            self._transport.close()
        except Exception as e:
            logger.error(f"Failed to close transport: {e}", exc_info=True)
