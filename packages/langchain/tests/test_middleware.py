"""Tests for LangChain middleware."""

from unittest.mock import Mock

from prefactor_langchain.middleware import PrefactorMiddleware
from prefactor_langchain.spans import AgentSpan, LLMSpan, ToolSpan


class TestPrefactorMiddleware:
    """Test PrefactorMiddleware."""

    def test_init(self):
        """Test initializing the middleware."""
        middleware = PrefactorMiddleware(
            api_url="http://test",
            api_token="test-token",
            agent_id="test-agent",
        )

        assert middleware is not None
        assert middleware._api_url == "http://test"
        assert middleware._api_token == "test-token"
        assert middleware._agent_id == "test-agent"
        assert middleware._client is None
        assert middleware._instance is None
        assert middleware._initialized is False

    def test_init_with_defaults(self):
        """Test initializing with default agent_id."""
        middleware = PrefactorMiddleware(
            api_url="http://test",
            api_token="test-token",
        )

        assert middleware._agent_id == "langchain-agent"

    def test_get_name_from_request_with_metadata(self):
        """Test extracting name from request metadata."""
        middleware = PrefactorMiddleware(
            api_url="http://test",
            api_token="test-token",
        )

        request = Mock()
        request.metadata = {"name": "custom-name"}

        name = middleware._get_name_from_request(request)
        assert name == "custom-name"

    def test_get_name_from_request_with_model(self):
        """Test extracting name from model."""
        middleware = PrefactorMiddleware(
            api_url="http://test",
            api_token="test-token",
        )

        request = Mock()
        request.metadata = {}
        request.model = Mock()
        request.model.model_name = "gpt-4"

        name = middleware._get_name_from_request(request)
        assert name == "model:gpt-4"

    def test_get_name_from_request_fallback(self):
        """Test fallback name extraction."""
        middleware = PrefactorMiddleware(
            api_url="http://test",
            api_token="test-token",
        )

        request = Mock(spec=[])  # No attributes

        name = middleware._get_name_from_request(request)
        assert name == "model_call"

    def test_extract_model_inputs_with_messages(self):
        """Test extracting inputs from messages."""
        middleware = PrefactorMiddleware(
            api_url="http://test",
            api_token="test-token",
        )

        request = Mock()
        request.messages = ["msg1", "msg2", "msg3", "msg4"]

        inputs = middleware._extract_model_inputs(request)
        # Should only include last 3 messages
        assert inputs == {"messages": ["msg2", "msg3", "msg4"]}

    def test_extract_model_inputs_with_prompt(self):
        """Test extracting inputs from prompt."""
        middleware = PrefactorMiddleware(
            api_url="http://test",
            api_token="test-token",
        )

        request = Mock()
        request.messages = None
        request.prompt = "Hello world"

        inputs = middleware._extract_model_inputs(request)
        assert inputs == {"prompt": "Hello world"}

    def test_extract_tool_inputs(self):
        """Test extracting tool inputs."""
        middleware = PrefactorMiddleware(
            api_url="http://test",
            api_token="test-token",
        )

        request = Mock()
        request.tool_call = {"name": "calculator", "args": {"x": 1}}

        inputs = middleware._extract_tool_inputs(request)
        assert inputs == {
            "tool_name": "calculator",
            "arguments": {"x": 1},
        }


class TestSpanSerialization:
    """Test span serialization for payloads."""

    def test_llm_span_serialization(self):
        """Test that LLM spans serialize correctly for payload."""
        span = LLMSpan(
            name="test-llm",
            model_name="gpt-4",
            provider="openai",
            temperature=0.7,
        )
        span.complete(outputs={"response": "Hello!"})

        span_dict = span.to_dict()

        assert span_dict["name"] == "test-llm"
        assert span_dict["type"] == "langchain:llm"
        assert span_dict["model_name"] == "gpt-4"
        assert span_dict["provider"] == "openai"
        assert span_dict["temperature"] == 0.7
        assert span_dict["status"] == "completed"

    def test_tool_span_serialization(self):
        """Test that tool spans serialize correctly for payload."""
        span = ToolSpan(
            name="calculator",
            tool_name="calculator",
            tool_type="function",
            arguments={"expression": "2+2"},
        )
        span.complete(outputs={"output": "4"})

        span_dict = span.to_dict()

        assert span_dict["name"] == "calculator"
        assert span_dict["type"] == "langchain:tool"
        assert span_dict["tool_name"] == "calculator"
        assert span_dict["tool_type"] == "function"
        assert span_dict["arguments"] == {"expression": "2+2"}
        assert span_dict["status"] == "completed"

    def test_agent_span_serialization(self):
        """Test that agent spans serialize correctly for payload."""
        span = AgentSpan(
            name="my-agent",
            agent_name="TestAgent",
            iteration_count=3,
        )
        span.complete(outputs={"result": "done"})

        span_dict = span.to_dict()

        assert span_dict["name"] == "my-agent"
        assert span_dict["type"] == "langchain:agent"
        assert span_dict["agent_name"] == "TestAgent"
        assert span_dict["iteration_count"] == 3
        assert span_dict["status"] == "completed"

    def test_span_fail_captures_error(self):
        """Test that span.fail() captures error information."""
        span = LLMSpan(name="test")

        try:
            raise ValueError("Test error message")
        except ValueError as e:
            span.fail(e)

        assert span.status == "error"
        assert span.error is not None
        assert span.error.error_type == "ValueError"
        assert span.error.message == "Test error message"
        assert span.error.stacktrace is not None

        # Verify serialization includes error
        span_dict = span.to_dict()
        assert span_dict["error"]["error_type"] == "ValueError"
        assert span_dict["error"]["message"] == "Test error message"
