"""Tests for queue infrastructure."""

import asyncio

import pytest

from prefactor_next.queue import InMemoryQueue, QueueClosedError, TaskExecutor


class TestInMemoryQueue:
    """Test suite for InMemoryQueue."""

    @pytest.fixture
    def queue(self):
        """Create a fresh queue for each test."""
        return InMemoryQueue()

    async def test_put_and_get(self, queue):
        """Test basic put and get operations."""
        await queue.put("item1")
        result = await queue.get()
        assert result == "item1"

    async def test_fifo_ordering(self, queue):
        """Test that queue maintains FIFO order."""
        await queue.put("first")
        await queue.put("second")
        await queue.put("third")

        assert await queue.get() == "first"
        assert await queue.get() == "second"
        assert await queue.get() == "third"

    async def test_size_tracking(self, queue):
        """Test that size is tracked correctly."""
        assert queue.size() == 0

        await queue.put("item1")
        assert queue.size() == 1

        await queue.put("item2")
        assert queue.size() == 2

        await queue.get()
        assert queue.size() == 1

    async def test_close_prevents_put(self, queue):
        """Test that put raises error after close."""
        await queue.close()

        with pytest.raises(QueueClosedError):
            await queue.put("item")

    async def test_close_allows_getting_remaining(self, queue):
        """Test that get works after close until empty."""
        await queue.put("item1")
        await queue.put("item2")
        await queue.close()

        # Should still be able to get existing items
        assert await queue.get() == "item1"
        assert await queue.get() == "item2"

        # Now should raise error
        with pytest.raises(QueueClosedError):
            await queue.get()

    async def test_closed_property(self, queue):
        """Test closed property."""
        assert not queue.closed
        await queue.close()
        assert queue.closed


class TestTaskExecutor:
    """Test suite for TaskExecutor."""

    @pytest.fixture
    async def executor(self):
        """Create executor with tracked processing."""
        queue = InMemoryQueue()
        processed_items = []

        async def handler(item):
            processed_items.append(item)

        executor = TaskExecutor(queue, handler, num_workers=2)
        executor.start()

        yield executor, queue, processed_items

        await executor.stop()

    async def test_processes_items(self, executor):
        """Test that executor processes queued items."""
        exec, queue, processed = executor

        await queue.put("item1")
        await queue.put("item2")
        await queue.put("item3")

        # Wait for processing
        await asyncio.sleep(0.2)

        assert "item1" in processed
        assert "item2" in processed
        assert "item3" in processed

    async def test_multiple_workers(self):
        """Test that multiple workers process concurrently."""
        queue = InMemoryQueue()
        processing_times = []

        async def slow_handler(item):
            await asyncio.sleep(0.1)
            processing_times.append(item)

        executor = TaskExecutor(queue, slow_handler, num_workers=3)
        executor.start()

        start_time = asyncio.get_event_loop().time()

        # Add 3 items - with 3 workers, should process in parallel
        await queue.put("a")
        await queue.put("b")
        await queue.put("c")

        # Wait for all to complete
        await asyncio.sleep(0.15)

        end_time = asyncio.get_event_loop().time()

        await executor.stop()

        # All items should be processed
        assert len(processing_times) == 3

        # Should take ~0.1s (parallel), not ~0.3s (sequential)
        assert end_time - start_time < 0.25

    async def test_graceful_shutdown(self):
        """Test that executor stops gracefully."""
        queue = InMemoryQueue()
        processed = []

        async def handler(item):
            processed.append(item)

        executor = TaskExecutor(queue, handler, num_workers=1)
        executor.start()

        await queue.put("item1")
        await queue.put("item2")

        # Let some items process
        await asyncio.sleep(0.1)

        # Stop should wait for pending items
        await executor.stop()

        # All items should be processed
        assert "item1" in processed
        assert "item2" in processed

    async def test_retry_on_failure(self):
        """Test that failed items are retried."""
        queue = InMemoryQueue()
        attempts = []

        async def failing_handler(item):
            attempts.append(item)
            if len(attempts) < 3:
                raise Exception("Temporary failure")

        executor = TaskExecutor(queue, failing_handler, num_workers=1, max_retries=3)
        executor.start()

        await queue.put("item1")

        # Wait for retries (1s, 2s, 4s delays + processing time)
        await asyncio.sleep(8)

        await executor.stop()

        # Should have attempted 3 times
        assert attempts.count("item1") == 3
