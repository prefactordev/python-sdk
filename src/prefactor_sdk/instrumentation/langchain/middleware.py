"""LangChain middleware for automatic tracing."""

from typing import Any, Callable, Optional

from langchain.agents.middleware import AgentMiddleware

from prefactor_sdk.instrumentation.langchain.metadata_extractor import (
    extract_token_usage,
)
from prefactor_sdk.tracing.context import SpanContext
from prefactor_sdk.tracing.span import SpanType, TokenUsage
from prefactor_sdk.tracing.tracer import Tracer
from prefactor_sdk.utils.logging import get_logger

logger = get_logger("instrumentation.langchain.middleware")


class PrefactorMiddleware(AgentMiddleware):
    """
    LangChain middleware for automatic tracing.

    This middleware integrates with LangChain's middleware system to automatically
    create and emit spans for agent execution, LLM calls, and tool executions.
    """

    def __init__(self, tracer: Tracer):
        """
        Initialize the middleware.

        Args:
            tracer: The tracer to use for span management.
        """
        self._tracer = tracer
        self._root_span = None

    def _get_name_from_request(self, request: Any) -> str:
        """
        Extract span name from request metadata or default to unknown.

        Args:
            request: The model request.

        Returns:
            Extracted name or 'unknown' as fallback.
        """
        try:
            # Try to get name from request attributes
            if hasattr(request, "metadata") and isinstance(request.metadata, dict):
                if "name" in request.metadata:
                    return request.metadata["name"]

            # Fallback to model name if available
            if hasattr(request, "model"):
                model = request.model
                if hasattr(model, "model_name"):
                    return f"model:{model.model_name}"
                elif hasattr(model, "name"):
                    return model.name

            return "model_call"
        except Exception as e:
            logger.debug(f"Error extracting name from request: {e}")
            return "model_call"

    def _extract_model_inputs(self, request: Any) -> dict[str, Any]:
        """
        Extract inputs from ModelRequest.

        Args:
            request: The model request.

        Returns:
            Dictionary of inputs.
        """
        try:
            # ModelRequest should have messages or similar
            if hasattr(request, "messages") and request.messages:
                # Only store last few messages to avoid huge inputs
                return {"messages": [str(m) for m in request.messages[-3:]]}
            if hasattr(request, "prompt"):
                return {"prompt": request.prompt}
            return {}
        except Exception as e:
            logger.error(f"Error extracting model inputs: {e}", exc_info=True)
            return {}

    def _extract_model_outputs(self, response: Any) -> dict[str, Any]:
        """
        Extract outputs from ModelResponse.

        Args:
            response: The model response.

        Returns:
            Dictionary of outputs.
        """
        try:
            # Check if response has content attribute (common pattern)
            if hasattr(response, "content"):
                return {"response": response.content}

            # Check if response has messages
            if hasattr(response, "messages") and response.messages:
                last_message = response.messages[-1]
                if hasattr(last_message, "content"):
                    return {"response": last_message.content}

            # Fallback to string representation
            return {"response": str(response)}
        except Exception as e:
            logger.error(f"Error extracting model outputs: {e}", exc_info=True)
            return {}

    def _extract_token_usage(self, response: Any) -> Optional[TokenUsage]:
        """
        Extract token usage from model response.

        Args:
            response: The model response.

        Returns:
            Token usage if available, None otherwise.
        """
        # Reuse existing metadata extractor
        return extract_token_usage(response)

    def _extract_tool_inputs(self, request: Any) -> dict[str, Any]:
        """
        Extract inputs from tool request.

        Args:
            request: The tool request.

        Returns:
            Dictionary of inputs.
        """
        try:
            if hasattr(request, "tool_call"):
                tool_call = request.tool_call
                return {
                    "tool_name": tool_call.get("name", "unknown"),
                    "arguments": tool_call.get("args", {}),
                }
            return {"tool_call": str(request)}
        except Exception as e:
            logger.error(f"Error extracting tool inputs: {e}", exc_info=True)
            return {}

    def _extract_tool_output(self, response: Any) -> dict[str, Any]:
        """
        Extract output from tool response.

        Args:
            response: The tool response.

        Returns:
            Dictionary of outputs.
        """
        try:
            if hasattr(response, "content"):
                return {"output": response.content}
            return {"output": str(response)}
        except Exception as e:
            logger.error(f"Error extracting tool output: {e}", exc_info=True)
            return {"output": str(response)}

    # Agent lifecycle hooks

    def before_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """
        Hook called before agent starts execution.

        Creates a root span for the entire agent execution.

        Args:
            state: The agent state.
            runtime: The runtime context.

        Returns:
            Optional state updates.
        """
        try:
            # Get parent span if exists (for nested agents)
            parent_span = SpanContext.get_current()

            # Extract messages from state
            messages = []
            if hasattr(state, "get"):
                messages = state.get("messages", [])
            elif hasattr(state, "messages"):
                messages = state.messages

            # Create root agent span
            span = self._tracer.start_span(
                name="agent",
                span_type=SpanType.AGENT,
                inputs={
                    "messages": [str(m) for m in messages[-3:]] if messages else []
                },
                parent_span_id=parent_span.span_id if parent_span else None,
                trace_id=parent_span.trace_id if parent_span else None,
                metadata={},
                tags=[],
            )

            # Set as current span for children
            SpanContext.set_current(span)

            # Store root span for later cleanup
            self._root_span = span

            logger.debug(f"Started agent span: {span.span_id}")
            return None

        except Exception as e:
            logger.error(f"Error in before_agent: {e}", exc_info=True)
            return None

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """
        Hook called after agent completes execution.

        Ends the root span created in before_agent.

        Args:
            state: The agent state.
            runtime: The runtime context.

        Returns:
            Optional state updates.
        """
        try:
            if self._root_span is None:
                logger.warning("No root span found in after_agent")
                return None

            span = self._root_span

            # Extract final messages from state
            messages = []
            if hasattr(state, "get"):
                messages = state.get("messages", [])
            elif hasattr(state, "messages"):
                messages = state.messages

            # Extract final outputs
            outputs = {"messages": [str(m) for m in messages[-3:]] if messages else []}

            # End the span
            self._tracer.end_span(span=span, outputs=outputs)

            # Clear context
            SpanContext.clear()
            self._root_span = None

            logger.debug(f"Ended agent span: {span.span_id}")

        except Exception as e:
            logger.error(f"Error in after_agent: {e}", exc_info=True)

        return None

    # Model call wrapping

    def wrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """
        Wrap model calls to trace LLM execution.

        Args:
            request: The model request.
            handler: The function that executes the model call.

        Returns:
            The model response.
        """
        # Get parent span from context
        parent_span = SpanContext.get_current()

        # Start LLM span
        span = self._tracer.start_span(
            name=self._get_name_from_request(request),
            span_type=SpanType.LLM,
            inputs=self._extract_model_inputs(request),
            parent_span_id=parent_span.span_id if parent_span else None,
            trace_id=parent_span.trace_id if parent_span else None,
            metadata={},
            tags=[],
        )

        # Set as current span for nested operations
        SpanContext.set_current(span)

        try:
            # Call the model
            response = handler(request)

            # Extract outputs and token usage
            outputs = self._extract_model_outputs(response)
            token_usage = self._extract_token_usage(response)

            # End span successfully
            self._tracer.end_span(
                span=span,
                outputs=outputs,
                token_usage=token_usage,
            )

            logger.debug(f"Model call completed: {span.span_id}")
            return response

        except Exception as e:
            # End span with error
            self._tracer.end_span(span=span, error=e)
            logger.error(f"Model call failed: {e}", exc_info=True)
            raise

        finally:
            # Restore parent span context
            SpanContext.set_current(parent_span)

    # Tool call wrapping

    def wrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """
        Wrap tool calls to trace tool execution.

        Args:
            request: The tool request.
            handler: The function that executes the tool call.

        Returns:
            The tool response.
        """
        # Get parent span from context
        parent_span = SpanContext.get_current()

        # Extract tool information
        inputs = self._extract_tool_inputs(request)
        tool_name = inputs.get("tool_name", "unknown_tool")

        # Start tool span
        span = self._tracer.start_span(
            name=tool_name,
            span_type=SpanType.TOOL,
            inputs=inputs,
            parent_span_id=parent_span.span_id if parent_span else None,
            trace_id=parent_span.trace_id if parent_span else None,
            metadata={},
            tags=[],
        )

        # Set as current span for nested operations
        SpanContext.set_current(span)

        try:
            # Call the tool
            response = handler(request)

            # Extract output
            outputs = self._extract_tool_output(response)

            # End span successfully
            self._tracer.end_span(span=span, outputs=outputs)

            logger.debug(f"Tool call completed: {span.span_id} ({tool_name})")
            return response

        except Exception as e:
            # End span with error
            self._tracer.end_span(span=span, error=e)
            logger.error(f"Tool call failed: {e}", exc_info=True)
            raise

        finally:
            # Restore parent span context
            SpanContext.set_current(parent_span)
