"""Tests for span context propagation."""

import asyncio

from prefactor_core.tracing.context import SpanContext
from prefactor_core.tracing.span import Span, SpanStatus, SpanType


class TestSpanContext:
    """Test SpanContext class."""

    def test_get_current_no_context(self):
        """Test getting current span when no context is set."""
        SpanContext.clear()
        span = SpanContext.get_current()
        assert span is None

    def test_set_and_get_current(self):
        """Test setting and getting current span."""
        SpanContext.clear()
        span = Span(
            span_id="span-123",
            parent_span_id=None,
            trace_id="trace-456",
            name="test_span",
            span_type=SpanType.LLM,
            start_time=1234567890.123,
            end_time=None,
            status=SpanStatus.RUNNING,
            inputs={"prompt": "Hello"},
            outputs=None,
            token_usage=None,
            error=None,
            metadata={},
            tags=[],
        )
        SpanContext.set_current(span)
        current = SpanContext.get_current()
        assert current is span
        assert current.span_id == "span-123"

    def test_clear_context(self):
        """Test clearing the context."""
        span = Span(
            span_id="span-123",
            parent_span_id=None,
            trace_id="trace-456",
            name="test_span",
            span_type=SpanType.LLM,
            start_time=1234567890.123,
            end_time=None,
            status=SpanStatus.RUNNING,
            inputs={"prompt": "Hello"},
            outputs=None,
            token_usage=None,
            error=None,
            metadata={},
            tags=[],
        )
        SpanContext.set_current(span)
        assert SpanContext.get_current() is not None

        SpanContext.clear()
        assert SpanContext.get_current() is None

    def test_parent_child_relationship(self):
        """Test parent-child span relationship."""
        SpanContext.clear()

        # Create parent span
        parent = Span(
            span_id="parent-123",
            parent_span_id=None,
            trace_id="trace-456",
            name="parent_span",
            span_type=SpanType.AGENT,
            start_time=1234567890.123,
            end_time=None,
            status=SpanStatus.RUNNING,
            inputs={},
            outputs=None,
            token_usage=None,
            error=None,
            metadata={},
            tags=[],
        )
        SpanContext.set_current(parent)

        # Get current and verify it's the parent
        current_parent = SpanContext.get_current()
        assert current_parent.span_id == "parent-123"

        # Create child span with parent
        child = Span(
            span_id="child-456",
            parent_span_id=current_parent.span_id,
            trace_id="trace-456",
            name="child_span",
            span_type=SpanType.LLM,
            start_time=1234567890.456,
            end_time=None,
            status=SpanStatus.RUNNING,
            inputs={},
            outputs=None,
            token_usage=None,
            error=None,
            metadata={},
            tags=[],
        )
        SpanContext.set_current(child)

        # Verify child is now current
        current_child = SpanContext.get_current()
        assert current_child.span_id == "child-456"
        assert current_child.parent_span_id == "parent-123"

    async def test_async_context_propagation(self):
        """Test context propagates correctly in async functions."""
        SpanContext.clear()

        # Create a span in the main task
        main_span = Span(
            span_id="main-123",
            parent_span_id=None,
            trace_id="trace-456",
            name="main_span",
            span_type=SpanType.AGENT,
            start_time=1234567890.123,
            end_time=None,
            status=SpanStatus.RUNNING,
            inputs={},
            outputs=None,
            token_usage=None,
            error=None,
            metadata={},
            tags=[],
        )
        SpanContext.set_current(main_span)

        async def child_task():
            # The context should propagate to this task
            current = SpanContext.get_current()
            assert current is not None
            assert current.span_id == "main-123"
            return current.span_id

        result = await child_task()
        assert result == "main-123"

    async def test_concurrent_async_tasks_isolation(self):
        """Test that concurrent async tasks have isolated contexts."""
        SpanContext.clear()

        results = []

        async def task_with_span(task_id: str):
            # Each task sets its own span
            span = Span(
                span_id=f"span-{task_id}",
                parent_span_id=None,
                trace_id="trace-456",
                name=f"task_{task_id}",
                span_type=SpanType.AGENT,
                start_time=1234567890.123,
                end_time=None,
                status=SpanStatus.RUNNING,
                inputs={},
                outputs=None,
                token_usage=None,
                error=None,
                metadata={},
                tags=[],
            )
            SpanContext.set_current(span)

            # Small delay to allow interleaving
            await asyncio.sleep(0.01)

            # Verify the context is still our span
            current = SpanContext.get_current()
            assert current is not None
            assert current.span_id == f"span-{task_id}"
            results.append(current.span_id)

        # Run multiple tasks concurrently
        await asyncio.gather(
            task_with_span("1"),
            task_with_span("2"),
            task_with_span("3"),
        )

        # All tasks should have their own isolated context
        assert len(results) == 3
        assert "span-1" in results
        assert "span-2" in results
        assert "span-3" in results

    def test_multiple_set_overwrites(self):
        """Test that setting context multiple times overwrites."""
        SpanContext.clear()

        span1 = Span(
            span_id="span-1",
            parent_span_id=None,
            trace_id="trace-456",
            name="span1",
            span_type=SpanType.LLM,
            start_time=1234567890.123,
            end_time=None,
            status=SpanStatus.RUNNING,
            inputs={},
            outputs=None,
            token_usage=None,
            error=None,
            metadata={},
            tags=[],
        )
        SpanContext.set_current(span1)
        assert SpanContext.get_current().span_id == "span-1"

        span2 = Span(
            span_id="span-2",
            parent_span_id=None,
            trace_id="trace-456",
            name="span2",
            span_type=SpanType.LLM,
            start_time=1234567890.456,
            end_time=None,
            status=SpanStatus.RUNNING,
            inputs={},
            outputs=None,
            token_usage=None,
            error=None,
            metadata={},
            tags=[],
        )
        SpanContext.set_current(span2)
        assert SpanContext.get_current().span_id == "span-2"
