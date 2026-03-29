"""Backward-compatible imports for SDK header helpers."""

from prefactor_http.sdk_header import (
    DEFAULT_SDK_HEADER,
    DEFAULT_SDK_HEADER_ENTRY,
    build_sdk_header,
    format_sdk_header_entry,
    normalize_sdk_header_entry,
)

__all__ = [
    "DEFAULT_SDK_HEADER",
    "DEFAULT_SDK_HEADER_ENTRY",
    "build_sdk_header",
    "format_sdk_header_entry",
    "normalize_sdk_header_entry",
]
