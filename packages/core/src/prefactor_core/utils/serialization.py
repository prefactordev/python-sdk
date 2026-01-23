"""JSON serialization utilities with truncation support."""

from typing import Any


def truncate_string(value: str, max_length: int) -> str:
    """
    Truncate a string to a maximum length.

    Args:
        value: The string to truncate.
        max_length: Maximum length of the string.

    Returns:
        The truncated string with a suffix if truncated.
    """
    if len(value) <= max_length:
        return value
    return value[:max_length] + "... [truncated]"


def serialize_value(value: Any, max_length: int | None = 10000) -> Any:
    """
    Serialize a value for JSON output with truncation support.

    Handles:
    - Truncating long strings
    - Converting non-serializable objects to strings
    - Recursively processing dicts and lists

    Args:
        value: The value to serialize.
        max_length: Maximum length for strings. None means no truncation.

    Returns:
        The serialized value.
    """
    # Handle None
    if value is None:
        return None

    # Handle basic types that are JSON serializable
    if isinstance(value, (bool, int, float)):
        return value

    # Handle strings with truncation
    if isinstance(value, str):
        if max_length is not None:
            return truncate_string(value, max_length)
        return value

    # Handle lists recursively
    if isinstance(value, list):
        return [serialize_value(item, max_length) for item in value]

    # Handle dicts recursively
    if isinstance(value, dict):
        return {key: serialize_value(val, max_length) for key, val in value.items()}

    # Handle bytes
    if isinstance(value, bytes):
        try:
            return repr(value)
        except Exception:
            return "<bytes object>"

    # Handle non-serializable objects
    try:
        # Try to convert to string
        return str(value)
    except Exception:
        # If that fails, return a generic representation
        return f"<{type(value).__name__} object>"
