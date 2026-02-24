"""Tests for LangChain middleware."""

from unittest.mock import Mock

from prefactor_langchain.middleware import PrefactorMiddleware
from prefactor_langchain.schemas import (
    LANGCHAIN_AGENT_SCHEMA,
    LANGCHAIN_LLM_SCHEMA,
    LANGCHAIN_TOOL_SCHEMA,
)
from prefactor_langchain.spans import AgentSpan, LLMSpan, ToolSpan


class TestPrefactorMiddleware:
    """Test PrefactorMiddleware."""

    def test_factory_pattern_basic(self):
        """Test factory pattern with from_config."""
        middleware = PrefactorMiddleware.from_config(
            api_url="http://test",
            api_token="test-token",
            agent_id="test-agent",
        )

        assert middleware is not None
        assert middleware._client is not None
        assert middleware._agent_id == "test-agent"
        assert middleware._agent_name is None
        assert middleware._instance is None
        assert middleware._owns_client is True
        assert middleware._owns_instance is True  # Will lazily create

    def test_factory_pattern_with_agent_name(self):
        """Test factory pattern with agent name."""
        middleware = PrefactorMiddleware.from_config(
            api_url="http://test",
            api_token="test-token",
            agent_id="my-agent",
            agent_name="My Test Agent",
        )

        assert middleware._agent_id == "my-agent"
        assert middleware._agent_name == "My Test Agent"

    def test_configuration_mode(self):
        """Test configuration mode with pre-created (mocked) client."""
        client = Mock()
        client._initialized = True

        middleware = PrefactorMiddleware(
            client=client,
            agent_id="cfg-agent",
            agent_name="Config Agent",
        )

        assert middleware._client is client
        assert middleware._agent_id == "cfg-agent"
        assert middleware._agent_name == "Config Agent"
        assert middleware._owns_client is False  # Caller created the client
        assert middleware._owns_instance is True  # Will lazily create

    def test_pre_configured_instance(self):
        """Test using a pre-configured AgentInstanceHandle."""
        mock_instance = Mock()

        middleware = PrefactorMiddleware(instance=mock_instance)

        assert middleware._instance is mock_instance
        assert middleware._client is None
        assert middleware._owns_instance is False  # Caller owns it
        assert middleware._owns_client is False

    def test_pre_configured_instance_with_client_raises(self):
        """Providing both client and instance should raise ValueError."""
        import pytest

        mock_client = Mock()
        mock_client._initialized = True
        mock_instance = Mock()

        with pytest.raises(ValueError, match="not both"):
            PrefactorMiddleware(client=mock_client, instance=mock_instance)

    def test_no_client_no_instance_raises(self):
        """Providing neither client nor instance should raise ValueError."""
        import pytest

        with pytest.raises(ValueError, match="Either 'client' or 'instance'"):
            PrefactorMiddleware()


class TestMiddlewareMethods:
    """Test middleware internal methods."""

    @property
    def _middleware(self) -> PrefactorMiddleware:
        """Create a middleware backed by a mock instance (no real client needed)."""
        return PrefactorMiddleware(instance=Mock())

    def test_get_name_from_request_with_model(self):
        """Test extracting model name from request."""
        middleware = self._middleware

        request = Mock()
        request.model = Mock()
        request.model.model_name = "gpt-4"

        name = middleware._get_name_from_request(request)
        assert name == "gpt-4"

    def test_get_name_from_request_fallback(self):
        """Test fallback name extraction."""
        middleware = self._middleware

        request = Mock(spec=[])  # No attributes

        name = middleware._get_name_from_request(request)
        assert name == "llm"

    def test_extract_model_inputs_with_messages(self):
        """Test extracting inputs from messages."""
        middleware = self._middleware

        msg = Mock()
        msg.type = "human"
        msg.content = "Hello"
        request = Mock()
        request.messages = [msg]
        request.system_message = None

        inputs = middleware._extract_model_inputs(request)
        assert "messages" in inputs
        assert inputs["messages"] == [{"role": "human", "content": "Hello"}]

    def test_extract_model_inputs_with_prompt(self):
        """Test extracting inputs when messages is falsy."""
        middleware = self._middleware

        request = Mock()
        request.messages = []
        request.system_message = None

        inputs = middleware._extract_model_inputs(request)
        assert "messages" not in inputs

    def test_extract_tool_inputs(self):
        """Test extracting tool inputs."""
        middleware = self._middleware

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

        assert span.status == "failed"
        assert span.error is not None
        assert span.error.error_type == "ValueError"
        assert span.error.message == "Test error message"
        assert span.error.stacktrace is not None

        # Verify serialization includes error
        span_dict = span.to_dict()
        assert span_dict["error"]["error_type"] == "ValueError"
        assert span_dict["error"]["message"] == "Test error message"


class TestSchemaConstants:
    """Test exported schema constants."""

    def test_langchain_agent_schema(self):
        """Test LANGCHAIN_AGENT_SCHEMA is exported."""
        assert LANGCHAIN_AGENT_SCHEMA is not None
        assert LANGCHAIN_AGENT_SCHEMA.get("type") == "object"
        assert "properties" in LANGCHAIN_AGENT_SCHEMA

    def test_langchain_llm_schema(self):
        """Test LANGCHAIN_LLM_SCHEMA is exported."""
        assert LANGCHAIN_LLM_SCHEMA is not None
        assert LANGCHAIN_LLM_SCHEMA.get("type") == "object"
        assert "properties" in LANGCHAIN_LLM_SCHEMA

    def test_langchain_tool_schema(self):
        """Test LANGCHAIN_TOOL_SCHEMA is exported."""
        assert LANGCHAIN_TOOL_SCHEMA is not None
        assert LANGCHAIN_TOOL_SCHEMA.get("type") == "object"
        assert "properties" in LANGCHAIN_TOOL_SCHEMA
