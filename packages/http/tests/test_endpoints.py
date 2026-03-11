"""Tests for AgentInstance and AgentSpan endpoint clients."""

import pytest
from aioresponses import aioresponses
from prefactor_http import HttpClientConfig, PrefactorHttpClient
from yarl import URL

NOW = "2024-01-01T00:00:00Z"

MOCK_INSTANCE = {
    "type": "agent_instance",
    "id": "inst-1",
    "account_id": "acct-1",
    "agent_id": "agent-1",
    "agent_version_id": "ver-1",
    "environment_id": "env-1",
    "status": "active",
    "inserted_at": NOW,
    "updated_at": NOW,
    "started_at": NOW,
    "finished_at": None,
}

MOCK_SPAN = {
    "type": "agent_span",
    "id": "span-1",
    "account_id": "acct-1",
    "agent_id": "agent-1",
    "agent_instance_id": "inst-1",
    "parent_span_id": None,
    "schema_name": "tool_call",
    "schema_title": "Tool Call",
    "status": "active",
    "payload": {"tool": "search"},
    "result_payload": None,
    "summary": None,
    "started_at": NOW,
    "inserted_at": NOW,
    "updated_at": NOW,
    "finished_at": None,
}


def get_request_body(mock, method, url):
    """Extract JSON body from the first matching aioresponses request."""
    key = (method, URL(url))
    call = mock.requests[key][0]
    return call.kwargs["json"]


@pytest.fixture
def config():
    return HttpClientConfig(
        api_url="https://api.test.com",
        api_token="test-token",
        max_retries=0,
    )


class TestAgentInstanceEndpoints:
    """Tests for AgentInstanceClient endpoints."""

    @pytest.mark.asyncio
    async def test_register_with_update_current_version(self, config):
        """register() sends update_current_version in payload."""
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_instance/register",
                payload={"status": "success", "details": MOCK_INSTANCE},
            )

            async with PrefactorHttpClient(config) as client:
                result = await client.agent_instances.register(
                    agent_id="agent-1",
                    agent_version={"name": "v1"},
                    agent_schema_version={"span_schemas": {}},
                    update_current_version=False,
                )

            assert result.id == "inst-1"
            body = get_request_body(
                m, "POST", "https://api.test.com/api/v1/agent_instance/register"
            )
            assert body["update_current_version"] is False

    @pytest.mark.asyncio
    async def test_register_default_update_current_version(self, config):
        """register() defaults update_current_version to True."""
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_instance/register",
                payload={"status": "success", "details": MOCK_INSTANCE},
            )

            async with PrefactorHttpClient(config) as client:
                await client.agent_instances.register(
                    agent_id="agent-1",
                    agent_version={},
                    agent_schema_version={},
                )

            body = get_request_body(
                m, "POST", "https://api.test.com/api/v1/agent_instance/register"
            )
            assert body["update_current_version"] is True

    @pytest.mark.asyncio
    async def test_finish_with_status(self, config):
        """finish() sends status in payload."""
        finished_instance = {**MOCK_INSTANCE, "status": "failed", "finished_at": NOW}
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_instance/inst-1/finish",
                payload={"status": "success", "details": finished_instance},
            )

            async with PrefactorHttpClient(config) as client:
                result = await client.agent_instances.finish("inst-1", status="failed")

            assert result.status == "failed"
            body = get_request_body(
                m, "POST", "https://api.test.com/api/v1/agent_instance/inst-1/finish"
            )
            assert body["status"] == "failed"

    @pytest.mark.asyncio
    async def test_finish_without_status(self, config):
        """finish() omits status from payload when not provided."""
        finished_instance = {**MOCK_INSTANCE, "status": "complete", "finished_at": NOW}
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_instance/inst-1/finish",
                payload={"status": "success", "details": finished_instance},
            )

            async with PrefactorHttpClient(config) as client:
                result = await client.agent_instances.finish("inst-1")

            assert result.status == "complete"
            body = get_request_body(
                m, "POST", "https://api.test.com/api/v1/agent_instance/inst-1/finish"
            )
            assert "status" not in body


class TestAgentSpanEndpoints:
    """Tests for AgentSpanClient endpoints."""

    @pytest.mark.asyncio
    async def test_create_with_status(self, config):
        """create() sends status in payload wrapped in details."""
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_spans",
                payload={"status": "success", "details": MOCK_SPAN},
            )

            async with PrefactorHttpClient(config) as client:
                result = await client.agent_spans.create(
                    agent_instance_id="inst-1",
                    schema_name="tool_call",
                    status="active",
                )

            assert result.id == "span-1"
            assert result.status == "active"
            body = get_request_body(
                m, "POST", "https://api.test.com/api/v1/agent_spans"
            )
            assert body["details"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_with_result_payload(self, config):
        """create() sends result_payload in payload wrapped in details."""
        span_with_result = {**MOCK_SPAN, "result_payload": {"output": "hello"}}
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_spans",
                payload={"status": "success", "details": span_with_result},
            )

            async with PrefactorHttpClient(config) as client:
                result = await client.agent_spans.create(
                    agent_instance_id="inst-1",
                    schema_name="tool_call",
                    status="complete",
                    result_payload={"output": "hello"},
                )

            assert result.result_payload == {"output": "hello"}
            body = get_request_body(
                m, "POST", "https://api.test.com/api/v1/agent_spans"
            )
            assert body["details"]["result_payload"] == {"output": "hello"}

    @pytest.mark.asyncio
    async def test_finish_with_status(self, config):
        """finish() sends status in payload."""
        finished_span = {**MOCK_SPAN, "status": "failed", "finished_at": NOW}
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_spans/span-1/finish",
                payload={"status": "success", "details": finished_span},
            )

            async with PrefactorHttpClient(config) as client:
                result = await client.agent_spans.finish("span-1", status="failed")

            assert result.status == "failed"
            body = get_request_body(
                m, "POST", "https://api.test.com/api/v1/agent_spans/span-1/finish"
            )
            assert body["status"] == "failed"

    @pytest.mark.asyncio
    async def test_finish_with_result_payload(self, config):
        """finish() sends result_payload in payload."""
        finished_span = {
            **MOCK_SPAN,
            "status": "complete",
            "finished_at": NOW,
            "result_payload": {"result": 42},
        }
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_spans/span-1/finish",
                payload={"status": "success", "details": finished_span},
            )

            async with PrefactorHttpClient(config) as client:
                result = await client.agent_spans.finish(
                    "span-1",
                    status="complete",
                    result_payload={"result": 42},
                )

            assert result.result_payload == {"result": 42}

    @pytest.mark.asyncio
    async def test_finish_without_status(self, config):
        """finish() omits status from payload when not provided."""
        finished_span = {**MOCK_SPAN, "status": "complete", "finished_at": NOW}
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_spans/span-1/finish",
                payload={"status": "success", "details": finished_span},
            )

            async with PrefactorHttpClient(config) as client:
                await client.agent_spans.finish("span-1")

            body = get_request_body(
                m, "POST", "https://api.test.com/api/v1/agent_spans/span-1/finish"
            )
            assert "status" not in body
            assert "result_payload" not in body


class TestIdempotencyKeyValidation:
    """Tests that oversized idempotency keys are rejected before making HTTP calls."""

    @pytest.mark.asyncio
    async def test_agent_span_create_rejects_oversized_key(self, config):
        async with PrefactorHttpClient(config) as client:
            with pytest.raises(ValueError, match="64 characters"):
                await client.agent_spans.create(
                    agent_instance_id="inst-1",
                    schema_name="tool_call",
                    status="active",
                    idempotency_key="a" * 65,
                )

    @pytest.mark.asyncio
    async def test_agent_span_finish_rejects_oversized_key(self, config):
        async with PrefactorHttpClient(config) as client:
            with pytest.raises(ValueError, match="64 characters"):
                await client.agent_spans.finish(
                    "span-1",
                    idempotency_key="a" * 65,
                )

    @pytest.mark.asyncio
    async def test_agent_instance_register_rejects_oversized_key(self, config):
        async with PrefactorHttpClient(config) as client:
            with pytest.raises(ValueError, match="64 characters"):
                await client.agent_instances.register(
                    agent_id="agent-1",
                    agent_version={},
                    agent_schema_version={},
                    idempotency_key="a" * 65,
                )

    @pytest.mark.asyncio
    async def test_agent_instance_start_rejects_oversized_key(self, config):
        async with PrefactorHttpClient(config) as client:
            with pytest.raises(ValueError, match="64 characters"):
                await client.agent_instances.start(
                    "inst-1",
                    idempotency_key="a" * 65,
                )

    @pytest.mark.asyncio
    async def test_agent_instance_finish_rejects_oversized_key(self, config):
        async with PrefactorHttpClient(config) as client:
            with pytest.raises(ValueError, match="64 characters"):
                await client.agent_instances.finish(
                    "inst-1",
                    idempotency_key="a" * 65,
                )

    @pytest.mark.asyncio
    async def test_exactly_64_chars_is_accepted(self, config):
        """A key of exactly 64 characters should not raise."""
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_spans",
                payload={"status": "success", "details": MOCK_SPAN},
            )
            async with PrefactorHttpClient(config) as client:
                result = await client.agent_spans.create(
                    agent_instance_id="inst-1",
                    schema_name="tool_call",
                    status="active",
                    idempotency_key="a" * 64,
                )
            assert result.id == "span-1"
