"""Tests for LangChain callback handler."""

from uuid import uuid4

from prefactor_core.tracing.span import SpanStatus, SpanType
from prefactor_core.tracing.tracer import Tracer
from prefactor_langchain.callback_handler import PrefactorCallbackHandler


class TestPrefactorCallbackHandler:
    """Test PrefactorCallbackHandler."""

    def test_init(self):
        """Test initializing the callback handler."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        assert handler is not None
        assert handler.raise_error is False

    def test_on_llm_start(self):
        """Test LLM start callback."""
        tracer = Tracer()
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
            tags=[],
            metadata={},
        )

        # A span should have been started
        assert run_id in handler._span_map
        span = handler._span_map[run_id]
        assert span.name == "OpenAI"
        assert span.span_type == SpanType.LLM
        assert span.inputs == {"prompts": prompts}
        assert span.status == SpanStatus.RUNNING

    def test_on_llm_end(self):
        """Test LLM end callback."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()

        # Start a span first
        handler.on_llm_start(
            serialized={"name": "test"},
            prompts=["Hello"],
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Create a mock LLMResult-like response
        class MockLLMResult:
            generations = []

        mock_response = MockLLMResult()

        handler.on_llm_end(
            response=mock_response,
            run_id=run_id,
            parent_run_id=None,
        )

        # Span should be removed from map
        assert run_id not in handler._span_map

    def test_on_llm_error(self):
        """Test LLM error callback."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()

        # Start a span first
        handler.on_llm_start(
            serialized={"name": "test"},
            prompts=["Hello"],
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Trigger an error
        error = Exception("Test error")
        handler.on_llm_error(error, run_id=run_id, parent_run_id=None)

        # Span should be removed from map after error
        assert run_id not in handler._span_map

    def test_on_tool_start(self):
        """Test tool start callback."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        serialized = {"name": "Calculator"}
        input_str = '{"expression": "1 + 1"}'

        handler.on_tool_start(
            serialized=serialized,
            input_str=input_str,
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # A span should have been started
        assert run_id in handler._span_map
        span = handler._span_map[run_id]
        assert span.name == "Calculator"
        assert span.span_type == SpanType.TOOL
        assert span.inputs == {"input": input_str}

    def test_on_tool_end(self):
        """Test tool end callback."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()

        # Start a span first
        handler.on_tool_start(
            serialized={"name": "test"},
            input_str="test",
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        handler.on_tool_end(
            output="2",
            run_id=run_id,
            parent_run_id=None,
        )

        # Span should be removed from map
        assert run_id not in handler._span_map

    def test_on_tool_error(self):
        """Test tool error callback."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()

        # Start a span first
        handler.on_tool_start(
            serialized={"name": "test"},
            input_str="test",
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Trigger an error
        error = Exception("Test error")
        handler.on_tool_error(error, run_id=run_id, parent_run_id=None)

        # Span should be removed from map after error
        assert run_id not in handler._span_map

    def test_on_chain_start(self):
        """Test chain start callback."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()
        serialized = {"name": "MyChain"}
        inputs = {"input": "Hello"}

        handler.on_chain_start(
            serialized=serialized,
            inputs=inputs,
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # A span should have been started
        assert run_id in handler._span_map
        span = handler._span_map[run_id]
        assert span.name == "MyChain"
        assert span.span_type == SpanType.CHAIN
        assert span.inputs == inputs

    def test_on_chain_end(self):
        """Test chain end callback."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()

        # Start a span first
        handler.on_chain_start(
            serialized={"name": "test"},
            inputs={"in": "test"},
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        handler.on_chain_end(
            outputs={"out": "result"},
            run_id=run_id,
            parent_run_id=None,
        )

        # Span should be removed from map
        assert run_id not in handler._span_map

    def test_on_chain_error(self):
        """Test chain error callback."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()

        # Start a span first
        handler.on_chain_start(
            serialized={"name": "test"},
            inputs={"in": "test"},
            run_id=run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Trigger an error
        error = Exception("Test error")
        handler.on_chain_error(error, run_id=run_id, parent_run_id=None)

        # Span should be removed from map after error
        assert run_id not in handler._span_map

    def test_parent_child_relationship(self):
        """Test parent-child span relationship."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        parent_run_id = uuid4()
        child_run_id = uuid4()

        # Start parent
        handler.on_chain_start(
            serialized={"name": "ParentChain"},
            inputs={},
            run_id=parent_run_id,
            parent_run_id=None,
            tags=[],
            metadata={},
        )

        # Start child
        handler.on_llm_start(
            serialized={"name": "ChildLLM"},
            prompts=["Hello"],
            run_id=child_run_id,
            parent_run_id=parent_run_id,
            tags=[],
            metadata={},
        )

        # Both spans should exist
        assert parent_run_id in handler._span_map
        assert child_run_id in handler._span_map

        # Child should have parent_span_id matching parent
        parent_span = handler._span_map[parent_run_id]
        child_span = handler._span_map[child_run_id]
        assert child_span.parent_span_id == parent_span.span_id
        assert child_span.trace_id == parent_span.trace_id

    def test_error_handling_no_span_found(self):
        """Test that errors in callback handler don't break execution."""
        tracer = Tracer()
        handler = PrefactorCallbackHandler(tracer=tracer)

        run_id = uuid4()

        # Try to end a span that doesn't exist - should not raise
        error = Exception("Test error")
        handler.on_llm_error(error, run_id=run_id, parent_run_id=None)
        # No assertion needed - just should not raise
