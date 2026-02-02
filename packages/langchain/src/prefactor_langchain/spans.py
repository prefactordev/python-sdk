"""LangChain-specific span definitions for Prefactor observability.

This module defines span dataclasses that capture LangChain-specific semantics
using the 'langchain:*' type namespace. These spans are self-contained and
can be serialized to JSON for transport to the backend.

Note: span_id, parent_span_id, and trace_id are managed by the backend
automatically, so they are not included in these span definitions.
"""

import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional


@dataclass
class TokenUsage:
    """Token usage information for LLM calls."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class ErrorInfo:
    """Error information for failed spans."""

    error_type: str
    message: str
    stacktrace: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {
            "error_type": self.error_type,
            "message": self.message,
        }
        if self.stacktrace:
            result["stacktrace"] = self.stacktrace
        return result


@dataclass
class LangChainSpan:
    """Base class for all LangChain spans.

    All LangChain spans share common fields for timing, status,
    inputs/outputs, and error information. Trace correlation
    (span_id, parent_span_id, trace_id) is handled by the backend.

    Note: The 'type' field is defined in subclasses to avoid dataclass
    field shadowing issues.
    """

    name: str = "unnamed"
    start_time: float = field(default_factory=lambda: datetime.now().timestamp())
    end_time: Optional[float] = None
    status: Literal["pending", "running", "completed", "error"] = "pending"
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    error: Optional[ErrorInfo] = None

    def complete(self, outputs: Optional[dict[str, Any]] = None) -> None:
        """Mark the span as completed with outputs."""
        self.status = "completed"
        self.end_time = datetime.now().timestamp()
        if outputs:
            self.outputs = outputs

    def fail(self, error: Exception) -> None:
        """Mark the span as failed with error information."""
        self.status = "error"
        self.end_time = datetime.now().timestamp()
        self.error = ErrorInfo(
            error_type=type(error).__name__,
            message=str(error),
            stacktrace=traceback.format_exc(),
        )

    # Class attribute for span type - must be defined in subclasses
    type: str = "langchain:agent"

    def to_dict(self) -> dict[str, Any]:
        """Convert span to dictionary for serialization.

        Returns a JSON-serializable dictionary representation of the span.
        """
        result: dict[str, Any] = {
            "name": self.name,
            "type": type(self).type,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": self.status,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "metadata": self.metadata,
            "tags": self.tags,
        }

        if self.error:
            result["error"] = self.error.to_dict()

        return result


@dataclass
class AgentSpan(LangChainSpan):
    """Span representing an agent execution.

    Captures the lifecycle of an agent run, including the agent's
    name, configuration, and the messages/state that drove the execution.
    """

    type = "langchain:agent"
    agent_name: Optional[str] = None
    agent_config: dict[str, Any] = field(default_factory=dict)
    initial_messages: list[dict[str, Any]] = field(default_factory=list)
    final_messages: list[dict[str, Any]] = field(default_factory=list)
    iteration_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary including agent-specific fields."""
        result = super().to_dict()
        result.update(
            {
                "agent_name": self.agent_name,
                "agent_config": self.agent_config,
                "initial_messages": self.initial_messages,
                "final_messages": self.final_messages,
                "iteration_count": self.iteration_count,
            }
        )
        return result


@dataclass
class LLMSpan(LangChainSpan):
    """Span representing an LLM call.

    Captures model-specific metadata including the model name, provider,
    token usage, and generation parameters.
    """

    type = "langchain:llm"
    model_name: Optional[str] = None
    provider: Optional[str] = None  # openai, anthropic, etc.
    token_usage: Optional[TokenUsage] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stop_sequences: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    response_content: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary including LLM-specific fields."""
        result = super().to_dict()
        result.update(
            {
                "model_name": self.model_name,
                "provider": self.provider,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "top_p": self.top_p,
                "stop_sequences": self.stop_sequences,
                "messages": self.messages,
                "response_content": self.response_content,
            }
        )
        if self.token_usage:
            result["token_usage"] = self.token_usage.to_dict()
        return result


@dataclass
class ToolSpan(LangChainSpan):
    """Span representing a tool execution.

    Captures tool-specific metadata including the tool name, schema,
    arguments, and execution time. Can represent any tool call including
    retrievers (with appropriate metadata).
    """

    type = "langchain:tool"
    tool_name: Optional[str] = None
    tool_schema: Optional[dict[str, Any]] = None
    arguments: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: Optional[int] = None
    tool_type: Optional[str] = None  # e.g., "function", "retriever", "api"
    retriever_metadata: Optional[dict[str, Any]] = None  # For retriever-type tools

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary including tool-specific fields."""
        result = super().to_dict()
        result.update(
            {
                "tool_name": self.tool_name,
                "tool_schema": self.tool_schema,
                "arguments": self.arguments,
                "execution_time_ms": self.execution_time_ms,
                "tool_type": self.tool_type,
            }
        )
        if self.retriever_metadata:
            result["retriever_metadata"] = self.retriever_metadata
        return result


__all__ = [
    "TokenUsage",
    "ErrorInfo",
    "LangChainSpan",
    "AgentSpan",
    "LLMSpan",
    "ToolSpan",
]
