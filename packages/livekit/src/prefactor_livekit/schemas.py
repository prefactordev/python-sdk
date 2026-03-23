"""LiveKit span schemas for Prefactor."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from prefactor_core import SchemaRegistry

GENERIC_OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
}


LIVEKIT_SESSION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "const": "livekit:session"},
        "agent_name": {"type": "string"},
        "session_class": {"type": "string"},
        "agent_class": {"type": "string"},
        "metadata": GENERIC_OBJECT_SCHEMA,
        "started_at": {"type": "number"},
        "finished_at": {"type": "number"},
    },
}

LIVEKIT_SESSION_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["completed", "failed", "cancelled"],
        },
        "usage": GENERIC_OBJECT_SCHEMA,
        "conversation": GENERIC_OBJECT_SCHEMA,
        "error": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_USER_TURN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "const": "livekit:user_turn"},
        "transcript": {"type": "string"},
        "speaker_id": {"type": "string"},
        "language": {"type": "string"},
        "is_final": {"type": "boolean"},
        "created_at": {"type": "number"},
        "metadata": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_USER_TURN_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed", "failed"]},
        "metadata": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_ASSISTANT_TURN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "const": "livekit:assistant_turn"},
        "source": {"type": "string"},
        "user_initiated": {"type": "boolean"},
        "created_at": {"type": "number"},
        "metadata": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_ASSISTANT_TURN_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["completed", "failed", "cancelled"],
        },
        "outputs": GENERIC_OBJECT_SCHEMA,
        "error": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_TOOL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "const": "livekit:tool"},
        "tool_name": {"type": "string"},
        "call_id": {"type": "string"},
        "group_id": {"type": "string"},
        "inputs": GENERIC_OBJECT_SCHEMA,
        "created_at": {"type": "number"},
        "metadata": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_TOOL_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed", "failed"]},
        "outputs": GENERIC_OBJECT_SCHEMA,
        "is_error": {"type": "boolean"},
        "error": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_LLM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "const": "livekit:llm"},
        "request_id": {"type": "string"},
        "label": {"type": "string"},
        "model_name": {"type": "string"},
        "provider": {"type": "string"},
        "timestamp": {"type": "number"},
        "metadata": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_LLM_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed", "failed"]},
        "metrics": GENERIC_OBJECT_SCHEMA,
        "error": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_STT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "const": "livekit:stt"},
        "request_id": {"type": "string"},
        "label": {"type": "string"},
        "model_name": {"type": "string"},
        "provider": {"type": "string"},
        "timestamp": {"type": "number"},
        "metadata": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_STT_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed", "failed"]},
        "metrics": GENERIC_OBJECT_SCHEMA,
        "error": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_TTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "const": "livekit:tts"},
        "request_id": {"type": "string"},
        "label": {"type": "string"},
        "model_name": {"type": "string"},
        "provider": {"type": "string"},
        "timestamp": {"type": "number"},
        "metadata": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_TTS_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed", "failed"]},
        "metrics": GENERIC_OBJECT_SCHEMA,
        "error": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_STATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "const": "livekit:state"},
        "actor": {"type": "string"},
        "old_state": {"type": "string"},
        "new_state": {"type": "string"},
        "event_type": {"type": "string"},
        "created_at": {"type": "number"},
        "metadata": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_STATE_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["completed"]},
        "metrics": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "const": "livekit:error"},
        "source": {"type": "string"},
        "error_type": {"type": "string"},
        "message": {"type": "string"},
        "created_at": {"type": "number"},
        "metadata": GENERIC_OBJECT_SCHEMA,
    },
}

LIVEKIT_ERROR_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["failed"]},
        "error": GENERIC_OBJECT_SCHEMA,
    },
}


@dataclass(frozen=True)
class LiveKitToolSchemaConfig:
    """Configuration for a tool-specific LiveKit span schema."""

    span_type: str
    input_schema: dict[str, Any]
    result_schema: dict[str, Any] = field(
        default_factory=lambda: deepcopy(GENERIC_OBJECT_SCHEMA)
    )


def _normalize_tool_config(
    tool_name: str,
    config: LiveKitToolSchemaConfig | Mapping[str, Any],
) -> LiveKitToolSchemaConfig:
    if isinstance(config, LiveKitToolSchemaConfig):
        normalized = config
    elif isinstance(config, Mapping):
        span_type = config.get("span_type")
        input_schema = config.get("input_schema")
        result_schema = config.get("result_schema", GENERIC_OBJECT_SCHEMA)
        if not isinstance(span_type, str):
            raise ValueError(
                f"Invalid tool_schemas.{tool_name}: expected an object with span_type"
            )
        normalized = LiveKitToolSchemaConfig(
            span_type=span_type,
            input_schema=input_schema,  # type: ignore[arg-type]
            result_schema=result_schema,  # type: ignore[arg-type]
        )
    else:
        raise ValueError(
            f"Invalid tool_schemas.{tool_name}: expected an object with span_type"
        )

    if not normalized.span_type.strip():
        raise ValueError(
            f"Invalid tool_schemas.{tool_name}.span_type: expected a non-empty string"
        )
    if not isinstance(normalized.input_schema, dict):
        raise ValueError(
            f"Invalid tool_schemas.{tool_name}.input_schema: expected an object"
        )
    if not isinstance(normalized.result_schema, dict):
        raise ValueError(
            f"Invalid tool_schemas.{tool_name}.result_schema: expected an object"
        )
    return normalized


def _normalize_tool_span_type(span_type: str) -> str:
    normalized = span_type.strip()
    if normalized.startswith("livekit:tool:"):
        return normalized
    if normalized.startswith("tool:"):
        return f"livekit:{normalized}"
    return f"livekit:tool:{normalized}"


def _tool_type_entry(
    span_name: str,
    input_schema: dict[str, Any],
    result_schema: dict[str, Any],
) -> dict[str, Any]:
    params = deepcopy(LIVEKIT_TOOL_SCHEMA)
    params["properties"]["type"] = {"type": "string", "const": span_name}
    params["properties"]["inputs"] = deepcopy(input_schema)
    return {
        "name": span_name,
        "params_schema": params,
        "result_schema": deepcopy(result_schema),
        "title": span_name,
        "description": f"LiveKit tool span for {span_name}",
    }


def _base_entries() -> list[dict[str, Any]]:
    return [
        {
            "name": "livekit:session",
            "params_schema": deepcopy(LIVEKIT_SESSION_SCHEMA),
            "result_schema": deepcopy(LIVEKIT_SESSION_RESULT_SCHEMA),
            "title": "LiveKit Session",
        },
        {
            "name": "livekit:user_turn",
            "params_schema": deepcopy(LIVEKIT_USER_TURN_SCHEMA),
            "result_schema": deepcopy(LIVEKIT_USER_TURN_RESULT_SCHEMA),
            "title": "LiveKit User Turn",
        },
        {
            "name": "livekit:assistant_turn",
            "params_schema": deepcopy(LIVEKIT_ASSISTANT_TURN_SCHEMA),
            "result_schema": deepcopy(LIVEKIT_ASSISTANT_TURN_RESULT_SCHEMA),
            "title": "LiveKit Assistant Turn",
        },
        {
            "name": "livekit:tool",
            "params_schema": deepcopy(LIVEKIT_TOOL_SCHEMA),
            "result_schema": deepcopy(LIVEKIT_TOOL_RESULT_SCHEMA),
            "title": "LiveKit Tool",
        },
        {
            "name": "livekit:llm",
            "params_schema": deepcopy(LIVEKIT_LLM_SCHEMA),
            "result_schema": deepcopy(LIVEKIT_LLM_RESULT_SCHEMA),
            "title": "LiveKit LLM Metrics",
        },
        {
            "name": "livekit:stt",
            "params_schema": deepcopy(LIVEKIT_STT_SCHEMA),
            "result_schema": deepcopy(LIVEKIT_STT_RESULT_SCHEMA),
            "title": "LiveKit STT Metrics",
        },
        {
            "name": "livekit:tts",
            "params_schema": deepcopy(LIVEKIT_TTS_SCHEMA),
            "result_schema": deepcopy(LIVEKIT_TTS_RESULT_SCHEMA),
            "title": "LiveKit TTS Metrics",
        },
        {
            "name": "livekit:state",
            "params_schema": deepcopy(LIVEKIT_STATE_SCHEMA),
            "result_schema": deepcopy(LIVEKIT_STATE_RESULT_SCHEMA),
            "title": "LiveKit State Transition",
        },
        {
            "name": "livekit:error",
            "params_schema": deepcopy(LIVEKIT_ERROR_SCHEMA),
            "result_schema": deepcopy(LIVEKIT_ERROR_RESULT_SCHEMA),
            "title": "LiveKit Error",
        },
    ]


DEFAULT_LIVEKIT_AGENT_SCHEMA: dict[str, Any] = {
    "external_identifier": "livekit-schema",
    "span_type_schemas": _base_entries(),
}


def compile_livekit_agent_schema(
    tool_schemas: Mapping[str, LiveKitToolSchemaConfig | Mapping[str, Any]]
    | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Compile built-in and tool-specific LiveKit schemas."""

    entries = _base_entries()
    tool_span_types: dict[str, str] = {}

    if tool_schemas:
        seen: dict[str, str] = {}
        for tool_name, raw_config in tool_schemas.items():
            config = _normalize_tool_config(tool_name, raw_config)
            normalized_span_type = _normalize_tool_span_type(config.span_type)
            if normalized_span_type in seen:
                conflict = seen[normalized_span_type]
                raise ValueError(
                    f'tool_schemas.{tool_name}.span_type conflicts with "{conflict}"'
                )
            seen[normalized_span_type] = tool_name
            tool_span_types[tool_name] = normalized_span_type
            entries.append(
                _tool_type_entry(
                    normalized_span_type,
                    config.input_schema,
                    config.result_schema,
                )
            )

    return {
        "external_identifier": "livekit-schema",
        "span_type_schemas": entries,
    }, tool_span_types


def register_livekit_schemas(
    registry: SchemaRegistry,
    tool_schemas: Mapping[str, LiveKitToolSchemaConfig | Mapping[str, Any]]
    | None = None,
) -> dict[str, str]:
    """Register LiveKit schemas in a schema registry."""

    compiled, tool_span_types = compile_livekit_agent_schema(tool_schemas=tool_schemas)
    for entry in compiled["span_type_schemas"]:
        registry.register_type(
            name=entry["name"],
            params_schema=entry["params_schema"],
            result_schema=entry.get("result_schema"),
            title=entry.get("title"),
            description=entry.get("description"),
            template=entry.get("template"),
        )
    return tool_span_types


__all__ = [
    "DEFAULT_LIVEKIT_AGENT_SCHEMA",
    "LIVEKIT_ASSISTANT_TURN_SCHEMA",
    "LIVEKIT_ERROR_SCHEMA",
    "LIVEKIT_LLM_SCHEMA",
    "LIVEKIT_SESSION_SCHEMA",
    "LIVEKIT_STATE_SCHEMA",
    "LIVEKIT_STT_SCHEMA",
    "LIVEKIT_TOOL_SCHEMA",
    "LIVEKIT_TTS_SCHEMA",
    "LIVEKIT_USER_TURN_SCHEMA",
    "LiveKitToolSchemaConfig",
    "compile_livekit_agent_schema",
    "register_livekit_schemas",
]
