"""Tests for Prefactor HTTP Client retry logic."""

import pytest
from prefactor_http.config import HttpClientConfig
from prefactor_http.exceptions import PrefactorRetryExhaustedError
from prefactor_http.retry import RetryHandler


class TestRetryHandler:
    """Tests for RetryHandler class."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return HttpClientConfig(
            api_url="https://api.test.com",
            api_token="test-token",
            max_retries=2,
            initial_retry_delay=0.1,
            max_retry_delay=1.0,
            retry_multiplier=2.0,
        )

    @pytest.fixture
    def handler(self, config):
        """Create retry handler."""
        return RetryHandler(config)

    async def test_success_no_retry(self, handler):
        """Test successful operation with no retries."""

        async def success_op():
            return "success"

        result = await handler.execute(success_op, lambda e: False)
        assert result == "success"

    async def test_retry_on_retryable_error(self, handler):
        """Test retry on retryable error."""
        call_count = 0

        async def succeeds_after_retries():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection failed")
            return "success"

        result = await handler.execute(
            succeeds_after_retries, lambda e: isinstance(e, ConnectionError)
        )
        assert result == "success"
        assert call_count == 3

    async def test_max_retries_exhausted(self, handler):
        """Test exhaustion of max retries."""

        async def always_fails():
            raise ConnectionError("Connection failed")

        with pytest.raises(PrefactorRetryExhaustedError):
            await handler.execute(
                always_fails, lambda e: isinstance(e, ConnectionError)
            )

    async def test_non_retryable_error(self, handler):
        """Test that non-retryable errors are raised immediately."""

        async def raises_value_error():
            raise ValueError("Invalid value")

        with pytest.raises(ValueError, match="Invalid value"):
            await handler.execute(
                raises_value_error, lambda e: isinstance(e, ConnectionError)
            )


class TestRetryDelay:
    """Tests for retry delay calculation."""

    def test_delay_calculation(self):
        """Test delay calculation with exponential backoff."""
        config = HttpClientConfig(
            api_url="https://api.test.com",
            api_token="test-token",
            initial_retry_delay=1.0,
            max_retry_delay=30.0,
            retry_multiplier=2.0,
        )
        handler = RetryHandler(config)

        # First attempt (delay = 1.0 * 2^1)
        delay0 = handler._calculate_delay(0)
        assert 0.75 <= delay0 <= 1.25  # With 25% jitter

        # Second attempt (delay = 1.0 * 2^2)
        delay1 = handler._calculate_delay(1)
        assert 1.5 <= delay1 <= 2.5  # With 25% jitter

        # Third attempt (delay = 1.0 * 2^2, capped at max)
        delay2 = handler._calculate_delay(5)
        assert delay2 <= 30.0  # Capped at max_retry_delay (no jitter applied after cap)
