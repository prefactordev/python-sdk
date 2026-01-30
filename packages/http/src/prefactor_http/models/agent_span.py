"""AgentSpan data models."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateAgentSpanRequest(BaseModel):
    """Request to create a new agent span.

    Attributes:
        agent_instance_id: ID of the agent instance this span belongs to
        schema_name: Name of the schema for this span
        payload: Span payload data (arbitrary JSON object)
        id: Optional custom ID for the span
        parent_span_id: Optional ID of the parent span
        started_at: Optional ISO 8601 start time (defaults to current time)
        finished_at: Optional ISO 8601 finish time (null if in progress)
        idempotency_key: Optional idempotency key
    """

    agent_instance_id: str
    schema_name: str
    payload: dict = Field(default_factory=dict)
    id: str | None = None
    parent_span_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    idempotency_key: str | None = None


class FinishSpanRequest(BaseModel):
    """Request to finish an agent span.

    Attributes:
        timestamp: Optional ISO 8601 timestamp (defaults to current time)
        idempotency_key: Optional idempotency key
    """

    timestamp: str | None = None
    idempotency_key: str | None = None


class AgentSpan(BaseModel):
    """Agent span model.

    Attributes:
        type: Resource type (always "agent_span")
        id: Span ID
        account_id: Account ID
        agent_id: Agent ID
        agent_instance_id: Agent instance ID
        parent_span_id: Parent span ID (None if root span)
        schema_name: Name of the schema for this span
        status: Span status (pending, active, complete)
        payload: Span payload data
        started_at: When the span started
        inserted_at: When the span was created
        updated_at: When the span was last updated
        finished_at: When the span finished (None if in progress)
    """

    type: Literal["agent_span"]
    id: str
    account_id: str
    agent_id: str
    agent_instance_id: str
    parent_span_id: str | None
    schema_name: str
    status: Literal["pending", "active", "complete"]
    payload: dict
    started_at: datetime
    inserted_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
