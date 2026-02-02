"""In-memory queue implementation.

Provides a simple, unbounded in-memory queue suitable for most use cases.
Data is lost on process termination - use a persistent queue implementation
for durability requirements.
"""

from asyncio import Queue as AsyncQueue
from typing import TypeVar

from prefactor_next.queue.base import Queue, QueueClosedError

T = TypeVar("T")


class InMemoryQueue(Queue[T]):
    """Unbounded in-memory queue implementation.

    This is the default queue implementation. It's simple, fast, and
    suitable for most use cases. All data is stored in memory and will
    be lost if the process terminates before processing completes.

    The queue uses asyncio.Queue internally for thread-safe operations.

    Example:
        queue = InMemoryQueue()
        await queue.put("operation")
        item = await queue.get()
        await queue.close()
    """

    def __init__(self) -> None:
        """Initialize an empty in-memory queue."""
        self._queue: AsyncQueue[T] = AsyncQueue()
        self._closed = False

    async def put(self, item: T) -> None:
        """Add an item to the queue.

        Args:
            item: The item to add.

        Raises:
            QueueClosedError: If the queue has been closed.
        """
        if self._closed:
            raise QueueClosedError("Cannot put to closed queue")
        await self._queue.put(item)

    async def get(self) -> T:
        """Remove and return an item from the queue.

        Returns:
            The next item from the queue.

        Raises:
            QueueClosedError: If the queue is closed and empty.
        """
        if self._closed and self._queue.empty():
            raise QueueClosedError("Queue is closed and empty")
        return await self._queue.get()

    def size(self) -> int:
        """Return the current number of items in the queue.

        Returns:
            The queue size.
        """
        return self._queue.qsize()

    async def close(self) -> None:
        """Close the queue.

        After closing, no new items can be added. Workers will continue
        to process existing items until the queue is empty.
        """
        self._closed = True

    @property
    def closed(self) -> bool:
        """Check if the queue has been closed.

        Returns:
            True if the queue is closed.
        """
        return self._closed


__all__ = ["InMemoryQueue"]
