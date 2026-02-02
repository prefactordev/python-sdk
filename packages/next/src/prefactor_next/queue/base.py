"""Queue infrastructure for prefactor-next.

This module provides the foundation layer for async queue-based processing.
All queue implementations must satisfy the Queue interface to be used with
the TaskExecutor.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class QueueClosedError(Exception):
    """Raised when attempting to use a closed queue."""

    pass


class Queue(ABC, Generic[T]):
    """Abstract base class for all queue implementations.

    This interface defines the contract for queue operations used by
    the TaskExecutor. Implementations must be thread-safe and support
    async operations.
    """

    @abstractmethod
    async def put(self, item: T) -> None:
        """Add an item to the queue.

        This method should return immediately without blocking the caller.
        The item will be processed asynchronously by workers.

        Args:
            item: The item to add to the queue.

        Raises:
            QueueClosedError: If the queue has been closed.
        """
        pass

    @abstractmethod
    async def get(self) -> T:
        """Remove and return an item from the queue.

        This method blocks until an item is available or the queue
        is closed.

        Returns:
            The next item from the queue.

        Raises:
            QueueClosedError: If the queue is closed and empty.
        """
        pass

    @abstractmethod
    def size(self) -> int:
        """Return the current number of items in the queue.

        Returns:
            The queue size (non-negative integer).
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the queue and signal workers to stop.

        After closing, no new items can be added. Workers should
        finish processing remaining items and then exit.
        """
        pass

    @property
    @abstractmethod
    def closed(self) -> bool:
        """Check if the queue has been closed.

        Returns:
            True if close() has been called, False otherwise.
        """
        pass


__all__ = ["Queue", "QueueClosedError"]
