"""LangChain span schemas for Prefactor.

This module provides JSON schemas for the built-in LangChain span types
and a function to register them with a SchemaRegistry.
"""

from typing import Any

LANGCHAIN_AGENT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Name of the agent span",
        },
        "type": {
            "type": "string",
            "const": "langchain:agent",
        },
        "agent_name": {
            "type": "string",
            "description": "Name of the agent instance",
        },
        "inputs": {
            "type": "object",
            "description": "Agent input data (typically messages)",
        },
        "outputs": {
            "type": "object",
            "description": "Agent output data (final messages/results)",
        },
        "status": {
            "type": "string",
            "enum": ["completed", "error"],
        },
        "iteration_count": {
            "type": "integer",
            "description": "Number of agent iterations/steps",
        },
        "error": {
            "type": "object",
            "properties": {
                "error_type": {"type": "string"},
                "message": {"type": "string"},
                "stacktrace": {"type": "string"},
            },
        },
        "metadata": {
            "type": "object",
            "description": "Additional agent metadata",
        },
        "started_at": {
            "type": "string",
            "format": "date-time",
        },
        "finished_at": {
            "type": "string",
            "format": "date-time",
        },
    },
}


LANGCHAIN_LLM_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Name of the LLM call span",
        },
        "type": {
            "type": "string",
            "const": "langchain:llm",
        },
        "model_name": {
            "type": "string",
            "description": "Name of the LLM model (e.g., 'gpt-4')",
        },
        "provider": {
            "type": "string",
            "description": "Provider of the LLM (e.g., 'openai', 'anthropic')",
        },
        "temperature": {
            "type": "number",
            "description": "Temperature setting for the model",
        },
        "inputs": {
            "type": "object",
            "description": "Input data (messages or prompt)",
        },
        "outputs": {
            "type": "object",
            "description": "Output data (model response)",
        },
        "status": {
            "type": "string",
            "enum": ["completed", "error"],
        },
        "error": {
            "type": "object",
            "properties": {
                "error_type": {"type": "string"},
                "message": {"type": "string"},
                "stacktrace": {"type": "string"},
            },
        },
        "token_usage": {
            "type": "object",
            "properties": {
                "prompt_tokens": {"type": "integer"},
                "completion_tokens": {"type": "integer"},
                "total_tokens": {"type": "integer"},
            },
        },
        "metadata": {
            "type": "object",
            "description": "Additional LLM call metadata",
        },
        "started_at": {
            "type": "string",
            "format": "date-time",
        },
        "finished_at": {
            "type": "string",
            "format": "date-time",
        },
    },
}


LANGCHAIN_TOOL_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Name of the tool span",
        },
        "type": {
            "type": "string",
            "const": "langchain:tool",
        },
        "tool_name": {
            "type": "string",
            "description": "Name of the tool that was called",
        },
        "tool_type": {
            "type": "string",
            "description": "Type of tool (e.g., 'function')",
        },
        "tool_schema": {
            "type": "object",
            "description": "JSON schema of the tool's parameters",
        },
        "inputs": {
            "type": "object",
            "description": "Tool input arguments",
        },
        "outputs": {
            "type": "object",
            "description": "Tool output data",
        },
        "status": {
            "type": "string",
            "enum": ["completed", "error"],
        },
        "error": {
            "type": "object",
            "properties": {
                "error_type": {"type": "string"},
                "message": {"type": "string"},
                "stacktrace": {"type": "string"},
            },
        },
        "metadata": {
            "type": "object",
            "description": "Additional tool execution metadata",
        },
        "started_at": {
            "type": "string",
            "format": "date-time",
        },
        "finished_at": {
            "type": "string",
            "format": "date-time",
        },
    },
}


def register_langchain_schemas(registry: Any) -> None:
    """Register all LangChain span schemas with a schema registry.

    This function registers the built-in schemas for LangChain-specific
    span types (agent, llm, tool) so they can be used with Prefactor
    agent instances.

    Args:
        registry: The SchemaRegistry to register schemas with.

    Example:
        from prefactor_core import SchemaRegistry
        from prefactor_langchain.schemas import register_langchain_schemas

        registry = SchemaRegistry()
        register_langchain_schemas(registry)

        # Now the registry has langchain:agent, langchain:llm, langchain:tool
        assert registry.has_schema("langchain:llm")
    """
    registry.register("langchain:agent", LANGCHAIN_AGENT_SCHEMA)
    registry.register("langchain:llm", LANGCHAIN_LLM_SCHEMA)
    registry.register("langchain:tool", LANGCHAIN_TOOL_SCHEMA)


__all__ = [
    "LANGCHAIN_AGENT_SCHEMA",
    "LANGCHAIN_LLM_SCHEMA",
    "LANGCHAIN_TOOL_SCHEMA",
    "register_langchain_schemas",
]
