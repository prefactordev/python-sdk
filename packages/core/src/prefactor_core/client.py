"""Main client for prefactor-core.

This module provides the PrefactorCoreClient, which is the main entry point
for the SDK. It manages the complete lifecycle of agent instances and spans
through an async queue-based architecture.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from prefactor_http.client import PrefactorHttpClient
from prefactor_http.exceptions import is_permanent_http_error, is_transient_http_error

from ._version import PACKAGE_NAME as CORE_PACKAGE_NAME
from ._version import PACKAGE_VERSION as CORE_PACKAGE_VERSION
from .config import PrefactorCoreConfig
from .context_stack import SpanContextStack
from .exceptions import (
    ClientAlreadyInitializedError,
    ClientNotInitializedError,
    PrefactorTelemetryFailureError,
)
from .managers.agent_instance import AgentInstanceManager
from .managers.span import SpanManager
from .operations import Operation, OperationType
from .queue.base import Queue
from .queue.executor import TaskExecutor
from .queue.memory import InMemoryQueue

if TYPE_CHECKING:
    from .managers.agent_instance import AgentInstanceHandle

logger = logging.getLogger(__name__)
CORE_SDK_HEADER_ENTRY = f"{CORE_PACKAGE_NAME}@{CORE_PACKAGE_VERSION}"


class PrefactorCoreClient:
    """Main entry point for the prefactor-core SDK.

    This client provides a high-level interface for managing agent instances
    and spans. All operations are queued and processed asynchronously, ensuring
    minimal impact on agent execution flow.

    The client must be initialized before use, either by calling initialize()
    or using it as an async context manager.

    Example:
        config = PrefactorCoreConfig(http_config=...)

        async with PrefactorCoreClient(config) as client:
            instance = await client.create_agent_instance(...)
            await instance.start()

            async with instance.span("agent:llm") as span:
                span.set_payload({"model": "gpt-4"})
                # Your agent logic here

            await instance.finish()
    """

    def __init__(
        self,
        config: PrefactorCoreConfig,
        queue: Queue[Operation] | None = None,
        sdk_header_entry: str | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            config: Configuration for the client.
            queue: Optional custom queue implementation. If not provided,
                an InMemoryQueue is used.
            sdk_header_entry: Optional upstream SDK header entry to prepend.
        """
        self._config = config
        self._queue = queue or InMemoryQueue()
        self._sdk_header_entry = sdk_header_entry.strip() if sdk_header_entry else None
        self._http: PrefactorHttpClient | None = None
        self._executor: TaskExecutor | None = None
        self._instance_manager: AgentInstanceManager | None = None
        self._span_manager: SpanManager | None = None
        self._initialized = False
        self._telemetry_failure: PrefactorTelemetryFailureError | None = None
        self._telemetry_failure_observed = False

    def _build_http_sdk_header(self) -> str:
        """Build the effective SDK header for HTTP requests."""
        if self._sdk_header_entry:
            return f"{self._sdk_header_entry} {CORE_SDK_HEADER_ENTRY}"
        return CORE_SDK_HEADER_ENTRY

    def _set_sdk_header_entry(self, sdk_header_entry: str | None) -> None:
        """Set the upstream SDK header entry for this client lifetime."""
        self._sdk_header_entry = sdk_header_entry.strip() if sdk_header_entry else None
        if self._http is not None:
            self._http._sdk_header = self._build_http_sdk_header()

    async def __aenter__(self) -> "PrefactorCoreClient":
        """Enter async context manager."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        try:
            await self.close()
        except PrefactorTelemetryFailureError:
            if exc_type is None:
                raise

    async def initialize(self) -> None:
        """Initialize the client and start processing.

        This method:
        1. Initializes the HTTP client
        2. Starts the task executor
        3. Initializes managers

        Raises:
            ClientAlreadyInitializedError: If already initialized.
        """
        if self._initialized:
            raise ClientAlreadyInitializedError("Client is already initialized")

        # Initialize HTTP client
        self._http = PrefactorHttpClient(
            self._config.http_config,
            sdk_header=self._build_http_sdk_header(),
        )
        await self._http.__aenter__()

        # Initialize executor
        self._executor = TaskExecutor(
            queue=self._queue,
            handler=self._process_operation,
            is_retryable=self._is_retryable_operation_error,
            num_workers=self._config.queue_config.num_workers,
            max_retries=self._config.queue_config.max_retries,
        )
        self._executor.start()

        # Initialize managers
        self._instance_manager = AgentInstanceManager(
            http_client=self._http,
            enqueue=self._enqueue,
        )
        self._span_manager = SpanManager(
            http_client=self._http,
            enqueue=self._enqueue,
        )

        self._initialized = True

    async def close(self) -> None:
        """Close the client and cleanup resources.

        This method gracefully shuts down the executor and closes the
        HTTP client. It should be called when the client is no longer needed.
        """
        if not self._initialized:
            return

        # Stop executor
        if self._executor:
            await self._executor.stop()

        # Close HTTP client
        if self._http:
            await self._http.__aexit__(None, None, None)

        self._initialized = False

        if self._telemetry_failure is not None and not self._telemetry_failure_observed:
            self._telemetry_failure_observed = True
            raise self._telemetry_failure

    def _ensure_initialized(self) -> None:
        """Ensure the client is initialized.

        Raises:
            ClientNotInitializedError: If not initialized.
        """
        if not self._initialized:
            raise ClientNotInitializedError(
                "Client is not initialized. Call initialize() or "
                "use as context manager."
            )

    def _record_telemetry_failure(
        self, cause: Exception, operation_type: OperationType | str
    ) -> None:
        """Latch the first permanent telemetry failure."""
        if self._telemetry_failure is not None:
            return
        if isinstance(operation_type, OperationType):
            operation_name = operation_type.name
        else:
            operation_name = str(operation_type)
        self._telemetry_failure = PrefactorTelemetryFailureError(
            f"Telemetry permanently failed during {operation_name}",
            cause=cause,
            operation_type=operation_name,
            dropped_operations=0,
        )

    def _increment_dropped_operations(self) -> None:
        """Increment the dropped operation counter on the latched failure."""
        if self._telemetry_failure is None:
            return
        self._telemetry_failure.dropped_operations += 1

    def _raise_if_telemetry_failed(self) -> None:
        """Raise the latched telemetry failure for caller-visible operations."""
        if self._telemetry_failure is None:
            return
        self._telemetry_failure_observed = True
        raise self._telemetry_failure

    def _is_retryable_operation_error(self, error: Exception) -> bool:
        """Return True when the worker should retry the operation."""
        if isinstance(error, PrefactorTelemetryFailureError):
            return False
        if is_permanent_http_error(error):
            return False
        if is_transient_http_error(error):
            return True
        return True

    async def _enqueue(self, operation: Operation) -> None:
        """Add an operation to the queue.

        Args:
            operation: The operation to queue.
        """
        if self._telemetry_failure is not None:
            self._increment_dropped_operations()
            self._raise_if_telemetry_failed()
        await self._queue.put(operation)

    async def _process_operation(self, operation: Operation) -> None:
        """Process a single operation from the queue.

        This method routes operations to the appropriate handler based on type.

        Args:
            operation: The operation to process.
        """
        if not self._http:
            return
        if self._telemetry_failure is not None:
            self._increment_dropped_operations()
            return

        try:
            if operation.type == OperationType.REGISTER_AGENT_INSTANCE:
                await self._http.agent_instances.register(
                    agent_id=operation.payload["agent_id"],
                    agent_version=operation.payload["agent_version"],
                    agent_schema_version=operation.payload["agent_schema_version"],
                    id=operation.payload.get("id"),
                )

            elif operation.type == OperationType.START_AGENT_INSTANCE:
                await self._http.agent_instances.start(
                    agent_instance_id=operation.payload["instance_id"],
                    timestamp=operation.timestamp,
                    idempotency_key=operation.payload.get("idempotency_key"),
                )

            elif operation.type == OperationType.FINISH_AGENT_INSTANCE:
                await self._http.agent_instances.finish(
                    agent_instance_id=operation.payload["instance_id"],
                    status=operation.payload.get("status", "complete"),
                    timestamp=operation.timestamp,
                    idempotency_key=operation.payload.get("idempotency_key"),
                )
            elif operation.type == OperationType.CREATE_SPAN:
                await self._http.agent_spans.create(
                    agent_instance_id=operation.payload["instance_id"],
                    schema_name=operation.payload["schema_name"],
                    status=operation.payload.get("status", "pending"),
                    id=operation.payload.get("span_id"),
                    parent_span_id=operation.payload.get("parent_span_id"),
                    payload=operation.payload.get("payload"),
                )

            elif operation.type == OperationType.FINISH_SPAN:
                await self._http.agent_spans.finish(
                    agent_span_id=operation.payload["span_id"],
                    status=operation.payload.get("status", "complete"),
                    result_payload=operation.payload.get("result_payload"),
                    timestamp=operation.timestamp,
                    idempotency_key=operation.payload.get("idempotency_key"),
                )

        except Exception as e:
            if is_permanent_http_error(e):
                self._record_telemetry_failure(e, operation.type)
            # Log error and re-raise so TaskExecutor retries can run
            logger.error(
                f"Failed to process operation {operation.type}: {e}",
                exc_info=True,
            )
            raise

    @property
    def instance_manager(self) -> AgentInstanceManager | None:
        """Public accessor for the agent instance manager."""
        return self._instance_manager

    async def create_agent_instance(
        self,
        agent_id: str,
        agent_version: dict[str, Any],
        agent_schema_version: dict[str, Any] | None = None,
        instance_id: str | None = None,
        external_schema_version_id: str | None = None,
        environment_id: str | None = None,
    ) -> "AgentInstanceHandle":
        """Create a new agent instance.

        Returns immediately with a handle. The actual registration happens
        asynchronously via the queue.

        If agent_schema_version is not provided but the client has a schema_registry,
        the registry's schemas will be used automatically.

        Args:
            agent_id: ID of the agent to create an instance for.
            agent_version: Version information (name, etc.).
            agent_schema_version: Schema version. Uses registry if not provided
                and registry is configured.
            instance_id: Optional custom ID for the instance.
            external_schema_version_id: Optional external identifier for the
                schema version. Defaults to "auto-generated" when using registry.
            environment_id: Optional environment ID used to scope the agent instance.

        Returns:
            AgentInstanceHandle for the created instance.

        Raises:
            ClientNotInitializedError: If the client is not initialized.
            ValueError: If no schema version provided and registry not configured.
        """
        self._ensure_initialized()
        self._raise_if_telemetry_failed()
        assert self._instance_manager is not None

        # Determine the agent_schema_version to use
        final_schema_version: dict[str, Any]
        if agent_schema_version is not None:
            final_schema_version = agent_schema_version
        elif self._config.schema_registry is not None:
            # Use registry to generate schema version
            ext_id = external_schema_version_id
            if ext_id is None:
                ext_id = f"auto-{agent_id}-{time.time()}"
            final_schema_version = self._config.schema_registry.to_agent_schema_version(
                ext_id
            )
        else:
            msg1 = "agent_schema_version required when no schema_registry configured"
            msg2 = "Either provide agent_schema_version or configure a SchemaRegistry"
            raise ValueError(f"{msg1}. {msg2}.")

        # Import here to avoid circular import
        from .managers.agent_instance import AgentInstanceHandle

        instance_id = await self._instance_manager.register(
            agent_id=agent_id,
            agent_version=agent_version,
            agent_schema_version=final_schema_version,
            instance_id=instance_id,
            environment_id=environment_id,
        )

        return AgentInstanceHandle(
            instance_id=instance_id,
            client=self,
        )

    async def create_span(
        self,
        instance_id: str,
        schema_name: str,
        parent_span_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """Create a span and return its ID without finishing it.

        Use this for spans that need to stay open across multiple operations.
        Call finish_span() when done.

        Args:
            instance_id: ID of the agent instance this span belongs to.
            schema_name: Name of the schema for this span.
            parent_span_id: Optional explicit parent span ID.
            payload: Optional initial payload (params/inputs) stored on creation.

        Returns:
            The span ID.
        """
        self._ensure_initialized()
        self._raise_if_telemetry_failed()
        assert self._span_manager is not None

        if parent_span_id is None:
            parent_span_id = SpanContextStack.peek()

        return await self._span_manager.create(
            instance_id=instance_id,
            schema_name=schema_name,
            parent_span_id=parent_span_id,
            payload=payload,
        )

    async def finish_span(
        self,
        span_id: str,
        result_payload: dict[str, Any] | None = None,
    ) -> None:
        """Finish a previously created span.

        Args:
            span_id: The ID of the span to finish.
            result_payload: Optional result data to store on the span.
        """
        self._ensure_initialized()
        assert self._span_manager is not None

        await self._span_manager.finish(span_id, result_payload=result_payload)

    @asynccontextmanager
    async def span(
        self,
        instance_id: str,
        schema_name: str,
        parent_span_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ):
        """Context manager for creating and finishing a span.

        If parent_span_id is not provided, the current span from the
        SpanContextStack is used as the parent.

        The returned :class:`SpanContext` supports an explicit lifecycle:

        1. ``await span.start(payload)`` — POST the span to the API.
        2. Do work.
        3. ``await span.complete(result)`` / ``span.fail(result)`` /
           ``span.cancel()`` — finish with a specific status.

        If ``start()`` or a finish method is not called explicitly, the
        context manager handles them automatically on exit.

        Args:
            instance_id: ID of the agent instance this span belongs to.
            schema_name: Name of the schema for this span.
            parent_span_id: Optional explicit parent span ID.
            payload: Optional initial payload sent via auto-start on exit
                if ``start()`` is never called explicitly.

        Yields:
            SpanContext for the created span.
        """
        self._ensure_initialized()
        self._raise_if_telemetry_failed()
        assert self._span_manager is not None

        # Import here to avoid circular import
        from .span_context import SpanContext

        # Auto-detect parent from stack if not explicit
        if parent_span_id is None:
            parent_span_id = SpanContextStack.peek()

        temp_id = self._span_manager.prepare(
            instance_id=instance_id,
            schema_name=schema_name,
            parent_span_id=parent_span_id,
        )

        context = SpanContext(
            temp_id=temp_id,
            span_manager=self._span_manager,
            default_payload=payload,
        )

        try:
            yield context
        finally:
            await context.finish()


__all__ = ["PrefactorCoreClient"]
