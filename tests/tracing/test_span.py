"""Tests for Span data models."""

from dataclasses import asdict

from prefactor_sdk.tracing.span import (
    ErrorInfo,
    Span,
    SpanStatus,
    SpanType,
    TokenUsage,
)


class TestSpanType:
    """Test SpanType enum."""

    def test_span_types(self):
        """Test all span types are defined."""
        assert SpanType.AGENT == "agent"
        assert SpanType.LLM == "llm"
        assert SpanType.TOOL == "tool"
        assert SpanType.CHAIN == "chain"
        assert SpanType.RETRIEVER == "retriever"


class TestSpanStatus:
    """Test SpanStatus enum."""

    def test_span_statuses(self):
        """Test all span statuses are defined."""
        assert SpanStatus.RUNNING == "running"
        assert SpanStatus.SUCCESS == "success"
        assert SpanStatus.ERROR == "error"


class TestTokenUsage:
    """Test TokenUsage data class."""

    def test_token_usage_creation(self):
        """Test creating TokenUsage."""
        usage = TokenUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 20
        assert usage.total_tokens == 30

    def test_token_usage_to_dict(self):
        """Test converting TokenUsage to dict."""
        usage = TokenUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        data = asdict(usage)
        assert data == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }


class TestErrorInfo:
    """Test ErrorInfo data class."""

    def test_error_info_creation(self):
        """Test creating ErrorInfo."""
        error = ErrorInfo(
            error_type="ValueError",
            message="Invalid value",
            stacktrace="File test.py, line 1",
        )
        assert error.error_type == "ValueError"
        assert error.message == "Invalid value"
        assert error.stacktrace == "File test.py, line 1"

    def test_error_info_to_dict(self):
        """Test converting ErrorInfo to dict."""
        error = ErrorInfo(
            error_type="ValueError",
            message="Invalid value",
            stacktrace="File test.py, line 1",
        )
        data = asdict(error)
        assert data == {
            "error_type": "ValueError",
            "message": "Invalid value",
            "stacktrace": "File test.py, line 1",
        }


class TestSpan:
    """Test Span data class."""

    def test_span_creation_minimal(self):
        """Test creating a minimal Span."""
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
        assert span.span_id == "span-123"
        assert span.parent_span_id is None
        assert span.trace_id == "trace-456"
        assert span.name == "test_span"
        assert span.span_type == SpanType.LLM
        assert span.start_time == 1234567890.123
        assert span.end_time is None
        assert span.status == SpanStatus.RUNNING
        assert span.inputs == {"prompt": "Hello"}
        assert span.outputs is None
        assert span.token_usage is None
        assert span.error is None
        assert span.metadata == {}
        assert span.tags == []

    def test_span_creation_with_parent(self):
        """Test creating a Span with parent."""
        span = Span(
            span_id="span-child",
            parent_span_id="span-parent",
            trace_id="trace-456",
            name="child_span",
            span_type=SpanType.TOOL,
            start_time=1234567890.123,
            end_time=None,
            status=SpanStatus.RUNNING,
            inputs={"tool": "calculator"},
            outputs=None,
            token_usage=None,
            error=None,
            metadata={"key": "value"},
            tags=["math"],
        )
        assert span.parent_span_id == "span-parent"
        assert span.metadata == {"key": "value"}
        assert span.tags == ["math"]

    def test_span_creation_completed(self):
        """Test creating a completed Span."""
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
            outputs={"response": "Hi there"},
            token_usage=token_usage,
            error=None,
            metadata={},
            tags=[],
        )
        assert span.end_time == 1234567891.456
        assert span.status == SpanStatus.SUCCESS
        assert span.outputs == {"response": "Hi there"}
        assert span.token_usage == token_usage

    def test_span_creation_with_error(self):
        """Test creating a Span with error."""
        error = ErrorInfo(
            error_type="ValueError",
            message="Invalid value",
            stacktrace="File test.py, line 1",
        )
        span = Span(
            span_id="span-123",
            parent_span_id=None,
            trace_id="trace-456",
            name="test_span",
            span_type=SpanType.CHAIN,
            start_time=1234567890.123,
            end_time=1234567891.456,
            status=SpanStatus.ERROR,
            inputs={"data": "test"},
            outputs=None,
            token_usage=None,
            error=error,
            metadata={},
            tags=[],
        )
        assert span.status == SpanStatus.ERROR
        assert span.error == error

    def test_span_to_dict(self):
        """Test converting Span to dict."""
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
            metadata={"key": "value"},
            tags=["tag1"],
        )
        data = asdict(span)
        assert data["span_id"] == "span-123"
        assert data["parent_span_id"] is None
        assert data["trace_id"] == "trace-456"
        assert data["name"] == "test_span"
        assert data["span_type"] == SpanType.LLM
        assert data["start_time"] == 1234567890.123
        assert data["end_time"] is None
        assert data["status"] == SpanStatus.RUNNING
        assert data["inputs"] == {"prompt": "Hello"}
        assert data["outputs"] is None
        assert data["token_usage"] is None
        assert data["error"] is None
        assert data["metadata"] == {"key": "value"}
        assert data["tags"] == ["tag1"]

    def test_span_with_token_usage_to_dict(self):
        """Test converting Span with token usage to dict."""
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
        data = asdict(span)
        assert data["token_usage"] == {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }
