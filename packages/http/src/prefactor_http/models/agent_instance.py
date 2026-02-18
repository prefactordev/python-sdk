"""AgentInstance data models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from prefactor_http.models.types import AgentStatus, FinishStatus


class SpanTypeSchemaForCreate(BaseModel):
    """Span type schema details for registration.

    Attributes:
        name: Name of the span type
        params_schema: JSON schema for span parameters
        result_schema: Optional JSON schema for span results
        title: Optional human-readable title
        description: Optional description
        template: Optional template string
    """

    name: str
    params_schema: dict
    result_schema: dict | None = None
    title: str | None = None
    description: str | None = None
    template: str | None = None


class AgentInstanceSpanCounts(BaseModel):
    """Span counts for an agent instance.

    Attributes:
        total: Total number of spans
        pending: Number of pending spans
        active: Number of active spans
        complete: Number of completed spans
        failed: Number of failed spans
        cancelled: Number of cancelled spans
        finished: Number of finished spans (complete + failed + cancelled)
    """

    total: int
    pending: int
    active: int
    complete: int
    failed: int
    cancelled: int
    finished: int


class AgentVersionForRegister(BaseModel):
    """Agent version information for registration.

    Attributes:
        name: Name of the agent version
        external_identifier: External identifier for the version (e.g., "v1.0.0")
        description: Optional description of the version
    """

    name: str | None = None
    external_identifier: str | None = None
    description: str | None = None


class AgentSchemaVersionForRegister(BaseModel):
    """Schema version information for registration.

    Attributes:
        external_identifier: External identifier for the schema version
        span_schemas: Map of span type names to JSON schemas
        span_result_schemas: Map of span type names to result JSON schemas
        span_type_schemas: List of span type schema details
    """

    external_identifier: str | None = None
    span_schemas: dict[str, dict] | None = None
    span_result_schemas: dict[str, dict] | None = None
    span_type_schemas: list[SpanTypeSchemaForCreate] | None = None


class RegisterAgentInstanceRequest(BaseModel):
    """Request to register a new agent instance.

    Attributes:
        agent_id: ID of the agent to create an instance for
        agent_version: Version information for the agent
        agent_schema_version: Schema version for the agent
        id: Optional custom ID for the instance
        idempotency_key: Optional idempotency key
        update_current_version: Whether to update the current version
    """

    agent_id: str
    agent_version: AgentVersionForRegister
    agent_schema_version: AgentSchemaVersionForRegister
    id: str | None = None
    idempotency_key: str | None = None
    update_current_version: bool | None = None


class TimestampRequest(BaseModel):
    """Request with optional timestamp for start/finish operations.

    Attributes:
        timestamp: Optional ISO 8601 timestamp (defaults to current time)
        idempotency_key: Optional idempotency key
    """

    timestamp: str | None = None
    idempotency_key: str | None = None


class FinishInstanceRequest(BaseModel):
    """Request to finish an agent instance.

    Attributes:
        status: Optional finish status (complete, failed, cancelled)
        timestamp: Optional ISO 8601 timestamp (defaults to current time)
        idempotency_key: Optional idempotency key
    """

    status: FinishStatus | None = None
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
        status: Instance status
        inserted_at: When the instance was created
        updated_at: When the instance was last updated
        started_at: When the instance started (null if not started)
        finished_at: When the instance finished (null if not finished)
        span_counts: Span counts for this instance
    """

    type: Literal["agent_instance"]
    id: str
    account_id: str
    agent_id: str
    agent_version_id: str
    environment_id: str
    status: AgentStatus
    inserted_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    span_counts: AgentInstanceSpanCounts | None = None
