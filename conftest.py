"""Shared pytest configuration for all packages in the workspace."""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import Mock

import aiohttp
import aioresponses.core


def _patch_aioresponses_for_aiohttp_314() -> None:
    """Let aioresponses build mock responses on aiohttp 3.14+.

    aiohttp 3.14 added a required keyword-only ``stream_writer`` argument to
    ``ClientResponse.__init__``, which aioresponses 0.7.9 does not pass. It is
    only read for its ``output_size``, so a mock is enough. This is a no-op on
    older aiohttp. Remove once a fixed aioresponses is released:
    https://github.com/pnuckowski/aioresponses/issues/289
    """
    params = inspect.signature(aiohttp.ClientResponse.__init__).parameters
    if "stream_writer" not in params:
        return

    class _ClientResponse(aiohttp.ClientResponse):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs.setdefault("stream_writer", Mock(output_size=0))
            super().__init__(*args, **kwargs)

    aioresponses.core.ClientResponse = _ClientResponse  # ty: ignore[invalid-assignment]


_patch_aioresponses_for_aiohttp_314()
