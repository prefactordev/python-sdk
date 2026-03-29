"""Prefactor LangChain - LangChain integration for Prefactor observability."""

from __future__ import annotations

from prefactor_langchain._version import PACKAGE_VERSION
from prefactor_langchain.metadata_extractor import (
    extract_error_info,
    extract_token_usage,
)
from prefactor_langchain.middleware import PrefactorMiddleware
from prefactor_langchain.schemas import (
    DEFAULT_LANGCHAIN_AGENT_SCHEMA,
    LANGCHAIN_AGENT_SCHEMA,
    LANGCHAIN_LLM_SCHEMA,
    LANGCHAIN_TOOL_SCHEMA,
    LangChainToolSchemaConfig,
    compile_langchain_agent_schema,
    register_langchain_schemas,
)
from prefactor_langchain.spans import (
    AgentSpan,
    ErrorInfo,
    LangChainSpan,
    LLMSpan,
    TokenUsage,
    ToolSpan,
)

__version__ = PACKAGE_VERSION

__all__ = [
    "__version__",
    # Middleware
    "PrefactorMiddleware",
    # Extractors
    "extract_token_usage",
    "extract_error_info",
    # Schemas
    "register_langchain_schemas",
    "compile_langchain_agent_schema",
    "LangChainToolSchemaConfig",
    "DEFAULT_LANGCHAIN_AGENT_SCHEMA",
    "LANGCHAIN_AGENT_SCHEMA",
    "LANGCHAIN_LLM_SCHEMA",
    "LANGCHAIN_TOOL_SCHEMA",
    # Spans
    "LangChainSpan",
    "AgentSpan",
    "LLMSpan",
    "ToolSpan",
    "TokenUsage",
    "ErrorInfo",
]
