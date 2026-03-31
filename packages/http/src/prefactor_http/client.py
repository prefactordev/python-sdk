"""HTTP client for Prefactor API."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import aiohttp

from prefactor_http._version import PACKAGE_NAME, PACKAGE_VERSION
from prefactor_http.config import HttpClientConfig
from prefactor_http.exceptions import (
    PrefactorApiError,
    PrefactorAuthError,
    PrefactorClientError,
    PrefactorNotFoundError,
    PrefactorResponseContractError,
    PrefactorRetryExhaustedError,
    PrefactorValidationError,
    is_transient_http_error,
)
from prefactor_http.retry import RetryHandler

if TYPE_CHECKING:
    from prefactor_http.endpoints.agent_instance import AgentInstanceClient
    from prefactor_http.endpoints.agent_span import AgentSpanClient
    from prefactor_http.endpoints.bulk import BulkClient


def _format_sdk_header_entry(package_name: str, package_version: str) -> str:
    """Format a single SDK header entry."""
    return f"{package_name}@{package_version}"


def _build_sdk_header(
    package_name: str,
    package_version: str,
    upstream_entry: str | None = None,
) -> str:
    """Build the effective SDK header value."""
    base_entry = _format_sdk_header_entry(package_name, package_version)
    if upstream_entry is None or not upstream_entry.strip():
        return base_entry
    return f"{upstream_entry.strip()} {base_entry}"


DEFAULT_SDK_HEADER = _build_sdk_header(PACKAGE_NAME, PACKAGE_VERSION)


class PrefactorHttpClient:
    """Main HTTP client for interacting with the Prefactor API.

    This client provides high-level methods for all API endpoints with
    built-in retry logic, error handling, and idempotency support.

    Usage:
        async with PrefactorHttpClient(config) as client:
            instance = await client.agent_instances.register(...)
            span = await client.agent_spans.create(...)
    """

    def __init__(self, config: HttpClientConfig, sdk_header: str | None = None):
        """Initialize the HTTP client.

        Args:
            config: HTTP client configuration.
            sdk_header: Effective SDK header value for outbound requests.
        """
        self.config = config
        self._session: aiohttp.ClientSession | None = None
        self._retry_handler = RetryHandler(config)
        self._sdk_header = sdk_header or DEFAULT_SDK_HEADER
        # Import here to avoid circular import during __init__.py loading
        self._bulk: BulkClient | None = None
        self._agent_instances: AgentInstanceClient | None = None
        self._agent_spans: AgentSpanClient | None = None

    async def __aenter__(self) -> "PrefactorHttpClient":
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_session(self) -> None:
        """Ensure the HTTP session is initialized."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(
                total=self.config.request_timeout,
                connect=self.config.connect_timeout,
            )
            self._session = aiohttp.ClientSession(timeout=timeout)

    @property
    def agent_instances(self) -> "AgentInstanceClient":
        """Access the agent instance endpoint client.

        Provides methods to interact with agent instances:
        - register: Create a new agent instance
        - start: Mark an instance as started
        - finish: Mark an instance as finished

        Example:
            instance = await client.agent_instances.register(agent_id, agent_version)
        """
        if self._agent_instances is None:
            # Import here to avoid circular import
            from prefactor_http.endpoints.agent_instance import AgentInstanceClient

            self._agent_instances = AgentInstanceClient(self)
        return self._agent_instances

    @property
    def agent_spans(self) -> "AgentSpanClient":
        """Access the agent span endpoint client.

        Provides methods to interact with agent spans:
        - create: Create a new agent span
        - finish: Mark a span as finished

        Example:
            span = await client.agent_spans.create(
                agent_instance_id, schema_name, payload
            )
        """
        if self._agent_spans is None:
            # Import here to avoid circular import
            from prefactor_http.endpoints.agent_span import AgentSpanClient

            self._agent_spans = AgentSpanClient(self)
        return self._agent_spans

    @property
    def bulk(self) -> "BulkClient":
        """Access the bulk endpoint client.

        Provides methods to execute multiple queries/actions in a single request:
        - execute: Execute bulk operations

        Example:
            response = await client.bulk.execute(bulk_request)
        """
        if self._bulk is None:
            # Import here to avoid circular import
            from prefactor_http.endpoints.bulk import BulkClient

            self._bulk = BulkClient(self)
        return self._bulk

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    @staticmethod
    def _truncate_body(body: str, limit: int = 200) -> str:
        """Return a compact response body snippet for error messages."""
        collapsed = " ".join(body.split())
        if len(collapsed) <= limit:
            return collapsed
        return f"{collapsed[:limit]}..."

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable.

        Retryable errors include network errors and specific HTTP status codes.

        Args:
            error: The exception to check.

        Returns:
            True if the error should trigger a retry.
        """
        return is_transient_http_error(error)

    def _raise_api_error(self, status: int, response_data: dict) -> None:
        """Raise appropriate exception based on API response.

        Args:
            status: HTTP status code.
            response_data: Parsed JSON response body.

        Raises:
            PrefactorApiError: Appropriate subclass based on status code.
        """
        code = response_data.get("code", "unknown")
        message = response_data.get("message", f"HTTP {status}")

        if status == 401 or status == 403:
            raise PrefactorAuthError(message, code, status)
        elif status == 404:
            raise PrefactorNotFoundError(message, code, status)
        elif status == 400 or status == 422:
            errors = response_data.get("errors", {})
            raise PrefactorValidationError(message, code, status, errors)
        else:
            raise PrefactorApiError(message, code, status)

    async def _make_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Make a single HTTP request.

        This is the core request method that handles the actual HTTP call,
        headers, and error response parsing.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path (e.g., /api/v1/agent_instance).
            params: Query parameters.
            json_data: JSON body data.
            idempotency_key: Optional idempotency key.

        Returns:
            Parsed JSON response.

        Raises:
            PrefactorApiError: On API errors.
            PrefactorClientError: On client-side errors.
        """
        if self._session is None or self._session.closed:
            raise PrefactorClientError("HTTP session not initialized")

        url = f"{self.config.api_url.rstrip('/')}{path}"

        headers = {
            "Authorization": f"Bearer {self.config.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Prefactor-SDK": self._sdk_header,
        }

        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        async with self._session.request(
            method=method,
            url=url,
            params=params,
            json=json_data,
            headers=headers,
        ) as response:
            response_text = await response.text()
            try:
                response_data = json.loads(response_text)
            except json.JSONDecodeError as exc:
                snippet = self._truncate_body(response_text)
                message = (
                    f"Expected JSON response from {path}, received invalid JSON"
                )
                if snippet:
                    message = f"{message}: {snippet}"
                raise PrefactorResponseContractError(
                    message,
                    status_code=response.status,
                    body_snippet=snippet or None,
                    cause=exc,
                ) from exc

            if not isinstance(response_data, dict):
                raise PrefactorResponseContractError(
                    f"Expected JSON object response from {path}",
                    status_code=response.status,
                    body_snippet=self._truncate_body(response_text) or None,
                )

            if response.status >= 400:
                self._raise_api_error(response.status, response_data)

            return response_data

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request with retry logic.

        This is the public request method that wraps the core request
        with retry handling.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            path: API path.
            params: Query parameters.
            json_data: JSON body data.
            idempotency_key: Optional idempotency key.

        Returns:
            Parsed JSON response.

        Raises:
            PrefactorRetryExhaustedError: When retries are exhausted.
            PrefactorApiError: On API errors.
        """
        await self._ensure_session()

        try:
            return await self._retry_handler.execute(
                self._make_request,
                self._is_retryable_error,
                method,
                path,
                params=params,
                json_data=json_data,
                idempotency_key=idempotency_key,
            )
        except PrefactorRetryExhaustedError as e:
            # Re-raise with context
            raise PrefactorRetryExhaustedError(
                f"Request to {path} failed after {self.config.max_retries + 1} "
                f"attempts",
                e.last_error,
            )
