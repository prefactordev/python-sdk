"""Configuration for Prefactor Core SDK."""

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from prefactor_core.utils.logging import get_logger

logger = get_logger("config")


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
    """Configuration for Prefactor Core SDK.

    Core configuration only contains capture behavior settings.
    HTTP transport configuration is managed by prefactor-sdk.
    """

    sample_rate: float = 1.0
    capture_inputs: bool = True
    capture_outputs: bool = True
    max_input_length: int = 10000
    max_output_length: int = 10000

    def __init__(
        self,
        sample_rate: float | None = None,
        capture_inputs: bool | None = None,
        capture_outputs: bool | None = None,
        max_input_length: int | None = None,
        max_output_length: int | None = None,
    ):
        """
        Initialize core configuration.

        Args:
            sample_rate: Sampling rate 0.0-1.0 (default: 1.0).
            capture_inputs: Whether to capture inputs (default: True).
            capture_outputs: Whether to capture outputs (default: True).
            max_input_length: Max input length in bytes (default: 10000).
            max_output_length: Max output length in bytes (default: 10000).
        """
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

    def __repr__(self) -> str:
        """Return string representation of config."""
        return (
            f"Config(sample_rate={self.sample_rate}, "
            f"capture_inputs={self.capture_inputs}, "
            f"capture_outputs={self.capture_outputs}, "
            f"max_input_length={self.max_input_length}, "
            f"max_output_length={self.max_output_length})"
        )
