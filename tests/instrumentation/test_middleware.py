"""Tests for LangChain middleware."""

from unittest.mock import Mock

import pytest

from prefactor_sdk.instrumentation.langchain.middleware import PrefactorMiddleware
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


class TestPrefactorMiddleware:
    """Test PrefactorMiddleware."""

    def setup_method(self):
        """Set up test fixtures."""
        # Clear span context before each test
        SpanContext.clear()

    def teardown_method(self):
        """Clean up after each test."""
        # Clear span context after each test
        SpanContext.clear()

    def test_init(self):
        """Test initializing the middleware."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        middleware = PrefactorMiddleware(tracer=tracer)

        assert middleware is not None
        assert middleware._tracer == tracer
        assert middleware._root_span is None

    def test_before_agent_creates_span(self):
        """Test that before_agent creates a root span."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        middleware = PrefactorMiddleware(tracer=tracer)

        # Mock state and runtime
        state = {"messages": ["Hello"]}
        runtime = Mock()

        # Call before_agent
        result = middleware.before_agent(state, runtime)

        # Should not modify state
        assert result is None

        # Should have created a root span
        assert middleware._root_span is not None
        assert middleware._root_span.span_type == SpanType.AGENT
        assert middleware._root_span.status == SpanStatus.RUNNING

        # Should set span in context
        current = SpanContext.get_current()
        assert current == middleware._root_span

    def test_after_agent_ends_span(self):
        """Test that after_agent ends the root span."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        middleware = PrefactorMiddleware(tracer=tracer)

        # Mock state and runtime
        state = {"messages": ["Hello", "Response"]}
        runtime = Mock()

        # Start agent
        middleware.before_agent(state, runtime)
        assert len(transport.emitted_spans) == 0

        # End agent
        middleware.after_agent(state, runtime)

        # Should have emitted the span
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.span_type == SpanType.AGENT
        assert span.status == SpanStatus.SUCCESS

        # Should clear context
        assert SpanContext.get_current() is None
        assert middleware._root_span is None

    def test_wrap_model_call_creates_span(self):
        """Test that wrap_model_call creates LLM spans."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        middleware = PrefactorMiddleware(tracer=tracer)

        # Mock request and response
        request = Mock()
        request.metadata = {"name": "gpt-4"}
        request.messages = ["Hello"]

        response = Mock()
        response.content = "Hi there!"

        # Mock handler
        handler = Mock(return_value=response)

        # Wrap model call
        result = middleware.wrap_model_call(request, handler)

        # Should call handler
        handler.assert_called_once_with(request)
        assert result == response

        # Should have emitted a span
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.span_type == SpanType.LLM
        assert span.status == SpanStatus.SUCCESS
        assert "response" in span.outputs

    def test_wrap_model_call_with_parent_span(self):
        """Test that wrap_model_call maintains parent-child relationships."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        middleware = PrefactorMiddleware(tracer=tracer)

        # Create parent span
        state = {"messages": ["Hello"]}
        runtime = Mock()
        middleware.before_agent(state, runtime)
        parent_span = middleware._root_span

        # Mock request and response
        request = Mock()
        request.metadata = {}
        request.messages = ["Hello"]
        response = Mock()
        response.content = "Hi!"

        handler = Mock(return_value=response)

        # Wrap model call
        middleware.wrap_model_call(request, handler)

        # LLM span should have been emitted immediately
        assert len(transport.emitted_spans) == 1
        llm_span = transport.emitted_spans[0]

        # End agent to emit agent span
        middleware.after_agent(state, runtime)

        # Should now have both spans
        assert len(transport.emitted_spans) == 2
        agent_span = transport.emitted_spans[1]

        # Verify parent-child relationship
        assert llm_span.parent_span_id == parent_span.span_id
        assert llm_span.trace_id == parent_span.trace_id

    def test_wrap_model_call_handles_errors(self):
        """Test that wrap_model_call handles errors properly."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        middleware = PrefactorMiddleware(tracer=tracer)

        # Mock request
        request = Mock()
        request.metadata = {}
        request.messages = ["Hello"]

        # Mock handler that raises
        error = ValueError("Model failed")
        handler = Mock(side_effect=error)

        # Wrap model call - should raise
        with pytest.raises(ValueError, match="Model failed"):
            middleware.wrap_model_call(request, handler)

        # Should have emitted error span
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.status == SpanStatus.ERROR
        assert span.error is not None
        assert span.error.error_type == "ValueError"
        assert "Model failed" in span.error.message

    def test_wrap_tool_call_creates_span(self):
        """Test that wrap_tool_call creates tool spans."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        middleware = PrefactorMiddleware(tracer=tracer)

        # Mock request and response
        request = Mock()
        request.tool_call = {"name": "calculator", "args": {"expression": "2+2"}}

        response = Mock()
        response.content = "4"

        # Mock handler
        handler = Mock(return_value=response)

        # Wrap tool call
        result = middleware.wrap_tool_call(request, handler)

        # Should call handler
        handler.assert_called_once_with(request)
        assert result == response

        # Should have emitted a span
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.name == "calculator"
        assert span.span_type == SpanType.TOOL
        assert span.status == SpanStatus.SUCCESS
        assert "output" in span.outputs

    def test_wrap_tool_call_with_parent_span(self):
        """Test that wrap_tool_call maintains parent-child relationships."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        middleware = PrefactorMiddleware(tracer=tracer)

        # Create parent span
        state = {"messages": ["Hello"]}
        runtime = Mock()
        middleware.before_agent(state, runtime)
        parent_span = middleware._root_span

        # Mock request and response
        request = Mock()
        request.tool_call = {"name": "search", "args": {"query": "test"}}
        response = Mock()
        response.content = "Results"

        handler = Mock(return_value=response)

        # Wrap tool call
        middleware.wrap_tool_call(request, handler)

        # Tool span should have been emitted immediately
        assert len(transport.emitted_spans) == 1
        tool_span = transport.emitted_spans[0]

        # End agent to emit agent span
        middleware.after_agent(state, runtime)

        # Should now have both spans
        assert len(transport.emitted_spans) == 2
        agent_span = transport.emitted_spans[1]

        # Verify parent-child relationship
        assert tool_span.parent_span_id == parent_span.span_id
        assert tool_span.trace_id == parent_span.trace_id

    def test_wrap_tool_call_handles_errors(self):
        """Test that wrap_tool_call handles errors properly."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        middleware = PrefactorMiddleware(tracer=tracer)

        # Mock request
        request = Mock()
        request.tool_call = {"name": "failing_tool", "args": {}}

        # Mock handler that raises
        error = RuntimeError("Tool execution failed")
        handler = Mock(side_effect=error)

        # Wrap tool call - should raise
        with pytest.raises(RuntimeError, match="Tool execution failed"):
            middleware.wrap_tool_call(request, handler)

        # Should have emitted error span
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.name == "failing_tool"
        assert span.status == SpanStatus.ERROR
        assert span.error is not None
        assert span.error.error_type == "RuntimeError"

    def test_nested_spans_maintain_hierarchy(self):
        """Test that nested operations maintain proper span hierarchy."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        middleware = PrefactorMiddleware(tracer=tracer)

        # Start agent
        state = {"messages": ["Task"]}
        runtime = Mock()
        middleware.before_agent(state, runtime)
        parent_span = middleware._root_span

        # First model call
        request1 = Mock()
        request1.metadata = {}
        request1.messages = ["Hello"]
        response1 = Mock()
        response1.content = "Response 1"
        handler1 = Mock(return_value=response1)
        middleware.wrap_model_call(request1, handler1)

        # Tool call
        tool_request = Mock()
        tool_request.tool_call = {"name": "search", "args": {}}
        tool_response = Mock()
        tool_response.content = "Tool result"
        tool_handler = Mock(return_value=tool_response)
        middleware.wrap_tool_call(tool_request, tool_handler)

        # Second model call
        request2 = Mock()
        request2.metadata = {}
        request2.messages = ["Follow-up"]
        response2 = Mock()
        response2.content = "Response 2"
        handler2 = Mock(return_value=response2)
        middleware.wrap_model_call(request2, handler2)

        # End agent
        middleware.after_agent(state, runtime)

        # Should have 4 spans total
        assert len(transport.emitted_spans) == 4

        # Spans are emitted in order: llm1, tool, llm2, agent
        llm_span1 = transport.emitted_spans[0]
        tool_span = transport.emitted_spans[1]
        llm_span2 = transport.emitted_spans[2]
        agent_span = transport.emitted_spans[3]

        # All children should have agent as parent
        assert llm_span1.parent_span_id == parent_span.span_id
        assert tool_span.parent_span_id == parent_span.span_id
        assert llm_span2.parent_span_id == parent_span.span_id

        # All should share same trace_id
        assert llm_span1.trace_id == parent_span.trace_id
        assert tool_span.trace_id == parent_span.trace_id
        assert llm_span2.trace_id == parent_span.trace_id
