"""Utilities for extracting metadata from LangChain objects."""

import traceback
from typing import Any, Optional

from prefactor_sdk.tracing.span import ErrorInfo, TokenUsage
from prefactor_sdk.utils.logging import get_logger

logger = get_logger("instrumentation.langchain.metadata_extractor")


def extract_token_usage(llm_result: Any) -> Optional[TokenUsage]:
    """
    Extract token usage from LangChain LLMResult.

    Args:
        llm_result: The LLMResult object from LangChain.

    Returns:
        TokenUsage if available, None otherwise.
    """
    try:
        if not hasattr(llm_result, "llm_output") or llm_result.llm_output is None:
            return None

        llm_output = llm_result.llm_output

        # Try different possible keys for token usage
        usage_data = None

        # Try "token_usage" key (OpenAI and others)
        if "token_usage" in llm_output:
            usage_data = llm_output["token_usage"]
        # Try "usage" key (alternative format)
        elif "usage" in llm_output:
            usage_data = llm_output["usage"]

        if usage_data is None:
            return None

        # Extract token counts
        prompt_tokens = usage_data.get("prompt_tokens")
        completion_tokens = usage_data.get("completion_tokens")
        total_tokens = usage_data.get("total_tokens")

        # All fields must be present
        if (
            prompt_tokens is not None
            and completion_tokens is not None
            and total_tokens is not None
        ):
            return TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )

        return None

    except Exception as e:
        logger.debug(f"Failed to extract token usage: {e}")
        return None


def extract_error_info(error: Exception) -> ErrorInfo:
    """
    Extract error information from an exception.

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
