"""Queue infrastructure layer for prefactor-next.

This module provides the foundation for asynchronous queue-based processing:
- Queue interface for different queue implementations
- InMemoryQueue for simple use cases
- TaskExecutor for managing worker pools

Future implementations can provide persistent queues (Redis, PostgreSQL, etc.)
by implementing the Queue interface.
"""

from .base import Queue, QueueClosedError
from .executor import TaskExecutor
from .memory import InMemoryQueue

__all__ = ["Queue", "QueueClosedError", "InMemoryQueue", "TaskExecutor"]
