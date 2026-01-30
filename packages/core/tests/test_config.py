"""Tests for configuration."""

import pytest
from prefactor_core import Config


class TestConfig:
    """Test Config class."""

    def test_config_defaults(self, monkeypatch):
        """Test default configuration values."""
        # Clear all env vars
        for key in [
            "PREFACTOR_SAMPLE_RATE",
            "PREFACTOR_CAPTURE_INPUTS",
            "PREFACTOR_CAPTURE_OUTPUTS",
            "PREFACTOR_MAX_INPUT_LENGTH",
            "PREFACTOR_MAX_OUTPUT_LENGTH",
        ]:
            monkeypatch.delenv(key, raising=False)

        config = Config()

        assert config.sample_rate == 1.0
        assert config.capture_inputs is True
        assert config.capture_outputs is True
        assert config.max_input_length == 10000
        assert config.max_output_length == 10000

    def test_config_from_env_vars(self, monkeypatch):
        """Test loading configuration from environment variables."""
        monkeypatch.setenv("PREFACTOR_SAMPLE_RATE", "0.5")
        monkeypatch.setenv("PREFACTOR_CAPTURE_INPUTS", "false")
        monkeypatch.setenv("PREFACTOR_CAPTURE_OUTPUTS", "false")
        monkeypatch.setenv("PREFACTOR_MAX_INPUT_LENGTH", "5000")
        monkeypatch.setenv("PREFACTOR_MAX_OUTPUT_LENGTH", "8000")

        config = Config()

        assert config.sample_rate == 0.5
        assert config.capture_inputs is False
        assert config.capture_outputs is False
        assert config.max_input_length == 5000
        assert config.max_output_length == 8000

    def test_config_explicit_values(self):
        """Test creating config with explicit values."""
        config = Config(
            sample_rate=0.3,
            capture_inputs=False,
            capture_outputs=True,
            max_input_length=2000,
            max_output_length=3000,
        )

        assert config.sample_rate == 0.3
        assert config.capture_inputs is False
        assert config.capture_outputs is True
        assert config.max_input_length == 2000
        assert config.max_output_length == 3000

    def test_config_explicit_overrides_env(self, monkeypatch):
        """Test that explicit values override environment variables."""
        monkeypatch.setenv("PREFACTOR_SAMPLE_RATE", "0.5")

        config = Config(
            sample_rate=0.8,
        )

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
            sample_rate=0.5,
        )

        repr_str = repr(config)
        assert "Config" in repr_str
        assert "0.5" in repr_str
