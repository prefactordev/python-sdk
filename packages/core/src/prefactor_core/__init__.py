"""Prefactor Core - Framework-agnostic tracing primitives."""

from prefactor_core.config import Config
from prefactor_core.tracing.context import SpanContext
from prefactor_core.tracing.span import (
    ErrorInfo,
    Span,
    SpanStatus,
    SpanType,
    TokenUsage,
)
from prefactor_core.utils.logging import configure_logging, get_logger
from prefactor_core.utils.serialization import serialize_value, truncate_string

__version__ = "0.3.0"

__all__ = [
    # Config
    "Config",
    # Tracing
    "Span",
    "SpanType",
    "SpanStatus",
    "TokenUsage",
    "ErrorInfo",
    "SpanContext",
    # Utils
    "configure_logging",
    "get_logger",
    "serialize_value",
    "truncate_string",
]
