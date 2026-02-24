"""Configuration for Prefactor HTTP Client."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class HttpClientConfig:
    """Configuration for the HTTP client.

    Attributes:
        api_url: Base URL for the Prefactor API.
            Example: 'https://api.prefactor.ai'
        api_token: Bearer token for API authentication.
        request_timeout: Total timeout for requests in seconds (default: 30.0).
        connect_timeout: Connection timeout in seconds (default: 10.0).
        max_retries: Maximum number of retry attempts (default: 3).
        initial_retry_delay: Initial delay between retries in seconds (default: 1.0).
        max_retry_delay: Maximum delay between retries in seconds (default: 60.0).
        retry_multiplier: Multiplier for exponential backoff (default: 2.0).
        retry_on_status_codes: HTTP status codes to retry on
            (default: 429, 500, 502, 503, 504).
        default_idempotency_key: Optional default idempotency key prefix.
    """

    api_url: str
    api_token: str
    request_timeout: float = 30.0
    connect_timeout: float = 10.0
    max_retries: int = 3
    initial_retry_delay: float = 1.0
    max_retry_delay: float = 60.0
    retry_multiplier: float = 2.0
    retry_on_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)
    default_idempotency_key: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.api_url:
            raise ValueError("api_url is required")
        if not self.api_token:
            raise ValueError("api_token is required")
        if self.request_timeout <= 0:
            raise ValueError("request_timeout must be positive")
        if self.connect_timeout <= 0:
            raise ValueError("connect_timeout must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if self.initial_retry_delay <= 0:
            raise ValueError("initial_retry_delay must be positive")
        if self.max_retry_delay <= 0:
            raise ValueError("max_retry_delay must be positive")
        if self.initial_retry_delay > self.max_retry_delay:
            raise ValueError("initial_retry_delay must be <= max_retry_delay")
        if self.retry_multiplier < 1:
            raise ValueError("retry_multiplier must be >= 1")
