"""Tests for JSON serialization utilities."""

from prefactor_sdk.utils.serialization import serialize_value, truncate_string


class TestTruncateString:
    """Test string truncation."""

    def test_truncate_short_string(self):
        """Test truncating a string shorter than max length."""
        result = truncate_string("hello", max_length=100)
        assert result == "hello"

    def test_truncate_exact_length(self):
        """Test truncating a string at exactly max length."""
        result = truncate_string("hello", max_length=5)
        assert result == "hello"

    def test_truncate_long_string(self):
        """Test truncating a string longer than max length."""
        result = truncate_string("hello world", max_length=5)
        assert result == "hello... [truncated]"

    def test_truncate_very_long_string(self):
        """Test truncating a very long string."""
        long_string = "a" * 10000
        result = truncate_string(long_string, max_length=100)
        assert len(result) == 115  # 100 + len("... [truncated]")
        assert result.endswith("... [truncated]")

    def test_truncate_empty_string(self):
        """Test truncating an empty string."""
        result = truncate_string("", max_length=100)
        assert result == ""


class TestSerializeValue:
    """Test value serialization."""

    def test_serialize_simple_types(self):
        """Test serializing simple types."""
        assert serialize_value(42) == 42
        assert serialize_value(3.14) == 3.14
        assert serialize_value("hello") == "hello"
        assert serialize_value(True) is True
        assert serialize_value(None) is None

    def test_serialize_list(self):
        """Test serializing a list."""
        assert serialize_value([1, 2, 3]) == [1, 2, 3]
        assert serialize_value(["a", "b", "c"]) == ["a", "b", "c"]

    def test_serialize_dict(self):
        """Test serializing a dict."""
        assert serialize_value({"key": "value"}) == {"key": "value"}
        assert serialize_value({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    def test_serialize_nested_dict(self):
        """Test serializing a nested dict."""
        data = {"outer": {"inner": {"value": 42}}}
        assert serialize_value(data) == data

    def test_serialize_long_string(self):
        """Test serializing a long string gets truncated."""
        long_string = "a" * 10000
        result = serialize_value(long_string, max_length=100)
        assert result.endswith("... [truncated]")
        assert len(result) == 115

    def test_serialize_dict_with_long_value(self):
        """Test serializing a dict with long string value."""
        long_string = "a" * 10000
        data = {"key": long_string}
        result = serialize_value(data, max_length=100)
        assert result["key"].endswith("... [truncated]")

    def test_serialize_list_with_long_string(self):
        """Test serializing a list with long string."""
        long_string = "a" * 10000
        data = ["short", long_string, "another"]
        result = serialize_value(data, max_length=100)
        assert result[0] == "short"
        assert result[1].endswith("... [truncated]")
        assert result[2] == "another"

    def test_serialize_non_serializable_object(self):
        """Test serializing a non-serializable object."""

        class CustomClass:
            def __init__(self, value):
                self.value = value

        obj = CustomClass(42)
        result = serialize_value(obj)
        assert "<CustomClass object" in result or "CustomClass" in result

    def test_serialize_non_serializable_in_dict(self):
        """Test serializing a dict with non-serializable value."""

        class CustomClass:
            pass

        obj = CustomClass()
        data = {"key": obj, "other": "value"}
        result = serialize_value(data)
        assert result["other"] == "value"
        assert "CustomClass" in result["key"]

    def test_serialize_bytes(self):
        """Test serializing bytes."""
        data = b"hello"
        result = serialize_value(data)
        assert result == "b'hello'" or result == "<bytes object>"

    def test_serialize_with_default_max_length(self):
        """Test serialization with default max length."""
        long_string = "a" * 20000
        result = serialize_value(long_string)
        assert result.endswith("... [truncated]")
        # Default max_length is 10000, so result should be
        # 10000 + len("... [truncated]")
        assert len(result) == 10015

    def test_serialize_none_max_length(self):
        """Test serialization with None max length (no truncation)."""
        long_string = "a" * 20000
        result = serialize_value(long_string, max_length=None)
        assert result == long_string
        assert len(result) == 20000
