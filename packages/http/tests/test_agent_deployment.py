"""Tests for AgentDeployment models and endpoint client."""

import pytest
from aioresponses import aioresponses
from prefactor_http import HttpClientConfig, PrefactorHttpClient, PrefactorResponseContractError
from pydantic import ValidationError
from prefactor_http.models.agent_deployment import (
    AgentDeployment,
    CreateAgentDeploymentRequest,
    UpdateAgentDeploymentRequest,
)

NOW = "2024-01-01T00:00:00Z"

MOCK_DEPLOYMENT = {
    "type": "agent_deployment",
    "id": "depl-1",
    "account_id": "acct-1",
    "agent_id": "agent-1",
    "environment_id": "env-1",
    "current_version_id": None,
    "inserted_at": NOW,
    "updated_at": NOW,
}


class TestAgentDeploymentModel:
    def test_valid_deployment_parses(self):
        d = AgentDeployment(**MOCK_DEPLOYMENT)
        assert d.id == "depl-1"
        assert d.type == "agent_deployment"
        assert d.agent_id == "agent-1"
        assert d.environment_id == "env-1"
        assert d.current_version_id is None

    def test_current_version_id_populated(self):
        d = AgentDeployment(**{**MOCK_DEPLOYMENT, "current_version_id": "ver-1"})
        assert d.current_version_id == "ver-1"

    def test_missing_required_field_raises(self):
        payload = {k: v for k, v in MOCK_DEPLOYMENT.items() if k != "agent_id"}
        with pytest.raises(ValidationError):
            AgentDeployment(**payload)

    def test_create_request_minimal(self):
        req = CreateAgentDeploymentRequest(agent_id="agent-1", environment_id="env-1")
        assert req.agent_id == "agent-1"
        assert req.environment_id == "env-1"
        assert req.current_version_id is None
        assert req.id is None

    def test_create_request_full(self):
        req = CreateAgentDeploymentRequest(
            agent_id="agent-1",
            environment_id="env-1",
            current_version_id="ver-1",
            id="depl-custom",
        )
        assert req.current_version_id == "ver-1"
        assert req.id == "depl-custom"

    def test_update_request_null_clears_version(self):
        req = UpdateAgentDeploymentRequest(current_version_id=None)
        assert req.current_version_id is None

    def test_update_request_with_version(self):
        req = UpdateAgentDeploymentRequest(current_version_id="ver-2")
        assert req.current_version_id == "ver-2"


class TestAgentInstanceHasDeploymentId:
    def test_agent_instance_includes_agent_deployment_id(self):
        from prefactor_http.models.agent_instance import AgentInstance

        inst = AgentInstance(
            type="agent_instance",
            id="inst-1",
            account_id="acct-1",
            agent_id="agent-1",
            agent_version_id="ver-1",
            environment_id="env-1",
            agent_deployment_id="depl-1",
            status="active",
            inserted_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
        )
        assert inst.agent_deployment_id == "depl-1"

    def test_agent_instance_requires_agent_deployment_id(self):
        from pydantic import ValidationError
        from prefactor_http.models.agent_instance import AgentInstance

        with pytest.raises(ValidationError):
            AgentInstance(
                type="agent_instance",
                id="inst-1",
                account_id="acct-1",
                agent_id="agent-1",
                agent_version_id="ver-1",
                environment_id="env-1",
                status="active",
                inserted_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
            )


def get_request_body(mock, method, url):
    from yarl import URL
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


class TestAgentDeploymentEndpoints:
    @pytest.mark.asyncio
    async def test_list_returns_deployments(self, config):
        payload = {
            "status": "success",
            "summaries": [MOCK_DEPLOYMENT],
            "pagination": None,
            "sorting": None,
        }
        with aioresponses() as m:
            m.get("https://api.test.com/api/v1/agent_deployment/", payload=payload)
            async with PrefactorHttpClient(config) as client:
                result = await client.agent_deployments.list()
        assert len(result) == 1
        assert result[0].id == "depl-1"

    @pytest.mark.asyncio
    async def test_list_with_agent_id_filter(self, config):
        payload = {
            "status": "success",
            "summaries": [MOCK_DEPLOYMENT],
            "pagination": None,
            "sorting": None,
        }
        with aioresponses() as m:
            m.get(
                "https://api.test.com/api/v1/agent_deployment/?agent_id=agent-1",
                payload=payload,
            )
            async with PrefactorHttpClient(config) as client:
                result = await client.agent_deployments.list(agent_id="agent-1")
        assert result[0].agent_id == "agent-1"

    @pytest.mark.asyncio
    async def test_get_returns_deployment(self, config):
        with aioresponses() as m:
            m.get(
                "https://api.test.com/api/v1/agent_deployment/depl-1",
                payload={"status": "success", "details": MOCK_DEPLOYMENT},
            )
            async with PrefactorHttpClient(config) as client:
                result = await client.agent_deployments.get("depl-1")
        assert result.id == "depl-1"

    @pytest.mark.asyncio
    async def test_create_sends_correct_payload(self, config):
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_deployment/",
                payload={"status": "success", "details": MOCK_DEPLOYMENT},
            )
            async with PrefactorHttpClient(config) as client:
                result = await client.agent_deployments.create(
                    agent_id="agent-1",
                    environment_id="env-1",
                )
        assert result.agent_id == "agent-1"
        body = get_request_body(
            m, "POST", "https://api.test.com/api/v1/agent_deployment/"
        )
        assert body["details"]["agent_id"] == "agent-1"
        assert body["details"]["environment_id"] == "env-1"

    @pytest.mark.asyncio
    async def test_create_with_optional_fields(self, config):
        with aioresponses() as m:
            m.post(
                "https://api.test.com/api/v1/agent_deployment/",
                payload={"status": "success", "details": MOCK_DEPLOYMENT},
            )
            async with PrefactorHttpClient(config) as client:
                await client.agent_deployments.create(
                    agent_id="agent-1",
                    environment_id="env-1",
                    current_version_id="ver-1",
                    id="depl-custom",
                )
        body = get_request_body(
            m, "POST", "https://api.test.com/api/v1/agent_deployment/"
        )
        assert body["details"]["current_version_id"] == "ver-1"
        assert body["details"]["id"] == "depl-custom"

    @pytest.mark.asyncio
    async def test_update_sends_correct_payload(self, config):
        with aioresponses() as m:
            m.put(
                "https://api.test.com/api/v1/agent_deployment/depl-1",
                payload={"status": "success", "details": MOCK_DEPLOYMENT},
            )
            async with PrefactorHttpClient(config) as client:
                result = await client.agent_deployments.update(
                    "depl-1", current_version_id="ver-2"
                )
        assert result.id == "depl-1"
        body = get_request_body(
            m, "PUT", "https://api.test.com/api/v1/agent_deployment/depl-1"
        )
        assert body["details"]["current_version_id"] == "ver-2"

    @pytest.mark.asyncio
    async def test_update_with_null_clears_version(self, config):
        with aioresponses() as m:
            m.put(
                "https://api.test.com/api/v1/agent_deployment/depl-1",
                payload={"status": "success", "details": MOCK_DEPLOYMENT},
            )
            async with PrefactorHttpClient(config) as client:
                await client.agent_deployments.update("depl-1", current_version_id=None)
        body = get_request_body(
            m, "PUT", "https://api.test.com/api/v1/agent_deployment/depl-1"
        )
        assert body["details"]["current_version_id"] is None

    @pytest.mark.asyncio
    async def test_delete_calls_correct_endpoint(self, config):
        with aioresponses() as m:
            m.delete(
                "https://api.test.com/api/v1/agent_deployment/depl-1",
                payload={"status": "success"},
            )
            async with PrefactorHttpClient(config) as client:
                await client.agent_deployments.delete("depl-1")

    @pytest.mark.asyncio
    async def test_get_invalid_response_raises_contract_error(self, config):
        with aioresponses() as m:
            m.get(
                "https://api.test.com/api/v1/agent_deployment/depl-1",
                payload={"status": "success", "details": {"id": "depl-1"}},
            )
            async with PrefactorHttpClient(config) as client:
                with pytest.raises(PrefactorResponseContractError):
                    await client.agent_deployments.get("depl-1")


class TestAgentDeploymentExports:
    def test_model_importable_from_models_package(self):
        from prefactor_http.models import AgentDeployment as D

        assert D is not None

    def test_client_importable_from_endpoints_package(self):
        from prefactor_http.endpoints import AgentDeploymentClient as C

        assert C is not None

    def test_model_importable_from_top_level(self):
        from prefactor_http import AgentDeployment as D

        assert D is not None
