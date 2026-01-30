"""Prefactor SDK - Automatic observability for LangChain agents.

This package provides the integration layer between prefactor-core (span management)
and prefactor-http (backend API). All HTTP transport and agent instance management
is handled through the prefactor-http package.
"""

import asyncio
import atexit
import hashlib
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from prefactor_core import (
    Config,
    ErrorInfo,
    Span,
    SpanContext,
    SpanStatus,
    SpanType,
    TokenUsage,
    configure_logging,
    get_logger,
    serialize_value,
    truncate_string,
)
from prefactor_http import HttpClientConfig, PrefactorHttpClient
from prefactor_http.exceptions import (
    PrefactorApiError,
    PrefactorAuthError,
    PrefactorClientError,
    PrefactorHttpError,
    PrefactorNotFoundError,
    PrefactorRetryExhaustedError,
    PrefactorValidationError,
)
from prefactor_langchain import (
    PrefactorCallbackHandler,
    PrefactorMiddleware,
    extract_error_info,
    extract_token_usage,
)

__version__ = "0.3.0"

logger = get_logger("init")

# Global instances
_global_http_client: Optional[PrefactorHttpClient] = None
_global_tracer: Optional["HttpTracer"] = None
_global_handler: Optional[PrefactorCallbackHandler] = None
_global_middleware: Optional[PrefactorMiddleware] = None
_global_sdk_config: Optional["SdkConfig"] = None


class SdkConfig:
    """SDK configuration combining capture and HTTP settings.

        This is the main configuration class for prefactor-sdk, replacing
    the old transport-based configuration in prefactor-core.
    """

    # API connection
    api_url: str
    api_token: str

    # Agent metadata (optional, auto-detected if not provided)
    agent_id: Optional[str] = None
    agent_version: Optional[str] = None
    agent_name: Optional[str] = None

    # Schema configuration (BYO schema support)
    agent_schema: Optional[dict[str, Any]] = None  # Full custom schema
    agent_schema_version: Optional[str] = None  # Schema version identifier only
    skip_schema: bool = False  # Skip schema in registration

    # HTTP client settings
    request_timeout: float = 30.0
    connect_timeout: float = 10.0

    # Retry settings
    max_retries: int = 3
    initial_retry_delay: float = 1.0
    max_retry_delay: float = 60.0
    retry_multiplier: float = 2.0

    # Capture settings (inherited from core Config)
    sample_rate: float = 1.0
    capture_inputs: bool = True
    capture_outputs: bool = True
    max_input_length: int = 10000
    max_output_length: int = 10000

    def __init__(
        self,
        # Required
        api_url: str,
        api_token: str,
        # Optional agent metadata
        agent_id: Optional[str] = None,
        agent_version: Optional[str] = None,
        agent_name: Optional[str] = None,
        # Optional schema configuration (mutually exclusive)
        agent_schema: Optional[dict[str, Any]] = None,
        agent_schema_version: Optional[str] = None,
        skip_schema: bool = False,
        # HTTP settings
        request_timeout: float = 30.0,
        connect_timeout: float = 10.0,
        max_retries: int = 3,
        initial_retry_delay: float = 1.0,
        max_retry_delay: float = 60.0,
        retry_multiplier: float = 2.0,
        # Capture settings
        sample_rate: Optional[float] = None,
        capture_inputs: Optional[bool] = None,
        capture_outputs: Optional[bool] = None,
        max_input_length: Optional[int] = None,
        max_output_length: Optional[int] = None,
    ):
        """Initialize SDK configuration.

        Args:
            api_url: Base URL for the Prefactor API
            api_token: Bearer token for API authentication
            agent_id: Optional agent ID (auto-detected from main file if
                not provided)
            agent_version: Optional agent version (auto-detected from git
                if not provided)
            agent_name: Optional agent name
            agent_schema: Full custom schema dictionary (requires
                external_identifier and span_schemas)
            agent_schema_version: Schema version identifier string
                (alternative to agent_schema)
            skip_schema: Skip schema completely if pre-registered on backend
            request_timeout: HTTP request timeout in seconds (default: 30)
            connect_timeout: HTTP connection timeout in seconds (default: 10)
            max_retries: Maximum retry attempts for failed requests
                (default: 3)
            initial_retry_delay: Initial retry delay in seconds (default: 1)
            max_retry_delay: Maximum retry delay in seconds (default: 60)
            retry_multiplier: Exponential backoff multiplier (default: 2)
            sample_rate: Sampling rate 0.0-1.0 (default: 1.0)
            capture_inputs: Whether to capture span inputs (default: True)
            capture_outputs: Whether to capture span outputs (default: True)
            max_input_length: Maximum input length in bytes (default: 10000)
            max_output_length: Maximum output length in bytes (default: 10000)
        """
        self.api_url = api_url
        self.api_token = api_token
        self.agent_id = agent_id or self._generate_agent_id()
        self.agent_version = agent_version or self._get_git_version()
        self.agent_name = agent_name

        # Schema configuration (validate mutual exclusivity)
        self.agent_schema = agent_schema
        self.agent_schema_version = agent_schema_version
        self.skip_schema = skip_schema

        schema_options_set = sum(
            [
                skip_schema,
                agent_schema is not None,
                agent_schema_version is not None,
            ]
        )
        if schema_options_set > 1:
            raise ValueError(
                "Only one schema option can be specified: "
                "skip_schema=True, agent_schema, or agent_schema_version"
            )

        # Validate agent_schema structure if provided
        if self.agent_schema is not None:
            if not isinstance(self.agent_schema, dict):
                raise ValueError(
                    f"agent_schema must be a dictionary, "
                    f"got {type(self.agent_schema).__name__}"
                )
            required_keys = {"external_identifier", "span_schemas"}
            missing_keys = required_keys - set(self.agent_schema.keys())
            if missing_keys:
                raise ValueError(f"agent_schema missing required keys: {missing_keys}")
            if not isinstance(self.agent_schema["span_schemas"], dict):
                raise ValueError("agent_schema['span_schemas'] must be a dictionary")
            if not isinstance(self.agent_schema["external_identifier"], str):
                raise ValueError("agent_schema['external_identifier'] must be a string")

        # HTTP settings
        self.request_timeout = request_timeout
        self.connect_timeout = connect_timeout
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay
        self.max_retry_delay = max_retry_delay
        self.retry_multiplier = retry_multiplier

        # Capture settings with environment fallbacks
        self.sample_rate = (
            sample_rate
            if sample_rate is not None
            else self._get_env_or_default("PREFACTOR_SAMPLE_RATE", 1.0, float)
        )
        self.capture_inputs = (
            capture_inputs
            if capture_inputs is not None
            else self._get_env_or_default(
                "PREFACTOR_CAPTURE_INPUTS", True, self._parse_bool
            )
        )
        self.capture_outputs = (
            capture_outputs
            if capture_outputs is not None
            else self._get_env_or_default(
                "PREFACTOR_CAPTURE_OUTPUTS", True, self._parse_bool
            )
        )
        self.max_input_length = (
            max_input_length
            if max_input_length is not None
            else self._get_env_or_default("PREFACTOR_MAX_INPUT_LENGTH", 10000, int)
        )
        self.max_output_length = (
            max_output_length
            if max_output_length is not None
            else self._get_env_or_default("PREFACTOR_MAX_OUTPUT_LENGTH", 10000, int)
        )

        # Validate sample rate
        if not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError("sample_rate must be between 0.0 and 1.0")

    @staticmethod
    def _parse_bool(value: str) -> bool:
        """Parse a string to boolean."""
        return value.lower() in ("true", "1", "yes")

    @staticmethod
    def _get_env_or_default(
        key: str,
        default: Any,
        converter: "Callable[[str], Any]" = str,
    ) -> Any:
        """Get environment variable or return default."""
        value = os.getenv(key)
        if value is None:
            return default
        try:
            return converter(value)
        except (ValueError, TypeError):
            logger.warning(
                f"Invalid value for {key}: {value}, using default: {default}"
            )
            return default

    @staticmethod
    def _generate_agent_id() -> str:
        """Generate agent ID from main module path."""
        import __main__

        main_file = getattr(__main__, "__file__", "unknown")
        return hashlib.sha256(main_file.encode()).hexdigest()[:16]

    @staticmethod
    def _get_git_version() -> str:
        """Get git commit hash if available."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if result.returncode == 0:
                return result.stdout.strip()[:8]
        except Exception:
            pass
        return "unknown"

    def to_http_client_config(self) -> HttpClientConfig:
        """Convert SDK config to HttpClientConfig."""
        return HttpClientConfig(
            api_url=self.api_url,
            api_token=self.api_token,
            request_timeout=self.request_timeout,
            connect_timeout=self.connect_timeout,
            max_retries=self.max_retries,
            initial_retry_delay=self.initial_retry_delay,
            max_retry_delay=self.max_retry_delay,
            retry_multiplier=self.retry_multiplier,
        )

    def to_core_config(self) -> Config:
        """Convert SDK config to core Config."""
        return Config(
            sample_rate=self.sample_rate,
            capture_inputs=self.capture_inputs,
            capture_outputs=self.capture_outputs,
            max_input_length=self.max_input_length,
            max_output_length=self.max_output_length,
        )

    def _get_default_schema(self) -> dict[str, Any]:
        """Get the default hardcoded schema."""
        return {
            "external_identifier": "1.0.0",
            "span_schemas": {
                "agent": {
                    "type": "object",
                    "properties": {"type": {"type": "string", "const": "agent"}},
                },
                "llm": {
                    "type": "object",
                    "properties": {"type": {"type": "string", "const": "llm"}},
                },
                "tool": {
                    "type": "object",
                    "properties": {"type": {"type": "string", "const": "tool"}},
                },
                "chain": {
                    "type": "object",
                    "properties": {"type": {"type": "string", "const": "chain"}},
                },
                "retriever": {
                    "type": "object",
                    "properties": {"type": {"type": "string", "const": "retriever"}},
                },
            },
        }

    def build_agent_metadata(self) -> dict[str, Any]:
        """Build agent metadata for registration."""
        # Base metadata
        metadata = {
            "agent_id": self.agent_id,
            "agent_version": {
                "name": self.agent_version or "unknown",
                "description": "Prefactor SDK",
                "external_identifier": self.agent_version or "unknown",
            },
        }

        # Determine schema mode
        if self.skip_schema:
            # Skip schema (pre-registered on backend)
            pass
        elif self.agent_schema is not None:
            # Use custom schema
            metadata["agent_schema_version"] = self.agent_schema
        elif self.agent_schema_version is not None:
            # Use schema version identifier only
            metadata["agent_schema_version"] = {
                "external_identifier": self.agent_schema_version,
            }
        else:
            # Use default schema
            metadata["agent_schema_version"] = self._get_default_schema()

        return metadata


class QueueItemType(str, Enum):
    """Types of items that can be queued."""

    SPAN = "span"
    FINISH_SPAN = "finish_span"


@dataclass
class QueueItem:
    """Item in the processing queue."""

    item_type: QueueItemType
    sdk_span_id: str
    payload: Any


class SpanFinishData:
    """Data needed to finish a span."""

    sdk_span_id: str
    backend_span_id: str
    timestamp: str


class HttpTracer:
    """Tracer that manages spans and sends them to backend via prefactor-http.

    This replaces the old Transport abstraction. All HTTP operations go through
    the prefactor-http client APIs.
    """

    def __init__(
        self,
        sdk_config: SdkConfig,
        sync_mode: bool = False,
    ):
        """Initialize the HTTP tracer.

        Args:
            sdk_config: SDK configuration with HTTP and agent metadata
            sync_mode: If True, use synchronous operations. If False, use async.
        """
        self._config = sdk_config
        self._sync_mode = sync_mode
        self._agent_instance_id: Optional[str] = None
        self._agent_instance_started = False
        self._agent_instance_finished = False

        # Span ID mapping (SDK span_id -> backend span_id)
        self._span_id_map: dict[str, str] = {}

        # HTTP client
        self._client = PrefactorHttpClient(sdk_config.to_http_client_config())

        # Async processing queue
        self._queue: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()

        # Sampling
        self._counter = 0

    async def _initialize(self) -> bool:
        """Initialize the tracer by registering the agent instance."""
        try:
            async with self._client:
                metadata = self._config.build_agent_metadata()
                instance = await self._client.agent_instances.register(
                    agent_id=metadata["agent_id"],
                    agent_version=metadata["agent_version"],
                    agent_schema_version=metadata.get(
                        "agent_schema_version", {"external_identifier": "1.0.0"}
                    ),
                )
                self._agent_instance_id = instance.id
                logger.info(f"Agent instance registered: {instance.id}")
                return True
        except Exception as e:
            logger.error(f"Failed to register agent instance: {e}", exc_info=True)
            return False

    def _should_sample(self) -> bool:
        """Determine if the current call should be sampled."""
        if self._config.sample_rate >= 1.0:
            return True
        self._counter += 1
        return (self._counter / self._config.sample_rate) >= 1

    def _transform_span_to_api_format(
        self,
        span: Span,
    ) -> tuple[str, dict[str, Any], str, Optional[str], Optional[str]]:
        """Transform SDK Span to API format components.

        Returns:
            Tuple of (schema_name, payload, sdk_span_id, backend_parent_id,
                finished_at)
        """
        # Map span types to schema names
        schema_name_map = {
            SpanType.AGENT: "agent",
            SpanType.LLM: "llm",
            SpanType.TOOL: "tool",
            SpanType.CHAIN: "chain",
            SpanType.RETRIEVER: "retriever",
        }

        # Build payload
        payload: dict[str, Any] = {
            "span_id": span.span_id,
            "trace_id": span.trace_id,
            "name": span.name,
            "status": span.status.value,
            "inputs": span.inputs if self._config.capture_inputs else {},
            "outputs": span.outputs if self._config.capture_outputs else None,
            "metadata": span.metadata,
            "tags": span.tags,
        }

        if span.token_usage:
            payload["token_usage"] = {
                "prompt_tokens": span.token_usage.prompt_tokens,
                "completion_tokens": span.token_usage.completion_tokens,
                "total_tokens": span.token_usage.total_tokens,
            }

        if span.error:
            payload["error"] = {
                "error_type": span.error.error_type,
                "message": span.error.message,
                "stacktrace": span.error.stacktrace,
            }

        # Get parent span backend ID
        parent_sdk_span_id = span.parent_span_id
        backend_parent_id = None
        if parent_sdk_span_id:
            backend_parent_id = self._span_id_map.get(parent_sdk_span_id)

        # Convert end_time to ISO 8601 if exists
        finished_at: Optional[str] = None
        if span.end_time:
            finished_at = datetime.fromtimestamp(
                span.end_time, tz=timezone.utc
            ).isoformat()

        return (
            schema_name_map[span.span_type],
            payload,
            span.span_id,
            backend_parent_id,
            finished_at,
        )

    async def start_agent_instance(self) -> None:
        """Mark the agent instance as started in the backend."""
        if not self._agent_instance_id or self._agent_instance_started:
            return

        try:
            async with self._client:
                await self._client.agent_instances.start(self._agent_instance_id)
                self._agent_instance_started = True
                logger.info(f"Agent instance started: {self._agent_instance_id}")
        except Exception as e:
            logger.error(f"Failed to start agent instance: {e}", exc_info=True)

    async def finish_agent_instance(self) -> None:
        """Mark the agent instance as finished in the backend."""
        if not self._agent_instance_id or self._agent_instance_finished:
            return

        try:
            async with self._client:
                await self._client.agent_instances.finish(self._agent_instance_id)
                self._agent_instance_finished = True
                logger.info(f"Agent instance finished: {self._agent_instance_id}")

            # Drain queue
            await self._drain_queue()
        except Exception as e:
            logger.error(f"Failed to finish agent instance: {e}", exc_info=True)

    async def emit_span(self, span: Span) -> None:
        """Emit a span to the backend.

        For agent spans (long-running), sends to backend immediately.
        For other spans, queues for batch processing.

        Args:
            span: The span to emit
        """
        if not self._should_sample():
            return

        if not self._agent_instance_id:
            logger.warning("Agent instance not registered, dropping span")
            return

        try:
            schema_name, payload, sdk_span_id, parent_id, finished_at = (
                self._transform_span_to_api_format(span)
            )

            async with self._client:
                result = await self._client.agent_spans.create(
                    agent_instance_id=self._agent_instance_id,
                    schema_name=schema_name,
                    payload=serialize_value(payload),
                    id=sdk_span_id,
                    parent_span_id=parent_id,
                    started_at=datetime.fromtimestamp(span.start_time, tz=timezone.utc),
                    finished_at=datetime.fromtimestamp(span.end_time, tz=timezone.utc)
                    if span.end_time
                    else None,
                )

                # Store backend ID mapping
                self._span_id_map[sdk_span_id] = result.id
                logger.debug(f"Emitted span {sdk_span_id} -> backend ID {result.id}")
        except Exception as e:
            logger.error(f"Failed to emit span: {e}", exc_info=True)

    async def emit_span_finish(self, span_id: str, end_time: float) -> None:
        """Emit a span finish event.

        For agent spans that were created without an end time and need to
        be marked as finished later.

        Args:
            span_id: SDK span ID to finish
            end_time: The end timestamp
        """
        backend_span_id = self._span_id_map.get(span_id)
        if not backend_span_id:
            logger.warning(f"Cannot finish span {span_id}: backend ID not found")
            return

        try:
            async with self._client:
                await self._client.agent_spans.finish(
                    backend_span_id,
                    timestamp=datetime.fromtimestamp(end_time, tz=timezone.utc),
                )
                logger.debug(f"Finished span {span_id} (backend ID: {backend_span_id})")
                del self._span_id_map[span_id]
        except Exception as e:
            logger.error(f"Failed to finish span: {e}", exc_info=True)

    async def _worker_loop(self) -> None:
        """Background worker for processing queued spans."""
        while not self._shutdown_event.is_set():
            try:
                # Wait for shutdown signal or timeout
                await asyncio.wait_for(self._shutdown_event.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                # Process any queued items
                while not self._queue.empty():
                    try:
                        item = self._queue.get_nowait()
                        if item.item_type == QueueItemType.SPAN:
                            # Process span
                            pass
                        elif item.item_type == QueueItemType.FINISH_SPAN:
                            # Process finish
                            pass
                    except asyncio.QueueEmpty:
                        break

    async def _drain_queue(self) -> None:
        """Drain remaining items from the queue."""
        items_processed = 0
        while not self._queue.empty() and items_processed < 100:
            try:
                item = self._queue.get_nowait()
                if item.item_type == QueueItemType.SPAN:
                    pass  # Process
                items_processed += 1
            except asyncio.QueueEmpty:
                break

        if not self._queue.empty():
            logger.warning(
                f"Queue not fully drained, {self._queue.qsize()} items remaining"
            )

    def close(self) -> None:
        """Close the tracer and cleanup resources."""
        if self._sync_mode:
            # Synchronous close
            pass
        else:
            # Async close
            pass


def init(sdk_config: Optional[SdkConfig] = None) -> PrefactorMiddleware:
    """Initialize Prefactor SDK for LangChain tracing.

    This creates middleware that can be passed to create_agent() to enable
    automatic tracing of agent execution, LLM calls, and tool usage.

    Args:
        sdk_config: Optional SDK configuration. If not provided, configuration
            must be available via environment variables (PREFACTOR_API_URL,
            PREFACTOR_API_TOKEN).

    Returns:
        The middleware to pass to create_agent().

    Example:
        ```python
        import prefactor_sdk
        from langchain.agents import create_agent

        # Initialize with explicit config
        config = prefactor_sdk.SdkConfig(
            api_url="https://api.prefactor.ai",
            api_token="your-token"
        )
        middleware = prefactor_sdk.init(config)

        # Create agent with middleware
        agent = create_agent(
            model="claude-sonnet-4-5-20250929",
            tools=[...],
            middleware=[middleware]
        )

        # All operations will now be automatically traced
        result = agent.invoke({"messages": [("user", "Hello!")]})
        ```
    """
    global _global_http_client, _global_tracer, _global_middleware, _global_sdk_config

    configure_logging()

    # Load config from environment if not provided
    if sdk_config is None:
        api_url = os.getenv("PREFACTOR_API_URL")
        api_token = os.getenv("PREFACTOR_API_TOKEN")

        if not api_url or not api_token:
            raise ValueError(
                "SDK configuration required. Either pass SdkConfig to init() "
                "or set PREFACTOR_API_URL and PREFACTOR_API_TOKEN "
                "environment variables."
            )

        sdk_config = SdkConfig(
            api_url=api_url,
            api_token=api_token,
        )

    logger.info(f"Initializing Prefactor SDK with config: {sdk_config.api_url}")

    _global_sdk_config = sdk_config

    # Create HTTP client
    if _global_http_client is None:
        _global_http_client = PrefactorHttpClient(sdk_config.to_http_client_config())
        logger.debug("Created HTTP client")

    # Create tracer (this will handle registration and span dispatch)
    if _global_tracer is None:
        _global_tracer = HttpTracer(sdk_config)
        logger.debug("Created HTTP tracer")

    # Create middleware
    if _global_middleware is None:
        _global_middleware = PrefactorMiddleware(tracer=_global_tracer)
        logger.debug("Created middleware")

    return _global_middleware


def shutdown() -> None:
    """Shutdown the Prefactor SDK and flush all pending spans.

    This finishes the agent instance and ensures all spans are sent.
    Automatically registered with atexit.
    """
    global _global_http_client, _global_tracer

    try:
        logger.debug("Shutting down Prefactor SDK")

        if _global_tracer is not None:
            _global_tracer.close()

        logger.info("Prefactor SDK shutdown complete")
    except Exception as e:
        try:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
        except Exception:
            pass


# Register automatic cleanup on program exit
atexit.register(shutdown)

__all__ = [
    # Init functions
    "init",
    "shutdown",
    # Config
    "SdkConfig",
    # Tracer
    "HttpTracer",
    # Core re-exports
    "Config",
    "Span",
    "SpanType",
    "SpanStatus",
    "SpanContext",
    "TokenUsage",
    "ErrorInfo",
    "configure_logging",
    "get_logger",
    "serialize_value",
    "truncate_string",
    # HTTP client re-exports
    "PrefactorHttpClient",
    "HttpClientConfig",
    # Exceptions
    "PrefactorHttpError",
    "PrefactorApiError",
    "PrefactorAuthError",
    "PrefactorClientError",
    "PrefactorNotFoundError",
    "PrefactorRetryExhaustedError",
    "PrefactorValidationError",
    # LangChain
    "PrefactorMiddleware",
    "PrefactorCallbackHandler",
    "extract_token_usage",
    "extract_error_info",
]
