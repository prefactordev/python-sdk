"""LangChain callback handler for automatic tracing."""

from typing import Any, Optional
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler

from prefactor_sdk.instrumentation.langchain.metadata_extractor import (
    extract_token_usage,
)
from prefactor_sdk.tracing.span import Span, SpanType
from prefactor_sdk.tracing.tracer import Tracer
from prefactor_sdk.utils.logging import get_logger

logger = get_logger("instrumentation.langchain.callback_handler")


class PrefactorCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler for automatic tracing.

    This handler integrates with LangChain's callback system to automatically
    create and emit spans for LLM calls, tool executions, chains, and more.
    """

    def __init__(self, tracer: Tracer):
        """
        Initialize the callback handler.

        Args:
            tracer: The tracer to use for span management.
        """
        super().__init__()
        self._tracer = tracer
        self._span_map: dict[UUID, Span] = {}
        # Never raise errors - fail gracefully
        self.raise_error = False

    def _get_name(
        self,
        serialized: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> str:
        """Extract name from serialized, metadata, tags, or kwargs."""
        # Check serialized dict first (common in LangChain callbacks)
        if serialized and "name" in serialized:
            return serialized["name"]

        # Modern LangChain API stores name in metadata
        if metadata:
            # Check common metadata fields
            if "ls_name" in metadata:
                return metadata["ls_name"]
            if "name" in metadata:
                return metadata["name"]
            if "langgraph_node" in metadata:
                return metadata["langgraph_node"]

        # Check kwargs for name
        if "name" in kwargs:
            return kwargs["name"]

        # Use first tag as fallback if available
        if tags and len(tags) > 0:
            return tags[0]

        return "unknown"

    # LLM Callbacks

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Handle LLM start event."""
        try:
            # Get parent span if exists
            parent_span = None
            trace_id = None
            if parent_run_id and parent_run_id in self._span_map:
                parent_span = self._span_map[parent_run_id]
                trace_id = parent_span.trace_id

            span = self._tracer.start_span(
                name=self._get_name(
                    serialized=serialized, metadata=metadata, tags=tags, **kwargs
                ),
                span_type=SpanType.LLM,
                inputs={"prompts": prompts},
                parent_span_id=parent_span.span_id if parent_span else None,
                trace_id=trace_id,
                metadata=metadata or {},
                tags=tags or [],
            )

            self._span_map[run_id] = span
            logger.debug(f"Started LLM span: {run_id}")

        except Exception as e:
            logger.error(f"Error in on_llm_start: {e}", exc_info=True)

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Handle LLM end event."""
        try:
            if run_id not in self._span_map:
                logger.warning(f"LLM span not found for run_id: {run_id}")
                return

            span = self._span_map[run_id]

            # Extract outputs
            outputs = {}
            if hasattr(response, "generations") and response.generations:
                # Get the first generation's text
                first_gen = response.generations[0]

                # Handle both message and text attributes
                if hasattr(first_gen, "message"):
                    # Chat model response with message
                    if hasattr(first_gen.message, "content"):
                        outputs["response"] = first_gen.message.content
                elif hasattr(first_gen, "text"):
                    # Text generation response
                    outputs["response"] = first_gen.text

            # Extract token usage
            token_usage = extract_token_usage(response)

            # End the span
            self._tracer.end_span(
                span=span,
                outputs=outputs,
                token_usage=token_usage,
            )

            # Clean up
            del self._span_map[run_id]
            logger.debug(f"Ended LLM span: {run_id}")

        except Exception as e:
            logger.error(f"Error in on_llm_end: {e}", exc_info=True)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Handle LLM error event."""
        try:
            if run_id not in self._span_map:
                logger.warning(f"LLM span not found for run_id: {run_id}")
                return

            span = self._span_map[run_id]

            # End the span with error
            self._tracer.end_span(
                span=span,
                error=error,
            )

            # Clean up
            del self._span_map[run_id]
            logger.debug(f"Ended LLM span with error: {run_id}")

        except Exception as e:
            logger.error(f"Error in on_llm_error: {e}", exc_info=True)

    # Tool Callbacks

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Handle tool start event."""
        try:
            # Get parent span if exists
            parent_span = None
            trace_id = None
            if parent_run_id and parent_run_id in self._span_map:
                parent_span = self._span_map[parent_run_id]
                trace_id = parent_span.trace_id

            span = self._tracer.start_span(
                name=self._get_name(
                    serialized=serialized, metadata=metadata, tags=tags, **kwargs
                ),
                span_type=SpanType.TOOL,
                inputs={"input": input_str},
                parent_span_id=parent_span.span_id if parent_span else None,
                trace_id=trace_id,
                metadata=metadata or {},
                tags=tags or [],
            )

            self._span_map[run_id] = span
            logger.debug(f"Started tool span: {run_id}")

        except Exception as e:
            logger.error(f"Error in on_tool_start: {e}", exc_info=True)

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Handle tool end event."""
        try:
            if run_id not in self._span_map:
                logger.warning(f"Tool span not found for run_id: {run_id}")
                return

            span = self._span_map[run_id]

            # End the span
            self._tracer.end_span(
                span=span,
                outputs={"output": output},
            )

            # Clean up
            del self._span_map[run_id]
            logger.debug(f"Ended tool span: {run_id}")

        except Exception as e:
            logger.error(f"Error in on_tool_end: {e}", exc_info=True)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Handle tool error event."""
        try:
            if run_id not in self._span_map:
                logger.warning(f"Tool span not found for run_id: {run_id}")
                return

            span = self._span_map[run_id]

            # End the span with error
            self._tracer.end_span(
                span=span,
                error=error,
            )

            # Clean up
            del self._span_map[run_id]
            logger.debug(f"Ended tool span with error: {run_id}")

        except Exception as e:
            logger.error(f"Error in on_tool_error: {e}", exc_info=True)

    # Chain Callbacks

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """Handle chain start event."""
        try:
            # Get parent span if exists
            parent_span = None
            trace_id = None
            if parent_run_id and parent_run_id in self._span_map:
                parent_span = self._span_map[parent_run_id]
                trace_id = parent_span.trace_id

            span = self._tracer.start_span(
                name=self._get_name(
                    serialized=serialized, metadata=metadata, tags=tags, **kwargs
                ),
                span_type=SpanType.CHAIN,
                inputs=inputs,
                parent_span_id=parent_span.span_id if parent_span else None,
                trace_id=trace_id,
                metadata=metadata or {},
                tags=tags or [],
            )

            self._span_map[run_id] = span
            logger.debug(f"Started chain span: {run_id}")

        except Exception as e:
            logger.error(f"Error in on_chain_start: {e}", exc_info=True)

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Handle chain end event."""
        try:
            if run_id not in self._span_map:
                logger.warning(f"Chain span not found for run_id: {run_id}")
                return

            span = self._span_map[run_id]

            # End the span
            self._tracer.end_span(
                span=span,
                outputs=outputs,
            )

            # Clean up
            del self._span_map[run_id]
            logger.debug(f"Ended chain span: {run_id}")

        except Exception as e:
            logger.error(f"Error in on_chain_end: {e}", exc_info=True)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Handle chain error event."""
        try:
            if run_id not in self._span_map:
                logger.warning(f"Chain span not found for run_id: {run_id}")
                return

            span = self._span_map[run_id]

            # End the span with error
            self._tracer.end_span(
                span=span,
                error=error,
            )

            # Clean up
            del self._span_map[run_id]
            logger.debug(f"Ended chain span with error: {run_id}")

        except Exception as e:
            logger.error(f"Error in on_chain_error: {e}", exc_info=True)
