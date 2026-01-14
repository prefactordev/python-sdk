"""Tests for LangChain callback handler."""

from unittest.mock import Mock
from uuid import uuid4

from prefactor_sdk.instrumentation.langchain.callback_handler import (
    PrefactorCallbackHandler,
)
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


class TestPrefactorCallbackHandler:
    """Test PrefactorCallbackHandler."""

    def test_init(self):
        """Test initializing the callback handler."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        assert handler is not None
        assert handler.raise_error is False

    def test_on_llm_start(self):
        """Test LLM start callback."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        parent_run_id = None
        serialized = {"name": "OpenAI"}
        prompts = ["Hello, how are you?"]

        handler.on_llm_start(
            serialized=serialized,
            prompts=prompts,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=["test"],
            metadata={"model": "gpt-4"},
        )

        # Should have created a span
        assert run_id in handler._span_map
        span = handler._span_map[run_id]
        assert span.name == "OpenAI"
        assert span.span_type == SpanType.LLM
        assert span.status == SpanStatus.RUNNING
        assert "prompts" in span.inputs

    def test_on_llm_end(self):
        """Test LLM end callback."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        serialized = {"name": "OpenAI"}
        prompts = ["Hello"]

        # Start the LLM span
        handler.on_llm_start(
            serialized=serialized,
            prompts=prompts,
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Mock LLMResult
        response = Mock()
        response.generations = [[Mock(text="Hi there!")]]
        response.llm_output = {
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            }
        }

        # End the LLM span
        handler.on_llm_end(
            response=response,
            run_id=run_id,
        )

        # Should have emitted the span
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.status == SpanStatus.SUCCESS
        assert span.token_usage is not None
        assert span.token_usage.prompt_tokens == 10

    def test_on_llm_error(self):
        """Test LLM error callback."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        serialized = {"name": "OpenAI"}
        prompts = ["Hello"]

        # Start the LLM span
        handler.on_llm_start(
            serialized=serialized,
            prompts=prompts,
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Trigger error
        error = ValueError("API error")
        handler.on_llm_error(
            error=error,
            run_id=run_id,
        )

        # Should have emitted the span with error
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.status == SpanStatus.ERROR
        assert span.error is not None
        assert span.error.error_type == "ValueError"

    def test_on_tool_start(self):
        """Test tool start callback."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        parent_run_id = uuid4()
        serialized = {"name": "Calculator"}
        input_str = "25 * 4"

        handler.on_tool_start(
            serialized=serialized,
            input_str=input_str,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=[],
            metadata={},
        )

        # Should have created a tool span
        assert run_id in handler._span_map
        span = handler._span_map[run_id]
        assert span.name == "Calculator"
        assert span.span_type == SpanType.TOOL
        assert "input" in span.inputs

    def test_on_tool_end(self):
        """Test tool end callback."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        serialized = {"name": "Calculator"}
        input_str = "25 * 4"

        # Start the tool span
        handler.on_tool_start(
            serialized=serialized,
            input_str=input_str,
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # End the tool span
        output = "100"
        handler.on_tool_end(
            output=output,
            run_id=run_id,
        )

        # Should have emitted the span
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.status == SpanStatus.SUCCESS
        assert span.outputs["output"] == "100"

    def test_on_tool_error(self):
        """Test tool error callback."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        serialized = {"name": "Calculator"}
        input_str = "invalid"

        # Start the tool span
        handler.on_tool_start(
            serialized=serialized,
            input_str=input_str,
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Trigger error
        error = ValueError("Invalid input")
        handler.on_tool_error(
            error=error,
            run_id=run_id,
        )

        # Should have emitted the span with error
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.status == SpanStatus.ERROR

    def test_on_chain_start(self):
        """Test chain start callback."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        serialized = {"name": "LLMChain"}
        inputs = {"question": "What is AI?"}

        handler.on_chain_start(
            serialized=serialized,
            inputs=inputs,
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Should have created a chain span
        assert run_id in handler._span_map
        span = handler._span_map[run_id]
        assert span.name == "LLMChain"
        assert span.span_type == SpanType.CHAIN
        assert span.inputs == inputs

    def test_on_chain_end(self):
        """Test chain end callback."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        serialized = {"name": "LLMChain"}
        inputs = {"question": "What is AI?"}

        # Start the chain span
        handler.on_chain_start(
            serialized=serialized,
            inputs=inputs,
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # End the chain span
        outputs = {"answer": "AI is artificial intelligence"}
        handler.on_chain_end(
            outputs=outputs,
            run_id=run_id,
        )

        # Should have emitted the span
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.status == SpanStatus.SUCCESS
        assert span.outputs == outputs

    def test_on_chain_error(self):
        """Test chain error callback."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        serialized = {"name": "LLMChain"}
        inputs = {"question": "What is AI?"}

        # Start the chain span
        handler.on_chain_start(
            serialized=serialized,
            inputs=inputs,
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Trigger error
        error = RuntimeError("Chain failed")
        handler.on_chain_error(
            error=error,
            run_id=run_id,
        )

        # Should have emitted the span with error
        assert len(transport.emitted_spans) == 1
        span = transport.emitted_spans[0]
        assert span.status == SpanStatus.ERROR

    def test_parent_child_relationship(self):
        """Test parent-child span relationship."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        # Create parent chain span
        parent_run_id = uuid4()
        handler.on_chain_start(
            serialized={"name": "ParentChain"},
            inputs={},
            run_id=parent_run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Create child LLM span
        child_run_id = uuid4()
        handler.on_llm_start(
            serialized={"name": "ChildLLM"},
            prompts=["test"],
            run_id=child_run_id,
            parent_run_id=parent_run_id,
            tags=[],
            metadata={},
        )

        # Get the spans
        parent_span = handler._span_map[parent_run_id]
        child_span = handler._span_map[child_run_id]

        # Verify relationship
        assert child_span.parent_span_id == parent_span.span_id
        assert child_span.trace_id == parent_span.trace_id

    def test_error_doesnt_break_execution(self):
        """Test that errors in callback handler don't break execution."""
        transport = MockTransport()
        tracer = Tracer(transport=transport)
        handler = PrefactorCallbackHandler(tracer=tracer)

        # Call on_llm_end without starting - should not raise
        run_id = uuid4()
        response = Mock()
        response.generations = [[Mock(text="test")]]
        response.llm_output = None

        # Should not raise even though span doesn't exist
        handler.on_llm_end(response=response, run_id=run_id)
