"""Tests for LangChain middleware."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from prefactor_core import AgentInstanceHandle, PrefactorCoreConfig, SchemaRegistry
from prefactor_http.config import HttpClientConfig
from prefactor_langchain.middleware import PrefactorMiddleware
from prefactor_langchain.schemas import (
    LANGCHAIN_AGENT_SCHEMA,
    LANGCHAIN_LLM_SCHEMA,
    LANGCHAIN_TOOL_SCHEMA,
    LangChainToolSchemaConfig,
)
from prefactor_langchain.spans import AgentSpan, LLMSpan, ToolSpan


class RecordingSpanContext:
    """Async context manager that records span payloads."""

    def __init__(self, call: dict[str, object]):
        self._call = call

    async def __aenter__(self) -> "RecordingSpanContext":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def start(self, payload: dict[str, object]) -> None:
        self._call["start_payload"] = payload

    async def complete(self, result_payload: dict[str, object]) -> None:
        self._call["result_payload"] = result_payload

    async def fail(self, result_payload: dict[str, object]) -> None:
        self._call["failed_payload"] = result_payload


class RecordingInstance:
    """Minimal AgentInstanceHandle stand-in for middleware tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def span(self, schema_name: str, parent_span_id=None, payload=None):
        call = {
            "schema_name": schema_name,
            "parent_span_id": parent_span_id,
            "payload": payload,
        }
        self.calls.append(call)
        return RecordingSpanContext(call)


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

    def test_factory_pattern_with_tool_schemas(self):
        """from_config() should register tool schemas and store span mappings."""
        middleware = PrefactorMiddleware.from_config(
            api_url="http://test",
            api_token="test-token",
            tool_schemas={
                "send_email": LangChainToolSchemaConfig(
                    span_type="send-email",
                    input_schema={
                        "type": "object",
                        "properties": {"to": {"type": "string"}},
                    },
                )
            },
        )

        assert middleware._tool_span_types == {
            "send_email": "langchain:tool:send-email"
        }
        assert middleware._client is not None
        schema_version = (
            middleware._client._config.schema_registry.to_agent_schema_version(
                "schema-v1"
            )
        )
        registered_names = {
            item["name"] for item in schema_version.get("span_type_schemas", [])
        }
        assert "langchain:tool:send-email" in registered_names

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

    def test_factory_pattern_without_tool_schemas_keeps_default_registration(self):
        """Default registration should not add tool-specific span types."""
        middleware = PrefactorMiddleware.from_config(
            api_url="http://test",
            api_token="test-token",
        )

        assert middleware._client is not None
        schema_version = (
            middleware._client._config.schema_registry.to_agent_schema_version(
                "schema-v1"
            )
        )
        registered_names = [
            item["name"] for item in schema_version.get("span_type_schemas", [])
        ]
        assert registered_names == [
            "langchain:agent",
            "langchain:llm",
            "langchain:tool",
        ]


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

    def test_extract_tool_inputs_falls_back_to_named_request(self):
        """Tool extraction should support request shapes without tool_call."""
        middleware = self._middleware

        request = SimpleNamespace(name="calculator", input={"x": 1})

        inputs = middleware._extract_tool_inputs(request)
        assert inputs == {
            "tool_name": "calculator",
            "arguments": {"x": 1},
        }


class TestToolSchemaRuntimeBehavior:
    """Tests for runtime selection of tool-specific span types."""

    def test_client_mode_registers_tool_schemas_and_uses_mapped_span_type(self):
        """client= mode should augment the registry and emit tool-specific spans."""
        client = Mock()
        client._initialized = True
        client._config = PrefactorCoreConfig(
            http_config=HttpClientConfig(api_url="http://test", api_token="token"),
            schema_registry=SchemaRegistry(),
        )

        middleware = PrefactorMiddleware(
            client=client,
            tool_schemas={
                "send_email": LangChainToolSchemaConfig(
                    span_type="send-email",
                    input_schema={
                        "type": "object",
                        "properties": {"to": {"type": "string"}},
                    },
                )
            },
        )
        instance = RecordingInstance()
        middleware._instance = cast(AgentInstanceHandle, instance)

        async def handler(_request):
            return {"output": "queued"}

        request = Mock()
        request.tool_call = {"name": "send_email", "args": {"to": "dev@example.com"}}
        response = asyncio.run(middleware.awrap_tool_call(request, handler))

        assert response == {"output": "queued"}
        assert middleware._tool_span_types == {
            "send_email": "langchain:tool:send-email"
        }
        assert client._config.schema_registry.has_schema("langchain:tool:send-email")
        assert instance.calls[0]["schema_name"] == "langchain:tool:send-email"
        assert instance.calls[0]["start_payload"] == {
            "tool_name": "send_email",
            "inputs": {"to": "dev@example.com"},
        }

    def test_instance_mode_uses_tool_specific_span_type(self):
        """instance= mode should resolve the configured tool span type at runtime."""
        instance = RecordingInstance()
        middleware = PrefactorMiddleware(
            instance=instance,
            tool_schemas={
                "send_email": LangChainToolSchemaConfig(
                    span_type="send-email",
                    input_schema={"type": "object"},
                )
            },
        )

        async def handler(_request):
            return {"output": "queued"}

        request = Mock()
        request.tool_call = {"name": "send_email", "args": {"to": "dev@example.com"}}
        asyncio.run(middleware.awrap_tool_call(request, handler))

        assert instance.calls[0]["schema_name"] == "langchain:tool:send-email"
        assert instance.calls[0]["start_payload"] == {
            "tool_name": "send_email",
            "inputs": {"to": "dev@example.com"},
        }

    def test_tool_specific_spans_preserve_empty_argument_objects(self):
        """Tool-specific spans should emit empty args as an empty inputs object."""
        instance = RecordingInstance()
        middleware = PrefactorMiddleware(
            instance=instance,
            tool_schemas={
                "get_current_date": LangChainToolSchemaConfig(
                    span_type="get-current-date",
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                )
            },
        )

        async def handler(_request):
            return {"output": "queued"}

        request = Mock()
        request.tool_call = {"name": "get_current_date", "args": {}}
        asyncio.run(middleware.awrap_tool_call(request, handler))

        assert instance.calls[0]["schema_name"] == "langchain:tool:get-current-date"
        assert instance.calls[0]["start_payload"] == {
            "tool_name": "get_current_date",
            "inputs": {},
        }

    def test_unknown_tools_fall_back_to_generic_langchain_tool_schema(self):
        """Unknown tools should continue to emit the generic langchain:tool span."""
        instance = RecordingInstance()
        middleware = PrefactorMiddleware(
            instance=instance,
            tool_schemas={
                "send_email": LangChainToolSchemaConfig(
                    span_type="send-email",
                    input_schema={"type": "object"},
                )
            },
        )

        async def handler(_request):
            return {"output": "ok"}

        request = Mock()
        request.tool_call = {"name": "lookup_customer", "args": {"id": "cust_123"}}
        asyncio.run(middleware.awrap_tool_call(request, handler))

        assert instance.calls[0]["schema_name"] == "langchain:tool"
        assert instance.calls[0]["start_payload"] == {
            "tool_name": "lookup_customer",
            "inputs": {
                "tool_name": "lookup_customer",
                "arguments": {"id": "cust_123"},
            },
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
