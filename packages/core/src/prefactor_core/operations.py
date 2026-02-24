"""Operation types for prefactor-core.

Operations represent discrete units of work that can be queued and processed
asynchronously. Each operation type maps to a specific API action.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class OperationType(Enum):
    """Types of operations that can be performed.

    Each operation type corresponds to a specific API endpoint action.
    """

    REGISTER_AGENT_INSTANCE = auto()
    START_AGENT_INSTANCE = auto()
    FINISH_AGENT_INSTANCE = auto()
    CREATE_SPAN = auto()
    FINISH_SPAN = auto()


@dataclass(frozen=True)
class Operation:
    """A single operation to be queued and processed.

    Operations are immutable and contain all data needed for execution.
    They are created synchronously and processed asynchronously by workers.

    Attributes:
        type: The type of operation to perform.
        payload: Dictionary containing operation-specific data.
        timestamp: When the operation was created.
        idempotency_key: Optional key for idempotent operations.
        metadata: Optional additional metadata.

    Example:
        from datetime import datetime, timezone

        operation = Operation(
            type=OperationType.CREATE_SPAN,
            payload={
                "instance_id": "inst-123",
                "schema_name": "agent:llm",
                "span_id": "span-456"
            },
            timestamp=datetime.now(timezone.utc),
            idempotency_key="span-456"
        )
    """

    type: OperationType
    payload: dict[str, Any]
    timestamp: datetime
    idempotency_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = ["OperationType", "Operation"]
