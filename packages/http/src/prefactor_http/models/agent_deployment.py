"""AgentDeployment data models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AgentDeployment(BaseModel):
    type: Literal["agent_deployment"]
    id: str
    account_id: str
    agent_id: str
    environment_id: str
    current_version_id: str | None = None
    inserted_at: datetime
    updated_at: datetime


class CreateAgentDeploymentRequest(BaseModel):
    agent_id: str
    environment_id: str
    current_version_id: str | None = None
    id: str | None = None


class UpdateAgentDeploymentRequest(BaseModel):
    current_version_id: str | None = None
