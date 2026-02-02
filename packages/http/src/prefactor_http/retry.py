"""Retry logic with exponential backoff and jitter."""

import asyncio
import random
from typing import Any, Callable

from prefactor_http.config import HttpClientConfig


class RetryHandler:
    """Handles retry logic with exponential backoff and jitter."""

    def __init__(self, config: HttpClientConfig):
        """Initialize retry handler with configuration.

        Args:
            config: HTTP client configuration containing retry parameters.
        """
        self.config = config

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a retry attempt with exponential backoff and jitter.

        The delay is calculated as:
        base_delay = initial_retry_delay * (retry_multiplier ^ attempt)
        delay = base_delay with jitter (±25%)

        Args:
            attempt: Current retry attempt number (0-indexed).

        Returns:
            Delay in seconds, capped at max_retry_delay.
        """
        base_delay = self.config.initial_retry_delay * (
            self.config.retry_multiplier**attempt
        )
        # Apply jitter first, then cap at max to ensure we don't exceed max_retry_delay
        jitter_factor = 0.75 + random.random() * 0.5
        delay = min(base_delay * jitter_factor, self.config.max_retry_delay)
        return delay

    async def execute(
        self,
        operation: Callable[..., Any],
        is_retryable: Callable[[Exception], bool],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute an operation with retry logic.

        Args:
            operation: Async function to execute.
            is_retryable: Function that determines if an exception is retryable.
            *args: Positional arguments for the operation.
            **kwargs: Keyword arguments for the operation.

        Returns:
            Result of the operation.

        Raises:
            PrefactorRetryExhaustedError: When all retry attempts are exhausted.
        """
        last_error = None

        for attempt in range(self.config.max_retries + 1):
            try:
                return await operation(*args, **kwargs)
            except Exception as e:
                last_error = e

                if attempt == self.config.max_retries:
                    # If max_retries is 0, we never actually retried, so re-raise
                    # the original exception instead of wrapping it
                    if self.config.max_retries == 0:
                        raise
                    break

                if not is_retryable(e):
                    raise

                delay = self._calculate_delay(attempt)
                await asyncio.sleep(delay)

        from prefactor_http.exceptions import PrefactorRetryExhaustedError

        raise PrefactorRetryExhaustedError(
            f"Operation failed after {self.config.max_retries + 1} attempts",
            last_error,
        )
