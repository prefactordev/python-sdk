"""Exceptions for Prefactor HTTP Client."""

from __future__ import annotations

import asyncio
from typing import Optional

import aiohttp


class PrefactorHttpError(Exception):
    """Base exception for all HTTP client errors."""

    pass


class PrefactorApiError(PrefactorHttpError):
    """API returned an error response.

    Attributes:
        message: Human-readable error message
        code: Error code from the API
        status_code: HTTP status code
    """

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int,
    ) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class PrefactorAuthError(PrefactorApiError):
    """Authentication/authorization errors (401, 403)."""

    pass


class PrefactorNotFoundError(PrefactorApiError):
    """Resource not found (404)."""

    pass


class PrefactorValidationError(PrefactorApiError):
    """Validation errors (400, 422).

    Attributes:
        errors: Detailed validation errors mapping field names to error messages
    """

    def __init__(
        self,
        message: str,
        code: str,
        status_code: int,
        errors: dict,
    ) -> None:
        self.errors = errors
        super().__init__(message, code, status_code)


class PrefactorRetryExhaustedError(PrefactorHttpError):
    """All retry attempts exhausted.

    Attributes:
        last_error: The last exception that caused the retry to fail
    """

    def __init__(
        self,
        message: str,
        last_error: Optional[Exception] = None,
    ) -> None:
        self.last_error = last_error
        super().__init__(message)


class PrefactorClientError(PrefactorHttpError):
    """Client-side error (not related to API)."""

    pass


class PrefactorResponseContractError(PrefactorHttpError):
    """Backend response violated the SDK's expected response contract."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body_snippet: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.body_snippet = body_snippet
        self.cause = cause
        super().__init__(message)


def is_transient_http_error(error: Exception) -> bool:
    """Return True when the error is safe to retry later."""
    if isinstance(error, PrefactorRetryExhaustedError) and error.last_error is not None:
        return is_transient_http_error(error.last_error)
    if isinstance(error, (aiohttp.ClientError, asyncio.TimeoutError)):
        return True
    if isinstance(error, PrefactorResponseContractError):
        return False
    if isinstance(error, PrefactorApiError):
        return error.status_code == 429 or error.status_code >= 500
    return False


def is_permanent_http_error(error: Exception) -> bool:
    """Return True when retrying the same operation should stop immediately."""
    if isinstance(error, PrefactorRetryExhaustedError) and error.last_error is not None:
        return is_permanent_http_error(error.last_error)
    if isinstance(error, PrefactorResponseContractError):
        return True
    if isinstance(error, PrefactorApiError):
        return 400 <= error.status_code < 500 and error.status_code != 429
    return False
