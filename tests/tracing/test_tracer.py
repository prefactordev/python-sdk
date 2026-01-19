"""Tests for Tracer class."""

import time
from unittest.mock import Mock

import pfid
from pfid import Partition

from prefactor_sdk.tracing.context import SpanContext
from prefactor_sdk.tracing.span import SpanStatus, SpanType
from prefactor_sdk.tracing.tracer import Tracer
from prefactor_sdk.transport.base import Transport


class MockTransport(Transport):
    """Mock transport for testing."""

    def __init__(self):
        self.emitted_spans = []

    def emit(self, span):
        self.emitted_spans.append(span)

    def close(self):
        pass


class TestTracer:
    """Test Tracer class."""

    def test_start_span_minimal(self):
        """Test starting a minimal span."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        span = tracer.start_span(
            name="test_span",
            span_type=SpanType.LLM,
            inputs={"prompt": "Hello"},
        )

        assert span is not None
        assert span.name == "test_span"
        assert span.span_type == SpanType.LLM
        assert span.status == SpanStatus.RUNNING
        assert span.inputs == {"prompt": "Hello"}
        assert span.outputs is None
        assert span.end_time is None
        assert span.span_id is not None
        assert span.trace_id is not None

    def test_start_span_with_parent(self):
        """Test starting a span with a parent."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        parent = tracer.start_span(
            name="parent_span",
            span_type=SpanType.AGENT,
            inputs={},
        )

        child = tracer.start_span(
            name="child_span",
            span_type=SpanType.LLM,
            inputs={},
            parent_span_id=parent.span_id,
            trace_id=parent.trace_id,
        )

        assert child.parent_span_id == parent.span_id
        assert child.trace_id == parent.trace_id

    def test_end_span_success(self):
        """Test ending a span successfully."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        span = tracer.start_span(
            name="test_span",
            span_type=SpanType.LLM,
            inputs={"prompt": "Hello"},
        )

        start_time = span.start_time

        # Small delay to ensure end_time > start_time
        time.sleep(0.01)

        tracer.end_span(
            span=span,
            outputs={"response": "Hi there"},
        )

        assert span.status == SpanStatus.SUCCESS
        assert span.outputs == {"response": "Hi there"}
        assert span.end_time is not None
        assert span.end_time > start_time

        # Should have emitted the span
        assert len(transport.emitted_spans) == 1
        assert transport.emitted_spans[0] is span

    def test_end_span_with_error(self):
        """Test ending a span with an error."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        span = tracer.start_span(
            name="test_span",
            span_type=SpanType.CHAIN,
            inputs={"data": "test"},
        )

        error = Exception("Test error")

        tracer.end_span(
            span=span,
            error=error,
        )

        assert span.status == SpanStatus.ERROR
        assert span.error is not None
        assert span.error.error_type == "Exception"
        assert span.error.message == "Test error"
        assert span.error.stacktrace is not None

        # Should have emitted the span
        assert len(transport.emitted_spans) == 1

    def test_context_integration(self):
        """Test integration with SpanContext."""
        SpanContext.clear()
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        # Start a parent span and set it in context
        parent = tracer.start_span(
            name="parent_span",
            span_type=SpanType.AGENT,
            inputs={},
        )
        SpanContext.set_current(parent)

        # Start a child span without explicit parent_span_id
        # It should use the context
        child = tracer.start_span(
            name="child_span",
            span_type=SpanType.LLM,
            inputs={},
        )

        # Since we don't automatically infer parent from context,
        # child should be a root span
        assert child.parent_span_id is None

        # But if we explicitly provide parent_span_id, it should work
        child2 = tracer.start_span(
            name="child_span_2",
            span_type=SpanType.TOOL,
            inputs={},
            parent_span_id=parent.span_id,
            trace_id=parent.trace_id,
        )

        assert child2.parent_span_id == parent.span_id

    def test_multiple_spans_same_trace(self):
        """Test multiple spans in the same trace."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        parent = tracer.start_span(
            name="parent",
            span_type=SpanType.AGENT,
            inputs={},
        )

        child1 = tracer.start_span(
            name="child1",
            span_type=SpanType.LLM,
            inputs={},
            parent_span_id=parent.span_id,
            trace_id=parent.trace_id,
        )

        child2 = tracer.start_span(
            name="child2",
            span_type=SpanType.TOOL,
            inputs={},
            parent_span_id=parent.span_id,
            trace_id=parent.trace_id,
        )

        # All should share the same trace_id
        assert child1.trace_id == parent.trace_id
        assert child2.trace_id == parent.trace_id

        # But have different span_ids
        assert child1.span_id != parent.span_id
        assert child2.span_id != parent.span_id
        assert child1.span_id != child2.span_id

    def test_span_with_metadata_and_tags(self):
        """Test creating a span with metadata and tags."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        span = tracer.start_span(
            name="test_span",
            span_type=SpanType.LLM,
            inputs={},
            metadata={"model": "gpt-4", "temperature": 0.7},
            tags=["production", "important"],
        )

        assert span.metadata == {"model": "gpt-4", "temperature": 0.7}
        assert span.tags == ["production", "important"]

    def test_end_span_with_token_usage(self):
        """Test ending a span with token usage."""
        from prefactor_sdk.tracing.span import TokenUsage

        transport = MockTransport()
        tracer = Tracer(transport=transport)

        span = tracer.start_span(
            name="test_span",
            span_type=SpanType.LLM,
            inputs={"prompt": "Hello"},
        )

        token_usage = TokenUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

        tracer.end_span(
            span=span,
            outputs={"response": "Hi"},
            token_usage=token_usage,
        )

        assert span.token_usage == token_usage
        assert span.token_usage.prompt_tokens == 10

    def test_tracer_close(self):
        """Test closing the tracer."""
        transport = Mock(spec=Transport)
        tracer = Tracer(transport=transport)

        tracer.close()

        # Should call transport.close()
        transport.close.assert_called_once()

    def test_span_ids_are_unique(self):
        """Test that span IDs are unique."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        spans = []
        for i in range(100):
            span = tracer.start_span(
                name=f"span_{i}",
                span_type=SpanType.LLM,
                inputs={},
            )
            spans.append(span)

        # All span IDs should be unique
        span_ids = [s.span_id for s in spans]
        assert len(span_ids) == len(set(span_ids))

    def test_nested_spans_different_traces(self):
        """Test that spans can have different traces."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        # Create two independent traces
        trace1_root = tracer.start_span(
            name="trace1_root",
            span_type=SpanType.AGENT,
            inputs={},
        )

        trace2_root = tracer.start_span(
            name="trace2_root",
            span_type=SpanType.AGENT,
            inputs={},
        )

        # They should have different trace IDs
        assert trace1_root.trace_id != trace2_root.trace_id

    def test_span_ids_are_valid_pfids(self):
        """Test that span IDs are valid PFIDs."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        span = tracer.start_span(
            name="test_span",
            span_type=SpanType.LLM,
            inputs={},
        )

        # Both span_id and trace_id should be valid PFIDs
        assert pfid.is_pfid(span.span_id)
        assert pfid.is_pfid(span.trace_id)

    def test_tracer_uses_provided_partition(self):
        """Test that tracer uses the provided partition for ID generation."""
        transport = MockTransport()
        partition = Partition(12345)
        tracer = Tracer(transport=transport, partition=partition)

        span = tracer.start_span(
            name="test_span",
            span_type=SpanType.LLM,
            inputs={},
        )

        # Verify IDs use the correct partition
        assert pfid.extract_partition(span.span_id) == partition
        assert pfid.extract_partition(span.trace_id) == partition

    def test_tracer_generates_partition_when_none_provided(self):
        """Test that tracer generates a partition when none is provided."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)

        span = tracer.start_span(
            name="test_span",
            span_type=SpanType.LLM,
            inputs={},
        )

        # IDs should still be valid PFIDs
        assert pfid.is_pfid(span.span_id)
        assert pfid.is_pfid(span.trace_id)

        # Extract partition should work (returns an int)
        partition = pfid.extract_partition(span.span_id)
        assert isinstance(partition, int)

    def test_multiple_spans_use_same_partition(self):
        """Test that all spans from same tracer use the same partition."""
        transport = MockTransport()
        partition = Partition(99999)
        tracer = Tracer(transport=transport, partition=partition)

        spans = []
        for i in range(5):
            span = tracer.start_span(
                name=f"span_{i}",
                span_type=SpanType.LLM,
                inputs={},
            )
            spans.append(span)

        # All spans should use the same partition
        for span in spans:
            assert pfid.extract_partition(span.span_id) == partition
