"""LangChain middleware for automatic tracing via prefactor-core."""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Callable

from langchain.agents.middleware import AgentMiddleware
from prefactor_core import (
    AgentInstanceHandle,
    PrefactorCoreClient,
    PrefactorCoreConfig,
    SchemaRegistry,
    SpanContext,
)
from prefactor_http.config import HttpClientConfig

if TYPE_CHECKING:
    pass

from .metadata_extractor import extract_token_usage
from .schemas import register_langchain_schemas
from .spans import AgentSpan, LLMSpan, ToolSpan

logger = logging.getLogger("prefactor_langchain.middleware")


class PrefactorMiddleware(AgentMiddleware):
    """LangChain middleware for automatic tracing.

    This middleware integrates with LangChain's middleware system to automatically
    create and emit spans for agent execution, LLM calls, and tool executions.

    Two usage patterns are supported:

    1. **Pre-configured Client** (recommended): Pass a pre-configured client for
       full control over settings. The user is responsible for client lifecycle.

    2. **Factory Pattern**: Use `from_config()` for quick setup. The middleware
       owns both client and agent instance lifecycle.

    Example - Pre-configured Client:
        from prefactor_core import PrefactorCoreClient, PrefactorCoreConfig
        from prefactor_http.config import HttpClientConfig

        # Configure and initialize client yourself
        http_config = HttpClientConfig(api_url="...", api_token="...")
        config = PrefactorCoreConfig(http_config=http_config)
        client = PrefactorCoreClient(config)
        await client.initialize()

        # Create middleware with pre-configured client
        middleware = PrefactorMiddleware(
            client=client,
            agent_id="my-agent",
            agent_name="My Agent",
        )

        # User must close both middleware and client
        await middleware.close()  # Only closes agent instance
        await client.close()  # User closes their own client

    Example - Factory Pattern:
        middleware = PrefactorMiddleware.from_config(
            api_url="https://api.prefactor.ai",
            api_token="my-token",
            agent_id="my-agent",
            agent_name="My Agent",
        )

        # Middleware manages both client and agent instance
        await middleware.close()  # Closes both
    """

    def __init__(
        self,
        client: PrefactorCoreClient,
        agent_id: str = "langchain-agent",
        agent_name: str | None = None,
    ):
        """Initialize the middleware with a pre-configured client.

        Args:
            client: Pre-initialized PrefactorCoreClient instance.
            agent_id: Agent identifier for categorization.
            agent_name: Optional human-readable agent name.

        Raises:
            ValueError: If client is None or not initialized.
        """
        if client is None:
            msg = (
                "Client is required"
                " - use PrefactorMiddleware.from_config()"
                " for quick setup"
            )
            raise ValueError(msg)

        if not hasattr(client, "_initialized") or not client._initialized:
            msg = (
                "Client must be initialized before being"
                " passed to middleware"
                " - call await client.initialize() first"
            )
            raise ValueError(msg)

        self._client = client
        self._agent_id = agent_id
        self._agent_name = agent_name

        # Client and instance tracking
        self._instance: AgentInstanceHandle | None = None
        self._owns_instance = True  # We create the agent instance
        self._owns_client = False  # We didn't create the client

        # Agent span context storage
        self._agent_span_context: SpanContext | None = None

    @classmethod
    def from_config(
        cls,
        api_url: str,
        api_token: str,
        agent_id: str = "langchain-agent",
        agent_name: str | None = None,
        schema_registry: SchemaRegistry | None = None,
        include_langchain_schemas: bool = True,
    ) -> "PrefactorMiddleware":
        """Factory method to create middleware from configuration.

        This creates a client and middleware with the specified settings.
        The middleware owns the client and will auto-initialize it on first use.

        Args:
            api_url: The Prefactor API URL.
            api_token: The API token for authentication.
            agent_id: Optional agent identifier for categorization.
            agent_name: Optional human-readable agent name.
            schema_registry: Optional SchemaRegistry for registering span schemas.
            include_langchain_schemas: If True and schema_registry is provided,
                automatically register LangChain-specific schemas.

        Returns:
            A configured PrefactorMiddleware instance with lazy initialization.

        Example:
            middleware = PrefactorMiddleware.from_config(
                api_url="https://api.prefactor.ai",
                api_token="my-token",
                agent_id="my-agent",
                agent_name="My Agent",
            )

            # Middleware auto-initializes on first use
            # Cleanup when done:
            await middleware.close()  # Closes both agent instance and client
        """
        http_config = HttpClientConfig(api_url=api_url, api_token=api_token)

        # Create or augment schema registry
        registry = schema_registry or SchemaRegistry()
        if include_langchain_schemas and not registry.has_schema("langchain:llm"):
            register_langchain_schemas(registry)

        config = PrefactorCoreConfig(
            http_config=http_config,
            schema_registry=registry,
        )
        client = PrefactorCoreClient(config)

        # Create middleware that owns the client (lazy init, no validation yet)
        middleware = cls.__new__(cls)
        middleware._client = client
        middleware._agent_id = agent_id
        middleware._agent_name = agent_name
        middleware._instance = None
        middleware._owns_instance = True
        middleware._owns_client = True  # We created the client, we'll manage it
        middleware._agent_span_context = None
        logger.debug("PrefactorMiddleware created via from_config()")
        return middleware

    async def _ensure_initialized(self) -> AgentInstanceHandle:
        """Ensure the agent instance is initialized (lazily created if needed).

        Returns:
            The agent instance handle.

        Raises:
            ValueError: If client is not available.
        """
        if self._instance is not None:
            return self._instance

        if self._client is None:
            raise ValueError("Client is not available - middleware has been closed")

        # Initialize client if we own it (factory pattern)
        if self._owns_client and not self._client._initialized:
            await self._client.initialize()

        # Create agent instance
        self._instance = await self._client.create_agent_instance(
            agent_id=self._agent_id,
            agent_version={
                "name": self._agent_name or "1.0.0",
                "external_identifier": "1.0.0",
            },
            agent_schema_version=None,  # Will use registry if available
            external_schema_version_id="langchain-1.0.0",
        )

        self._owns_instance = True
        logger.debug("Initialized agent instance %s", self._instance.id)
        return self._instance

    async def close(self) -> None:
        """Close the middleware and cleanup resources.

        This closes the agent instance (if we created it) and client (if we own it).
        """
        if self._instance is not None and self._owns_instance:
            await self._instance.finish()
            self._instance = None
            self._owns_instance = False

        if self._client is not None and self._owns_client:
            await self._client.close()
            self._client = None
            self._owns_client = False

    def _get_name_from_request(self, request: Any) -> str:
        """Extract span name from request metadata or default to unknown.

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
            logger.debug("Error extracting name from request: %s", e)
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
            logger.error("Error extracting model inputs: %s", e, exc_info=True)
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
            logger.error("Error extracting model outputs: %s", e, exc_info=True)
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
            logger.error("Error extracting tool inputs: %s", e, exc_info=True)
            return {}

    def _extract_tool_output(self, response: Any) -> dict[str, Any]:
        """Extract output from tool response."""
        try:
            if hasattr(response, "content"):
                return {"output": response.content}
            return {"output": str(response)}
        except Exception as e:
            logger.error("Error extracting tool output: %s", e, exc_info=True)
            return {"output": str(response)}

    # Agent lifecycle hooks

    def before_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Hook called before agent starts execution.

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
            logger.error("Error in before_agent: %s", e, exc_info=True)
            return None

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Hook called after agent completes execution.

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
            logger.error("Error in after_agent: %s", e, exc_info=True)

        return None

    # Model call wrapping

    def wrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Wrap synchronous model calls to trace LLM execution.

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

            logger.error("Model call failed: %s", e, exc_info=True)
            raise

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Wrap async model calls to trace LLM execution.

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
                logger.error("Model call failed: %s", e, exc_info=True)
                raise

    # Tool call wrapping

    def wrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Wrap synchronous tool calls to trace tool execution.

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

            logger.debug("Tool call completed (%s)", tool_name)
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

            logger.error("Tool call failed: %s", e, exc_info=True)
            raise

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """Wrap async tool calls to trace tool execution.

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
                logger.debug("Tool call completed (%s)", tool_name)
                return response

            except Exception as e:
                # Fail span with error
                span_data.fail(e)
                ctx.set_payload(span_data.to_dict())
                logger.error("Tool call failed: %s", e, exc_info=True)
                raise
