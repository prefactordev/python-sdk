"""Prefactor LangChain - LangChain integration for Prefactor observability."""

from prefactor_langchain.metadata_extractor import (
    extract_error_info,
    extract_token_usage,
)
from prefactor_langchain.middleware import PrefactorMiddleware
from prefactor_langchain.schemas import (
    LANGCHAIN_AGENT_SCHEMA,
    LANGCHAIN_LLM_SCHEMA,
    LANGCHAIN_TOOL_SCHEMA,
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

__version__ = "0.2.2"

__all__ = [
    # Middleware
    "PrefactorMiddleware",
    # Extractors
    "extract_token_usage",
    "extract_error_info",
    # Schemas
    "register_langchain_schemas",
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
