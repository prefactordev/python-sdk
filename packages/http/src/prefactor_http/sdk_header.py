"""Public helpers for constructing Prefactor SDK request headers."""

from __future__ import annotations

from prefactor_http._version import PACKAGE_NAME, PACKAGE_VERSION


def format_sdk_header_entry(package_name: str, package_version: str) -> str:
    """Format a package/version pair as a header entry."""
    return f"{package_name.lstrip('@')}@{package_version}"


def normalize_sdk_header_entry(entry: str) -> str:
    """Normalize SDK header entries to a consistent package@version format."""
    normalized_entry = entry.lstrip("@")
    package_name, separator, package_version = normalized_entry.rpartition("@")
    if separator and package_name and package_version:
        return f"{package_name}@{package_version}"
    return normalized_entry


def build_sdk_header(base_entry: str, *entries: str | None) -> str:
    """Build the space-separated SDK header value."""
    parts = [
        *(
            normalize_sdk_header_entry(entry)
            for entry in entries
            if entry is not None and entry.strip()
        ),
        normalize_sdk_header_entry(base_entry),
    ]
    return " ".join(dict.fromkeys(parts))


DEFAULT_SDK_HEADER_ENTRY = format_sdk_header_entry(PACKAGE_NAME, PACKAGE_VERSION)
DEFAULT_SDK_HEADER = build_sdk_header(DEFAULT_SDK_HEADER_ENTRY)


__all__ = [
    "DEFAULT_SDK_HEADER",
    "DEFAULT_SDK_HEADER_ENTRY",
    "build_sdk_header",
    "format_sdk_header_entry",
    "normalize_sdk_header_entry",
]
