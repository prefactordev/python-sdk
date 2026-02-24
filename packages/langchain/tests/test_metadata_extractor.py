"""Tests for LangChain metadata extraction."""

from unittest.mock import Mock

from prefactor_langchain.metadata_extractor import (
    extract_error_info,
    extract_token_usage,
)


class TestExtractTokenUsage:
    """Test token usage extraction."""

    def test_extract_token_usage_from_model_response(self):
        """Test extracting token usage from a ModelResponse with usage_metadata."""
        msg = Mock()
        msg.usage_metadata = {
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
        }
        response = Mock()
        response.result = [msg]

        usage = extract_token_usage(response)

        assert usage is not None
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 20
        assert usage.total_tokens == 30

    def test_extract_token_usage_multiple_messages(self):
        """Test accumulating token usage across multiple messages."""
        msg1 = Mock()
        msg1.usage_metadata = {
            "input_tokens": 10,
            "output_tokens": 20,
            "total_tokens": 30,
        }
        msg2 = Mock()
        msg2.usage_metadata = {
            "input_tokens": 5,
            "output_tokens": 5,
            "total_tokens": 10,
        }
        response = Mock()
        response.result = [msg1, msg2]

        usage = extract_token_usage(response)

        assert usage is not None
        assert usage.prompt_tokens == 15
        assert usage.completion_tokens == 25
        assert usage.total_tokens == 40

    def test_extract_token_usage_no_result(self):
        """Test extracting token usage when result is empty."""
        response = Mock()
        response.result = []

        usage = extract_token_usage(response)

        assert usage is None

    def test_extract_token_usage_no_usage_metadata(self):
        """Test extracting token usage when messages have no usage_metadata."""
        msg = Mock()
        msg.usage_metadata = None
        response = Mock()
        response.result = [msg]

        usage = extract_token_usage(response)

        assert usage is None

    def test_extract_token_usage_exception(self):
        """Test extracting token usage when an exception occurs."""
        response = Mock()
        response.result = Mock(side_effect=Exception("Error"))

        usage = extract_token_usage(response)

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
        assert error_info.stacktrace is not None
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
