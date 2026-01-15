"""Basic integration tests with LangChain."""

import json
from io import StringIO
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

import prefactor_sdk
from prefactor_sdk import init_callback


class TestLangChainIntegration:
    """Test integration with LangChain (Callback API)."""

    def setup_method(self):
        """Reset global state before each test."""
        prefactor_sdk._global_tracer = None
        prefactor_sdk._global_handler = None
        prefactor_sdk._global_middleware = None

    def test_init_returns_handler(self):
        """Test that init_callback() returns a callback handler."""
        handler = init_callback()
        assert handler is not None
        assert hasattr(handler, "on_llm_start")
        assert hasattr(handler, "on_llm_end")

    @patch("sys.stdout", new_callable=StringIO)
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_llm_call_with_handler(self, mock_stdout):
        """Test that LLM calls are traced."""
        handler = init_callback()

        # Mock the OpenAI client
        with patch("langchain_openai.ChatOpenAI._generate") as mock_generate:
            # Create a mock response
            from langchain_core.messages import AIMessage
            from langchain_core.outputs import ChatGeneration, ChatResult

            mock_message = AIMessage(content="Hello! How can I help you?")

            mock_generation = ChatGeneration(message=mock_message)
            mock_result = ChatResult(
                generations=[mock_generation],
                llm_output={
                    "token_usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 8,
                        "total_tokens": 18,
                    }
                },
            )
            mock_generate.return_value = mock_result

            # Create LLM with callback
            llm = ChatOpenAI(name="gpt-4", callbacks=[handler])

            # Make a call
            llm.invoke([HumanMessage(content="Hi!")])

        # Check that spans were emitted
        output = mock_stdout.getvalue()
        lines = output.strip().split("\n")

        # Should have at least one span
        assert len(lines) >= 1

        # Parse the JSON and verify span structure
        for line in lines:
            if line:
                span_data = json.loads(line)
                assert "span_id" in span_data
                assert "trace_id" in span_data
                assert "span_type" in span_data
                assert "status" in span_data

    @patch("sys.stdout", new_callable=StringIO)
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_multiple_llm_calls(self, mock_stdout):
        """Test tracing multiple LLM calls."""
        handler = init_callback()

        with patch("langchain_openai.ChatOpenAI._generate") as mock_generate:
            from langchain_core.messages import AIMessage
            from langchain_core.outputs import ChatGeneration, ChatResult

            mock_message = AIMessage(content="Response")

            mock_result = ChatResult(
                generations=[ChatGeneration(message=mock_message)],
                llm_output={
                    "token_usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 5,
                        "total_tokens": 10,
                    }
                },
            )
            mock_generate.return_value = mock_result

            llm = ChatOpenAI(name="gpt-4", callbacks=[handler])

            # Make multiple calls
            llm.invoke([HumanMessage(content="First")])
            llm.invoke([HumanMessage(content="Second")])
            llm.invoke([HumanMessage(content="Third")])

        # Check output
        output = mock_stdout.getvalue()
        lines = [line for line in output.strip().split("\n") if line]

        # Should have 3 spans
        assert len(lines) == 3

        # Each should be a valid span
        for line in lines:
            span_data = json.loads(line)
            assert span_data["span_type"] == "llm"
            assert span_data["status"] == "success"

    @patch("sys.stdout", new_callable=StringIO)
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_llm_error_tracking(self, mock_stdout):
        """Test that LLM errors are tracked."""
        handler = init_callback()

        with patch("langchain_openai.ChatOpenAI._generate") as mock_generate:
            # Make the LLM call raise an error
            mock_generate.side_effect = ValueError("API error")

            llm = ChatOpenAI(name="gpt-4", callbacks=[handler])

            # Make a call that will error
            with pytest.raises(ValueError):
                llm.invoke([HumanMessage(content="Hi!")])

        # Check output
        output = mock_stdout.getvalue()
        lines = [line for line in output.strip().split("\n") if line]

        # Should have 1 span with error
        assert len(lines) == 1

        span_data = json.loads(lines[0])
        assert span_data["status"] == "error"
        assert span_data["error"] is not None
        assert span_data["error"]["error_type"] == "ValueError"

    def test_handler_reuse(self):
        """Test that the same handler is reused across multiple inits."""
        handler1 = init_callback()
        handler2 = init_callback()

        assert handler1 is handler2


class TestTokenUsageTracking:
    """Test token usage tracking."""

    def setup_method(self):
        """Reset global state before each test."""
        prefactor_sdk._global_tracer = None
        prefactor_sdk._global_handler = None

    @patch("sys.stdout", new_callable=StringIO)
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_token_usage_captured(self, mock_stdout):
        """Test that token usage is captured."""
        handler = init_callback()

        with patch("langchain_openai.ChatOpenAI._generate") as mock_generate:
            from langchain_core.messages import AIMessage
            from langchain_core.outputs import ChatGeneration, ChatResult

            mock_message = AIMessage(content="Response")

            mock_result = ChatResult(
                generations=[ChatGeneration(message=mock_message)],
                llm_output={
                    "token_usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 200,
                        "total_tokens": 300,
                    }
                },
            )
            mock_generate.return_value = mock_result

            llm = ChatOpenAI(name="gpt-4", callbacks=[handler])
            llm.invoke([HumanMessage(content="Test")])

        # Check output
        output = mock_stdout.getvalue()
        lines = [line for line in output.strip().split("\n") if line]

        span_data = json.loads(lines[0])
        assert span_data["token_usage"] is not None
        assert span_data["token_usage"]["prompt_tokens"] == 100
        assert span_data["token_usage"]["completion_tokens"] == 200
        assert span_data["token_usage"]["total_tokens"] == 300
