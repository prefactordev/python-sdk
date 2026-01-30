"""Exceptions for Prefactor HTTP Client."""

from typing import Optional


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
