"""AgentDeployment endpoint client."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from prefactor_http.exceptions import PrefactorResponseContractError
from prefactor_http.models.agent_deployment import (
    AgentDeployment,
    CreateAgentDeploymentRequest,
    UpdateAgentDeploymentRequest,
)
from prefactor_http.models.base import ApiResponse, ListResponse

if TYPE_CHECKING:
    from prefactor_http.client import PrefactorHttpClient


class AgentDeploymentClient:
    """Client for AgentDeployment CRUD endpoints."""

    def __init__(self, http_client: "PrefactorHttpClient") -> None:
        self._client = http_client

    def _parse_response(self, response: dict, operation: str) -> AgentDeployment:
        try:
            api_response = ApiResponse[AgentDeployment](**response)
        except ValidationError as exc:
            raise PrefactorResponseContractError(
                f"Invalid response payload for {operation}",
                cause=exc,
            ) from exc
        return api_response.details

    async def list(self, agent_id: str | None = None) -> list[AgentDeployment]:
        """List agent deployments, optionally filtered by agent_id.

        GET /api/v1/agent_deployment/
        """
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id

        response = await self._client.request(
            "GET",
            "/api/v1/agent_deployment/",
            params=params or None,
        )

        try:
            list_response = ListResponse[AgentDeployment](**response)
        except ValidationError as exc:
            raise PrefactorResponseContractError(
                "Invalid response payload for agent_deployments.list",
                cause=exc,
            ) from exc
        return list_response.summaries

    async def get(self, agent_deployment_id: str) -> AgentDeployment:
        """Get a single agent deployment by ID.

        GET /api/v1/agent_deployment/:agent_deployment_id
        """
        response = await self._client.request(
            "GET",
            f"/api/v1/agent_deployment/{agent_deployment_id}",
        )
        return self._parse_response(response, "agent_deployments.get")

    async def create(
        self,
        agent_id: str,
        environment_id: str,
        current_version_id: str | None = None,
        id: str | None = None,
    ) -> AgentDeployment:
        """Create a new agent deployment.

        POST /api/v1/agent_deployment/
        """
        details = CreateAgentDeploymentRequest(
            agent_id=agent_id,
            environment_id=environment_id,
            current_version_id=current_version_id,
            id=id,
        )
        response = await self._client.request(
            "POST",
            "/api/v1/agent_deployment/",
            json_data={"details": details.model_dump(exclude_none=True)},
        )
        return self._parse_response(response, "agent_deployments.create")

    async def update(
        self,
        agent_deployment_id: str,
        current_version_id: str | None = None,
    ) -> AgentDeployment:
        """Update an agent deployment. Pass current_version_id=None to clear pinned version.

        PUT /api/v1/agent_deployment/:agent_deployment_id
        """
        details = UpdateAgentDeploymentRequest(current_version_id=current_version_id)
        response = await self._client.request(
            "PUT",
            f"/api/v1/agent_deployment/{agent_deployment_id}",
            json_data={"details": details.model_dump()},
        )
        return self._parse_response(response, "agent_deployments.update")

    async def delete(self, agent_deployment_id: str) -> None:
        """Delete an agent deployment.

        DELETE /api/v1/agent_deployment/:agent_deployment_id
        """
        await self._client.request(
            "DELETE",
            f"/api/v1/agent_deployment/{agent_deployment_id}",
        )
