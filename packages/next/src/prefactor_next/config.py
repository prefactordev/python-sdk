"""Configuration for prefactor-next.

This module contains configuration classes for the prefactor-next SDK.
"""

from prefactor_http.config import HttpClientConfig
from pydantic import BaseModel, Field


class QueueConfig(BaseModel):
    """Configuration for queue processing.

    Attributes:
        num_workers: Number of concurrent worker tasks.
        max_retries: Maximum retry attempts per failed operation.
        retry_delay_base: Base delay for exponential backoff (seconds).
    """

    num_workers: int = Field(default=3, ge=1, le=20)
    max_retries: int = Field(default=3, ge=0)
    retry_delay_base: float = Field(default=1.0, gt=0)


class PrefactorNextConfig(BaseModel):
    """Complete configuration for PrefactorNextClient.

    Attributes:
        http_config: Configuration for the HTTP client.
        queue_config: Configuration for queue processing.
    """

    http_config: HttpClientConfig
    queue_config: QueueConfig = Field(default_factory=QueueConfig)


__all__ = ["QueueConfig", "PrefactorNextConfig"]
