"""Tests for configuration."""

import pytest
from prefactor_sdk import Config


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

    def test_http_transport_missing_url(self, monkeypatch):
        """Test HTTP transport with missing URL raises ValueError."""
        # Clear env vars that could interfere
        monkeypatch.delenv("PREFACTOR_API_URL", raising=False)
        monkeypatch.delenv("PREFACTOR_API_TOKEN", raising=False)
        monkeypatch.delenv("PREFACTOR_SKIP_SCHEMA", raising=False)
        monkeypatch.delenv("PREFACTOR_AGENT_SCHEMA", raising=False)
        monkeypatch.delenv("PREFACTOR_AGENT_SCHEMA_VERSION", raising=False)

        with pytest.raises(ValueError, match="api_url"):
            Config(
                transport_type="http",
                api_token="test-token",
            )

    def test_http_transport_missing_token(self, monkeypatch):
        """Test HTTP transport with missing token raises ValueError."""
        # Clear env vars that could interfere
        monkeypatch.delenv("PREFACTOR_API_URL", raising=False)
        monkeypatch.delenv("PREFACTOR_API_TOKEN", raising=False)
        monkeypatch.delenv("PREFACTOR_SKIP_SCHEMA", raising=False)
        monkeypatch.delenv("PREFACTOR_AGENT_SCHEMA", raising=False)
        monkeypatch.delenv("PREFACTOR_AGENT_SCHEMA_VERSION", raising=False)

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

    def test_schema_default_mode(self):
        """Test default schema mode (no schema params)."""
        config = Config(
            transport_type="http",
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
        )

        assert config.http_config is not None
        assert config.http_config.skip_schema is False
        assert config.http_config.agent_schema is None
        assert config.http_config.agent_schema_version is None

    def test_schema_skip_mode(self):
        """Test skip schema mode."""
        config = Config(
            transport_type="http",
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            skip_schema=True,
        )

        assert config.http_config is not None
        assert config.http_config.skip_schema is True
        assert config.http_config.agent_schema is None
        assert config.http_config.agent_schema_version is None

    def test_schema_skip_mode_from_env(self, monkeypatch):
        """Test skip schema mode from environment variable."""
        monkeypatch.setenv("PREFACTOR_SKIP_SCHEMA", "true")

        config = Config(
            transport_type="http",
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
        )

        assert config.http_config is not None
        assert config.http_config.skip_schema is True

    def test_schema_custom_mode(self):
        """Test custom schema mode."""
        custom_schema = {
            "external_identifier": "custom-v2",
            "span_schemas": {"llm": {"type": "object"}},
        }

        config = Config(
            transport_type="http",
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            agent_schema=custom_schema,
        )

        assert config.http_config is not None
        assert config.http_config.agent_schema == custom_schema
        assert config.http_config.skip_schema is False
        assert config.http_config.agent_schema_version is None

    def test_schema_custom_mode_from_env(self, monkeypatch):
        """Test custom schema mode from environment variable."""
        schema_json = '{"external_identifier": "v2", "span_schemas": {}}'
        monkeypatch.setenv("PREFACTOR_AGENT_SCHEMA", schema_json)

        config = Config(
            transport_type="http",
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
        )

        assert config.http_config is not None
        assert config.http_config.agent_schema is not None
        assert config.http_config.agent_schema["external_identifier"] == "v2"

    def test_schema_version_mode(self):
        """Test schema version mode."""
        config = Config(
            transport_type="http",
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            agent_schema_version="2.0.0",
        )

        assert config.http_config is not None
        assert config.http_config.agent_schema_version == "2.0.0"
        assert config.http_config.skip_schema is False
        assert config.http_config.agent_schema is None

    def test_schema_version_mode_from_env(self, monkeypatch):
        """Test schema version mode from environment variable."""
        monkeypatch.setenv("PREFACTOR_AGENT_SCHEMA_VERSION", "3.0.0")

        config = Config(
            transport_type="http",
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
        )

        assert config.http_config is not None
        assert config.http_config.agent_schema_version == "3.0.0"

    def test_schema_mutual_exclusivity_skip_and_custom(self):
        """Test that skip_schema and agent_schema are mutually exclusive."""
        custom_schema = {
            "external_identifier": "v2",
            "span_schemas": {},
        }

        with pytest.raises(ValueError, match="Only one schema option"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                skip_schema=True,
                agent_schema=custom_schema,
            )

    def test_schema_mutual_exclusivity_skip_and_version(self):
        """Test that skip_schema and agent_schema_version are mutually exclusive."""
        with pytest.raises(ValueError, match="Only one schema option"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                skip_schema=True,
                agent_schema_version="2.0.0",
            )

    def test_schema_mutual_exclusivity_custom_and_version(self):
        """Test that agent_schema and agent_schema_version are mutually exclusive."""
        custom_schema = {
            "external_identifier": "v2",
            "span_schemas": {},
        }

        with pytest.raises(ValueError, match="Only one schema option"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema=custom_schema,
                agent_schema_version="2.0.0",
            )

    def test_schema_mutual_exclusivity_all_three(self):
        """Test that all three schema options are mutually exclusive."""
        custom_schema = {
            "external_identifier": "v2",
            "span_schemas": {},
        }

        with pytest.raises(ValueError, match="Only one schema option"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                skip_schema=True,
                agent_schema=custom_schema,
                agent_schema_version="2.0.0",
            )

    def test_schema_validation_missing_external_identifier(self):
        """Test that agent_schema must have external_identifier."""
        invalid_schema = {"span_schemas": {}}

        with pytest.raises(ValueError, match="missing required keys"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema=invalid_schema,
            )

    def test_schema_validation_missing_span_schemas(self):
        """Test that agent_schema must have span_schemas."""
        invalid_schema = {"external_identifier": "v2"}

        with pytest.raises(ValueError, match="missing required keys"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema=invalid_schema,
            )

    def test_schema_validation_wrong_type(self):
        """Test that agent_schema must be a dict."""
        with pytest.raises(ValueError, match="must be a dictionary"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema="not-a-dict",  # type: ignore[arg-type]
            )

    def test_schema_validation_span_schemas_wrong_type(self):
        """Test that span_schemas must be a dict."""
        invalid_schema = {
            "external_identifier": "v2",
            "span_schemas": "not-a-dict",
        }

        with pytest.raises(ValueError, match="span_schemas.*must be a dictionary"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema=invalid_schema,
            )

    def test_schema_validation_external_identifier_wrong_type(self):
        """Test that external_identifier must be a string."""
        invalid_schema = {
            "external_identifier": 123,
            "span_schemas": {},
        }

        with pytest.raises(ValueError, match="external_identifier.*must be a string"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema=invalid_schema,
            )

    def test_schema_version_validation_empty_string(self, monkeypatch):
        """Test that agent_schema_version cannot be empty."""
        # Clear env vars that could interfere
        monkeypatch.delenv("PREFACTOR_SKIP_SCHEMA", raising=False)
        monkeypatch.delenv("PREFACTOR_AGENT_SCHEMA", raising=False)
        monkeypatch.delenv("PREFACTOR_AGENT_SCHEMA_VERSION", raising=False)

        with pytest.raises(ValueError, match="cannot be empty"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema_version="",
            )

    def test_schema_version_validation_wrong_type(self):
        """Test that agent_schema_version must be a string."""
        with pytest.raises(ValueError, match="must be a string"):
            Config(
                transport_type="http",
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema_version=123,  # type: ignore[arg-type]
            )

    def test_schema_invalid_json_from_env(self, monkeypatch):
        """Test handling of invalid JSON in PREFACTOR_AGENT_SCHEMA."""
        monkeypatch.setenv("PREFACTOR_AGENT_SCHEMA", "{invalid json}")

        # Should not raise, just log warning and use default
        config = Config(
            transport_type="http",
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
        )

        assert config.http_config is not None
        assert config.http_config.agent_schema is None  # Falls back to None

    def test_schema_explicit_overrides_env(self, monkeypatch):
        """Test that explicit schema params override environment variables."""
        # Set env var for agent_schema_version
        monkeypatch.setenv("PREFACTOR_AGENT_SCHEMA_VERSION", "env-version")
        monkeypatch.delenv("PREFACTOR_SKIP_SCHEMA", raising=False)
        monkeypatch.delenv("PREFACTOR_AGENT_SCHEMA", raising=False)

        # Explicitly override with a different schema version
        config = Config(
            transport_type="http",
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            agent_schema_version="explicit-version",
        )

        assert config.http_config is not None
        # Explicit param should override env var
        assert config.http_config.agent_schema_version == "explicit-version"
        assert config.http_config.skip_schema is False
        assert config.http_config.agent_schema is None
