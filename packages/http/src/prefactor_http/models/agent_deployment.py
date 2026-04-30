"""AgentDeployment data models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AgentDeployment(BaseModel):
    """Agent deployment resource returned by the API.

    Attributes:
        type: Resource discriminator.
        id: Agent deployment ID.
        account_id: Account ID that owns the deployment.
        agent_id: Agent ID associated with the deployment.
        environment_id: Environment ID associated with the deployment.
        current_version_id: Currently pinned agent version ID, if any.
        inserted_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    type: Literal["agent_deployment"]
    id: str
    account_id: str
    agent_id: str
    environment_id: str
    current_version_id: str | None = None
    inserted_at: datetime
    updated_at: datetime


class CreateAgentDeploymentRequest(BaseModel):
    """Request payload for creating an agent deployment.

    Attributes:
        agent_id: Agent ID to deploy.
        environment_id: Environment ID to deploy into.
        current_version_id: Optional initial pinned agent version ID.
        id: Optional explicit agent deployment ID.
    """

    agent_id: str
    environment_id: str
    current_version_id: str | None = None
    id: str | None = None


class UpdateAgentDeploymentRequest(BaseModel):
    """Request payload for updating an agent deployment.

    Attributes:
        current_version_id: New pinned agent version ID, or None to clear it.
    """

    current_version_id: str | None = None
