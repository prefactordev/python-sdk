"""Tests for STDIO transport."""

import json
import threading

from prefactor_sdk.tracing.span import Span, SpanStatus, SpanType, TokenUsage
from prefactor_sdk.transport.stdio import StdioTransport


class TestStdioTransport:
    """Test StdioTransport class."""

    def test_emit_simple_span(self, capsys):
        """Test emitting a simple span."""
        transport = StdioTransport()

        span = Span(
            span_id="span-123",
            parent_span_id=None,
            trace_id="trace-456",
            name="test_span",
            span_type=SpanType.LLM,
            start_time=1234567890.123,
            end_time=1234567891.456,
            status=SpanStatus.SUCCESS,
            inputs={"prompt": "Hello"},
            outputs={"response": "Hi there"},
            token_usage=None,
            error=None,
            metadata={},
            tags=[],
        )

        transport.emit(span)
        transport.close()

        # Capture stdout
        captured = capsys.readouterr()
        output = captured.out

        # Should be valid JSON
        lines = output.strip().split("\n")
        assert len(lines) == 1

        data = json.loads(lines[0])
        assert data["span_id"] == "span-123"
        assert data["trace_id"] == "trace-456"
        assert data["name"] == "test_span"
        assert data["span_type"] == "llm"
        assert data["status"] == "success"

    def test_emit_span_with_token_usage(self, capsys):
        """Test emitting a span with token usage."""
        transport = StdioTransport()

        token_usage = TokenUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

        span = Span(
            span_id="span-123",
            parent_span_id=None,
            trace_id="trace-456",
            name="test_span",
            span_type=SpanType.LLM,
            start_time=1234567890.123,
            end_time=1234567891.456,
            status=SpanStatus.SUCCESS,
            inputs={"prompt": "Hello"},
            outputs={"response": "Hi"},
            token_usage=token_usage,
            error=None,
            metadata={},
            tags=[],
        )

        transport.emit(span)
        transport.close()

        captured = capsys.readouterr()
        output = captured.out
        lines = output.strip().split("\n")
        data = json.loads(lines[0])

        assert data["token_usage"] is not None
        assert data["token_usage"]["prompt_tokens"] == 10
        assert data["token_usage"]["completion_tokens"] == 20
        assert data["token_usage"]["total_tokens"] == 30

    def test_emit_multiple_spans(self, capsys):
        """Test emitting multiple spans."""
        transport = StdioTransport()

        for i in range(3):
            span = Span(
                span_id=f"span-{i}",
                parent_span_id=None,
                trace_id="trace-456",
                name=f"span_{i}",
                span_type=SpanType.LLM,
                start_time=1234567890.123,
                end_time=1234567891.456,
                status=SpanStatus.SUCCESS,
                inputs={},
                outputs={},
                token_usage=None,
                error=None,
                metadata={},
                tags=[],
            )
            transport.emit(span)

        transport.close()

        captured = capsys.readouterr()
        output = captured.out
        lines = output.strip().split("\n")

        assert len(lines) == 3
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data["span_id"] == f"span-{i}"
            assert data["name"] == f"span_{i}"

    def test_emit_with_parent(self, capsys):
        """Test emitting a span with parent."""
        transport = StdioTransport()

        span = Span(
            span_id="child-123",
            parent_span_id="parent-456",
            trace_id="trace-789",
            name="child_span",
            span_type=SpanType.TOOL,
            start_time=1234567890.123,
            end_time=1234567891.456,
            status=SpanStatus.SUCCESS,
            inputs={},
            outputs={},
            token_usage=None,
            error=None,
            metadata={},
            tags=[],
        )

        transport.emit(span)
        transport.close()

        captured = capsys.readouterr()
        output = captured.out
        lines = output.strip().split("\n")
        data = json.loads(lines[0])

        assert data["parent_span_id"] == "parent-456"

    def test_thread_safety(self, capsys):
        """Test that StdioTransport is thread-safe."""
        transport = StdioTransport()
        num_threads = 10
        spans_per_thread = 5

        def emit_spans(thread_id: int):
            for i in range(spans_per_thread):
                span = Span(
                    span_id=f"span-{thread_id}-{i}",
                    parent_span_id=None,
                    trace_id="trace-456",
                    name=f"span_{thread_id}_{i}",
                    span_type=SpanType.LLM,
                    start_time=1234567890.123,
                    end_time=1234567891.456,
                    status=SpanStatus.SUCCESS,
                    inputs={},
                    outputs={},
                    token_usage=None,
                    error=None,
                    metadata={},
                    tags=[],
                )
                transport.emit(span)

        threads = []
        for t in range(num_threads):
            thread = threading.Thread(target=emit_spans, args=(t,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        transport.close()

        captured = capsys.readouterr()
        output = captured.out
        lines = output.strip().split("\n")

        # Should have all spans
        assert len(lines) == num_threads * spans_per_thread

        # All lines should be valid JSON
        for line in lines:
            data = json.loads(line)
            assert "span_id" in data
            assert "trace_id" in data

    def test_emit_error_handling(self, capsys, monkeypatch):
        """Test error handling in emit."""
        transport = StdioTransport()

        # Create a span that will fail to serialize (simulate by monkeypatching)
        span = Span(
            span_id="span-123",
            parent_span_id=None,
            trace_id="trace-456",
            name="test_span",
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

        # Mock orjson.dumps to raise an exception
        def mock_dumps(*args, **kwargs):
            raise ValueError("Serialization error")

        import prefactor_sdk.transport.stdio as stdio_module

        monkeypatch.setattr(stdio_module.orjson, "dumps", mock_dumps)

        # Should not raise, just log the error
        transport.emit(span)
        transport.close()

        # Should have no output due to error
        captured = capsys.readouterr()
        output = captured.out
        assert output.strip() == ""

    def test_close_idempotent(self):
        """Test that close() can be called multiple times."""
        transport = StdioTransport()
        transport.close()
        transport.close()  # Should not raise
