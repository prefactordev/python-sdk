"""Prefactor Core - Framework-agnostic tracing primitives."""

from prefactor_core.config import Config, HttpTransportConfig
from prefactor_core.tracing.context import SpanContext
from prefactor_core.tracing.span import (
    ErrorInfo,
    Span,
    SpanStatus,
    SpanType,
    TokenUsage,
)
from prefactor_core.tracing.tracer import Tracer
from prefactor_core.transport.base import Transport
from prefactor_core.transport.http import HttpTransport
from prefactor_core.transport.stdio import StdioTransport
from prefactor_core.utils.logging import configure_logging, get_logger
from prefactor_core.utils.serialization import serialize_value, truncate_string

__version__ = "0.2.0"

__all__ = [
    # Config
    "Config",
    "HttpTransportConfig",
    # Tracing
    "Span",
    "SpanType",
    "SpanStatus",
    "TokenUsage",
    "ErrorInfo",
    "Tracer",
    "SpanContext",
    # Transport
    "Transport",
    "StdioTransport",
    "HttpTransport",
    # Utils
    "configure_logging",
    "get_logger",
    "serialize_value",
    "truncate_string",
]
