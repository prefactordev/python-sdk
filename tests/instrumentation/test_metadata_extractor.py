"""Tests for LangChain metadata extraction."""

from unittest.mock import Mock

import pytest

from prefactor_sdk.instrumentation.langchain.metadata_extractor import (
    extract_error_info,
    extract_token_usage,
)
from prefactor_sdk.tracing.span import ErrorInfo, TokenUsage


class TestExtractTokenUsage:
    """Test token usage extraction."""

    def test_extract_token_usage_from_llm_result(self):
        """Test extracting token usage from LLMResult."""
        # Mock LLMResult with llm_output containing token counts
        llm_result = Mock()
        llm_result.llm_output = {
            "token_usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            }
        }

        usage = extract_token_usage(llm_result)

        assert usage is not None
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 20
        assert usage.total_tokens == 30

    def test_extract_token_usage_alternative_keys(self):
        """Test extracting token usage with alternative key names."""
        # Some providers use different keys
        llm_result = Mock()
        llm_result.llm_output = {
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 25,
                "total_tokens": 40,
            }
        }

        usage = extract_token_usage(llm_result)

        assert usage is not None
        assert usage.prompt_tokens == 15
        assert usage.completion_tokens == 25
        assert usage.total_tokens == 40

    def test_extract_token_usage_no_llm_output(self):
        """Test extracting token usage when llm_output is missing."""
        llm_result = Mock()
        llm_result.llm_output = None

        usage = extract_token_usage(llm_result)

        assert usage is None

    def test_extract_token_usage_no_usage_data(self):
        """Test extracting token usage when usage data is missing."""
        llm_result = Mock()
        llm_result.llm_output = {"other_field": "value"}

        usage = extract_token_usage(llm_result)

        assert usage is None

    def test_extract_token_usage_missing_fields(self):
        """Test extracting token usage with missing fields."""
        llm_result = Mock()
        llm_result.llm_output = {
            "token_usage": {
                "prompt_tokens": 10,
                # missing completion_tokens and total_tokens
            }
        }

        usage = extract_token_usage(llm_result)

        # Should return None if required fields are missing
        assert usage is None

    def test_extract_token_usage_exception(self):
        """Test extracting token usage when an exception occurs."""
        llm_result = Mock()
        llm_result.llm_output = Mock()
        llm_result.llm_output.__getitem__ = Mock(side_effect=Exception("Error"))

        usage = extract_token_usage(llm_result)

        # Should return None on exception
        assert usage is None


class TestExtractErrorInfo:
    """Test error info extraction."""

    def test_extract_error_info_basic(self):
        """Test extracting basic error info."""
        error = ValueError("Invalid value")

        error_info = extract_error_info(error)

        assert error_info is not None
        assert error_info.error_type == "ValueError"
        assert error_info.message == "Invalid value"
        assert error_info.stacktrace is not None

    def test_extract_error_info_with_stacktrace(self):
        """Test extracting error info with stacktrace."""
        try:
            raise RuntimeError("Test error")
        except Exception as e:
            error_info = extract_error_info(e)

        assert error_info is not None
        assert error_info.error_type == "RuntimeError"
        assert error_info.message == "Test error"
        assert "RuntimeError" in error_info.stacktrace
        assert "Test error" in error_info.stacktrace

    def test_extract_error_info_nested_exception(self):
        """Test extracting error info from nested exception."""
        try:
            try:
                raise ValueError("Inner error")
            except Exception:
                raise RuntimeError("Outer error")
        except Exception as e:
            error_info = extract_error_info(e)

        assert error_info is not None
        assert error_info.error_type == "RuntimeError"
        assert error_info.message == "Outer error"

    def test_extract_error_info_empty_message(self):
        """Test extracting error info with empty message."""
        error = Exception()

        error_info = extract_error_info(error)

        assert error_info is not None
        assert error_info.error_type == "Exception"
        assert error_info.message == ""

    def test_extract_error_info_custom_exception(self):
        """Test extracting error info from custom exception."""

        class CustomError(Exception):
            pass

        error = CustomError("Custom error message")

        error_info = extract_error_info(error)

        assert error_info is not None
        assert error_info.error_type == "CustomError"
        assert error_info.message == "Custom error message"
