"""Main client for prefactor-core.

This module provides the PrefactorCoreClient, which is the main entry point
for the SDK. It manages the complete lifecycle of agent instances and spans
through an async queue-based architecture.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from prefactor_http.client import PrefactorHttpClient

from .config import PrefactorCoreConfig
from .context_stack import SpanContextStack
from .exceptions import (
    ClientAlreadyInitializedError,
    ClientNotInitializedError,
)
from .managers.agent_instance import AgentInstanceManager
from .managers.span import SpanManager
from .operations import Operation, OperationType
from .queue.base import Queue
from .queue.executor import TaskExecutor
from .queue.memory import InMemoryQueue

if TYPE_CHECKING:
    from .managers.agent_instance import AgentInstanceHandle


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
    ) -> None:
        """Initialize the client.

        Args:
            config: Configuration for the client.
            queue: Optional custom queue implementation. If not provided,
                an InMemoryQueue is used.
        """
        self._config = config
        self._queue = queue or InMemoryQueue()
        self._http: PrefactorHttpClient | None = None
        self._executor: TaskExecutor | None = None
        self._instance_manager: AgentInstanceManager | None = None
        self._span_manager: SpanManager | None = None
        self._initialized = False

    async def __aenter__(self) -> "PrefactorCoreClient":
        """Enter async context manager."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager."""
        await self.close()

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
        self._http = PrefactorHttpClient(self._config.http_config)
        await self._http.__aenter__()

        # Initialize executor
        self._executor = TaskExecutor(
            queue=self._queue,
            handler=self._process_operation,
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

    async def _enqueue(self, operation: Operation) -> None:
        """Add an operation to the queue.

        Args:
            operation: The operation to queue.
        """
        await self._queue.put(operation)

    async def _process_operation(self, operation: Operation) -> None:
        """Process a single operation from the queue.

        This method routes operations to the appropriate handler based on type.

        Args:
            operation: The operation to process.
        """
        if not self._http:
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
                )

            elif operation.type == OperationType.FINISH_AGENT_INSTANCE:
                await self._http.agent_instances.finish(
                    agent_instance_id=operation.payload["instance_id"],
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
                )

            # Note: UPDATE_SPAN_PAYLOAD requires API support or batching

        except Exception as e:
            # Log error but don't re-raise - we don't want to crash the worker
            import logging

            logging.getLogger(__name__).error(
                f"Failed to process operation {operation.type}: {e}"
            )

    async def create_agent_instance(
        self,
        agent_id: str,
        agent_version: dict[str, Any],
        agent_schema_version: dict[str, Any] | None = None,
        instance_id: str | None = None,
        external_schema_version_id: str | None = None,
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

        Returns:
            AgentInstanceHandle for the created instance.

        Raises:
            ClientNotInitializedError: If the client is not initialized.
            ValueError: If no schema version provided and registry not configured.
        """
        self._ensure_initialized()
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
        )

        return AgentInstanceHandle(
            instance_id=instance_id,
            client=self,
        )

    @asynccontextmanager
    async def span(
        self,
        instance_id: str,
        schema_name: str,
        parent_span_id: str | None = None,
        span_id: str | None = None,
    ):
        """Context manager for creating and finishing a span.

        If parent_span_id is not provided, the current span from the
        SpanContextStack is used as the parent.

        Args:
            instance_id: ID of the agent instance this span belongs to.
            schema_name: Name of the schema for this span.
            parent_span_id: Optional explicit parent span ID.
            span_id: Optional custom ID for the span.

        Yields:
            SpanContext for the created span.
        """
        self._ensure_initialized()
        assert self._span_manager is not None

        # Import here to avoid circular import
        from .span_context import SpanContext

        # Auto-detect parent from stack if not explicit
        if parent_span_id is None:
            parent_span_id = SpanContextStack.peek()

        span_id = await self._span_manager.create(
            instance_id=instance_id,
            schema_name=schema_name,
            parent_span_id=parent_span_id,
            span_id=span_id,
        )

        context = SpanContext(
            span_id=span_id,
            span_manager=self._span_manager,
        )

        try:
            yield context
        finally:
            await self._span_manager.finish(span_id)


__all__ = ["PrefactorCoreClient"]
