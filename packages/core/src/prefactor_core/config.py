"""Configuration for Prefactor SDK."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from prefactor_core.utils.logging import get_logger

logger = get_logger("config")


@dataclass
class HttpTransportConfig:
    """Configuration for HTTP transport."""

    # API connection
    api_url: str
    api_token: str

    # Agent metadata (optional, auto-detected if not provided)
    agent_id: Optional[str] = None
    agent_version: Optional[str] = None
    agent_name: Optional[str] = None

    # Schema configuration (BYO schema support)
    agent_schema: Optional[dict[str, Any]] = None  # Full custom schema
    agent_schema_version: Optional[str] = None  # Schema version identifier only
    skip_schema: bool = False  # Skip schema in registration

    # HTTP settings
    request_timeout: float = 30.0
    connect_timeout: float = 10.0

    # Retry settings
    max_retries: int = 3
    initial_retry_delay: float = 1.0
    max_retry_delay: float = 60.0
    retry_multiplier: float = 2.0


def _parse_bool(value: str) -> bool:
    """Parse a string to boolean."""
    return value.lower() in ("true", "1", "yes")


def _get_env_or_default(
    key: str,
    default: Any,
    converter: Callable[[str], Any] = str,
) -> Any:
    """Get environment variable or return default."""
    value = os.getenv(key)
    if value is None:
        return default

    try:
        return converter(value)
    except (ValueError, TypeError):
        logger.warning(f"Invalid value for {key}: {value}, using default: {default}")
        return default


@dataclass
class Config:
    """Configuration for Prefactor SDK."""

    transport_type: str = "stdio"
    sample_rate: float = 1.0
    capture_inputs: bool = True
    capture_outputs: bool = True
    max_input_length: int = 10000
    max_output_length: int = 10000
    http_config: Optional[HttpTransportConfig] = None

    def __init__(
        self,
        transport_type: Optional[str] = None,
        sample_rate: Optional[float] = None,
        capture_inputs: Optional[bool] = None,
        capture_outputs: Optional[bool] = None,
        max_input_length: Optional[int] = None,
        max_output_length: Optional[int] = None,
        api_url: Optional[str] = None,
        api_token: Optional[str] = None,
        agent_id: Optional[str] = None,
        agent_version: Optional[str] = None,
        agent_schema: Optional[dict[str, Any]] = None,
        agent_schema_version: Optional[str] = None,
        skip_schema: Optional[bool] = None,
    ):
        """
        Initialize configuration.

        Args:
            transport_type: Transport type (default: "stdio").
            sample_rate: Sampling rate 0.0-1.0 (default: 1.0).
            capture_inputs: Whether to capture inputs (default: True).
            capture_outputs: Whether to capture outputs (default: True).
            max_input_length: Max input length in bytes (default: 10000).
            max_output_length: Max output length in bytes (default: 10000).
            api_url: API URL for HTTP transport (env: PREFACTOR_API_URL).
            api_token: API token for HTTP transport (env: PREFACTOR_API_TOKEN).
            agent_id: Agent ID (env: PREFACTOR_AGENT_ID).
            agent_version: Agent version (env: PREFACTOR_AGENT_VERSION).
            agent_schema: Full custom schema dict
                (env: PREFACTOR_AGENT_SCHEMA as JSON).
            agent_schema_version: Schema version identifier
                (env: PREFACTOR_AGENT_SCHEMA_VERSION).
            skip_schema: Skip schema in registration (env: PREFACTOR_SKIP_SCHEMA).
        """
        # Load from environment variables or use defaults
        self.transport_type = transport_type or _get_env_or_default(
            "PREFACTOR_TRANSPORT",
            "stdio",
        )

        self.sample_rate = (
            sample_rate
            if sample_rate is not None
            else _get_env_or_default(
                "PREFACTOR_SAMPLE_RATE",
                1.0,
                float,
            )
        )

        self.capture_inputs = (
            capture_inputs
            if capture_inputs is not None
            else _get_env_or_default(
                "PREFACTOR_CAPTURE_INPUTS",
                True,
                _parse_bool,
            )
        )

        self.capture_outputs = (
            capture_outputs
            if capture_outputs is not None
            else _get_env_or_default(
                "PREFACTOR_CAPTURE_OUTPUTS",
                True,
                _parse_bool,
            )
        )

        self.max_input_length = (
            max_input_length
            if max_input_length is not None
            else _get_env_or_default(
                "PREFACTOR_MAX_INPUT_LENGTH",
                10000,
                int,
            )
        )

        self.max_output_length = (
            max_output_length
            if max_output_length is not None
            else _get_env_or_default(
                "PREFACTOR_MAX_OUTPUT_LENGTH",
                10000,
                int,
            )
        )

        # Validate sample rate
        if not 0.0 <= self.sample_rate <= 1.0:
            raise ValueError("sample_rate must be between 0.0 and 1.0")

        # Initialize HTTP config if transport is HTTP or HTTP params provided
        if self.transport_type == "http" or api_url or api_token:
            final_api_url = api_url or os.getenv("PREFACTOR_API_URL")
            final_api_token = api_token or os.getenv("PREFACTOR_API_TOKEN")

            if not final_api_url:
                raise ValueError(
                    "HTTP transport requires api_url parameter or "
                    "PREFACTOR_API_URL environment variable"
                )

            if not final_api_token:
                raise ValueError(
                    "HTTP transport requires api_token parameter or "
                    "PREFACTOR_API_TOKEN environment variable"
                )

            # Parse schema configuration (with env var fallbacks)
            final_skip_schema = (
                skip_schema
                if skip_schema is not None
                else _get_env_or_default("PREFACTOR_SKIP_SCHEMA", False, _parse_bool)
            )

            final_schema_version = (
                agent_schema_version
                if agent_schema_version is not None
                else os.getenv("PREFACTOR_AGENT_SCHEMA_VERSION")
            )

            # Parse agent_schema from env or param (with JSON parsing)
            final_agent_schema = agent_schema
            if final_agent_schema is None:
                schema_json = os.getenv("PREFACTOR_AGENT_SCHEMA")
                if schema_json:
                    try:
                        import json

                        final_agent_schema = json.loads(schema_json)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(
                            f"Failed to parse PREFACTOR_AGENT_SCHEMA: {e}, "
                            "using default schema"
                        )
                        final_agent_schema = None

            self.http_config = HttpTransportConfig(
                api_url=final_api_url,
                api_token=final_api_token,
                agent_id=agent_id or os.getenv("PREFACTOR_AGENT_ID"),
                agent_version=agent_version or os.getenv("PREFACTOR_AGENT_VERSION"),
                agent_schema=final_agent_schema,
                agent_schema_version=final_schema_version,
                skip_schema=final_skip_schema,
            )

            # Validate schema configuration (mutual exclusivity)
            schema_options_set = sum(
                [
                    self.http_config.skip_schema,
                    self.http_config.agent_schema is not None,
                    self.http_config.agent_schema_version is not None,
                ]
            )

            if schema_options_set > 1:
                raise ValueError(
                    "Only one schema option can be specified: "
                    "skip_schema=True, agent_schema, or agent_schema_version. "
                    f"Currently {schema_options_set} options are set."
                )

            # Validate agent_schema structure if provided
            if self.http_config.agent_schema is not None:
                schema = self.http_config.agent_schema

                if not isinstance(schema, dict):
                    raise ValueError(
                        f"agent_schema must be a dictionary, "
                        f"got {type(schema).__name__}"
                    )

                required_keys = {"external_identifier", "span_schemas"}
                missing_keys = required_keys - set(schema.keys())
                if missing_keys:
                    raise ValueError(
                        f"agent_schema missing required keys: {missing_keys}"
                    )

                if not isinstance(schema["span_schemas"], dict):
                    raise ValueError(
                        "agent_schema['span_schemas'] must be a dictionary"
                    )

                if not isinstance(schema["external_identifier"], str):
                    raise ValueError(
                        "agent_schema['external_identifier'] must be a string"
                    )

            # Validate agent_schema_version if provided
            if self.http_config.agent_schema_version is not None:
                if not isinstance(self.http_config.agent_schema_version, str):
                    raise ValueError(
                        "agent_schema_version must be a string, "
                        f"got {type(self.http_config.agent_schema_version).__name__}"
                    )

                if not self.http_config.agent_schema_version.strip():
                    raise ValueError("agent_schema_version cannot be empty")

    def __repr__(self) -> str:
        """Return string representation of config."""
        return (
            f"Config(transport_type={self.transport_type!r}, "
            f"sample_rate={self.sample_rate}, "
            f"capture_inputs={self.capture_inputs}, "
            f"capture_outputs={self.capture_outputs}, "
            f"max_input_length={self.max_input_length}, "
            f"max_output_length={self.max_output_length})"
        )
