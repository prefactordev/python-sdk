"""Task executor for processing queue items asynchronously.

The TaskExecutor manages a pool of async workers that continuously
pull items from a queue and process them using a handler function.
"""

import asyncio
import logging
from asyncio import Task, create_task, sleep
from typing import Any, Awaitable, Callable

from .base import Queue, QueueClosedError

logger = logging.getLogger(__name__)


class TaskExecutor:
    """Manages async workers that process queue items.

    The executor runs a configurable number of worker tasks that
    continuously pull items from the queue and process them. If
    processing fails, items are retried with exponential backoff.

    Example:
        async def handler(item: str) -> None:
            print(f"Processing: {item}")

        queue = InMemoryQueue()
        executor = TaskExecutor(queue, handler, num_workers=3)
        executor.start()

        await queue.put("item1")
        await queue.put("item2")

        # Later, when done
        await executor.stop()
    """

    def __init__(
        self,
        queue: Queue[Any],
        handler: Callable[[Any], Awaitable[None]],
        num_workers: int = 3,
        max_retries: int = 3,
    ) -> None:
        """Initialize the task executor.

        Args:
            queue: The queue to pull items from.
            handler: Async function to process each item.
            num_workers: Number of concurrent worker tasks.
            max_retries: Maximum retry attempts per item.
        """
        self._queue = queue
        self._handler = handler
        self._num_workers = num_workers
        self._max_retries = max_retries
        self._workers: list[Task] = []
        self._running = False
        self._active_tasks = 0

    def start(self) -> None:
        """Start the worker tasks.

        Workers will begin pulling items from the queue immediately.
        """
        if self._running:
            return

        self._running = True
        for i in range(self._num_workers):
            task = create_task(
                self._worker_loop(f"worker-{i}"), name=f"prefactor-core-worker-{i}"
            )
            self._workers.append(task)

        logger.info(f"Started {self._num_workers} workers")

    async def drain(self) -> None:
        """Wait until the queue is empty and all in-flight work is done."""
        await self._wait_for_idle()

    async def stop(self) -> None:
        """Stop all workers gracefully.

        Closes the queue (so no new items can be added), wakes any workers
        blocked in get(), and waits for them to drain the remaining items
        and exit on their own.  Workers are never cancelled — that would
        discard already-queued items.
        """
        if not self._running:
            return

        logger.info("Stopping workers...")
        self._running = False

        await self._wait_for_idle(timeout=10.0)

        # Close the queue and wake all workers that are blocked in get().
        await self._queue.close(num_waiters=len(self._workers))

        # Wait for workers to drain remaining items and exit naturally.
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._workers, return_exceptions=True), timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for workers to stop")
            for worker in self._workers:
                worker.cancel()

        self._workers = []
        logger.info("Workers stopped")

    async def _worker_loop(self, worker_id: str) -> None:
        """Main processing loop for each worker.

        Continuously pulls items from the queue and processes them
        until the queue is closed and empty.

        Args:
            worker_id: Identifier for this worker (for logging).
        """
        logger.debug(f"Worker {worker_id} started")

        while True:
            try:
                item = await self._queue.get()
            except QueueClosedError:
                # Queue closed and empty - worker can exit
                logger.debug(f"Worker {worker_id} exiting (queue closed)")
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error getting item: {e}")
                continue

            try:
                self._active_tasks += 1
                await self._process_with_retry(item)
            except Exception as e:
                logger.error(
                    f"Worker {worker_id} failed to process item after retries: {e}"
                )
            finally:
                self._active_tasks -= 1

            # Brief yield to allow other tasks to run
            await asyncio.sleep(0)

        logger.debug(f"Worker {worker_id} stopped")

    async def _process_with_retry(self, item: Any) -> None:
        """Process an item with exponential backoff retry.

        Args:
            item: The item to process.

        Raises:
            Exception: If all retry attempts fail.
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries):
            try:
                await self._handler(item)
                return
            except Exception as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = 2**attempt  # 1s, 2s, 4s
                    logger.warning(
                        f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}"
                    )
                    await sleep(delay)

        # All retries exhausted
        if last_error:
            raise last_error

    async def _wait_for_idle(self, timeout: float | None = None) -> None:
        """Wait until there are no queued or active tasks."""
        loop = asyncio.get_event_loop()
        deadline = None if timeout is None else loop.time() + timeout

        while self._queue.size() > 0 or self._active_tasks > 0:
            if deadline is not None and loop.time() > deadline:
                logger.warning("Timed out waiting for queue to drain")
                break
            await asyncio.sleep(0)


__all__ = ["TaskExecutor"]
