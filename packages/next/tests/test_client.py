"""Tests for SpanContextStack and context management."""

import asyncio

from prefactor_next import SpanContextStack


class TestSpanContextStack:
    """Test suite for SpanContextStack."""

    def setup_method(self):
        """Clear the stack before each test."""
        # Note: In real usage, the stack is managed automatically by context managers
        # These tests verify the stack mechanics directly
        while not SpanContextStack.is_empty():
            SpanContextStack.pop()

    async def test_push_and_pop(self):
        """Test basic push and pop operations."""
        SpanContextStack.push("span-1")
        SpanContextStack.push("span-2")

        assert SpanContextStack.peek() == "span-2"
        assert SpanContextStack.pop() == "span-2"
        assert SpanContextStack.peek() == "span-1"
        assert SpanContextStack.pop() == "span-1"
        assert SpanContextStack.peek() is None

    async def test_depth_tracking(self):
        """Test depth tracking."""
        assert SpanContextStack.depth() == 0

        SpanContextStack.push("span-1")
        assert SpanContextStack.depth() == 1

        SpanContextStack.push("span-2")
        assert SpanContextStack.depth() == 2

        SpanContextStack.pop()
        assert SpanContextStack.depth() == 1

    async def test_is_empty(self):
        """Test is_empty method."""
        assert SpanContextStack.is_empty()

        SpanContextStack.push("span-1")
        assert not SpanContextStack.is_empty()

        SpanContextStack.pop()
        assert SpanContextStack.is_empty()

    async def test_pop_empty_stack(self):
        """Test popping from empty stack returns None."""
        result = SpanContextStack.pop()
        assert result is None

    async def test_peek_empty_stack(self):
        """Test peeking empty stack returns None."""
        result = SpanContextStack.peek()
        assert result is None

    async def test_concurrent_contexts(self):
        """Test that concurrent async contexts maintain separate stacks."""
        results = {}

        async def task_a():
            SpanContextStack.push("task-a-span")
            await asyncio.sleep(0.01)
            results["a"] = SpanContextStack.peek()
            SpanContextStack.pop()

        async def task_b():
            SpanContextStack.push("task-b-span")
            await asyncio.sleep(0.01)
            results["b"] = SpanContextStack.peek()
            SpanContextStack.pop()

        # Run both tasks concurrently
        await asyncio.gather(task_a(), task_b())

        # Each task should see its own span
        assert results["a"] == "task-a-span"
        assert results["b"] == "task-b-span"

    async def test_nested_contexts(self):
        """Test deeply nested span contexts."""
        SpanContextStack.push("root")
        SpanContextStack.push("child-1")
        SpanContextStack.push("child-2")
        SpanContextStack.push("child-3")

        assert SpanContextStack.depth() == 4
        assert SpanContextStack.peek() == "child-3"

        # Pop all
        assert SpanContextStack.pop() == "child-3"
        assert SpanContextStack.pop() == "child-2"
        assert SpanContextStack.pop() == "child-1"
        assert SpanContextStack.pop() == "root"
        assert SpanContextStack.pop() is None
