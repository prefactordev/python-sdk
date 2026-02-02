"""Data models for prefactor-next.

This module contains dataclasses and models used throughout the SDK.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AgentInstance:
    """Represents an agent instance.

    An agent instance is a single execution of an agent. It tracks
    the lifecycle from registration through completion.

    Attributes:
        id: Unique identifier for this instance.
        agent_id: ID of the agent this is an instance of.
        status: Current status (pending, active, complete).
        created_at: When the instance was registered.
        started_at: When the instance started executing (if started).
        finished_at: When the instance completed (if finished).
        metadata: Additional metadata about the instance.
    """

    id: str
    agent_id: str
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Span:
    """Represents a span within an agent instance.

    Spans represent discrete units of work within an agent execution,
    such as LLM calls, tool executions, or processing steps.

    Attributes:
        id: Unique identifier for this span.
        instance_id: ID of the agent instance this span belongs to.
        parent_span_id: ID of the parent span (if nested).
        schema_name: Name of the schema defining this span type.
        status: Current status (pending, active, complete).
        payload: Arbitrary data associated with this span.
        created_at: When the span was created.
        started_at: When the span started (defaults to created_at).
        finished_at: When the span completed (if finished).
    """

    id: str
    instance_id: str
    schema_name: str
    parent_span_id: str | None = None
    status: str = "pending"
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


__all__ = ["AgentInstance", "Span"]
