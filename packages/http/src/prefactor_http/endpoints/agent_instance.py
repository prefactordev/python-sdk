"""AgentInstance endpoint client."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import ValidationError

from prefactor_http.exceptions import PrefactorResponseContractError
from prefactor_http.models.agent_instance import AgentInstance, FinishInstanceRequest
from prefactor_http.models.base import ApiResponse
from prefactor_http.models.types import FinishStatus

if TYPE_CHECKING:
    from prefactor_http.client import PrefactorHttpClient


def _validate_idempotency_key(key: str) -> None:
    """Validate that an idempotency key is at most 64 characters.

    Args:
        key: The idempotency key to validate.

    Raises:
        ValueError: If the key exceeds 64 characters.
    """
    if len(key) > 64:
        raise ValueError(
            f"Idempotency key must be at most 64 characters, got {len(key)}"
        )


class AgentInstanceClient:
    """Client for AgentInstance POST endpoints.

    Provides methods to interact with agent instances including:
    - register: Create a new agent instance
    - start: Mark an instance as started
    - finish: Mark an instance as finished
    """

    def __init__(self, http_client: "PrefactorHttpClient"):
        """Initialize the client.

        Args:
            http_client: The main HTTP client instance.
        """
        self._client = http_client

    def _parse_response(self, response: dict, operation: str) -> AgentInstance:
        """Parse a typed API response and wrap schema mismatches."""
        try:
            api_response = ApiResponse[AgentInstance](**response)
        except ValidationError as exc:
            raise PrefactorResponseContractError(
                f"Invalid response payload for {operation}",
                cause=exc,
            ) from exc
        return api_response.details

    async def register(
        self,
        agent_id: str,
        agent_version: dict,
        agent_schema_version: dict,
        environment_id: str | None = None,
        id: str | None = None,
        idempotency_key: str | None = None,
        update_current_version: bool = True,
    ) -> AgentInstance:
        """Register a new agent instance.

        POST /api/v1/agent_instance/register

        Args:
            agent_id: ID of the agent to create an instance for
            agent_version: Version info dict with name, external_identifier,
                description
            agent_schema_version: Schema version dict with external_identifier
                and span type definitions (span_type_schemas, span_schemas,
                and/or span_result_schemas)
            environment_id: Environment to deploy into. Required when using an
                account-scoped token; omit when using a deployment-scoped token
            id: Optional custom ID for the instance
            idempotency_key: Optional idempotency key
            update_current_version: Whether to update the deployment's pinned
                version (defaults to True)

        Returns:
            The created agent instance

        Raises:
            PrefactorApiError: On API errors
            PrefactorValidationError: On validation errors
        """
        if idempotency_key is not None:
            _validate_idempotency_key(idempotency_key)

        payload = {
            "agent_id": agent_id,
            "agent_version": agent_version,
            "agent_schema_version": agent_schema_version,
            "update_current_version": update_current_version,
        }
        if environment_id is not None:
            payload["environment_id"] = environment_id
        if id is not None:
            payload["id"] = id
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key

        response = await self._client.request(
            "POST",
            "/api/v1/agent_instance/register",
            json_data=payload,
        )

        return self._parse_response(response, "agent_instances.register")

    async def start(
        self,
        agent_instance_id: str,
        timestamp: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> AgentInstance:
        """Mark an agent instance as started.

        POST /api/v1/agent_instance/{agent_instance_id}/start

        Args:
            agent_instance_id: The instance ID
            timestamp: Optional start time (defaults to now)
            idempotency_key: Optional idempotency key

        Returns:
            The updated agent instance

        Raises:
            PrefactorNotFoundError: If instance not found
            PrefactorApiError: On other errors
        """
        if idempotency_key is not None:
            _validate_idempotency_key(idempotency_key)

        payload = {"timestamp": timestamp.isoformat() if timestamp else None}
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key

        response = await self._client.request(
            "POST",
            f"/api/v1/agent_instance/{agent_instance_id}/start",
            json_data=payload,
        )

        return self._parse_response(response, "agent_instances.start")

    async def finish(
        self,
        agent_instance_id: str,
        status: FinishStatus | None = None,
        timestamp: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> AgentInstance:
        """Mark an agent instance as finished.

        POST /api/v1/agent_instance/{agent_instance_id}/finish

        Args:
            agent_instance_id: The instance ID
            status: Optional finish status (complete, failed, cancelled)
            timestamp: Optional finish time (defaults to now)
            idempotency_key: Optional idempotency key

        Returns:
            The updated agent instance

        Raises:
            PrefactorNotFoundError: If instance not found
            PrefactorApiError: On other errors
        """
        if idempotency_key is not None:
            _validate_idempotency_key(idempotency_key)

        finish_request = FinishInstanceRequest(
            status=status,
            timestamp=timestamp.isoformat() if timestamp else None,
            idempotency_key=idempotency_key,
        )

        response = await self._client.request(
            "POST",
            f"/api/v1/agent_instance/{agent_instance_id}/finish",
            json_data=finish_request.model_dump(exclude_none=True),
        )

        return self._parse_response(response, "agent_instances.finish")
