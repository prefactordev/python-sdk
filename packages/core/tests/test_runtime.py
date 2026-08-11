"""Tests for build_runtime_environment and auto-injection in create_agent_instance."""

from __future__ import annotations

import platform
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from prefactor_core import PrefactorCoreClient
from prefactor_core.config import PrefactorCoreConfig, QueueConfig
from prefactor_core.runtime import build_runtime_environment
from prefactor_http.config import HttpClientConfig


def _make_config() -> PrefactorCoreConfig:
    return PrefactorCoreConfig(
        http_config=HttpClientConfig(
            api_url="https://api.test.com",
            api_token="test-token",
            max_retries=0,
        ),
        queue_config=QueueConfig(num_workers=1, max_retries=0),
    )


class _StubAgentInstances:
    def __init__(self) -> None:
        self.register_calls: list[dict] = []

    async def register(self, **kwargs):
        self.register_calls.append(kwargs)
        return SimpleNamespace(id="inst-1")

    async def start(self, **kwargs):
        return SimpleNamespace(id=kwargs["agent_instance_id"])

    async def finish(self, **kwargs):
        return SimpleNamespace(id=kwargs["agent_instance_id"])


class _StubAgentSpans:
    async def create(self, **kwargs):
        return SimpleNamespace(id="span-1")

    async def finish(self, **kwargs):
        return SimpleNamespace(id=kwargs["agent_span_id"])


class _StubHttpClient:
    def __init__(self, *args, **kwargs) -> None:
        self.agent_instances = _StubAgentInstances()
        self.agent_spans = _StubAgentSpans()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def validate_token(self):
        return {"status": "success"}


# ═══════════════════════════════════════════════════════════════════════════════
# build_runtime_environment unit tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildRuntimeEnvironment:
    """Unit tests for build_runtime_environment()."""

    def test_returns_all_four_keys(self):
        """Result always has agent_sdk, os, prefactor_sdk, runtime keys."""
        result = build_runtime_environment()
        assert set(result.keys()) == {"agent_sdk", "os", "prefactor_sdk", "runtime"}

    def test_os_matches_platform(self):
        """os field matches platform.system().lower()."""
        result = build_runtime_environment()
        assert result["os"] == platform.system().lower()

    def test_runtime_includes_python_version(self):
        """runtime field includes implementation name and major.minor version."""
        result = build_runtime_environment()
        impl = sys.implementation.name
        ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        expected = f"{impl}@{ver}"
        assert result["runtime"] == expected

    def test_prefactor_sdk_includes_core_and_http(self):
        """prefactor_sdk always includes prefactor-core and prefactor-http."""
        result = build_runtime_environment()
        names = [entry.split("@")[0] for entry in result["prefactor_sdk"]]
        assert "prefactor-core" in names
        assert "prefactor-http" in names

    def test_agent_sdk_empty_without_header(self):
        """agent_sdk is empty list when no sdk_header_entry provided."""
        result = build_runtime_environment()
        assert result["agent_sdk"] == []

    def test_agent_sdk_empty_with_none(self):
        """agent_sdk is empty list when sdk_header_entry is None."""
        result = build_runtime_environment(sdk_header_entry=None)
        assert result["agent_sdk"] == []

    def test_agent_sdk_parses_single_upstream(self):
        """Single upstream entry is captured in agent_sdk."""
        result = build_runtime_environment(
            sdk_header_entry="prefactor-langchain@0.2.7 prefactor-core@0.5.1"
        )
        assert result["agent_sdk"] == ["prefactor-langchain@0.2.7"]

    def test_agent_sdk_parses_multiple_upstream(self):
        """Multiple upstream entries are all captured in agent_sdk."""
        result = build_runtime_environment(
            sdk_header_entry=(
                "prefactor-langchain@0.2.7 my-framework@1.0.0 prefactor-core@0.5.1"
            )
        )
        assert result["agent_sdk"] == [
            "prefactor-langchain@0.2.7",
            "my-framework@1.0.0",
        ]

    def test_agent_sdk_strips_core_self_entry(self):
        """The prefactor-core@... self-entry is stripped from agent_sdk."""
        result = build_runtime_environment(sdk_header_entry="prefactor-core@0.5.1")
        assert result["agent_sdk"] == []

    def test_agent_sdk_handles_whitespace(self):
        """Leading/trailing whitespace in sdk_header_entry is handled."""
        result = build_runtime_environment(
            sdk_header_entry="  prefactor-langchain@0.2.7 prefactor-core@0.5.1  "
        )
        assert result["agent_sdk"] == ["prefactor-langchain@0.2.7"]


# ═══════════════════════════════════════════════════════════════════════════════
# Auto-injection in create_agent_instance
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_create_agent_instance_auto_injects_runtime_environment():
    """create_agent_instance adds runtime_environment when not provided."""
    stub_http = _StubHttpClient()
    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        async with PrefactorCoreClient(_make_config()) as client:
            await client.create_agent_instance(
                agent_id="agent-1",
                agent_version={"name": "v1"},
                agent_schema_version={"span_schemas": {}},
            )
    call = stub_http.agent_instances.register_calls[0]
    av = call["agent_version"]
    assert "runtime_environment" in av
    re_env = av["runtime_environment"]
    assert set(re_env.keys()) == {"agent_sdk", "os", "prefactor_sdk", "runtime"}
    assert re_env["os"] == platform.system().lower()


@pytest.mark.asyncio
async def test_preserves_existing_runtime_environment():
    """create_agent_instance does not overwrite caller-provided env."""
    stub_http = _StubHttpClient()
    custom_env = {
        "agent_sdk": ["my-custom@1.0"],
        "os": "custom-os",
        "prefactor_sdk": ["custom-sdk@2.0"],
        "runtime": "custom-runtime@9.9",
    }
    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        async with PrefactorCoreClient(_make_config()) as client:
            await client.create_agent_instance(
                agent_id="agent-1",
                agent_version={
                    "name": "v1",
                    "runtime_environment": custom_env,
                },
                agent_schema_version={"span_schemas": {}},
            )
    call = stub_http.agent_instances.register_calls[0]
    assert call["agent_version"]["runtime_environment"] == custom_env


@pytest.mark.asyncio
async def test_create_agent_instance_includes_agent_sdk_from_header():
    """agent_sdk is populated from the client's sdk_header_entry."""
    stub_http = _StubHttpClient()
    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        client = PrefactorCoreClient(
            _make_config(),
            sdk_header_entry="prefactor-langchain@0.2.7",
        )
        await client.initialize()
        await client.create_agent_instance(
            agent_id="agent-1",
            agent_version={"name": "v1"},
            agent_schema_version={"span_schemas": {}},
        )
        await client.close()
    call = stub_http.agent_instances.register_calls[0]
    re_env = call["agent_version"]["runtime_environment"]
    assert re_env["agent_sdk"] == ["prefactor-langchain@0.2.7"]


@pytest.mark.asyncio
async def test_create_agent_instance_empty_agent_sdk_without_header():
    """agent_sdk is empty when no sdk_header_entry is set on the client."""
    stub_http = _StubHttpClient()
    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        async with PrefactorCoreClient(_make_config()) as client:
            await client.create_agent_instance(
                agent_id="agent-1",
                agent_version={"name": "v1"},
                agent_schema_version={"span_schemas": {}},
            )
    call = stub_http.agent_instances.register_calls[0]
    re_env = call["agent_version"]["runtime_environment"]
    assert re_env["agent_sdk"] == []
