"""Public API for prefactor-core.

This module exports the main classes and functions for the prefactor-core SDK.
"""

from .client import PrefactorCoreClient
from .config import PrefactorCoreConfig, QueueConfig
from .context_stack import SpanContextStack
from .exceptions import (
    ClientAlreadyInitializedError,
    ClientNotInitializedError,
    InstanceNotFoundError,
    OperationError,
    PrefactorCoreError,
    SpanNotFoundError,
)
from .managers.agent_instance import AgentInstanceHandle
from .models import AgentInstance, Span
from .operations import Operation, OperationType
from .queue import InMemoryQueue, Queue, QueueClosedError, TaskExecutor
from .schema_registry import SchemaRegistry
from .span_context import SpanContext

__version__ = "0.1.0"

__all__ = [
    # Client
    "PrefactorCoreClient",
    # Config
    "PrefactorCoreConfig",
    "QueueConfig",
    # Context
    "SpanContext",
    "SpanContextStack",
    # Exceptions
    "PrefactorCoreError",
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
    # Schema Registry
    "SchemaRegistry",
]
