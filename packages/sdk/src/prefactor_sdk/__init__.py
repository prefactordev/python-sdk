"""Prefactor SDK - Automatic observability for LangChain agents."""

import atexit
from typing import Optional

import pfid

# Re-export core components for backward compatibility
from prefactor_core import (
    Config,
    ErrorInfo,
    HttpTransport,
    HttpTransportConfig,
    Span,
    SpanContext,
    SpanStatus,
    SpanType,
    StdioTransport,
    TokenUsage,
    Tracer,
    Transport,
    configure_logging,
    get_logger,
    serialize_value,
    truncate_string,
)

# Re-export langchain components for backward compatibility
from prefactor_langchain import (
    PrefactorCallbackHandler,
    PrefactorMiddleware,
    extract_error_info,
    extract_token_usage,
)

__version__ = "0.2.0"

# Global tracer, handler, and middleware instances
_global_tracer: Optional[Tracer] = None
_global_handler: Optional[PrefactorCallbackHandler] = None
_global_middleware: Optional[PrefactorMiddleware] = None

logger = get_logger("init")


def init(config: Optional[Config] = None) -> PrefactorMiddleware:
    """
    Initialize Prefactor SDK for LangChain tracing (Middleware API).

    This creates middleware that can be passed to create_agent() to enable
    automatic tracing of agent execution, LLM calls, and tool usage.

    Args:
        config: Optional configuration. If not provided, defaults will be used.

    Returns:
        The middleware to pass to create_agent().

    Example:
        ```python
        import prefactor_sdk
        from langchain.agents import create_agent

        # Initialize Prefactor
        middleware = prefactor_sdk.init()

        # Create agent with middleware
        agent = create_agent(
            model="claude-sonnet-4-5-20250929",
            tools=[...],
            middleware=[middleware]
        )

        # All operations will now be automatically traced
        result = agent.invoke({"messages": [("user", "Hello!")]})
        ```

    Note:
        For legacy callback handler support, use init_callback() instead.
    """
    global _global_tracer, _global_middleware

    # Configure logging
    configure_logging()

    # Use provided config or create default
    if config is None:
        config = Config()

    logger.info(f"Initializing Prefactor SDK with config: {config}")

    # Create transport
    if config.transport_type == "stdio":
        transport = StdioTransport()
    elif config.transport_type == "http":
        if config.http_config is None:
            raise ValueError("HTTP transport requires configuration")
        transport = HttpTransport(config.http_config)
    else:
        raise ValueError(f"Unsupported transport type: {config.transport_type}")

    # Create tracer if not already created
    if _global_tracer is None:
        # Extract partition from agent_id if provided (for HTTP transport)
        partition = None
        if config.http_config is not None and config.http_config.agent_id is not None:
            partition = pfid.extract_partition(config.http_config.agent_id)
        _global_tracer = Tracer(transport=transport, partition=partition)
        logger.debug("Created global tracer")

    # Create middleware
    if _global_middleware is None:
        _global_middleware = PrefactorMiddleware(tracer=_global_tracer)
        logger.debug("Created middleware")

    return _global_middleware


def init_callback(config: Optional[Config] = None) -> PrefactorCallbackHandler:
    """
    Initialize Prefactor callback handler (LEGACY).

    .. deprecated:: 0.2.0
        Use init() with create_agent() instead for the modern middleware API.
        This legacy API will be maintained for backwards compatibility but
        new code should use the middleware approach.

    This creates a callback handler that can be passed to LangChain
    models and chains to enable automatic tracing.

    Args:
        config: Optional configuration. If not provided, defaults will be used.

    Returns:
        The callback handler to pass to LangChain models/chains.

    Example:
        ```python
        import prefactor_sdk
        from langchain_openai import ChatOpenAI

        # Initialize Prefactor (legacy)
        handler = prefactor_sdk.init_callback()

        # Pass the handler to your LangChain model
        llm = ChatOpenAI(model="gpt-4", callbacks=[handler])

        # All operations will now be automatically traced
        response = llm.invoke("Hello!")
        ```
    """
    global _global_tracer, _global_handler

    # Configure logging
    configure_logging()

    # Use provided config or create default
    if config is None:
        config = Config()

    logger.info(f"Initializing Prefactor SDK (callback mode) with config: {config}")

    # Create transport
    if config.transport_type == "stdio":
        transport = StdioTransport()
    elif config.transport_type == "http":
        if config.http_config is None:
            raise ValueError("HTTP transport requires configuration")
        transport = HttpTransport(config.http_config)
    else:
        raise ValueError(f"Unsupported transport type: {config.transport_type}")

    # Create tracer if not already created (share with middleware if both are used)
    if _global_tracer is None:
        # Extract partition from agent_id if provided (for HTTP transport)
        partition = None
        if config.http_config is not None and config.http_config.agent_id is not None:
            partition = pfid.extract_partition(config.http_config.agent_id)
        _global_tracer = Tracer(transport=transport, partition=partition)
        logger.debug("Created global tracer")

    # Create callback handler
    if _global_handler is None:
        _global_handler = PrefactorCallbackHandler(tracer=_global_tracer)
        logger.debug("Created callback handler")

    return _global_handler


def get_tracer() -> Tracer:
    """
    Get the global tracer instance.

    If init() has not been called yet, this will automatically
    call init() with default configuration.

    Returns:
        The global Tracer instance.

    Example:
        ```python
        import prefactor

        tracer = prefactor.get_tracer()
        ```
    """
    global _global_tracer

    if _global_tracer is None:
        logger.debug("Tracer not initialized, calling init()")
        init()

    assert _global_tracer is not None, "Tracer should be initialized after init()"
    return _global_tracer


def shutdown() -> None:
    """
    Shutdown the Prefactor SDK and flush all pending spans.

    This closes the tracer and ensures all queued spans are sent before
    the program exits. This is automatically registered with atexit, but
    can also be called manually for explicit cleanup.

    It's safe to call this multiple times - subsequent calls will be no-ops.

    Example:
        ```python
        import prefactor_sdk

        middleware = prefactor_sdk.init()
        # ... use the agent ...

        # Explicitly flush and cleanup
        prefactor_sdk.shutdown()
        ```

    Note:
        This function is automatically called at program exit via atexit.
        Manual calls are only needed if you want to ensure cleanup at a
        specific point in your code.
    """
    global _global_tracer

    if _global_tracer is not None:
        try:
            logger.debug("Shutting down Prefactor SDK")
        except Exception:
            # Logging may already be shut down during atexit
            pass

        try:
            _global_tracer.close()
        except Exception as e:
            try:
                logger.error(f"Error during shutdown: {e}", exc_info=True)
            except Exception:
                # Logging may already be shut down during atexit
                pass

        try:
            logger.info("Prefactor SDK shutdown complete")
        except Exception:
            # Logging may already be shut down during atexit
            pass


# Register automatic cleanup on program exit
atexit.register(shutdown)


__all__ = [
    # Init functions
    "init",
    "init_callback",
    "get_tracer",
    "shutdown",
    # Config
    "Config",
    "HttpTransportConfig",
    # Tracing
    "Span",
    "SpanType",
    "SpanStatus",
    "TokenUsage",
    "ErrorInfo",
    "Tracer",
    "SpanContext",
    # Transport
    "Transport",
    "StdioTransport",
    "HttpTransport",
    # LangChain
    "PrefactorMiddleware",
    "PrefactorCallbackHandler",
    "extract_token_usage",
    "extract_error_info",
    # Utils
    "configure_logging",
    "get_logger",
    "serialize_value",
    "truncate_string",
]
