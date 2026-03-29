"""Agent instance handle and manager for convenient span creation.

The AgentInstanceManager handles agent instance lifecycle operations, while
AgentInstanceHandle provides a high-level interface for managing
an agent instance and creating spans within it.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from ..operations import Operation, OperationType
from ..utils import generate_idempotency_key

if TYPE_CHECKING:
    from prefactor_http.client import PrefactorHttpClient

    from ..client import PrefactorCoreClient


class AgentInstanceManager:
    """Manages agent instance lifecycle operations.

    This class provides a high-level interface for agent instance operations.
    Registration is done synchronously to get the API-generated ID, while
    start/finish operations are queued for async processing.

    Example:
        manager = AgentInstanceManager(http_client, enqueue_func)

        # Register a new instance (synchronous - returns API-generated ID)
        instance_id = await manager.register(
            agent_id="my-agent",
            agent_version={"name": "1.0.0"},
            agent_schema_version={"version": "1.0.0"}
        )

        # Start the instance (queued)
        await manager.start(instance_id)

        # Finish the instance (queued)
        await manager.finish(instance_id)
    """

    def __init__(
        self,
        http_client: "PrefactorHttpClient",
        enqueue: Callable[[Operation], Awaitable[None]],
    ) -> None:
        """Initialize the manager.

        Args:
            http_client: HTTP client for API calls.
            enqueue: Function to queue operations for processing.
        """
        self._http = http_client
        self._enqueue = enqueue

    async def register(
        self,
        agent_id: str,
        agent_version: dict[str, Any],
        agent_schema_version: dict[str, Any],
        instance_id: str | None = None,
    ) -> str:
        """Register a new agent instance.

        Makes a synchronous API call to register the instance and returns
        the API-generated ID.

        Args:
            agent_id: ID of the agent to create an instance for.
            agent_version: Version information (name, external_identifier, etc.).
            agent_schema_version: Schema version information.
            instance_id: Optional ID to forward to the API as ``id``.  When
                provided, the API uses it as the instance ID; when omitted,
                the API generates one.

        Returns:
            The instance ID (API-generated).
        """
        result = await self._http.agent_instances.register(
            agent_id=agent_id,
            agent_version=agent_version,
            agent_schema_version=agent_schema_version,
            id=instance_id,
            idempotency_key=generate_idempotency_key(),
        )
        return result.id

    async def start(self, instance_id: str) -> None:
        """Mark an instance as started.

        Queues a start operation for the instance.

        Args:
            instance_id: The ID of the instance to start.
        """
        operation = Operation(
            type=OperationType.START_AGENT_INSTANCE,
            payload={
                "instance_id": instance_id,
                "idempotency_key": generate_idempotency_key(),
            },
            timestamp=datetime.now(timezone.utc),
        )

        await self._enqueue(operation)

    async def finish(self, instance_id: str) -> None:
        """Mark an instance as finished.

        Queues a finish operation for the instance.

        Args:
            instance_id: The ID of the instance to finish.
        """
        operation = Operation(
            type=OperationType.FINISH_AGENT_INSTANCE,
            payload={
                "instance_id": instance_id,
                "idempotency_key": generate_idempotency_key(),
            },
            timestamp=datetime.now(timezone.utc),
        )

        await self._enqueue(operation)


class AgentInstanceHandle:
    """Handle to an agent instance with convenience methods.

    This class provides a clean interface for:
    - Starting and finishing the instance
    - Creating spans within the instance
    - Managing the instance lifecycle

    Example:
        async with client.create_agent_instance(...) as instance:
            await instance.start()

            async with instance.span("agent:llm") as span:
                span.set_payload({"model": "gpt-4"})
                # ... do work ...

            await instance.finish()
    """

    def __init__(
        self,
        instance_id: str,
        client: "PrefactorCoreClient",
    ) -> None:
        """Initialize the handle.

        Args:
            instance_id: The ID of the agent instance.
            client: The PrefactorCoreClient that created this handle.
        """
        self._instance_id = instance_id
        self._client = client
        self._started = False
        self._finished = False

    @property
    def id(self) -> str:
        """Get the instance ID.

        Returns:
            The unique identifier for this agent instance.
        """
        return self._instance_id

    @property
    def sdk_header_entries(self) -> tuple[str, ...]:
        """Return the upstream SDK header entries active for this instance."""
        return self._client.sdk_header_entries

    def add_sdk_header_entry(self, sdk_header_entry: str) -> bool:
        """Add an upstream SDK header entry for requests made by this instance."""
        return self._client.add_sdk_header_entry(sdk_header_entry)

    def remove_sdk_header_entry(self, sdk_header_entry: str) -> bool:
        """Remove an upstream SDK header entry for this instance's client."""
        return self._client.remove_sdk_header_entry(sdk_header_entry)

    async def start(self) -> None:
        """Mark the instance as started.

        This queues a start operation for the instance.
        """
        if self._started:
            return

        manager = self._client.instance_manager
        assert manager is not None
        await manager.start(self._instance_id)
        self._started = True

    async def finish(self) -> None:
        """Mark the instance as finished.

        This queues a finish operation for the instance.
        """
        if self._finished:
            return

        manager = self._client.instance_manager
        assert manager is not None
        await manager.finish(self._instance_id)
        self._finished = True

    async def create_span(
        self,
        schema_name: str,
        parent_span_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """Create a span within this instance and return its ID.

        The span stays open until finish_span() is called.

        Args:
            schema_name: Name of the schema for this span.
            parent_span_id: Optional explicit parent span ID.
            payload: Optional initial payload (params/inputs) stored on creation.

        Returns:
            The span ID.
        """
        return await self._client.create_span(
            instance_id=self._instance_id,
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
        await self._client.finish_span(span_id, result_payload=result_payload)

    @asynccontextmanager
    async def span(
        self,
        schema_name: str,
        parent_span_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ):
        """Create a span within this instance.

        This is a convenience method that delegates to the client.

        Args:
            schema_name: Name of the schema for this span.
            parent_span_id: Optional explicit parent span ID.
            payload: Optional initial payload (params/inputs) stored on creation.

        Yields:
            SpanContext for the created span.
        """
        async with self._client.span(
            instance_id=self._instance_id,
            schema_name=schema_name,
            parent_span_id=parent_span_id,
            payload=payload,
        ) as context:
            yield context


__all__ = ["AgentInstanceManager", "AgentInstanceHandle"]
