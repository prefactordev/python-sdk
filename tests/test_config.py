"""Tests for configuration."""

import pytest

from prefactor_sdk.config import Config


class TestConfig:
    """Test Config class."""

    def test_config_defaults(self, monkeypatch):
        """Test default configuration values."""
        # Clear all env vars
        for key in [
            "PREFACTOR_TRANSPORT",
            "PREFACTOR_SAMPLE_RATE",
            "PREFACTOR_CAPTURE_INPUTS",
            "PREFACTOR_CAPTURE_OUTPUTS",
            "PREFACTOR_MAX_INPUT_LENGTH",
            "PREFACTOR_MAX_OUTPUT_LENGTH",
        ]:
            monkeypatch.delenv(key, raising=False)

        config = Config()

        assert config.transport_type == "stdio"
        assert config.sample_rate == 1.0
        assert config.capture_inputs is True
        assert config.capture_outputs is True
        assert config.max_input_length == 10000
        assert config.max_output_length == 10000

    def test_config_from_env_vars(self, monkeypatch):
        """Test loading configuration from environment variables."""
        monkeypatch.setenv("PREFACTOR_TRANSPORT", "stdio")
        monkeypatch.setenv("PREFACTOR_SAMPLE_RATE", "0.5")
        monkeypatch.setenv("PREFACTOR_CAPTURE_INPUTS", "false")
        monkeypatch.setenv("PREFACTOR_CAPTURE_OUTPUTS", "false")
        monkeypatch.setenv("PREFACTOR_MAX_INPUT_LENGTH", "5000")
        monkeypatch.setenv("PREFACTOR_MAX_OUTPUT_LENGTH", "8000")

        config = Config()

        assert config.transport_type == "stdio"
        assert config.sample_rate == 0.5
        assert config.capture_inputs is False
        assert config.capture_outputs is False
        assert config.max_input_length == 5000
        assert config.max_output_length == 8000

    def test_config_explicit_values(self):
        """Test creating config with explicit values."""
        config = Config(
            transport_type="stdio",
            sample_rate=0.3,
            capture_inputs=False,
            capture_outputs=True,
            max_input_length=2000,
            max_output_length=3000,
        )

        assert config.transport_type == "stdio"
        assert config.sample_rate == 0.3
        assert config.capture_inputs is False
        assert config.capture_outputs is True
        assert config.max_input_length == 2000
        assert config.max_output_length == 3000

    def test_config_explicit_overrides_env(self, monkeypatch):
        """Test that explicit values override environment variables."""
        monkeypatch.setenv("PREFACTOR_TRANSPORT", "http")
        monkeypatch.setenv("PREFACTOR_SAMPLE_RATE", "0.5")

        config = Config(
            transport_type="stdio",
            sample_rate=0.8,
        )

        assert config.transport_type == "stdio"
        assert config.sample_rate == 0.8

    def test_config_sample_rate_validation(self):
        """Test sample rate validation."""
        # Valid sample rates
        config = Config(sample_rate=0.0)
        assert config.sample_rate == 0.0

        config = Config(sample_rate=1.0)
        assert config.sample_rate == 1.0

        config = Config(sample_rate=0.5)
        assert config.sample_rate == 0.5

        # Invalid sample rates should raise
        with pytest.raises(ValueError):
            Config(sample_rate=-0.1)

        with pytest.raises(ValueError):
            Config(sample_rate=1.5)

    def test_config_boolean_env_vars(self, monkeypatch):
        """Test parsing boolean environment variables."""
        # Test various boolean representations
        test_cases = [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
        ]

        for env_value, expected in test_cases:
            monkeypatch.setenv("PREFACTOR_CAPTURE_INPUTS", env_value)
            config = Config()
            assert config.capture_inputs is expected, f"Failed for {env_value}"

    def test_config_invalid_env_var_types(self, monkeypatch):
        """Test handling of invalid environment variable types."""
        # Invalid sample rate - should use default
        monkeypatch.setenv("PREFACTOR_SAMPLE_RATE", "invalid")
        config = Config()
        assert config.sample_rate == 1.0  # Default value

        # Invalid max length - should use default
        monkeypatch.setenv("PREFACTOR_MAX_INPUT_LENGTH", "not_a_number")
        config = Config()
        assert config.max_input_length == 10000  # Default value

    def test_config_repr(self):
        """Test config string representation."""
        config = Config(
            transport_type="stdio",
            sample_rate=0.5,
        )

        repr_str = repr(config)
        assert "Config" in repr_str
        assert "stdio" in repr_str
        assert "0.5" in repr_str

    def test_http_transport_config(self):
        """Test HTTP transport configuration."""
        config = Config(
            transport_type="http",
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            agent_id="test-agent",
            agent_version="1.0.0",
        )

        assert config.transport_type == "http"
        assert config.http_config is not None
        assert config.http_config.api_url == "https://api.test.prefactor.ai"
        assert config.http_config.api_token == "test-token"
        assert config.http_config.agent_id == "test-agent"
        assert config.http_config.agent_version == "1.0.0"

    def test_http_transport_missing_url(self):
        """Test HTTP transport with missing URL raises ValueError."""
        with pytest.raises(ValueError, match="api_url"):
            Config(
                transport_type="http",
                api_token="test-token",
            )

    def test_http_transport_missing_token(self):
        """Test HTTP transport with missing token raises ValueError."""
        with pytest.raises(ValueError, match="api_token"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
            )

    def test_http_transport_from_env(self, monkeypatch):
        """Test HTTP transport configuration from environment variables."""
        monkeypatch.setenv("PREFACTOR_TRANSPORT", "http")
        monkeypatch.setenv("PREFACTOR_API_URL", "https://api.test.prefactor.ai")
        monkeypatch.setenv("PREFACTOR_API_TOKEN", "test-token")
        monkeypatch.setenv("PREFACTOR_AGENT_ID", "test-agent")
        monkeypatch.setenv("PREFACTOR_AGENT_VERSION", "1.0.0")

        config = Config()

        assert config.transport_type == "http"
        assert config.http_config is not None
        assert config.http_config.api_url == "https://api.test.prefactor.ai"
        assert config.http_config.api_token == "test-token"
        assert config.http_config.agent_id == "test-agent"
        assert config.http_config.agent_version == "1.0.0"
