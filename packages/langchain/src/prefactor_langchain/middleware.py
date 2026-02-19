"""LangChain middleware for automatic tracing via prefactor-core."""

import asyncio
import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any, AsyncContextManager, Callable

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

    Three usage patterns are supported:

    1. **Pre-configured Client** (recommended): Pass a pre-configured client for
       full control over settings. The user is responsible for client lifecycle.

    2. **Pre-configured Instance**: Pass an existing `AgentInstanceHandle` to share
       a single instance between the LangChain middleware and other parts of your
       program. Use this when you need to create spans outside of the LangChain
       agent (e.g. for custom pre/post-processing steps). The caller owns the
       instance lifecycle and must call ``instance.finish()`` themselves.

    3. **Factory Pattern**: Use `from_config()` for quick setup. The middleware
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

    Example - Pre-configured Instance (spans outside the agent):
        from prefactor_core import PrefactorCoreClient, PrefactorCoreConfig
        from prefactor_http.config import HttpClientConfig

        http_config = HttpClientConfig(api_url="...", api_token="...")
        config = PrefactorCoreConfig(http_config=http_config)
        client = PrefactorCoreClient(config)
        await client.initialize()

        instance = await client.create_agent_instance(agent_id="my-agent")
        await instance.start()

        # Share the same instance with the middleware AND your own code
        middleware = PrefactorMiddleware(instance=instance)

        # Instrument your own code with the same instance
        async with instance.span("custom:preprocessing") as ctx:
            ctx.set_result({"step": "preprocess", "status": "ok"})

        # Run your LangChain agent (middleware traces it automatically)
        result = agent.invoke({"messages": [...]})

        # Caller is responsible for cleanup
        await instance.finish()
        await client.close()

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
        client: PrefactorCoreClient | None = None,
        agent_id: str = "langchain-agent",
        agent_name: str | None = None,
        instance: AgentInstanceHandle | None = None,
    ):
        """Initialize the middleware with a pre-configured client or instance.

        Pass either ``client`` or ``instance``, but not both.

        Args:
            client: Pre-initialized PrefactorCoreClient instance. The middleware
                will lazily create its own AgentInstance from this client.
            agent_id: Agent identifier used when the middleware creates its own
                instance from ``client``. Ignored when ``instance`` is provided.
            agent_name: Optional human-readable agent name. Ignored when
                ``instance`` is provided.
            instance: An existing AgentInstanceHandle to use for all spans.
                When provided, the caller is responsible for the instance
                lifecycle (``start()`` / ``finish()``). ``client`` must be
                ``None`` when this is set.

        Raises:
            ValueError: If neither or both of ``client`` and ``instance`` are
                provided, or if ``client`` is not yet initialized.
        """
        if instance is not None and client is not None:
            raise ValueError("Provide either 'client' or 'instance', not both.")

        if instance is not None:
            self._client = None
            self._agent_id = agent_id
            self._agent_name = agent_name
            self._instance = instance
            self._owns_instance = False
            self._owns_client = False
            self._agent_span_cm: AsyncContextManager[SpanContext] | None = None
            self._agent_span_context: SpanContext | None = None
            self._agent_span_id: str | None = None
            self._current_parent_span_id: str | None = None
            self._loop: asyncio.AbstractEventLoop | None = None
            self._pending_emit_futures: list[asyncio.Task[None]] = []
            return

        if client is None:
            msg = (
                "Either 'client' or 'instance' is required"
                " - use PrefactorMiddleware.from_config() for quick setup"
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

        self._instance: AgentInstanceHandle | None = None
        self._owns_instance = True
        self._owns_client = False

        self._agent_span_cm: AsyncContextManager[SpanContext] | None = None
        self._agent_span_context: SpanContext | None = None
        self._agent_span_id: str | None = None
        self._current_parent_span_id: str | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_emit_futures: list[asyncio.Task[None]] = []

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

        middleware = cls.__new__(cls)
        middleware._client = client
        middleware._agent_id = agent_id
        middleware._agent_name = agent_name
        middleware._instance = None
        middleware._owns_instance = True
        middleware._owns_client = True
        middleware._agent_span_cm = None
        middleware._agent_span_context = None
        middleware._agent_span_id = None
        middleware._current_parent_span_id = None
        middleware._loop = None
        middleware._pending_emit_futures = []
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

        # Capture the event loop so sync hooks running in worker threads can
        # schedule coroutines back onto it via loop.call_soon_threadsafe().
        self._loop = asyncio.get_running_loop()

        # Derive a stable schema version ID from the registry + agent_name so
        # that the same configuration always maps to the same version
        # (idempotent across runs) and any change produces a new, distinct ID.
        agent_version_name = "langchain-agent"
        schema_version_id = f"langchain-{self._agent_id}"
        if self._client._config.schema_registry is not None:
            raw = self._client._config.schema_registry.to_agent_schema_version(
                schema_version_id
            )
            digest = hashlib.sha1(
                json.dumps({"name": agent_version_name, **raw}, sort_keys=True).encode()
            ).hexdigest()[:8]
            schema_version_id = f"langchain-{self._agent_id}-{digest}"

        # Create agent instance.  agent_version fields are immutable once
        # stored by the API, so both name and external_identifier must be
        # derived deterministically from the schema content.
        self._instance = await self._client.create_agent_instance(
            agent_id=self._agent_id,
            agent_version={
                "name": agent_version_name,
                "external_identifier": schema_version_id,
            },
            agent_schema_version=None,  # Will use registry if available
            external_schema_version_id=schema_version_id,
        )

        self._owns_instance = True
        await self._instance.start()
        logger.debug("Initialized agent instance %s", self._instance.id)
        return self._instance

    async def close(self) -> None:
        """Close the middleware and cleanup resources.

        Awaits all in-flight span-emit tasks first so that every span has
        been handed to the queue, then closes the agent instance (if we
        created it) and finally the client (which drains and stops the queue).
        """
        # Drain any fire-and-forget span tasks scheduled by sync hooks.
        if self._pending_emit_futures:
            await asyncio.gather(*self._pending_emit_futures, return_exceptions=True)
            self._pending_emit_futures.clear()

        if self._instance is not None and self._owns_instance:
            await self._instance.finish()
            self._instance = None
            self._owns_instance = False

        if self._client is not None and self._owns_client:
            await self._client.close()
            self._client = None
            self._owns_client = False

    def _get_name_from_request(self, request: Any) -> str:
        """Extract model name from request for use as the span name.

        Args:
            request: The model request.

        Returns:
            Model name string, or 'llm' as fallback.
        """
        try:
            if hasattr(request, "model"):
                model = request.model
                return getattr(model, "model_name", getattr(model, "model", "llm"))
            return "llm"
        except Exception as e:
            logger.debug("Error extracting name from request: %s", e)
            return "llm"

    def _message_to_dict(self, message: Any) -> dict[str, Any]:
        """Convert a LangChain message to a compact dict."""
        role = getattr(message, "type", "unknown")
        content = getattr(message, "content", "")
        result: dict[str, Any] = {"role": role}
        # content may be a string or a list of content blocks
        if isinstance(content, str):
            result["content"] = content
        elif isinstance(content, list):
            # Extract text blocks; summarise tool-use blocks
            texts = [
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in content
                if not isinstance(b, dict) or b.get("type") != "tool_use"
            ]
            tool_uses = [
                b
                for b in content
                if isinstance(b, dict) and b.get("type") == "tool_use"
            ]
            if texts:
                result["content"] = " ".join(t for t in texts if t)
            if tool_uses:
                result["tool_calls"] = [
                    {"name": t.get("name"), "args": t.get("input", {})}
                    for t in tool_uses
                ]
        return result

    def _extract_model_inputs(self, request: Any) -> dict[str, Any]:
        """Extract inputs from ModelRequest."""
        try:
            inputs: dict[str, Any] = {}
            if hasattr(request, "model"):
                model = request.model
                inputs["model"] = getattr(
                    model, "model_name", getattr(model, "model", None)
                )
            if hasattr(request, "messages") and request.messages:
                inputs["messages"] = [
                    self._message_to_dict(m) for m in request.messages
                ]
            if hasattr(request, "system_message") and request.system_message:
                inputs["system"] = getattr(request.system_message, "content", None)
            return inputs
        except Exception as e:
            logger.error("Error extracting model inputs: %s", e, exc_info=True)
            return {}

    def _extract_model_outputs(self, response: Any) -> dict[str, Any]:
        """Extract outputs from ModelResponse."""
        try:
            # ModelResponse has a .result list of messages
            if hasattr(response, "result") and response.result:
                messages = [self._message_to_dict(m) for m in response.result]
                return {"messages": messages}
            if hasattr(response, "content"):
                return {"content": response.content}
            return {}
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
            return {}
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

    def _build_llm_params(self, span_data: Any) -> dict[str, Any]:
        """Build the payload (params) dict for an LLM span."""
        params: dict[str, Any] = {}
        if span_data.model_name:
            params["model_name"] = span_data.model_name
        if span_data.provider:
            params["provider"] = span_data.provider
        if span_data.inputs:
            params["inputs"] = span_data.inputs
        if span_data.temperature is not None:
            params["temperature"] = span_data.temperature
        return params

    def _build_llm_result(self, span_data: Any) -> dict[str, Any]:
        """Build the result_payload dict for an LLM span."""
        result: dict[str, Any] = {}
        if span_data.outputs:
            result["outputs"] = span_data.outputs
        if span_data.token_usage:
            result["token_usage"] = span_data.token_usage.to_dict()
        if span_data.error:
            result["error"] = span_data.error.to_dict()
        return result

    def _build_tool_params(self, span_data: Any) -> dict[str, Any]:
        """Build the payload (params) dict for a tool span."""
        params: dict[str, Any] = {}
        if span_data.tool_name:
            params["tool_name"] = span_data.tool_name
        if span_data.inputs:
            params["inputs"] = span_data.inputs
        return params

    def _build_tool_result(self, span_data: Any) -> dict[str, Any]:
        """Build the result_payload dict for a tool span."""
        result: dict[str, Any] = {}
        if span_data.outputs:
            result["outputs"] = span_data.outputs
        if span_data.error:
            result["error"] = span_data.error.to_dict()
        return result

    def _build_agent_params(self, span_data: Any) -> dict[str, Any]:
        """Build the payload (params) dict for an agent span."""
        params: dict[str, Any] = {}
        if span_data.inputs:
            params["inputs"] = span_data.inputs
        if span_data.agent_name:
            params["agent_name"] = span_data.agent_name
        return params

    def _build_agent_result(self, span_data: Any) -> dict[str, Any]:
        """Build the result_payload dict for an agent span."""
        result: dict[str, Any] = {}
        if span_data.outputs:
            result["outputs"] = span_data.outputs
        if span_data.error:
            result["error"] = span_data.error.to_dict()
        return result

    def set_parent_span(self, span_id: str | None) -> None:
        """Set the parent span ID for the next agent invocation (sync path only).

        Only needed when using ``agent.invoke()`` via ``run_in_executor``.
        In that case, ``before_agent`` runs in a worker thread where
        ``contextvars`` are not inherited, so the parent span ID must be
        passed explicitly before entering the executor.

        When using ``agent.ainvoke()`` (the recommended async path), parent
        wiring is automatic via ``SpanContextStack`` — do not call this method.

        Args:
            span_id: The span ID to use as the parent, or None to clear it.
        """
        self._current_parent_span_id = span_id

    def _create_agent_span_sync(
        self,
        instance: AgentInstanceHandle,
        params: dict[str, Any],
    ) -> str:
        """Synchronously create an agent span and return its ID.

        Uses run_coroutine_threadsafe to block until the span is created,
        ensuring the ID is available for child spans to reference.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return ""

        import asyncio

        # Use whatever parent was set by set_parent_span() from the async side.
        # We cannot read the SpanContextStack here because run_in_executor does
        # not copy contextvars into threads (only asyncio.Task does).
        parent_span_id = self._current_parent_span_id

        future = asyncio.run_coroutine_threadsafe(
            instance.create_span(
                schema_name="langchain:agent",
                payload=params,
                parent_span_id=parent_span_id,
            ),
            loop,
        )
        span_id = future.result(timeout=5.0)
        self._agent_span_id = span_id
        self._current_parent_span_id = span_id
        return span_id

    def _emit_child_span(self, span_data: Any) -> None:
        """Schedule a child span (LLM/tool) emission with parent tracking.

        Uses the current parent span ID from _current_parent_span_id.
        """
        if self._instance is None:
            return
        loop = getattr(self, "_loop", None)
        if loop is None or loop.is_closed():
            return

        instance = self._instance
        schema_name: str = span_data.type
        parent_span_id = self._current_parent_span_id
        pending = self._pending_emit_futures

        if schema_name == "langchain:llm":
            params = self._build_llm_params(span_data)
            result = self._build_llm_result(span_data)
        elif schema_name == "langchain:tool":
            params = self._build_tool_params(span_data)
            result = self._build_tool_result(span_data)
        else:
            return

        is_failed = span_data.status == "failed"

        async def _emit() -> None:
            async with instance.span(schema_name, parent_span_id=parent_span_id) as ctx:
                await ctx.start(params)
                if is_failed:
                    await ctx.fail(result)
                else:
                    await ctx.complete(result)

        def _schedule() -> None:
            task = loop.create_task(_emit())
            pending.append(task)

        loop.call_soon_threadsafe(_schedule)

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
            if self._instance is None:
                return None

            messages = []
            if hasattr(state, "get"):
                messages = state.get("messages", [])
            elif hasattr(state, "messages"):
                messages = state.messages

            params = self._build_agent_params(
                AgentSpan(
                    name="agent",
                    type="langchain:agent",
                    inputs={
                        "messages": [str(m) for m in messages[-3:]] if messages else []
                    },
                )
            )
            self._create_agent_span_sync(self._instance, params)
            logger.debug("Created agent span %s", self._agent_span_id)
            return None

        except Exception as e:
            logger.error("Error in before_agent: %s", e, exc_info=True)
            return None

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Hook called after agent completes execution.

        Finishes the agent span created in before_agent.

        Args:
            state: The agent state.
            runtime: The runtime context.

        Returns:
            Optional state updates.
        """
        try:
            if self._agent_span_id is None or self._instance is None:
                return None

            messages = []
            if hasattr(state, "get"):
                messages = state.get("messages", [])
            elif hasattr(state, "messages"):
                messages = state.messages

            outputs = {"messages": [str(m) for m in messages[-3:]] if messages else []}
            result = {"outputs": outputs}

            loop = self._loop
            if loop is None or loop.is_closed():
                return None

            import asyncio

            instance = self._instance
            span_id = self._agent_span_id

            async def _finish() -> None:
                await instance.finish_span(span_id, result_payload=result)

            future = asyncio.run_coroutine_threadsafe(_finish(), loop)
            future.result(timeout=5.0)

            self._agent_span_id = None
            self._current_parent_span_id = None
            logger.debug("Finished agent span %s", span_id)

        except Exception as e:
            logger.error("Error in after_agent: %s", e, exc_info=True)

        return None

    async def abefore_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Async hook called before agent starts execution.

        Creates a ``langchain:agent`` span using the async context manager so
        that ``SpanContextStack`` is updated automatically.  Any outer workflow
        span already on the stack (e.g. ``workflow:agent_step``) is picked up
        as the parent without any manual ``set_parent_span()`` call.

        The span context is kept open and stored in ``_agent_span_context``
        until ``aafter_agent`` exits it.

        Args:
            state: The agent state.
            runtime: The runtime context.

        Returns:
            Optional state updates.
        """
        try:
            instance = await self._ensure_initialized()

            messages = []
            if hasattr(state, "get"):
                messages = state.get("messages", [])
            elif hasattr(state, "messages"):
                messages = state.messages

            params = self._build_agent_params(
                AgentSpan(
                    name="agent",
                    type="langchain:agent",
                    inputs={
                        "messages": [str(m) for m in messages[-3:]] if messages else []
                    },
                )
            )

            # Enter the span context manager and store both the CM object (for
            # __aexit__ in aafter_agent) and the yielded SpanContext.
            # SpanContextStack.peek() here returns the outer workflow span
            # because we are executing in the async event loop context.
            self._agent_span_cm = instance.span("langchain:agent")
            self._agent_span_context = await self._agent_span_cm.__aenter__()
            await self._agent_span_context.start(params)

            self._agent_span_id = self._agent_span_context.id
            logger.debug("Created agent span %s (async)", self._agent_span_id)

        except Exception as e:
            logger.error("Error in abefore_agent: %s", e, exc_info=True)

        return None

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        """Async hook called after agent completes execution.

        Finishes the ``langchain:agent`` span opened by ``abefore_agent`` by
        exiting its async context manager.

        Args:
            state: The agent state.
            runtime: The runtime context.

        Returns:
            Optional state updates.
        """
        try:
            if self._agent_span_cm is None or self._agent_span_context is None:
                return None

            messages = []
            if hasattr(state, "get"):
                messages = state.get("messages", [])
            elif hasattr(state, "messages"):
                messages = state.messages

            outputs = {"messages": [str(m) for m in messages[-3:]] if messages else []}
            await self._agent_span_context.complete({"outputs": outputs})
            await self._agent_span_cm.__aexit__(None, None, None)

            logger.debug("Finished agent span %s (async)", self._agent_span_id)
            self._agent_span_cm = None
            self._agent_span_context = None
            self._agent_span_id = None

        except Exception as e:
            logger.error("Error in aafter_agent: %s", e, exc_info=True)

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
        inputs = self._extract_model_inputs(request)
        span_data = LLMSpan(
            name=self._get_name_from_request(request),
            type="langchain:llm",
            inputs=inputs,
            model_name=inputs.get("model"),
        )

        try:
            response = handler(request)

            span_data.complete(outputs=self._extract_model_outputs(response))
            span_data.token_usage = extract_token_usage(response)

            self._emit_child_span(span_data)
            logger.debug("Model call completed")
            return response

        except Exception as e:
            span_data.fail(e)
            self._emit_child_span(span_data)
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

        inputs = self._extract_model_inputs(request)
        span_data = LLMSpan(
            name=self._get_name_from_request(request),
            type="langchain:llm",
            inputs=inputs,
            model_name=inputs.get("model"),
        )

        async with instance.span("langchain:llm") as ctx:
            await ctx.start(self._build_llm_params(span_data))
            try:
                response = await handler(request)

                span_data.complete(outputs=self._extract_model_outputs(response))
                span_data.token_usage = extract_token_usage(response)

                await ctx.complete(self._build_llm_result(span_data))
                logger.debug("Model call completed")
                return response

            except Exception as e:
                span_data.fail(e)
                await ctx.fail(self._build_llm_result(span_data))
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
        inputs = self._extract_tool_inputs(request)
        tool_name = inputs.get("tool_name", "unknown_tool")

        span_data = ToolSpan(
            name=tool_name,
            type="langchain:tool",
            inputs=inputs,
            tool_name=tool_name,
        )

        try:
            response = handler(request)

            outputs = self._extract_tool_output(response)
            span_data.complete(outputs=outputs)

            self._emit_child_span(span_data)
            logger.debug("Tool call completed (%s)", tool_name)
            return response

        except Exception as e:
            span_data.fail(e)
            self._emit_child_span(span_data)
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

        inputs = self._extract_tool_inputs(request)
        tool_name = inputs.get("tool_name", "unknown_tool")

        span_data = ToolSpan(
            name=tool_name,
            type="langchain:tool",
            inputs=inputs,
            tool_name=tool_name,
        )

        async with instance.span("langchain:tool") as ctx:
            await ctx.start(self._build_tool_params(span_data))
            try:
                response = await handler(request)

                span_data.complete(outputs=self._extract_tool_output(response))

                await ctx.complete(self._build_tool_result(span_data))
                logger.debug("Tool call completed (%s)", tool_name)
                return response

            except Exception as e:
                span_data.fail(e)
                await ctx.fail(self._build_tool_result(span_data))
                logger.error("Tool call failed: %s", e, exc_info=True)
                raise
