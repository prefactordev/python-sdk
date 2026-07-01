"""Tests for permanent telemetry failure handling in prefactor-core."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
        validate_token_error: PrefactorAuthError | None = None,
        **_kwargs,
    ) -> None:
        self.agent_instances = agent_instances or _StubAgentInstances()
        self.agent_spans = agent_spans or _StubAgentSpans()
        self._validate_token_error = validate_token_error
        self.enter_calls = 0
        self.exit_calls = 0

    async def __aenter__(self):
        self.enter_calls += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exit_calls += 1
        return None

    async def validate_token(self):
        if self._validate_token_error is not None:
            raise self._validate_token_error
        return {"status": "success"}


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


async def _wait_until(
    predicate, *, timeout: float = 1.0, interval: float = 0.01
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    raise AssertionError("Timed out waiting for expected condition")


@pytest.mark.asyncio
async def test_termination_sync_loop_survives_iteration_failures(caplog):
    """A failed sync iteration should be logged without stopping future syncs."""
    client = PrefactorCoreClient(_make_client_config())
    monitor = Mock()
    calls = 0

    def sync(_instance_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("sync failed")

    monitor.sync.side_effect = sync
    client._termination_monitor = monitor
    original_sleep = asyncio.sleep

    async def fast_sleep(_delay):
        await original_sleep(0)

    with (
        caplog.at_level(logging.ERROR, logger="prefactor_core.client"),
        patch("prefactor_core.client.asyncio.sleep", side_effect=fast_sleep),
    ):
        task = asyncio.create_task(client._run_sync_loop())
        try:
            await _wait_until(lambda: monitor.sync.call_count >= 2)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    assert "Termination sync iteration failed" in caplog.text


@pytest.mark.asyncio
async def test_close_observes_completed_sync_task_exceptions(caplog):
    """close() should await already-failed sync tasks and clear the task handle."""
    client = PrefactorCoreClient(_make_client_config())
    client._initialized = True

    async def fail_sync_loop():
        raise RuntimeError("sync task failed")

    client._sync_task = asyncio.create_task(fail_sync_loop())
    await asyncio.sleep(0)

    with caplog.at_level(logging.ERROR, logger="prefactor_core.client"):
        await client.close()

    assert client._sync_task is None
    assert "Termination sync loop exited with error during close()" in caplog.text


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
        await _wait_until(lambda: client._telemetry_failure is not None)

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
        await _wait_until(lambda: client._telemetry_failure is not None)

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
        await _wait_until(lambda: stub_http.agent_instances.start_calls == 1)

        await instance.finish()
        await _wait_until(lambda: stub_http.agent_instances.finish_calls == 1)
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
        await _wait_until(lambda: stub_http.agent_instances.start_calls == 1)

        await instance.finish()
        await _wait_until(lambda: stub_http.agent_instances.finish_calls == 1)
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
                await _wait_until(lambda: client._telemetry_failure is not None)
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
                await _wait_until(lambda: client._telemetry_failure is not None)


@pytest.mark.asyncio
async def test_latched_failure_drops_already_queued_backlog():
    """Queued work should be dropped once a permanent telemetry failure is latched."""
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
        await instance.finish()
        await _wait_until(lambda: client._telemetry_failure is not None)

        assert stub_http.agent_instances.start_calls == 1
        assert stub_http.agent_instances.finish_calls == 0

        with pytest.raises(PrefactorTelemetryFailureError) as exc_info:
            await client.close()

        assert exc_info.value.dropped_operations == 1


@pytest.mark.asyncio
async def test_initialize_raises_auth_error_when_token_validation_fails():
    """Invalid tokens should fail during initialize() before workers start."""
    stub_http = _StubHttpClient(
        validate_token_error=PrefactorAuthError("Token expired", "bad_authtoken", 401)
    )

    with patch("prefactor_core.client.PrefactorHttpClient", return_value=stub_http):
        client = PrefactorCoreClient(_make_client_config())
        with pytest.raises(PrefactorAuthError) as exc_info:
            await client.initialize()

        assert exc_info.value.code == "bad_authtoken"
        assert stub_http.enter_calls == 1
        assert stub_http.exit_calls == 1
        assert client._http is None
        assert client._executor is None
        await client.close()
