"""Utilities for extracting metadata from LangChain objects."""

import logging
import traceback
from typing import Any, Optional

from .spans import ErrorInfo, TokenUsage

logger = logging.getLogger("prefactor_langchain.metadata_extractor")


def extract_token_usage(response: Any) -> Optional[TokenUsage]:
    """Extract token usage from a ModelResponse.

    Checks each message in ``response.result`` for ``usage_metadata``
    (the standard LangChain field populated by all providers), accumulating
    totals across messages.

    Args:
        response: A ModelResponse object from LangChain.

    Returns:
        TokenUsage if available, None otherwise.
    """
    try:
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        found = False

        messages = getattr(response, "result", None) or []
        for msg in messages:
            usage = getattr(msg, "usage_metadata", None)
            if not usage:
                continue
            # usage_metadata keys: input_tokens, output_tokens, total_tokens
            prompt_tokens += usage.get("input_tokens", 0)
            completion_tokens += usage.get("output_tokens", 0)
            total_tokens += usage.get("total_tokens", 0)
            found = True

        if not found:
            return None

        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens or (prompt_tokens + completion_tokens),
        )

    except Exception as e:
        logger.debug(f"Failed to extract token usage: {e}")
        return None


def extract_error_info(error: Exception) -> ErrorInfo:
    """Extract error information from an exception.

    Args:
        error: The exception to extract information from.

    Returns:
        ErrorInfo containing error details.
    """
    return ErrorInfo(
        error_type=type(error).__name__,
        message=str(error),
        stacktrace=traceback.format_exc(),
    )
