"""Runtime environment collection for agent version registration.

Provides :func:`build_runtime_environment` which collects OS, Python
runtime, and SDK version information into the dict format expected by
the Prefactor API's ``agent_version.runtime_environment`` field.
"""

from __future__ import annotations

import platform
import sys

from prefactor_http._version import PACKAGE_NAME as HTTP_PACKAGE_NAME
from prefactor_http._version import PACKAGE_VERSION as HTTP_PACKAGE_VERSION

from prefactor_core._version import PACKAGE_NAME as CORE_PACKAGE_NAME
from prefactor_core._version import PACKAGE_VERSION as CORE_PACKAGE_VERSION


def build_runtime_environment(
    sdk_header_entry: str | None = None,
) -> dict:
    """Build the ``runtime_environment`` dict for ``agent_version``.

    Parses *sdk_header_entry* (a space-separated list of ``"pkg@ver"``
    tokens as set by upstream adaptors) into ``agent_sdk`` entries.
    Always includes ``prefactor_sdk``, ``os``, and ``runtime``.

    Args:
        sdk_header_entry: Space-separated SDK header string set by
            upstream adaptors (e.g. ``"prefactor-langchain@0.2.7"``).
            The trailing ``prefactor-core@...`` self-entry added by the
            client is automatically stripped from ``agent_sdk``.

    Returns:
        A dict with keys ``agent_sdk``, ``os``, ``prefactor_sdk``, and
        ``runtime``, suitable for use as the ``runtime_environment``
        field of ``agent_version``.
    """
    # ── agent_sdk: upstream framework packages ─────────────────────
    agent_sdk: list[str] = []
    if sdk_header_entry:
        tokens = sdk_header_entry.strip().split()
        # The last token is always "prefactor-core@..." (added by the
        # client).  Everything before it is the upstream agent SDK.
        agent_sdk = [t for t in tokens if not t.startswith("prefactor-core@")]

    # ── prefactor_sdk: the Prefactor SDK packages in use ──────────
    prefactor_sdk = [
        f"{CORE_PACKAGE_NAME}@{CORE_PACKAGE_VERSION}",
        f"{HTTP_PACKAGE_NAME}@{HTTP_PACKAGE_VERSION}",
    ]

    # ── os / runtime ──────────────────────────────────────────────
    os_name = platform.system().lower()
    python_version = (
        f"{sys.implementation.name}@{sys.version_info.major}.{sys.version_info.minor}"
    )

    return {
        "agent_sdk": agent_sdk,
        "os": os_name,
        "prefactor_sdk": prefactor_sdk,
        "runtime": python_version,
    }


__all__ = ["build_runtime_environment"]
