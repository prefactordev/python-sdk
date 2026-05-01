"""Prefactor HTTP Client - Async HTTP client for Prefactor API.

This package provides a high-level async HTTP client for interacting with
the Prefactor API, including:

- AgentInstance endpoints (register, start, finish)
- AgentSpan endpoints (create, finish)
- Bulk endpoints (execute multiple operations)
- Automatic retry with exponential backoff
- Comprehensive error handling
- Type-safe data models

Example:
    >>> import asyncio
    >>> from prefactor_http import PrefactorHttpClient, HttpClientConfig
    >>>
    >>> async def main():
    ...     config = HttpClientConfig(
    ...         api_url="https://api.prefactor.ai",
    ...         api_token="your-token"
    ...     )
    ...     async with PrefactorHttpClient(config) as client:
    ...         instance = await client.agent_instances.register(...)
    ...         print(instance)
    >>>
    >>> asyncio.run(main())
"""

from __future__ import annotations

from prefactor_http._version import __version__
from prefactor_http.client import PrefactorHttpClient
from prefactor_http.config import HttpClientConfig
from prefactor_http.exceptions import (
    PrefactorApiError,
    PrefactorAuthError,
    PrefactorClientError,
    PrefactorHttpError,
    PrefactorNotFoundError,
    PrefactorResponseContractError,
    PrefactorRetryExhaustedError,
    PrefactorValidationError,
)
from prefactor_http.models.agent_instance import (
    AgentInstance,
    AgentInstanceSpanCounts,
    AgentSchemaVersionForRegister,
    AgentVersionForRegister,
    FinishInstanceRequest,
    SpanTypeSchemaForCreate,
)
from prefactor_http.models.agent_span import AgentSpan
from prefactor_http.models.base import ApiResponse
from prefactor_http.models.bulk import (
    BulkItem,
    BulkOutput,
    BulkRequest,
    BulkResponse,
)
from prefactor_http.models.types import AgentStatus, FinishStatus

__all__ = [
    # Main client
    "PrefactorHttpClient",
    # Configuration
    "HttpClientConfig",
    # Exceptions
    "PrefactorHttpError",
    "PrefactorApiError",
    "PrefactorAuthError",
    "PrefactorClientError",
    "PrefactorNotFoundError",
    "PrefactorResponseContractError",
    "PrefactorRetryExhaustedError",
    "PrefactorValidationError",
    # Type definitions
    "AgentStatus",
    "FinishStatus",
    # AgentInstance models
    "AgentInstance",
    "AgentInstanceSpanCounts",
    "AgentVersionForRegister",
    "AgentSchemaVersionForRegister",
    "FinishInstanceRequest",
    "SpanTypeSchemaForCreate",
    # AgentSpan models
    "AgentSpan",
    # Base models
    "ApiResponse",
    # Bulk models
    "BulkItem",
    "BulkRequest",
    "BulkResponse",
    "BulkOutput",
    "__version__",
]
