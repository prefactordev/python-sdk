"""Tests for AgentDeployment models and endpoint client."""

import pytest
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
