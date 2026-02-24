"""Tests for Prefactor HTTP Client configuration."""

import pytest
from prefactor_http.config import HttpClientConfig


class TestHttpClientConfig:
    """Tests for HttpClientConfig class."""

    def test_valid_config(self):
        """Test creating a valid configuration."""
        config = HttpClientConfig(
            api_url="https://api.test.com",
            api_token="test-token",
        )
        assert config.api_url == "https://api.test.com"
        assert config.api_token == "test-token"
        assert config.max_retries == 3
        assert config.initial_retry_delay == 1.0

    def test_custom_config(self):
        """Test creating configuration with custom values."""
        config = HttpClientConfig(
            api_url="https://api.test.com",
            api_token="test-token",
            max_retries=5,
            initial_retry_delay=0.5,
            max_retry_delay=30.0,
            retry_multiplier=1.5,
            retry_on_status_codes=(429, 500, 503),
        )
        assert config.max_retries == 5
        assert config.initial_retry_delay == 0.5
        assert config.max_retry_delay == 30.0
        assert config.retry_multiplier == 1.5
        assert config.retry_on_status_codes == (429, 500, 503)

    def test_missing_api_url_raises_error(self):
        """Test that missing api_url raises ValueError."""
        with pytest.raises(ValueError, match="api_url is required"):
            HttpClientConfig(
                api_url="",
                api_token="token",
            )

    def test_missing_api_token_raises_error(self):
        """Test that missing api_token raises ValueError."""
        with pytest.raises(ValueError, match="api_token is required"):
            HttpClientConfig(
                api_url="https://api.test.com",
                api_token="",
            )

    def test_negative_max_retries_raises_error(self):
        """Test that negative max_retries raises ValueError."""
        with pytest.raises(ValueError, match="max_retries must be non-negative"):
            HttpClientConfig(
                api_url="https://api.test.com",
                api_token="token",
                max_retries=-1,
            )

    def test_invalid_retry_delay_raises_error(self):
        """Test that invalid retry delay raises ValueError."""
        with pytest.raises(ValueError, match="initial_retry_delay must be positive"):
            HttpClientConfig(
                api_url="https://api.test.com",
                api_token="token",
                initial_retry_delay=0,
            )

    def test_retry_multiplier_less_than_one_raises_error(self):
        """Test that retry_multiplier < 1 raises ValueError."""
        with pytest.raises(ValueError, match="retry_multiplier must be >= 1"):
            HttpClientConfig(
                api_url="https://api.test.com",
                api_token="token",
                retry_multiplier=0.5,
            )


class TestHttpClientConfigDefaults:
    """Tests for HttpClientConfig default values."""

    def test_default_timeouts(self):
        """Test default timeout values."""
        config = HttpClientConfig(
            api_url="https://api.test.com",
            api_token="token",
        )
        assert config.request_timeout == 30.0
        assert config.connect_timeout == 10.0

    def test_default_retry_values(self):
        """Test default retry configuration values."""
        config = HttpClientConfig(
            api_url="https://api.test.com",
            api_token="token",
        )
        assert config.max_retries == 3
        assert config.initial_retry_delay == 1.0
        assert config.max_retry_delay == 60.0
        assert config.retry_multiplier == 2.0
        assert config.retry_on_status_codes == (429, 500, 502, 503, 504)
