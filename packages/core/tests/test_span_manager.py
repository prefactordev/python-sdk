"""Tests for SpanManager idempotency key auto-generation."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from prefactor_core.managers.span import SpanManager


def _make_span_result(span_id: str = "api-span-id") -> MagicMock:
    result = MagicMock()
    result.id = span_id
    return result


@pytest.fixture
def http_client():
    client = MagicMock()
    client.agent_spans = MagicMock()
    client.agent_spans.create = AsyncMock(return_value=_make_span_result())
    client.agent_spans.finish = AsyncMock(return_value=_make_span_result())
    return client


@pytest.fixture
def enqueue():
    return AsyncMock()


@pytest.fixture
def manager(http_client, enqueue):
    return SpanManager(http_client, enqueue)


class TestSpanManagerIdempotencyKeys:
    async def test_start_passes_idempotency_key(self, manager, http_client):
        temp_id = manager.prepare(instance_id="inst-1", schema_name="agent:llm")
        await manager.start(temp_id)

        call_kwargs = http_client.agent_spans.create.call_args.kwargs
        key = call_kwargs.get("idempotency_key")
        assert key is not None
        assert len(key) <= 64
        uuid.UUID(key)  # must be valid UUID

    async def test_cancel_unstarted_passes_distinct_keys(self, manager, http_client):
        temp_id = manager.prepare(instance_id="inst-1", schema_name="agent:llm")
        await manager.cancel_unstarted(temp_id)

        create_key = http_client.agent_spans.create.call_args.kwargs.get(
            "idempotency_key"
        )
        finish_key = http_client.agent_spans.finish.call_args.kwargs.get(
            "idempotency_key"
        )

        assert create_key is not None
        assert finish_key is not None
        assert create_key != finish_key

    async def test_finish_includes_idempotency_key_in_operation(
        self, manager, http_client, enqueue
    ):
        # Start a span first to get a real API id
        temp_id = manager.prepare(instance_id="inst-1", schema_name="agent:llm")
        api_id = await manager.start(temp_id)

        await manager.finish(api_id)

        enqueue.assert_called_once()
        operation = enqueue.call_args.args[0]
        key = operation.payload.get("idempotency_key")
        assert key is not None
        assert len(key) <= 64
        uuid.UUID(key)
