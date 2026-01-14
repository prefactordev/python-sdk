"""Span data models for distributed tracing."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SpanType(str, Enum):
    """Types of spans in the tracing system."""

    AGENT = "agent"
    LLM = "llm"
    TOOL = "tool"
    CHAIN = "chain"
    RETRIEVER = "retriever"


class SpanStatus(str, Enum):
    """Status of a span."""

    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


@dataclass
class TokenUsage:
    """Token usage information for LLM calls."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class ErrorInfo:
    """Error information captured during span execution."""

    error_type: str
    message: str
    stacktrace: str


@dataclass
class Span:
    """Represents a single span in a distributed trace."""

    span_id: str
    parent_span_id: str | None
    trace_id: str
    name: str
    span_type: SpanType
    start_time: float
    end_time: float | None
    status: SpanStatus
    inputs: dict[str, Any]
    outputs: dict[str, Any] | None
    token_usage: TokenUsage | None
    error: ErrorInfo | None
    metadata: dict[str, Any]
    tags: list[str]
