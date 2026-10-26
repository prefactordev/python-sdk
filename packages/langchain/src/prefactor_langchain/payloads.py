"""Span payload builders shared by the middleware and the callback handler.

Both integrations send the same params and result shapes for each span type,
so Prefactor reads them the same way.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .spans import AgentSpan, LLMSpan, ToolSpan


def message_to_dict(message: Any) -> dict[str, Any]:
    """Convert a LangChain message to a compact dict.

    Args:
        message: A LangChain message.

    Returns:
        A dict with ``role``, plus ``content`` and ``tool_calls`` when present.
    """
    role = getattr(message, "type", "unknown")
    content = getattr(message, "content", "")
    result: dict[str, Any] = {"role": role}
    # content may be a string or a list of content blocks
    if isinstance(content, str):
        result["content"] = content
    elif isinstance(content, list):
        # Extract text blocks; summarise tool-use blocks
        texts = [
            b.get("text", "") if isinstance(b, dict) else str(b)
            for b in content
            if not isinstance(b, dict) or b.get("type") != "tool_use"
        ]
        tool_uses = [
            b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        if texts:
            result["content"] = " ".join(t for t in texts if t)
        if tool_uses:
            result["tool_calls"] = [
                {"name": t.get("name"), "args": t.get("input", {})} for t in tool_uses
            ]
    # OpenAI-style providers return tool calls on the message, not in content
    tool_calls = getattr(message, "tool_calls", None)
    if isinstance(tool_calls, list) and tool_calls and "tool_calls" not in result:
        result["tool_calls"] = [
            {"name": t.get("name"), "args": t.get("args", {})} for t in tool_calls
        ]
    return result


def state_to_json(state: Any) -> dict[str, Any]:
    """Convert graph state to a JSON-safe dict.

    ``messages`` lists are converted with :func:`message_to_dict`. Every other
    value is passed through JSON, with unknown types converted to strings.

    Args:
        state: Graph state, usually a dict.

    Returns:
        A JSON-safe dict, or ``{"value": ...}`` when the state is not a mapping.
    """
    if not isinstance(state, Mapping):
        return {"value": _to_json(state)}
    result: dict[str, Any] = {}
    for key, value in state.items():
        if key == "messages" and isinstance(value, list):
            result[key] = [message_to_dict(m) for m in value]
        else:
            result[key] = _to_json(value)
    return result


def _to_json(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def build_llm_params(span_data: LLMSpan) -> dict[str, Any]:
    """Build the payload (params) dict for an LLM span."""
    params: dict[str, Any] = {}
    if span_data.model_name:
        params["model_name"] = span_data.model_name
    if span_data.provider:
        params["provider"] = span_data.provider
    if span_data.inputs:
        params["inputs"] = span_data.inputs
    if span_data.temperature is not None:
        params["temperature"] = span_data.temperature
    return params


def build_llm_result(span_data: LLMSpan) -> dict[str, Any]:
    """Build the result_payload dict for an LLM span."""
    result: dict[str, Any] = {}
    if span_data.outputs:
        result["outputs"] = span_data.outputs
    if span_data.token_usage:
        result["token_usage"] = span_data.token_usage.to_dict()
    if span_data.error:
        result["error"] = span_data.error.to_dict()
    return result


def build_tool_params(span_data: ToolSpan, schema_name: str) -> dict[str, Any]:
    """Build the payload (params) dict for a tool span."""
    params: dict[str, Any] = {}
    if span_data.tool_name:
        params["tool_name"] = span_data.tool_name
    if schema_name != "langchain:tool":
        params["inputs"] = span_data.arguments
    elif span_data.inputs:
        params["inputs"] = span_data.inputs
    return params


def build_tool_result(span_data: ToolSpan) -> dict[str, Any]:
    """Build the result_payload dict for a tool span."""
    result: dict[str, Any] = {}
    if span_data.outputs:
        result["outputs"] = span_data.outputs
    if span_data.error:
        result["error"] = span_data.error.to_dict()
    return result


def build_agent_params(span_data: AgentSpan) -> dict[str, Any]:
    """Build the payload (params) dict for an agent span."""
    params: dict[str, Any] = {}
    if span_data.inputs:
        params["inputs"] = span_data.inputs
    if span_data.agent_name:
        params["agent_name"] = span_data.agent_name
    return params


def build_agent_result(span_data: AgentSpan) -> dict[str, Any]:
    """Build the result_payload dict for an agent span."""
    result: dict[str, Any] = {}
    if span_data.outputs:
        result["outputs"] = span_data.outputs
    if span_data.error:
        result["error"] = span_data.error.to_dict()
    return result


__all__ = [
    "build_agent_params",
    "build_agent_result",
    "build_llm_params",
    "build_llm_result",
    "build_tool_params",
    "build_tool_result",
    "message_to_dict",
    "state_to_json",
]
