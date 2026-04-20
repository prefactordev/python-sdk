"""Tests for AgentInstanceHandle.finish() accepting an optional status.

See GitHub issue prefactordev/python-sdk#13.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from prefactor_core import PrefactorCoreClient
from prefactor_core.config import PrefactorCoreConfig, QueueConfig
from prefactor_http.config import HttpClientConfig


class _StubAgentInstances:
    def __init__(self) -> None:
        self.finish_calls: list[dict] = []

    async def register(self, **kwargs):
        return SimpleNamespace(id=kwargs.get("id") or "inst-1")

    async def start(self, **kwargs):
        return SimpleNamespace(id=kwargs["agent_instance_id"])

    async def finish(self, **kwargs):
        self.finish_calls.append(kwargs)
        return SimpleNamespace(id=kwargs["agent_instance_id"])


class _StubAgentSpans:
    async def create(self, **kwargs):
        return SimpleNamespace(id="span-1")

    async def finish(self, **kwargs):
        return SimpleNamespace(id=kwargs["agent_span_id"])


class _StubHttpClient:
    def __init__(
        self,
        *_args,
        agent_instances: _StubAgentInstances | None = None,
        **_kwargs,
    ) -> None:
        self.agent_instances = agent_instances or _StubAgentInstances()
        self.agent_spans = _StubAgentSpans()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


def _make_client_config() -> PrefactorCoreConfig:
    return PrefactorCoreConfig(
        http_config=HttpClientConfig(
            api_url="https://api.test.com",
            api_token="test-token",
            max_retries=0,
            initial_retry_delay=0.01,
            max_retry_delay=0.02,
        ),
        queue_config=QueueConfig(num_workers=1, max_retries=0),
    )


@pytest.mark.asyncio
async def test_finish_without_status_defaults_to_complete():
    """Default call to finish() should forward status='complete' to HTTP."""
    stub_http = _StubHttpClient()

    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        async with PrefactorCoreClient(_make_client_config()) as client:
            instance = await client.create_agent_instance(
                agent_id="agent-1",
                agent_version={"name": "v1"},
                agent_schema_version={"span_schemas": {}},
            )
            await instance.finish()

    assert len(stub_http.agent_instances.finish_calls) == 1
    assert stub_http.agent_instances.finish_calls[0].get("status") == "complete"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "cancelled", "complete"])
async def test_finish_forwards_explicit_status(status):
    """Explicit status on handle.finish() should reach the HTTP layer."""
    stub_http = _StubHttpClient()

    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        async with PrefactorCoreClient(_make_client_config()) as client:
            instance = await client.create_agent_instance(
                agent_id="agent-1",
                agent_version={"name": "v1"},
                agent_schema_version={"span_schemas": {}},
            )
            await instance.finish(status=status)

    assert len(stub_http.agent_instances.finish_calls) == 1
    assert stub_http.agent_instances.finish_calls[0]["status"] == status
