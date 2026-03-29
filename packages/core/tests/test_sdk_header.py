"""Tests for core SDK header composition."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from prefactor_core import PrefactorCoreClient
from prefactor_core._version import PACKAGE_VERSION, resolve_package_version
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

    async def test_set_sdk_header_entry_updates_initialized_http_client(self):
        """The compatibility shim updates the live HTTP client header."""
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
            client.set_sdk_header_entry("prefactor-langchain@0.2.4")
            assert client._http is not None
            assert client._http._sdk_header == (
                f"prefactor-langchain@0.2.4 {CORE_SDK_HEADER_ENTRY}"
            )
            await client.close()

    async def test_add_and_remove_sdk_header_entries_update_initialized_http_client(
        self,
    ):
        """Adding and removing entries keeps the live HTTP client in sync."""
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

            assert client.add_sdk_header_entry("prefactor-langchain@0.2.4") is True
            assert client.add_sdk_header_entry("prefactor-another@1.0.0") is True
            assert client.add_sdk_header_entry("prefactor-langchain@0.2.4") is False
            assert client.sdk_header_entries == (
                "prefactor-langchain@0.2.4",
                "prefactor-another@1.0.0",
            )
            assert client._http is not None
            assert client._http._sdk_header == (
                "prefactor-langchain@0.2.4 "
                "prefactor-another@1.0.0 "
                f"{CORE_SDK_HEADER_ENTRY}"
            )

            assert client.remove_sdk_header_entry("prefactor-langchain@0.2.4") is True
            assert client.remove_sdk_header_entry("prefactor-missing@9.9.9") is False
            assert client.sdk_header_entries == ("prefactor-another@1.0.0",)
            assert client._http._sdk_header == (
                f"prefactor-another@1.0.0 {CORE_SDK_HEADER_ENTRY}"
            )
            await client.close()


class TestCoreVersionHelpers:
    """Tests for package version lookup helpers."""

    def test_package_version_matches_public_export(self):
        """Test that the package version helper matches the public export."""
        import prefactor_core

        assert prefactor_core.__version__ == PACKAGE_VERSION

    def test_resolve_package_version_prefers_installed_metadata(self, monkeypatch):
        """Test that metadata version is used when available."""
        monkeypatch.setattr(
            "prefactor_core._version.metadata.version",
            lambda _distribution_name: "9.9.9",
        )

        resolved = resolve_package_version("prefactor-core", Path("/tmp/missing"))
        assert resolved == "9.9.9"

    def test_resolve_package_version_falls_back_to_pyproject(
        self, tmp_path, monkeypatch
    ):
        """Test that version lookup falls back to pyproject for source imports."""

        def raise_package_not_found(_distribution_name: str) -> str:
            raise __import__("importlib").metadata.PackageNotFoundError

        monkeypatch.setattr(
            "prefactor_core._version.metadata.version",
            raise_package_not_found,
        )

        pyproject_path = tmp_path / "pyproject.toml"
        pyproject_path.write_text(
            '[project]\nname = "prefactor-core"\nversion = "1.2.3"\n',
            encoding="utf-8",
        )

        resolved = resolve_package_version("prefactor-core", tmp_path)
        assert resolved == "1.2.3"
