"""LangChain span schemas for Prefactor.

This module provides JSON schemas for the built-in LangChain span types,
helpers for compiling per-tool span schemas, and registration helpers for
loading those schemas into a ``SchemaRegistry``.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

LANGCHAIN_AGENT_PARAMS_SCHEMA: dict[str, Any] = {
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

LANGCHAIN_AGENT_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "outputs": {
            "type": "object",
            "description": "Agent output data (final messages/results)",
        },
        "status": {
            "type": "string",
            "enum": ["completed", "error"],
        },
    },
}

LANGCHAIN_LLM_PARAMS_SCHEMA: dict[str, Any] = {
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

LANGCHAIN_LLM_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "outputs": {
            "type": "object",
            "description": "Output data (model response)",
        },
        "token_usage": {
            "type": "object",
            "properties": {
                "prompt_tokens": {"type": "integer"},
                "completion_tokens": {"type": "integer"},
                "total_tokens": {"type": "integer"},
            },
        },
        "status": {
            "type": "string",
            "enum": ["completed", "error"],
        },
    },
}

LANGCHAIN_TOOL_PARAMS_SCHEMA: dict[str, Any] = {
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

LANGCHAIN_TOOL_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "outputs": {
            "type": "object",
            "description": "Tool output data",
        },
        "status": {
            "type": "string",
            "enum": ["completed", "error"],
        },
    },
}

DEFAULT_LANGCHAIN_AGENT_SCHEMA: dict[str, Any] = {
    "external_identifier": "langchain-schema",
    "span_schemas": {
        "langchain:agent": deepcopy(LANGCHAIN_AGENT_PARAMS_SCHEMA),
        "langchain:llm": deepcopy(LANGCHAIN_LLM_PARAMS_SCHEMA),
        "langchain:tool": deepcopy(LANGCHAIN_TOOL_PARAMS_SCHEMA),
    },
    "span_result_schemas": {
        "langchain:agent": deepcopy(LANGCHAIN_AGENT_RESULT_SCHEMA),
        "langchain:llm": deepcopy(LANGCHAIN_LLM_RESULT_SCHEMA),
        "langchain:tool": deepcopy(LANGCHAIN_TOOL_RESULT_SCHEMA),
    },
}

GENERIC_OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
}


@dataclass(frozen=True)
class LangChainToolSchemaConfig:
    """Configuration for a tool-specific LangChain span schema.

    Attributes:
        span_type: Tool-specific span type suffix or full span type. Values are
            normalized to ``langchain:tool:<suffix>``.
        input_schema: JSON schema for the tool arguments stored in ``inputs`` for
            tool-specific spans.
    """

    span_type: str
    input_schema: dict[str, Any]


ToolSchemaMapping = Mapping[
    str, LangChainToolSchemaConfig | Mapping[str, Any]
]


# Legacy aliases for backwards compatibility
LANGCHAIN_AGENT_SCHEMA = LANGCHAIN_AGENT_PARAMS_SCHEMA
LANGCHAIN_LLM_SCHEMA = LANGCHAIN_LLM_PARAMS_SCHEMA
LANGCHAIN_TOOL_SCHEMA = LANGCHAIN_TOOL_PARAMS_SCHEMA


def compile_langchain_agent_schema(
    agent_schema: Mapping[str, Any] | None = None,
    *,
    tool_schemas: ToolSchemaMapping | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Compile a LangChain agent schema with optional tool-specific span types.

    Args:
        agent_schema: Optional base agent schema to merge with the built-in
            LangChain span schemas.
        tool_schemas: Optional Python-first per-tool schema configuration.

    Returns:
        A tuple of ``(compiled_agent_schema, tool_span_types)`` where
        ``tool_span_types`` maps tool names to normalized span types.
    """
    base_schema = _merge_with_default_agent_schema(agent_schema)
    normalized_tool_schemas = _normalize_tool_schemas(agent_schema, tool_schemas)
    if not normalized_tool_schemas:
        return base_schema, {}

    span_schemas = _clone_record(base_schema.get("span_schemas"))
    span_result_schemas = _clone_record(base_schema.get("span_result_schemas"))

    for tool_name, config in normalized_tool_schemas.items():
        span_type = config.span_type
        if span_type not in span_schemas:
            span_schemas[span_type] = _build_tool_params_schema(
                span_type, config.input_schema
            )
        if span_type not in span_result_schemas:
            span_result_schemas[span_type] = deepcopy(GENERIC_OBJECT_SCHEMA)

    compiled_schema = {
        **base_schema,
        "span_schemas": span_schemas,
        "span_result_schemas": span_result_schemas,
    }

    tool_span_types = {
        tool_name: config.span_type
        for tool_name, config in normalized_tool_schemas.items()
    }
    return compiled_schema, tool_span_types


def register_langchain_schemas(
    registry: Any,
    *,
    agent_schema: Mapping[str, Any] | None = None,
    tool_schemas: ToolSchemaMapping | None = None,
) -> dict[str, str]:
    """Register all LangChain span schemas with a schema registry.

    Registers the built-in schemas for LangChain-specific span types
    (agent, llm, tool) using the full ``span_type_schemas`` form, which
    includes params schemas, result schemas, titles, and descriptions. When
    tool schemas are configured, this also registers per-tool span types.

    Args:
        registry: The SchemaRegistry to register schemas with.
        agent_schema: Optional base agent schema that may include embedded
            ``toolSchemas`` or ``tool_schemas`` config.
        tool_schemas: Optional Python-first per-tool schema configuration.

    Example:
        from prefactor_core import SchemaRegistry
        from prefactor_langchain.schemas import register_langchain_schemas

        registry = SchemaRegistry()
        register_langchain_schemas(registry)

        # Now the registry has langchain:agent, langchain:llm, langchain:tool
        assert registry.has_schema("langchain:llm")
    """
    compiled_schema, tool_span_types = compile_langchain_agent_schema(
        agent_schema=agent_schema,
        tool_schemas=tool_schemas,
    )

    _register_type_if_missing(
        registry,
        name="langchain:agent",
        params_schema=LANGCHAIN_AGENT_PARAMS_SCHEMA,
        result_schema=LANGCHAIN_AGENT_RESULT_SCHEMA,
        title="LangChain Agent",
        description="A LangChain agent execution span",
    )
    _register_type_if_missing(
        registry,
        name="langchain:llm",
        params_schema=LANGCHAIN_LLM_PARAMS_SCHEMA,
        result_schema=LANGCHAIN_LLM_RESULT_SCHEMA,
        title="LLM Call",
        description="A call to a language model",
        template="{{model_name}}",
    )
    _register_type_if_missing(
        registry,
        name="langchain:tool",
        params_schema=LANGCHAIN_TOOL_PARAMS_SCHEMA,
        result_schema=LANGCHAIN_TOOL_RESULT_SCHEMA,
        title="Tool Call",
        description="A LangChain tool execution span",
        template="{{tool_name}}",
    )

    for tool_name, span_type in tool_span_types.items():
        _register_type_if_missing(
            registry,
            name=span_type,
            params_schema=compiled_schema["span_schemas"][span_type],
            result_schema=compiled_schema["span_result_schemas"][span_type],
            title=f"Tool Call: {tool_name}",
            description=f"A LangChain tool execution span for {tool_name}",
            template="{{tool_name}}",
            reject_if_conflicting=True,
        )

    return tool_span_types


def _register_type_if_missing(
    registry: Any,
    *,
    name: str,
    params_schema: dict[str, Any],
    result_schema: dict[str, Any] | None = None,
    title: str | None = None,
    description: str | None = None,
    template: str | None = None,
    reject_if_conflicting: bool = False,
) -> None:
    """Register a span type if the target name is not already present."""
    if hasattr(registry, "has_schema") and registry.has_schema(name):
        if reject_if_conflicting:
            existing = _get_registered_type_schema(registry, name)
            if existing is None:
                raise ValueError(
                    f"Schema '{name}' is already registered but could not be read "
                    "back for compatibility checks."
                )
            if not _registered_schema_matches(
                existing,
                params_schema=params_schema,
                result_schema=result_schema,
            ):
                raise ValueError(
                    f"Schema '{name}' is already registered with a different "
                    "params_schema or result_schema."
                )
        return

    registry.register_type(
        name=name,
        params_schema=deepcopy(params_schema),
        result_schema=deepcopy(result_schema) if result_schema is not None else None,
        title=title,
        description=description,
        template=template,
    )


def _get_registered_type_schema(registry: Any, name: str) -> dict[str, Any] | None:
    """Read a registered schema back from a registry for compatibility checks."""
    if not hasattr(registry, "to_agent_schema_version"):
        return None

    schema_version = registry.to_agent_schema_version("__prefactor_registry_check__")
    for entry in schema_version.get("span_type_schemas", []):
        if entry.get("name") == name:
            return {
                "params_schema": entry.get("params_schema"),
                "result_schema": entry.get("result_schema"),
            }

    span_schemas = schema_version.get("span_schemas", {})
    span_result_schemas = schema_version.get("span_result_schemas", {})
    if name in span_schemas or name in span_result_schemas:
        return {
            "params_schema": span_schemas.get(name),
            "result_schema": span_result_schemas.get(name),
        }
    return None


def _registered_schema_matches(
    existing: Mapping[str, Any],
    *,
    params_schema: dict[str, Any],
    result_schema: dict[str, Any] | None,
) -> bool:
    """Return True when an existing registry entry matches the requested schema."""
    return (
        existing.get("params_schema") == params_schema
        and existing.get("result_schema") == result_schema
    )


def _clone_record(value: Any) -> dict[str, Any]:
    """Clone a mapping-like value into a plain dictionary."""
    if not isinstance(value, Mapping):
        return {}
    return {key: deepcopy(item) for key, item in value.items()}


def _merge_with_default_agent_schema(
    agent_schema: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merge a user-provided agent schema into the LangChain defaults."""
    base_schema = _strip_tool_schema_fields(agent_schema)
    if not base_schema:
        return deepcopy(DEFAULT_LANGCHAIN_AGENT_SCHEMA)

    return {
        **deepcopy(DEFAULT_LANGCHAIN_AGENT_SCHEMA),
        **dict(base_schema),
        "span_schemas": {
            **_clone_record(DEFAULT_LANGCHAIN_AGENT_SCHEMA.get("span_schemas")),
            **_clone_record(base_schema.get("span_schemas")),
        },
        "span_result_schemas": {
            **_clone_record(DEFAULT_LANGCHAIN_AGENT_SCHEMA.get("span_result_schemas")),
            **_clone_record(base_schema.get("span_result_schemas")),
        },
    }


def _strip_tool_schema_fields(
    agent_schema: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Remove embedded tool schema configuration from an agent schema dict."""
    if not isinstance(agent_schema, Mapping):
        return None

    result = dict(agent_schema)
    result.pop("toolSchemas", None)
    result.pop("tool_schemas", None)
    return result


def _normalize_tool_schemas(
    agent_schema: Mapping[str, Any] | None,
    tool_schemas: ToolSchemaMapping | None,
) -> dict[str, LangChainToolSchemaConfig]:
    """Parse and normalize tool schema config from all supported inputs."""
    merged_raw_tool_schemas: dict[str, Any] = {}
    for source in (_get_embedded_tool_schemas(agent_schema), tool_schemas):
        if source is None:
            continue
        if not isinstance(source, Mapping):
            raise ValueError(
                "Invalid tool_schemas: expected an object keyed by tool name."
            )
        merged_raw_tool_schemas.update(dict(source))

    if not merged_raw_tool_schemas:
        return {}

    normalized: dict[str, LangChainToolSchemaConfig] = {}
    tool_by_span_type: dict[str, str] = {}
    for tool_name, raw_config in merged_raw_tool_schemas.items():
        config = _parse_tool_schema_config(tool_name, raw_config)
        normalized_span_type = _normalize_unique_tool_span_type(
            tool_name,
            config.span_type,
            tool_by_span_type,
        )
        normalized[tool_name] = LangChainToolSchemaConfig(
            span_type=normalized_span_type,
            input_schema=deepcopy(config.input_schema),
        )

    return normalized


def _get_embedded_tool_schemas(
    agent_schema: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Extract embedded tool schema config from an agent schema dict."""
    if agent_schema is None:
        return None
    if not isinstance(agent_schema, Mapping):
        raise ValueError("Invalid agent_schema: expected a mapping.")

    for key in ("toolSchemas", "tool_schemas"):
        raw_tool_schemas = agent_schema.get(key)
        if raw_tool_schemas is not None:
            if not isinstance(raw_tool_schemas, Mapping):
                raise ValueError(
                    f"Invalid agent_schema.{key}: expected an object keyed by "
                    "tool name."
                )
            return raw_tool_schemas
    return None


def _parse_tool_schema_config(
    tool_name: str,
    raw_config: LangChainToolSchemaConfig | Mapping[str, Any],
) -> LangChainToolSchemaConfig:
    """Parse a single tool schema config into the normalized dataclass form."""
    if isinstance(raw_config, LangChainToolSchemaConfig):
        span_type = raw_config.span_type
        input_schema = raw_config.input_schema
    elif isinstance(raw_config, Mapping):
        span_type = raw_config.get("span_type", raw_config.get("spanType"))
        input_schema = raw_config.get("input_schema", raw_config.get("inputSchema"))
    else:
        raise ValueError(
            f"Invalid tool_schemas.{tool_name}: expected an object with "
            "span_type and input_schema."
        )

    if not isinstance(span_type, str):
        raise ValueError(
            f"Invalid tool_schemas.{tool_name}.span_type: expected a non-empty string."
        )
    if not isinstance(input_schema, Mapping):
        raise ValueError(
            f"Invalid tool_schemas.{tool_name}.input_schema: expected an object."
        )

    return LangChainToolSchemaConfig(
        span_type=span_type,
        input_schema=dict(input_schema),
    )


def _normalize_unique_tool_span_type(
    tool_name: str,
    span_type: str,
    tool_by_span_type: dict[str, str],
) -> str:
    """Normalize a span type and reject collisions across tools."""
    normalized_span_type = _normalize_tool_span_type(span_type, tool_name)
    conflicting_tool = tool_by_span_type.get(normalized_span_type)
    if conflicting_tool and conflicting_tool != tool_name:
        raise ValueError(
            f"Invalid tool_schemas.{tool_name}.span_type: normalized span type "
            f'"{normalized_span_type}" conflicts with "{conflicting_tool}".'
        )

    tool_by_span_type[normalized_span_type] = tool_name
    return normalized_span_type


def _normalize_tool_span_type(span_type: str, tool_name: str) -> str:
    """Normalize a tool span type into the ``langchain:tool:<suffix>`` form."""
    trimmed_span_type = span_type.strip()
    if not trimmed_span_type:
        raise ValueError(
            f"Invalid tool_schemas.{tool_name}.span_type: expected a non-empty string."
        )

    provider_tool_prefix = "langchain:tool:"
    if trimmed_span_type.startswith(provider_tool_prefix):
        suffix = trimmed_span_type[len(provider_tool_prefix) :].lstrip(":")
    else:
        suffix = trimmed_span_type
        if suffix.startswith("langchain:"):
            suffix = suffix[len("langchain:") :]
        if suffix.startswith("tool:"):
            suffix = suffix[len("tool:") :]
        suffix = suffix.lstrip(":")

    if not suffix:
        raise ValueError(
            f"Invalid tool_schemas.{tool_name}.span_type: expected a non-empty "
            "suffix after normalization."
        )

    return f"langchain:tool:{suffix}"


def _build_tool_params_schema(
    span_type: str,
    input_schema: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a tool params schema for a tool-specific span type."""
    schema = deepcopy(LANGCHAIN_TOOL_PARAMS_SCHEMA)
    schema["properties"]["type"]["const"] = span_type
    schema["properties"]["inputs"] = deepcopy(dict(input_schema))
    return schema


__all__ = [
    "DEFAULT_LANGCHAIN_AGENT_SCHEMA",
    "GENERIC_OBJECT_SCHEMA",
    "LANGCHAIN_AGENT_PARAMS_SCHEMA",
    "LANGCHAIN_AGENT_RESULT_SCHEMA",
    "LANGCHAIN_LLM_PARAMS_SCHEMA",
    "LANGCHAIN_LLM_RESULT_SCHEMA",
    "LANGCHAIN_TOOL_PARAMS_SCHEMA",
    "LANGCHAIN_TOOL_RESULT_SCHEMA",
    "LangChainToolSchemaConfig",
    # Legacy aliases
    "LANGCHAIN_AGENT_SCHEMA",
    "LANGCHAIN_LLM_SCHEMA",
    "LANGCHAIN_TOOL_SCHEMA",
    "compile_langchain_agent_schema",
    "register_langchain_schemas",
]
