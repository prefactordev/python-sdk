"""Tests for core SDK header composition."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from prefactor_core import PrefactorCoreClient
from prefactor_core._version import PACKAGE_VERSION
from prefactor_core.client import CORE_SDK_HEADER_ENTRY
from prefactor_core.config import PrefactorCoreConfig
from prefactor_http.config import HttpClientConfig


def create_config() -> PrefactorCoreConfig:
    """Create a minimal core config for SDK header tests."""
    return PrefactorCoreConfig(
        http_config=HttpClientConfig(
            api_url="https://api.test.com",
            api_token="test-token",
        )
    )


class TestPrefactorCoreSdkHeader:
    """Tests for core SDK header behavior."""

    async def test_initialize_sets_core_sdk_header(self):
        """Core initializes the HTTP client with the core SDK header."""
        client = PrefactorCoreClient(create_config())

        with (
            patch(
                "prefactor_http.client.PrefactorHttpClient.__aenter__",
                AsyncMock(return_value=None),
            ),
            patch(
                "prefactor_http.client.PrefactorHttpClient.__aexit__",
                AsyncMock(return_value=None),
            ),
        ):
            await client.initialize()
            assert client._http is not None
            assert client._http._sdk_header == CORE_SDK_HEADER_ENTRY
            await client.close()

    async def test_initialize_prepends_adapter_sdk_header(self):
        """Core prepends the adapter entry ahead of the core entry."""
        client = PrefactorCoreClient(
            create_config(),
            sdk_header_entry="prefactor-langchain@0.2.4",
        )

        with (
            patch(
                "prefactor_http.client.PrefactorHttpClient.__aenter__",
                AsyncMock(return_value=None),
            ),
            patch(
                "prefactor_http.client.PrefactorHttpClient.__aexit__",
                AsyncMock(return_value=None),
            ),
        ):
            await client.initialize()
            assert client._http is not None
            assert client._http._sdk_header == (
                f"prefactor-langchain@0.2.4 {CORE_SDK_HEADER_ENTRY}"
            )
            await client.close()


class TestCoreVersionHelpers:
    """Tests for package version exports."""

    def test_package_version_matches_public_export(self):
        """Test that the package version export matches the internal constant."""
        import prefactor_core

        assert prefactor_core.__version__ == PACKAGE_VERSION
