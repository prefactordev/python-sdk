"""Public API for prefactor-next.

This module exports the main classes and functions for the prefactor-next SDK.
"""

from .client import PrefactorNextClient
from .config import PrefactorNextConfig, QueueConfig
from .context_stack import SpanContextStack
from .exceptions import (
    ClientAlreadyInitializedError,
    ClientNotInitializedError,
    InstanceNotFoundError,
    OperationError,
    PrefactorNextError,
    SpanNotFoundError,
)
from .managers.agent_instance import AgentInstanceHandle
from .models import AgentInstance, Span
from .operations import Operation, OperationType
from .queue import InMemoryQueue, Queue, QueueClosedError, TaskExecutor
from .span_context import SpanContext

__version__ = "0.1.0"

__all__ = [
    # Client
    "PrefactorNextClient",
    # Config
    "PrefactorNextConfig",
    "QueueConfig",
    # Context
    "SpanContext",
    "SpanContextStack",
    # Exceptions
    "PrefactorNextError",
    "ClientNotInitializedError",
    "ClientAlreadyInitializedError",
    "OperationError",
    "InstanceNotFoundError",
    "SpanNotFoundError",
    # Models
    "AgentInstance",
    "Span",
    # Operations
    "Operation",
    "OperationType",
    # Queue
    "Queue",
    "QueueClosedError",
    "InMemoryQueue",
    "TaskExecutor",
    # Handle
    "AgentInstanceHandle",
]
