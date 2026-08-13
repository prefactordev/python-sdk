"""Utility functions for prefactor-core."""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def generate_idempotency_key() -> str:
    """Generate a new UUID-based idempotency key.

    The returned key is a UUID4 string (36 characters), always within the
    64-character API limit.

    Returns:
        A unique idempotency key string.
    """
    return str(uuid.uuid4())


def validate_idempotency_key(key: str) -> str:
    """Validate that an idempotency key is a non-empty string of at most 64 characters.

    Args:
        key: The idempotency key to validate.

    Returns:
        The key unchanged if valid.

    Raises:
        ValueError: If the key is empty or exceeds 64 characters.
    """
    if not key:
        raise ValueError("Idempotency key must not be empty")
    if len(key) > 64:
        raise ValueError(
            f"Idempotency key must be at most 64 characters, got {len(key)}"
        )
    return key


def warn_missing_adaptor_config(
    instance_id: str,
    adaptor_name: str,
    create_client_call: str,
) -> None:
    """Warn that an instance was registered before the adaptor configured the client.

    Called by framework adaptors (langchain, livekit, etc.) when a
    pre-created instance is passed in and the backing client wasn't set up
    through :meth:`create_client` or :meth:`from_config`.

    Args:
        instance_id: The agent instance ID that was registered too early.
        adaptor_name: Human-readable adaptor name (e.g. ``"middleware"``).
        create_client_call: The call the user should use instead
            (e.g. ``"PrefactorMiddleware.create_client(config)"``).
    """
    logger.warning(
        "Agent instance %s was registered before the %s "
        "could configure the client. Use %s to create the "
        "client before creating the instance.",
        instance_id,
        adaptor_name,
        create_client_call,
    )


__all__ = [
    "generate_idempotency_key",
    "validate_idempotency_key",
    "warn_missing_adaptor_config",
]
