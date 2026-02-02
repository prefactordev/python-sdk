"""LangChain middleware for automatic tracing via prefactor-core."""

import asyncio
import logging
from typing import Any, Callable, Optional

from langchain.agents.middleware import AgentMiddleware
from prefactor_core import (
    AgentInstanceHandle,
    PrefactorCoreClient,
    PrefactorCoreConfig,
    SpanContext,
)
from prefactor_http.config import HttpClientConfig

from .metadata_extractor import extract_token_usage
from .spans import AgentSpan, LLMSpan, ToolSpan

logger = logging.getLogger("prefactor_langchain.middleware")


class PrefactorMiddleware(AgentMiddleware):
    """
    LangChain middleware for automatic tracing.

    This middleware integrates with LangChain's middleware system to automatically
    create and emit spans for agent execution, LLM calls, and tool executions.

    The middleware uses prefactor-next for all span and instance management,
    which handles:
    - Async queue-based span emission
    - Automatic parent-child span relationships via SpanContextStack
    - Agent instance lifecycle management

    The LangChain-specific span types (AgentSpan, LLMSpan, ToolSpan) are sent
    as the payload for each span.
    """

    def __init__(
        self,
        api_url: str,
        api_token: str,
        agent_id: Optional[str] = None,
        agent_name: Optional[str] = None,
    ):
        """
        Initialize the middleware.

        Args:
            api_url: The Prefactor API URL.
            api_token: The API token for authentication.
            agent_id: Optional agent identifier for categorization.
            agent_name: Optional human-readable agent name.
        """
        self._api_url = api_url
        self._api_token = api_token
        self._agent_id = agent_id or "langchain-agent"
        self._agent_name = agent_name

        # prefactor-core client and instance
        self._client: Optional[PrefactorCoreClient] = None
        self._instance: Optional[AgentInstanceHandle] = None
        self._initialized = False

        # Agent span context storage
        self._agent_span_context: Optional["SpanContext"] = None

    async def _ensure_initialized(self) -> AgentInstanceHandle:
        """Ensure the client and instance are initialized.

        Returns:
            The agent instance handle.
        """
        if self._initialized and self._instance:
            return self._instance

        # Create config
        http_config = HttpClientConfig(
            api_url=self._api_url,
            api_token=self._api_token,
        )
        config = PrefactorCoreConfig(http_config=http_config)

        # Create and initialize client
        self._client = PrefactorCoreClient(config)
        await self._client.initialize()

        # Create agent instance
        self._instance = await self._client.create_agent_instance(
            agent_id=self._agent_id,
            agent_version={
                "name": self._agent_name or "1.0.0",
                "external_identifier": "1.0.0",
            },
            agent_schema_version={
                "external_identifier": "langchain-1.0.0",
                "span_schemas": {
                    "langchain:agent": {"type": "object"},
                    "langchain:llm": {"type": "object"},
                    "langchain:tool": {"type": "object"},
                },
            },
        )

        self._initialized = True
        logger.debug(
            f"Initialized prefactor-next client with instance {self._instance.id}"
        )
        return self._instance

    async def close(self) -> None:
        """Close the middleware and cleanup resources."""
        if self._instance:
            await self._instance.finish()
            self._instance = None

        if self._client:
            await self._client.close()
            self._client = None

        self._initialized = False

    def _get_name_from_request(self, request: Any) -> str:
        """
        Extract span name from request metadata or default to unknown.

        Args:
            request: The model request.

        Returns:
            Extracted name or 'model_call' as fallback.
        """
        try:
            if hasattr(request, "metadata") and isinstance(request.metadata, dict):
                if "name" in request.metadata:
                    return request.metadata["name"]

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
        """Extract inputs from ModelRequest."""
        try:
            if hasattr(request, "messages") and request.messages:
                return {"messages": [str(m) for m in request.messages[-3:]]}
            if hasattr(request, "prompt"):
                return {"prompt": request.prompt}
            return {}
        except Exception as e:
            logger.error(f"Error extracting model inputs: {e}", exc_info=True)
            return {}

    def _extract_model_outputs(self, response: Any) -> dict[str, Any]:
        """Extract outputs from ModelResponse."""
        try:
            if hasattr(response, "content"):
                return {"response": response.content}

            if hasattr(response, "messages") and response.messages:
                last_message = response.messages[-1]
                if hasattr(last_message, "content"):
                    return {"response": last_message.content}

            return {"response": str(response)}
        except Exception as e:
            logger.error(f"Error extracting model outputs: {e}", exc_info=True)
            return {}

    def _extract_tool_inputs(self, request: Any) -> dict[str, Any]:
        """Extract inputs from tool request."""
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
        """Extract output from tool response."""
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
            # Run async initialization
            loop = asyncio.get_event_loop()
            instance = loop.run_until_complete(self._ensure_initialized())

            # Start the instance
            loop.run_until_complete(instance.start())

            # Extract messages from state
            messages = []
            if hasattr(state, "get"):
                messages = state.get("messages", [])
            elif hasattr(state, "messages"):
                messages = state.messages

            # Create agent span payload
            span_data = AgentSpan(
                name="agent",
                type="langchain:agent",
                inputs={
                    "messages": [str(m) for m in messages[-3:]] if messages else []
                },
            )

            # Create span via prefactor-next (async)
            async def create_span():
                async with instance.span("langchain:agent") as ctx:
                    ctx.set_payload(span_data.to_dict())
                    # Store context for after_agent
                    self._agent_span_context = ctx

            loop.run_until_complete(create_span())

            logger.debug("Started agent span")
            return None

        except Exception as e:
            logger.error(f"Error in before_agent: {e}", exc_info=True)
            return None

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """
        Hook called after agent completes execution.

        Args:
            state: The agent state.
            runtime: The runtime context.

        Returns:
            Optional state updates.
        """
        try:
            # Extract final messages from state
            messages = []
            if hasattr(state, "get"):
                messages = state.get("messages", [])
            elif hasattr(state, "messages"):
                messages = state.messages

            # Update span with final outputs
            outputs = {"messages": [str(m) for m in messages[-3:]] if messages else []}

            if self._agent_span_context is not None:
                self._agent_span_context.set_payload(
                    {
                        "outputs": outputs,
                        "status": "completed",
                    }
                )

            logger.debug("Ended agent span")

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
        Wrap synchronous model calls to trace LLM execution.

        Args:
            request: The model request.
            handler: The function that executes the model call.

        Returns:
            The model response.
        """
        # Create span data
        span_data = LLMSpan(
            name=self._get_name_from_request(request),
            type="langchain:llm",
            inputs=self._extract_model_inputs(request),
        )

        try:
            # Call the model
            response = handler(request)

            # Extract outputs and token usage
            outputs = self._extract_model_outputs(response)
            token_usage = extract_token_usage(response)

            # Complete span data
            span_data.complete(outputs=outputs)
            if token_usage:
                span_data.token_usage = token_usage

            # Emit span via prefactor-next
            if self._instance is not None:
                _instance: AgentInstanceHandle = self._instance
                _span_data = span_data

                async def emit():
                    async with _instance.span("langchain:llm") as ctx:
                        ctx.set_payload(_span_data.to_dict())

                try:
                    asyncio.get_event_loop().run_until_complete(emit())
                except RuntimeError:
                    asyncio.create_task(emit())

            logger.debug("Model call completed")
            return response

        except Exception as e:
            # Fail span with error
            span_data.fail(e)

            # Emit span via prefactor-next
            if self._instance is not None:
                _instance: AgentInstanceHandle = self._instance
                _span_data = span_data

                async def emit_error():
                    async with _instance.span("langchain:llm") as ctx:
                        ctx.set_payload(_span_data.to_dict())

                try:
                    asyncio.get_event_loop().run_until_complete(emit_error())
                except RuntimeError:
                    asyncio.create_task(emit_error())

            logger.error(f"Model call failed: {e}", exc_info=True)
            raise

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """
        Wrap async model calls to trace LLM execution.

        Args:
            request: The model request.
            handler: The function that executes the model call.

        Returns:
            The model response.
        """
        instance = await self._ensure_initialized()

        # Create span data
        span_data = LLMSpan(
            name=self._get_name_from_request(request),
            type="langchain:llm",
            inputs=self._extract_model_inputs(request),
        )

        async with instance.span("langchain:llm") as ctx:
            try:
                # Call the model
                response = await handler(request)

                # Extract outputs and token usage
                outputs = self._extract_model_outputs(response)
                token_usage = extract_token_usage(response)

                # Complete span data
                span_data.complete(outputs=outputs)
                if token_usage:
                    span_data.token_usage = token_usage

                ctx.set_payload(span_data.to_dict())
                logger.debug("Model call completed")
                return response

            except Exception as e:
                # Fail span with error
                span_data.fail(e)
                ctx.set_payload(span_data.to_dict())
                logger.error(f"Model call failed: {e}", exc_info=True)
                raise

    # Tool call wrapping

    def wrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """
        Wrap synchronous tool calls to trace tool execution.

        Args:
            request: The tool request.
            handler: The function that executes the tool call.

        Returns:
            The tool response.
        """
        # Extract tool information
        inputs = self._extract_tool_inputs(request)
        tool_name = inputs.get("tool_name", "unknown_tool")

        # Create span data
        span_data = ToolSpan(
            name=tool_name,
            type="langchain:tool",
            inputs=inputs,
            tool_name=tool_name,
        )

        try:
            # Call the tool
            response = handler(request)

            # Extract output
            outputs = self._extract_tool_output(response)
            span_data.complete(outputs=outputs)

            # Emit span via prefactor-next
            if self._instance is not None:
                _instance: AgentInstanceHandle = self._instance
                _span_data = span_data

                async def emit():
                    async with _instance.span("langchain:tool") as ctx:
                        ctx.set_payload(_span_data.to_dict())

                try:
                    asyncio.get_event_loop().run_until_complete(emit())
                except RuntimeError:
                    asyncio.create_task(emit())

            logger.debug(f"Tool call completed ({tool_name})")
            return response

        except Exception as e:
            # Fail span with error
            span_data.fail(e)

            # Emit span via prefactor-next
            if self._instance is not None:
                _instance: AgentInstanceHandle = self._instance
                _span_data = span_data

                async def emit_error():
                    async with _instance.span("langchain:tool") as ctx:
                        ctx.set_payload(_span_data.to_dict())

                try:
                    asyncio.get_event_loop().run_until_complete(emit_error())
                except RuntimeError:
                    asyncio.create_task(emit_error())

            logger.error(f"Tool call failed: {e}", exc_info=True)
            raise

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """
        Wrap async tool calls to trace tool execution.

        Args:
            request: The tool request.
            handler: The function that executes the tool call.

        Returns:
            The tool response.
        """
        instance = await self._ensure_initialized()

        # Extract tool information
        inputs = self._extract_tool_inputs(request)
        tool_name = inputs.get("tool_name", "unknown_tool")

        # Create span data
        span_data = ToolSpan(
            name=tool_name,
            type="langchain:tool",
            inputs=inputs,
            tool_name=tool_name,
        )

        async with instance.span("langchain:tool") as ctx:
            try:
                # Call the tool
                response = await handler(request)

                # Extract output
                outputs = self._extract_tool_output(response)
                span_data.complete(outputs=outputs)

                ctx.set_payload(span_data.to_dict())
                logger.debug(f"Tool call completed ({tool_name})")
                return response

            except Exception as e:
                # Fail span with error
                span_data.fail(e)
                ctx.set_payload(span_data.to_dict())
                logger.error(f"Tool call failed: {e}", exc_info=True)
                raise
