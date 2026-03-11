"""Utility functions for prefactor-core."""

from __future__ import annotations

import uuid


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


__all__ = ["generate_idempotency_key", "validate_idempotency_key"]
