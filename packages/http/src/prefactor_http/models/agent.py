"""Agent data models."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AgentAvailableActions(BaseModel):
    """Available actions for an agent based on its status.

    Attributes:
        update: Whether the agent can be updated.
        retire: Whether the agent can be retired.
        reinstate: Whether the agent can be reinstated from retired.
        delete: Whether the agent can be deleted.
    """

    update: bool = False
    retire: bool = False
    reinstate: bool = False
    delete: bool = False


class AgentInstanceCounts(BaseModel):
    """Instance counts for an agent.

    Attributes:
        total: Total number of agent instances.
        pending: Number of instances with status pending.
        active: Number of instances with status active (running).
        complete: Number of instances with status complete.
        failed: Number of instances with status failed.
        cancelled: Number of instances with status cancelled.
        terminated: Number of instances with status terminated.
        finished: Number of instances in a finished state.
    """

    total: int = 0
    pending: int = 0
    active: int = 0
    complete: int = 0
    failed: int = 0
    cancelled: int = 0
    terminated: int = 0
    finished: int = 0


class Agent(BaseModel):
    """Full agent details.

    Attributes:
        type: Resource type (always "agent").
        id: Agent ID.
        name: Agent name.
        description: Optional agent description.
        external_identifier: Optional external identifier (unique per account).
        status: Agent status (pending, active, dormant, retired).
        owner_person_id: Optional owner person ID.
        risk_profile_id: Optional risk profile ID.
        team_id: Optional team ID.
        instance_counts: Instance counts for this agent.
        available_actions: Available actions based on current status.
        inserted_at: When the agent was created.
        updated_at: When the agent was last updated.
    """

    type: Literal["agent"]
    id: str
    name: str
    description: str | None = None
    external_identifier: str | None = None
    status: Literal["pending", "active", "dormant", "retired"]
    owner_person_id: str | None = None
    risk_profile_id: str | None = None
    team_id: str | None = None
    instance_counts: AgentInstanceCounts | None = None
    available_actions: AgentAvailableActions | None = None
    inserted_at: datetime | None = None
    updated_at: datetime | None = None


class AgentSummary(BaseModel):
    """Agent summary for list responses.

    Attributes:
        type: Resource type (always "agent").
        id: Agent ID.
        name: Agent name.
        description: Optional agent description.
        external_identifier: Optional external identifier (unique per account).
        status: Agent status.
        owner_person_id: Optional owner person ID.
        team_id: Optional team ID.
        available_actions: Available actions based on current status.
        inserted_at: When the agent was created.
        updated_at: When the agent was last updated.
    """

    type: Literal["agent"]
    id: str
    name: str
    description: str | None = None
    external_identifier: str | None = None
    status: Literal["pending", "active", "dormant", "retired"]
    owner_person_id: str | None = None
    team_id: str | None = None
    available_actions: AgentAvailableActions | None = None
    inserted_at: datetime | None = None
    updated_at: datetime | None = None


class AgentForCreate(BaseModel):
    """Parameters for creating a new agent.

    Attributes:
        name: Agent name (required).
        description: Optional agent description.
        external_identifier: Optional external identifier (unique per account).
        id: Optional custom ID (PFID with matching partition).
        owner_person_id: Optional owner person ID.
        risk_profile_id: Optional risk profile ID.
        team_id: Optional team ID.
    """

    name: str
    description: str | None = None
    external_identifier: str | None = None
    id: str | None = None
    owner_person_id: str | None = None
    risk_profile_id: str | None = None
    team_id: str | None = None


class AgentForUpdate(BaseModel):
    """Parameters for updating an agent.

    Note: ``external_identifier`` cannot be updated via the API — it is only
    settable at create time.

    Attributes:
        name: Agent name (omit to keep current).
        description: Agent description (omit to keep current).
        owner_person_id: Owner person ID (omit to keep current; null to clear).
        risk_profile_id: Risk profile ID (omit to keep current; null to clear).
        team_id: Team ID (omit to keep current; null to clear).
    """

    name: str | None = None
    description: str | None = None
    owner_person_id: str | None = None
    risk_profile_id: str | None = None
    team_id: str | None = None


__all__ = [
    "Agent",
    "AgentAvailableActions",
    "AgentForCreate",
    "AgentForUpdate",
    "AgentInstanceCounts",
    "AgentSummary",
]
