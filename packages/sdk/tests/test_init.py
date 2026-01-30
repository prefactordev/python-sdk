"""Tests for public API (with new SdkConfig)."""

import prefactor_sdk
import pytest
from prefactor_sdk import HttpTracer, SdkConfig, init


class TestInit:
    """Test init() function with new SdkConfig."""

    def setup_method(self):
        """Reset global state before each test."""
        prefactor_sdk._global_http_client = None
        prefactor_sdk._global_tracer = None
        prefactor_sdk._global_handler = None
        prefactor_sdk._global_middleware = None
        prefactor_sdk._global_sdk_config = None

    def test_init_succeeds_when_env_configured(self, monkeypatch):
        """Test initialization with environment configuration."""
        monkeypatch.setenv("PREFACTOR_API_URL", "https://api.test.prefactor.ai")
        monkeypatch.setenv("PREFACTOR_API_TOKEN", "test-token")

        middleware = init()

        assert middleware is not None
        assert prefactor_sdk._global_tracer is not None
        assert isinstance(prefactor_sdk._global_tracer, HttpTracer)

    def test_init_with_config(self, monkeypatch):
        """Test initialization with explicit SdkConfig."""
        config = SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            sample_rate=0.5,
        )

        middleware = init(config)

        assert middleware is not None
        assert prefactor_sdk._global_tracer is not None

    def test_init_missing_config_error(self, monkeypatch):
        """Test initialization fails without configuration."""
        monkeypatch.delenv("PREFACTOR_API_URL", raising=False)
        monkeypatch.delenv("PREFACTOR_API_TOKEN", raising=False)

        with pytest.raises(ValueError):
            init()

    def test_init_creates_single_instance(self):
        """Test calling init() multiple times returns same instance."""
        config = SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
        )

        middleware1 = init(config)
        middleware2 = init(config)

        assert middleware1 is middleware2
        assert prefactor_sdk._global_middleware is middleware1


class TestSdkConfig:
    """Test SdkConfig class."""

    def test_config_with_required_params(self):
        """Test creating config with required parameters."""
        config = SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
        )

        assert config.api_url == "https://api.test.prefactor.ai"
        assert config.api_token == "test-token"
        # Should have auto-detected agent_id
        assert config.agent_id is not None
        # Should have auto-detected agent_version
        assert config.agent_version is not None

    def test_config_custom_values(self):
        """Test creating config with custom values."""
        config = SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            agent_id="my-agent",
            agent_version="1.0.0",
            agent_name="Test Agent",
            sample_rate=0.5,
            capture_inputs=False,
            capture_outputs=True,
            max_input_length=5000,
            max_output_length=8000,
        )

        assert config.agent_id == "my-agent"
        assert config.agent_version == "1.0.0"
        assert config.agent_name == "Test Agent"
        assert config.sample_rate == 0.5
        assert config.capture_inputs is False
        assert config.capture_outputs is True
        assert config.max_input_length == 5000
        assert config.max_output_length == 8000

    def test_config_sample_rate_validation(self):
        """Test sample rate validation."""
        # Valid sample rates
        SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            sample_rate=0.0,
        )

        SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            sample_rate=1.0,
        )

        # Invalid sample rates should raise
        with pytest.raises(ValueError):
            SdkConfig(
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                sample_rate=-0.1,
            )

        with pytest.raises(ValueError):
            SdkConfig(
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                sample_rate=1.5,
            )

    def test_config_http_client_config_conversion(self):
        """Test conversion to HttpClientConfig."""
        config = SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            request_timeout=60.0,
            connect_timeout=15.0,
            max_retries=5,
        )

        http_config = config.to_http_client_config()

        assert http_config.api_url == "https://api.test.prefactor.ai"
        assert http_config.api_token == "test-token"
        assert http_config.request_timeout == 60.0
        assert http_config.connect_timeout == 15.0
        assert http_config.max_retries == 5

    def test_config_core_config_conversion(self):
        """Test conversion to core Config."""
        config = SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            sample_rate=0.5,
            capture_inputs=False,
        )

        core_config = config.to_core_config()

        assert core_config.sample_rate == 0.5
        assert core_config.capture_inputs is False

    def test_config_default_schema_generation(self):
        """Test default schema generation."""
        config = SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
        )

        metadata = config.build_agent_metadata()

        assert "agent_id" in metadata
        assert "agent_version" in metadata
        assert "agent_schema_version" in metadata
        assert metadata["agent_schema_version"]["external_identifier"] == "1.0.0"

    def test_config_custom_schema(self):
        """Test custom schema configuration."""
        custom_schema = {
            "external_identifier": "custom-v2",
            "span_schemas": {"llm": {"type": "object"}},
        }

        config = SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            agent_schema=custom_schema,
        )

        metadata = config.build_agent_metadata()
        assert metadata["agent_schema_version"] == custom_schema

    def test_config_schema_version_only(self):
        """Test schema version identifier only."""
        config = SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            agent_schema_version="2.0.0",
        )

        metadata = config.build_agent_metadata()
        assert metadata["agent_schema_version"]["external_identifier"] == "2.0.0"

    def test_config_skip_schema(self):
        """Test skip schema mode."""
        config = SdkConfig(
            api_url="https://api.test.prefactor.ai",
            api_token="test-token",
            skip_schema=True,
        )

        metadata = config.build_agent_metadata()
        # Should not include agent_schema_version key
        assert "agent_schema_version" not in metadata

    def test_config_schema_mutual_exclusivity(self):
        """Test that schema options are mutually exclusive."""
        # skip_schema + agent_schema
        with pytest.raises(ValueError, match="Only one schema option"):
            SdkConfig(
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                skip_schema=True,
                agent_schema={"external_identifier": "v1", "span_schemas": {}},
            )

        # skip_schema + agent_schema_version
        with pytest.raises(ValueError, match="Only one schema option"):
            SdkConfig(
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                skip_schema=True,
                agent_schema_version="1.0.0",
            )

        # agent_schema + agent_schema_version
        with pytest.raises(ValueError, match="Only one schema option"):
            SdkConfig(
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema={"external_identifier": "v1", "span_schemas": {}},
                agent_schema_version="2.0.0",
            )

    def test_config_invalid_agent_schema_structure(self):
        """Test validation of agent_schema structure."""
        # Missing required keys
        with pytest.raises(ValueError, match="missing required keys"):
            SdkConfig(
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema={"external_identifier": "v1"},  # missing span_schemas
            )

        # Wrong type for span_schemas
        with pytest.raises(ValueError, match="must be a dictionary"):
            SdkConfig(
                api_url="https://api.test.prefactor.ai",
                api_token="test-token",
                agent_schema={
                    "external_identifier": "v1",
                    "span_schemas": "not-a-dict",
                },
            )
