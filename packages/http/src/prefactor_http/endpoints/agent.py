"""Agent endpoint client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from prefactor_http.exceptions import PrefactorResponseContractError
from prefactor_http.models.agent import (
    Agent,
    AgentForCreate,
    AgentForUpdate,
    AgentSummary,
)
from prefactor_http.models.base import ApiResponse, ListResponse

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


class AgentClient:
    """Client for Agent endpoints.

    Provides methods to manage agents including:
    - create: Create a new agent
    - get: Fetch an agent by ID
    - update: Update an agent
    - list: List agents
    - show: Look up an agent by ID or external_identifier
    - retire: Retire an agent
    - reinstate: Reinstate a retired agent
    - delete: Delete an agent
    """

    def __init__(self, http_client: "PrefactorHttpClient"):
        """Initialize the client.

        Args:
            http_client: The main HTTP client instance.
        """
        self._client = http_client

    def _parse_response(self, response: dict, operation: str) -> Agent:
        """Parse a typed API response and wrap schema mismatches."""
        try:
            api_response = ApiResponse[Agent](**response)
        except ValidationError as exc:
            raise PrefactorResponseContractError(
                f"Invalid response payload for {operation}",
                cause=exc,
            ) from exc
        return api_response.details

    async def create(
        self,
        details: AgentForCreate,
        idempotency_key: str | None = None,
    ) -> Agent:
        """Create a new agent.

        POST /api/v1/agent

        Args:
            details: Agent creation parameters.
            idempotency_key: Optional idempotency key.

        Returns:
            The created agent.

        Raises:
            PrefactorApiError: On API errors.
            PrefactorValidationError: On validation errors.
        """
        if idempotency_key is not None:
            _validate_idempotency_key(idempotency_key)

        payload: dict = {"details": details.model_dump(exclude_none=True)}
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key

        response = await self._client.request(
            "POST",
            "/api/v1/agent",
            json_data=payload,
        )

        return self._parse_response(response, "agents.create")

    async def get(self, agent_id: str) -> Agent:
        """Fetch an agent by ID.

        GET /api/v1/agent/{agent_id}

        Args:
            agent_id: The agent ID to fetch.

        Returns:
            The agent.

        Raises:
            PrefactorNotFoundError: If agent not found.
            PrefactorApiError: On other errors.
        """
        response = await self._client.request(
            "GET",
            f"/api/v1/agent/{agent_id}",
        )
        return self._parse_response(response, "agents.get")

    async def update(
        self,
        agent_id: str,
        details: AgentForUpdate,
        idempotency_key: str | None = None,
    ) -> Agent:
        """Update an agent.

        PUT /api/v1/agent/{agent_id}

        Args:
            agent_id: The agent ID to update.
            details: Fields to update (only provided fields are changed).
            idempotency_key: Optional idempotency key.

        Returns:
            The updated agent.

        Raises:
            PrefactorNotFoundError: If agent not found.
            PrefactorApiError: On other errors.
        """
        if idempotency_key is not None:
            _validate_idempotency_key(idempotency_key)

        payload: dict = {"details": details.model_dump(exclude_none=True)}
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key

        response = await self._client.request(
            "PUT",
            f"/api/v1/agent/{agent_id}",
            json_data=payload,
        )

        return self._parse_response(response, "agents.update")

    async def list_agents(
        self,
        risk_profile_id: str | None = None,
        team_id: str | None = None,
        owner_person_id: str | None = None,
        sorting: str | None = None,
        offset: int | None = None,
        page_size: int | None = None,
    ) -> list[AgentSummary]:
        """List agents.

        GET /api/v1/agent

        Args:
            risk_profile_id: Filter by risk profile (null for agents with none).
            team_id: Filter by team (null for agents with no team).
            owner_person_id: Filter by owner (null for agents with no owner).
            sorting: Sort order (e.g. ``"name"`` or ``"-id"``).
            offset: Zero-based offset for pagination.
            page_size: Number of items per page (1-100).

        Returns:
            List of agent summaries.

        Raises:
            PrefactorApiError: On API errors.
        """
        params: dict = {}
        if risk_profile_id is not None:
            params["risk_profile_id"] = risk_profile_id
        if team_id is not None:
            params["team_id"] = team_id
        if owner_person_id is not None:
            params["owner_person_id"] = owner_person_id
        if sorting is not None:
            params["sorting"] = sorting
        if offset is not None:
            params["pagination[offset]"] = offset
        if page_size is not None:
            params["pagination[page_size]"] = page_size

        response = await self._client.request(
            "GET",
            "/api/v1/agent",
            params=params or None,
        )

        try:
            list_response = ListResponse[AgentSummary](**response)
        except ValidationError as exc:
            raise PrefactorResponseContractError(
                "Invalid response payload for agents.list",
                cause=exc,
            ) from exc

        return list_response.summaries

    async def show(
        self,
        *,
        agent_id: str | None = None,
        external_identifier: str | None = None,
        environment_id: str | None = None,
        include_counts: bool = False,
        include_risk_rollup: bool = False,
    ) -> Agent:
        """Look up an agent by ID or external_identifier.

        GET /api/v1/agent/show

        Provide exactly one of ``agent_id`` or ``external_identifier``.

        Args:
            agent_id: Agent ID to look up.
            external_identifier: External identifier to look up (exact match).
            environment_id: Optional environment to scope risk rollup and counts.
            include_counts: Include instance counts in the response.
            include_risk_rollup: Include risk rollup in the response.

        Returns:
            The agent.

        Raises:
            PrefactorNotFoundError: If agent not found.
            PrefactorApiError: On other errors.
        """
        params: dict = {}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if external_identifier is not None:
            params["external_identifier"] = external_identifier
        if environment_id is not None:
            params["environment_id"] = environment_id
        if include_counts:
            params["include_counts"] = "true"
        if include_risk_rollup:
            params["include_risk_rollup"] = "true"

        response = await self._client.request(
            "GET",
            "/api/v1/agent/show",
            params=params or None,
        )

        return self._parse_response(response, "agents.show")

    async def retire(
        self,
        agent_id: str,
        idempotency_key: str | None = None,
    ) -> Agent:
        """Retire an agent.

        POST /api/v1/agent/{agent_id}/retire

        Args:
            agent_id: The agent ID to retire.
            idempotency_key: Optional idempotency key.

        Returns:
            The updated agent.

        Raises:
            PrefactorNotFoundError: If agent not found.
            PrefactorApiError: On other errors.
        """
        if idempotency_key is not None:
            _validate_idempotency_key(idempotency_key)

        payload: dict = {}
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key

        response = await self._client.request(
            "POST",
            f"/api/v1/agent/{agent_id}/retire",
            json_data=payload or None,
        )

        return self._parse_response(response, "agents.retire")

    async def reinstate(
        self,
        agent_id: str,
        idempotency_key: str | None = None,
    ) -> Agent:
        """Reinstate a retired agent.

        POST /api/v1/agent/{agent_id}/reinstate

        Args:
            agent_id: The agent ID to reinstate.
            idempotency_key: Optional idempotency key.

        Returns:
            The updated agent.

        Raises:
            PrefactorNotFoundError: If agent not found.
            PrefactorApiError: On other errors.
        """
        if idempotency_key is not None:
            _validate_idempotency_key(idempotency_key)

        payload: dict = {}
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key

        response = await self._client.request(
            "POST",
            f"/api/v1/agent/{agent_id}/reinstate",
            json_data=payload or None,
        )

        return self._parse_response(response, "agents.reinstate")

    async def delete(
        self,
        agent_id: str,
        idempotency_key: str | None = None,
    ) -> Agent:
        """Delete an agent.

        DELETE /api/v1/agent/{agent_id}

        Args:
            agent_id: The agent ID to delete.
            idempotency_key: Optional idempotency key.

        Returns:
            The deleted agent.

        Raises:
            PrefactorNotFoundError: If agent not found.
            PrefactorApiError: On other errors.
        """
        if idempotency_key is not None:
            _validate_idempotency_key(idempotency_key)

        payload: dict = {}
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key

        response = await self._client.request(
            "DELETE",
            f"/api/v1/agent/{agent_id}",
            json_data=payload or None,
        )

        return self._parse_response(response, "agents.delete")


__all__ = ["AgentClient"]
