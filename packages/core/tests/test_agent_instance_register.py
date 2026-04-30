"""Tests for environment_id threading through the core register flow."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from prefactor_core import PrefactorCoreClient
from prefactor_core.config import PrefactorCoreConfig, QueueConfig
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


@pytest.mark.asyncio
async def test_create_agent_instance_passes_environment_id_to_register():
    """environment_id passed to create_agent_instance() reaches the HTTP layer."""
    stub_http = _StubHttpClient()
    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        async with PrefactorCoreClient(_make_config()) as client:
            await client.create_agent_instance(
                agent_id="agent-1",
                agent_version={"name": "v1"},
                agent_schema_version={"span_schemas": {}},
                environment_id="env-1",
            )
    assert stub_http.agent_instances.register_calls[0]["environment_id"] == "env-1"


@pytest.mark.asyncio
async def test_create_agent_instance_without_environment_id_omits_field():
    """Omitting environment_id does not send it to the HTTP register call."""
    stub_http = _StubHttpClient()
    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        async with PrefactorCoreClient(_make_config()) as client:
            await client.create_agent_instance(
                agent_id="agent-1",
                agent_version={"name": "v1"},
                agent_schema_version={"span_schemas": {}},
            )
    call = stub_http.agent_instances.register_calls[0]
    assert "environment_id" not in call or call["environment_id"] is None
