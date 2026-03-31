"""Tests for permanent telemetry failure handling in prefactor-core."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import aiohttp
import pytest
from prefactor_core import PrefactorCoreClient
from prefactor_core.config import PrefactorCoreConfig, QueueConfig
from prefactor_core.exceptions import PrefactorTelemetryFailureError
from prefactor_http.config import HttpClientConfig
from prefactor_http.exceptions import (
    PrefactorAuthError,
    PrefactorResponseContractError,
    PrefactorRetryExhaustedError,
)


class _StubAgentInstances:
    def __init__(
        self,
        *,
        start_side_effect: Exception | None = None,
        finish_side_effect: Exception | None = None,
    ) -> None:
        self.start_side_effect = start_side_effect
        self.finish_side_effect = finish_side_effect
        self.start_calls = 0
        self.finish_calls = 0

    async def register(self, **kwargs):
        return SimpleNamespace(id=kwargs.get("id") or "inst-1")

    async def start(self, **kwargs):
        self.start_calls += 1
        if self.start_side_effect is not None:
            raise self.start_side_effect
        return SimpleNamespace(id=kwargs["agent_instance_id"])

    async def finish(self, **kwargs):
        self.finish_calls += 1
        if self.finish_side_effect is not None:
            raise self.finish_side_effect
        return SimpleNamespace(id=kwargs["agent_instance_id"])


class _StubAgentSpans:
    def __init__(self) -> None:
        self.create_calls = []
        self.finish_calls = []

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return SimpleNamespace(id=f"span-{len(self.create_calls)}")

    async def finish(self, **kwargs):
        self.finish_calls.append(kwargs)
        return SimpleNamespace(id=kwargs["agent_span_id"])


class _StubHttpClient:
    def __init__(
        self,
        *_args,
        agent_instances: _StubAgentInstances | None = None,
        agent_spans: _StubAgentSpans | None = None,
        **_kwargs,
    ) -> None:
        self.agent_instances = agent_instances or _StubAgentInstances()
        self.agent_spans = agent_spans or _StubAgentSpans()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


def _make_client_config(max_retries: int = 0) -> PrefactorCoreConfig:
    return PrefactorCoreConfig(
        http_config=HttpClientConfig(
            api_url="https://api.test.com",
            api_token="test-token",
            max_retries=0,
            initial_retry_delay=0.01,
            max_retry_delay=0.02,
        ),
        queue_config=QueueConfig(num_workers=1, max_retries=max_retries),
    )


@pytest.mark.asyncio
async def test_permanent_worker_failure_latches_and_rejects_future_operations():
    """Permanent failures should latch and reject later queued operations."""
    stub_http = _StubHttpClient(
        agent_instances=_StubAgentInstances(
            start_side_effect=PrefactorAuthError("bad token", "unauthorized", 401)
        )
    )

    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        client = PrefactorCoreClient(_make_client_config())
        await client.initialize()
        instance = await client.create_agent_instance(
            agent_id="agent-1",
            agent_version={"name": "v1"},
            agent_schema_version={"span_schemas": {}},
        )

        await instance.start()
        await asyncio.sleep(0.05)

        with pytest.raises(PrefactorTelemetryFailureError) as exc_info:
            await instance.finish()

        assert exc_info.value.operation_type == "START_AGENT_INSTANCE"
        assert isinstance(exc_info.value.cause, PrefactorAuthError)
        assert exc_info.value.dropped_operations == 1

        await client.close()


@pytest.mark.asyncio
async def test_close_raises_latched_failure_when_not_previously_observed():
    """close() should surface the latched permanent failure."""
    stub_http = _StubHttpClient(
        agent_instances=_StubAgentInstances(
            start_side_effect=PrefactorAuthError("bad token", "unauthorized", 401)
        )
    )

    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        client = PrefactorCoreClient(_make_client_config())
        await client.initialize()
        instance = await client.create_agent_instance(
            agent_id="agent-1",
            agent_version={"name": "v1"},
            agent_schema_version={"span_schemas": {}},
        )

        await instance.start()
        await asyncio.sleep(0.05)

        with pytest.raises(PrefactorTelemetryFailureError):
            await client.close()


@pytest.mark.asyncio
async def test_close_raises_permanent_failure_first_latched_during_shutdown():
    """close() should surface permanent failures discovered while draining shutdown."""
    stub_http = _StubHttpClient(
        agent_instances=_StubAgentInstances(
            finish_side_effect=PrefactorAuthError("bad token", "unauthorized", 401)
        )
    )

    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        client = PrefactorCoreClient(_make_client_config())
        await client.initialize()
        instance = await client.create_agent_instance(
            agent_id="agent-1",
            agent_version={"name": "v1"},
            agent_schema_version={"span_schemas": {}},
        )

        await instance.finish()

        with pytest.raises(PrefactorTelemetryFailureError) as exc_info:
            await client.close()

        assert exc_info.value.operation_type == "FINISH_AGENT_INSTANCE"
        assert isinstance(exc_info.value.cause, PrefactorAuthError)


@pytest.mark.asyncio
async def test_transient_retry_exhaustion_does_not_latch_permanent_failure():
    """Transient failures should not poison the client permanently."""
    retry_error = PrefactorRetryExhaustedError(
        "network exhausted",
        last_error=aiohttp.ClientError("network down"),
    )
    stub_http = _StubHttpClient(
        agent_instances=_StubAgentInstances(start_side_effect=retry_error)
    )

    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        client = PrefactorCoreClient(_make_client_config())
        await client.initialize()
        instance = await client.create_agent_instance(
            agent_id="agent-1",
            agent_version={"name": "v1"},
            agent_schema_version={"span_schemas": {}},
        )

        await instance.start()
        await asyncio.sleep(0.05)

        await instance.finish()
        await asyncio.sleep(0.05)
        await client.close()


@pytest.mark.asyncio
async def test_malformed_503_retry_exhaustion_does_not_latch_permanent_failure():
    """Malformed 5xx responses should still be treated as transient."""
    retry_error = PrefactorRetryExhaustedError(
        "server exhausted",
        last_error=PrefactorResponseContractError(
            "invalid JSON",
            status_code=503,
            body_snippet="<html>temporary outage</html>",
        ),
    )
    stub_http = _StubHttpClient(
        agent_instances=_StubAgentInstances(start_side_effect=retry_error)
    )

    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        client = PrefactorCoreClient(_make_client_config())
        await client.initialize()
        instance = await client.create_agent_instance(
            agent_id="agent-1",
            agent_version={"name": "v1"},
            agent_schema_version={"span_schemas": {}},
        )

        await instance.start()
        await asyncio.sleep(0.05)

        await instance.finish()
        await asyncio.sleep(0.05)
        await client.close()


@pytest.mark.asyncio
async def test_async_context_preserves_user_exception_when_telemetry_failed():
    """Context manager exit should not replace the caller's own exception."""
    stub_http = _StubHttpClient(
        agent_instances=_StubAgentInstances(
            start_side_effect=PrefactorAuthError("bad token", "unauthorized", 401)
        )
    )

    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        with pytest.raises(ValueError, match="user boom"):
            async with PrefactorCoreClient(_make_client_config()) as client:
                instance = await client.create_agent_instance(
                    agent_id="agent-1",
                    agent_version={"name": "v1"},
                    agent_schema_version={"span_schemas": {}},
                )

                await instance.start()
                await asyncio.sleep(0.05)
                raise ValueError("user boom")


@pytest.mark.asyncio
async def test_async_context_raises_latched_failure_when_body_succeeds():
    """Context manager exit should still surface unobserved telemetry failure."""
    stub_http = _StubHttpClient(
        agent_instances=_StubAgentInstances(
            start_side_effect=PrefactorAuthError("bad token", "unauthorized", 401)
        )
    )

    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        with pytest.raises(PrefactorTelemetryFailureError):
            async with PrefactorCoreClient(_make_client_config()) as client:
                instance = await client.create_agent_instance(
                    agent_id="agent-1",
                    agent_version={"name": "v1"},
                    agent_schema_version={"span_schemas": {}},
                )

                await instance.start()
                await asyncio.sleep(0.05)
