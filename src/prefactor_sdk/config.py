"""Configuration for Prefactor SDK."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from prefactor_sdk.utils.logging import get_logger

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
                    "HTTP transport requires api_url parameter or PREFACTOR_API_URL environment variable"
                )

            if not final_api_token:
                raise ValueError(
                    "HTTP transport requires api_token parameter or PREFACTOR_API_TOKEN environment variable"
                )

            self.http_config = HttpTransportConfig(
                api_url=final_api_url,
                api_token=final_api_token,
                agent_id=agent_id or os.getenv("PREFACTOR_AGENT_ID"),
                agent_version=agent_version or os.getenv("PREFACTOR_AGENT_VERSION"),
            )

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
