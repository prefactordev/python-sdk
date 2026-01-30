"""Prefactor HTTP Client - Async HTTP client for Prefactor API.

This package provides a high-level async HTTP client for interacting with
the Prefactor API, including:

- AgentInstance endpoints (register, start, finish, list, get)
- AgentSpan endpoints (create, finish, list)
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
    ...         instance = await client.agent_instances.get("instance-id")
    ...         print(instance)
    >>>
    >>> asyncio.run(main())
"""

from prefactor_http.client import PrefactorHttpClient
from prefactor_http.config import HttpClientConfig
from prefactor_http.exceptions import (
    PrefactorApiError,
    PrefactorAuthError,
    PrefactorClientError,
    PrefactorHttpError,
    PrefactorNotFoundError,
    PrefactorRetryExhaustedError,
    PrefactorValidationError,
)
from prefactor_http.models.bulk import (
    BulkItem,
    BulkOutput,
    BulkRequest,
    BulkResponse,
)

__version__ = "0.1.0"

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
    "PrefactorRetryExhaustedError",
    "PrefactorValidationError",
    # Bulk models
    "BulkItem",
    "BulkRequest",
    "BulkResponse",
    "BulkOutput",
]
