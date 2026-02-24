"""Configuration for prefactor-core.

This module contains configuration classes for the prefactor-core SDK.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from prefactor_http.config import HttpClientConfig
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


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


class PrefactorCoreConfig(BaseModel):
    """Complete configuration for PrefactorCoreClient.

    Attributes:
        http_config: Configuration for the HTTP client.
        queue_config: Configuration for queue processing.
        schema_registry: Optional schema registry for aggregating span type definitions.

    Example:
        from prefactor_core.schema_registry import SchemaRegistry
        from prefactor_core import PrefactorCoreConfig

        registry = SchemaRegistry()
        registry.register("langchain:llm", {"type": "object"})

        config = PrefactorCoreConfig(
            http_config=HttpClientConfig(...),
            schema_registry=registry
        )
    """

    http_config: HttpClientConfig
    queue_config: QueueConfig = Field(default_factory=QueueConfig)
    schema_registry: Any = Field(
        default=None,
        description="Optional SchemaRegistry for aggregating span type definitions",
    )


__all__ = ["QueueConfig", "PrefactorCoreConfig"]
