"""AgentInstance data models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AgentVersionForRegister(BaseModel):
    """Agent version information for registration.

    Attributes:
        name: Name of the agent version
        external_identifier: External identifier for the version (e.g., "v1.0.0")
        description: Optional description of the version
    """

    name: str
    external_identifier: str
    description: str | None = None


class AgentSchemaVersionForRegister(BaseModel):
    """Schema version information for registration.

    Attributes:
        external_identifier: External identifier for the schema version
        span_schemas: Map of span type names to JSON schemas
    """

    external_identifier: str
    span_schemas: dict[str, dict]


class RegisterAgentInstanceRequest(BaseModel):
    """Request to register a new agent instance.

    Attributes:
        agent_id: ID of the agent to create an instance for
        agent_version: Version information for the agent
        agent_schema_version: Schema version for the agent
        id: Optional custom ID for the instance
        idempotency_key: Optional idempotency key
    """

    agent_id: str
    agent_version: AgentVersionForRegister
    agent_schema_version: AgentSchemaVersionForRegister
    id: str | None = None
    idempotency_key: str | None = None


class TimestampRequest(BaseModel):
    """Request with optional timestamp for start/finish operations.

    Attributes:
        timestamp: Optional ISO 8601 timestamp (defaults to current time)
        idempotency_key: Optional idempotency key
    """

    timestamp: str | None = None
    idempotency_key: str | None = None


class AgentInstance(BaseModel):
    """Agent instance model.

    Attributes:
        type: Resource type (always "agent_instance")
        id: Instance ID
        account_id: Account ID
        agent_id: Agent ID
        agent_version_id: Agent version ID
        environment_id: Environment ID
        status: Instance status (pending, active, complete)
        inserted_at: When the instance was created
        updated_at: When the instance was last updated
        started_at: When the instance started (null if not started)
        finished_at: When the instance finished (null if not finished)
    """

    type: Literal["agent_instance"]
    id: str
    account_id: str
    agent_id: str
    agent_version_id: str
    environment_id: str
    status: Literal["pending", "active", "complete"]
    inserted_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
