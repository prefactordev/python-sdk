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
    from prefactor_http.models.types import FinishStatus, InstancePurpose

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
        agent_version: dict[str, Any],
        agent_schema_version: dict[str, Any],
        agent_id: str | None = None,
        instance_id: str | None = None,
        environment_id: str | None = None,
        purpose: "InstancePurpose | None" = None,
    ) -> str:
        """Register a new agent instance.

        Makes a synchronous API call to register the instance and returns
        the API-generated ID.

        Args:
            agent_id: Agent ID. Omit when using a deployment-scoped token.
            agent_version: Version information (name, external_identifier, etc.).
            agent_schema_version: Schema version information.
            instance_id: Optional ID to forward to the API as ``id``.  When
                provided, the API uses it as the instance ID; when omitted,
                the API generates one.
            environment_id: Optional environment ID. Required when using an
                account-scoped token; omit when using a deployment-scoped token.
            purpose: Why this instance ran — ``"live"``, ``"smoke_test"``,
                or ``"eval"``. Omitted (None) lets the API default to ``"live"``.

        Returns:
            The instance ID (API-generated).
        """
        result = await self._http.agent_instances.register(
            agent_id=agent_id,
            agent_version=agent_version,
            agent_schema_version=agent_schema_version,
            environment_id=environment_id,
            id=instance_id,
            idempotency_key=generate_idempotency_key(),
            purpose=purpose,
        )
        return result.id

    async def start(
        self,
        instance_id: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Mark an instance as started.

        Queues a start operation for the instance.

        Args:
            instance_id: The ID of the instance to start.
            timestamp: Optional ISO 8601 start time (defaults to current time).
        """
        await self.start_with_idempotency_key(
            instance_id,
            generate_idempotency_key(),
            timestamp=timestamp,
        )

    async def start_with_idempotency_key(
        self,
        instance_id: str,
        idempotency_key: str,
        timestamp: datetime | None = None,
    ) -> None:
        """Queue a start operation using a stable idempotency key.

        Args:
            instance_id: The ID of the instance to start.
            idempotency_key: Stable key for idempotent retries.
            timestamp: Optional ISO 8601 start time (defaults to current time).
        """
        operation = Operation(
            type=OperationType.START_AGENT_INSTANCE,
            payload={
                "instance_id": instance_id,
                "idempotency_key": idempotency_key,
            },
            timestamp=timestamp or datetime.now(timezone.utc),
        )

        await self._enqueue(operation)

    async def finish(
        self,
        instance_id: str,
        status: "FinishStatus" = "complete",
        timestamp: datetime | None = None,
    ) -> None:
        """Mark an instance as finished.

        Queues a finish operation for the instance.

        Args:
            instance_id: The ID of the instance to finish.
            status: Terminal status for the instance. Defaults to ``"complete"``.
            timestamp: Optional ISO 8601 finish time (defaults to current time).
        """
        await self.finish_with_idempotency_key(
            instance_id,
            generate_idempotency_key(),
            status=status,
            timestamp=timestamp,
        )

    async def finish_with_idempotency_key(
        self,
        instance_id: str,
        idempotency_key: str,
        status: "FinishStatus" = "complete",
        timestamp: datetime | None = None,
    ) -> None:
        """Queue a finish operation using a stable idempotency key.

        Args:
            instance_id: The ID of the instance to finish.
            idempotency_key: Stable key for idempotent retries.
            status: Terminal status for the instance. Defaults to ``"complete"``.
            timestamp: Optional ISO 8601 finish time (defaults to current time).
        """
        operation = Operation(
            type=OperationType.FINISH_AGENT_INSTANCE,
            payload={
                "instance_id": instance_id,
                "idempotency_key": idempotency_key,
                "status": status,
            },
            timestamp=timestamp or datetime.now(timezone.utc),
        )

        await self._enqueue(operation)

    async def record_quality(
        self,
        instance_id: str,
        name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Record a quality payload on an agent instance.

        Queues a record_quality operation for the instance.

        Args:
            instance_id: The ID of the instance to update.
            name: Quality schema name (key in the agent schema version
                quality_schemas).
            payload: Quality payload for this name (None to remove).
        """
        operation = Operation(
            type=OperationType.RECORD_QUALITY,
            payload={
                "instance_id": instance_id,
                "name": name,
                "payload": payload,
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
        self._start_idempotency_key = generate_idempotency_key()
        self._finish_idempotency_key = generate_idempotency_key()

    @property
    def id(self) -> str:
        """Get the instance ID.

        Returns:
            The unique identifier for this agent instance.
        """
        return self._instance_id

    async def start(self, timestamp: datetime | None = None) -> None:
        """Mark the instance as started.

        This queues a start operation for the instance.

        Args:
            timestamp: Optional ISO 8601 start time (defaults to current time).
        """
        manager = self._client.instance_manager
        assert manager is not None
        await manager.start_with_idempotency_key(
            self._instance_id,
            self._start_idempotency_key,
            timestamp=timestamp,
        )

    async def finish(
        self,
        status: "FinishStatus" = "complete",
        timestamp: datetime | None = None,
    ) -> None:
        """Mark the instance as finished.

        Resets the termination monitor (fence + new event) before enqueueing
        the HTTP finish so stale span responses from the dying run cannot
        trigger termination on the next run.

        Args:
            status: Terminal status for the instance — one of ``"complete"``,
                ``"failed"``, or ``"cancelled"``. Defaults to ``"complete"``.
            timestamp: Optional ISO 8601 finish time (defaults to current time).
        """
        monitor = getattr(self._client, "_termination_monitor", None)
        if monitor is not None:
            monitor.reset()
        self._client._clear_current_instance(self._instance_id)
        manager = self._client.instance_manager
        assert manager is not None
        await manager.finish_with_idempotency_key(
            self._instance_id,
            self._finish_idempotency_key,
            status=status,
            timestamp=timestamp,
        )

    async def record_quality(
        self,
        name: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Record a quality payload on the instance.

        This queues a record_quality operation for the instance.

        Args:
            name: Quality schema name (key in the agent schema version
                quality_schemas).
            payload: Quality payload for this name (None to remove).
        """
        manager = self._client.instance_manager
        assert manager is not None
        await manager.record_quality(
            self._instance_id,
            name=name,
            payload=payload,
        )

    async def create_span(
        self,
        schema_name: str,
        parent_span_id: str | None = None,
        payload: dict[str, Any] | None = None,
        started_at: datetime | None = None,
    ) -> str:
        """Create a span within this instance and return its ID.

        The span stays open until finish_span() is called.

        Args:
            schema_name: Name of the schema for this span.
            parent_span_id: Optional explicit parent span ID.
            payload: Optional initial payload (params/inputs) stored on creation.
            started_at: Optional ISO 8601 start time (defaults to current time).

        Returns:
            The span ID.
        """
        self._client._raise_if_telemetry_failed()
        return await self._client.create_span(
            instance_id=self._instance_id,
            schema_name=schema_name,
            parent_span_id=parent_span_id,
            payload=payload,
            started_at=started_at,
        )

    async def finish_span(
        self,
        span_id: str,
        result_payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Finish a previously created span.

        Args:
            span_id: The ID of the span to finish.
            result_payload: Optional result data to store on the span.
            timestamp: Optional ISO 8601 finish time (defaults to current time).
        """
        await self._client.finish_span(
            span_id,
            result_payload=result_payload,
            timestamp=timestamp,
        )

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
