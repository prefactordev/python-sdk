"""Tests for Prefactor HTTP Client models."""

import pytest
from prefactor_http.models.agent_instance import (
    AgentInstance,
    AgentInstanceSpanCounts,
    AgentSchemaVersionForRegister,
    AgentVersionForRegister,
    FinishInstanceRequest,
    SpanTypeSchemaForCreate,
)
from prefactor_http.models.agent_span import (
    AgentSpan,
    CreateAgentSpanRequest,
    FinishSpanRequest,
)
from pydantic import ValidationError

NOW = "2024-01-01T00:00:00Z"


class TestAgentStatus:
    """Tests for AgentStatus enum coverage on models."""

    def test_agent_instance_accepts_all_statuses(self):
        """AgentInstance.status accepts pending, active, complete, failed, cancelled."""
        base = {
            "type": "agent_instance",
            "id": "inst-1",
            "account_id": "acct-1",
            "agent_id": "agent-1",
            "agent_version_id": "ver-1",
            "environment_id": "env-1",
            "agent_deployment_id": "depl-1",
            "inserted_at": NOW,
            "updated_at": NOW,
        }
        for status in ("pending", "active", "complete", "failed", "cancelled"):
            inst = AgentInstance(**{**base, "status": status})
            assert inst.status == status

    def test_agent_instance_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            AgentInstance(
                type="agent_instance",
                id="x",
                account_id="x",
                agent_id="x",
                agent_version_id="x",
                environment_id="x",
                agent_deployment_id="depl-1",
                status="unknown",
                inserted_at=NOW,
                updated_at=NOW,
            )

    def test_agent_span_accepts_all_statuses(self):
        """AgentSpan.status accepts pending, active, complete, failed, cancelled."""
        base = {
            "type": "agent_span",
            "id": "span-1",
            "account_id": "acct-1",
            "agent_id": "agent-1",
            "agent_instance_id": "inst-1",
            "parent_span_id": None,
            "schema_name": "test",
            "schema_title": "Test",
            "payload": {},
            "started_at": NOW,
            "inserted_at": NOW,
            "updated_at": NOW,
        }
        for status in ("pending", "active", "complete", "failed", "cancelled"):
            span = AgentSpan(**{**base, "status": status})
            assert span.status == status

    def test_agent_span_rejects_invalid_status(self):
        with pytest.raises(ValidationError):
            AgentSpan(
                type="agent_span",
                id="x",
                account_id="x",
                agent_id="x",
                agent_instance_id="x",
                parent_span_id=None,
                schema_name="x",
                schema_title="X",
                status="unknown",
                payload={},
                started_at=NOW,
                inserted_at=NOW,
                updated_at=NOW,
            )


class TestAgentInstanceSpanCounts:
    """Tests for AgentInstanceSpanCounts model."""

    def test_span_counts_on_instance(self):
        inst = AgentInstance(
            type="agent_instance",
            id="inst-1",
            account_id="acct-1",
            agent_id="agent-1",
            agent_version_id="ver-1",
            environment_id="env-1",
            agent_deployment_id="depl-1",
            status="active",
            inserted_at=NOW,
            updated_at=NOW,
            span_counts=AgentInstanceSpanCounts(
                total=10,
                pending=1,
                active=2,
                complete=3,
                failed=2,
                cancelled=1,
                finished=6,
            ),
        )
        assert inst.span_counts is not None
        assert inst.span_counts.total == 10
        assert inst.span_counts.finished == 6

    def test_span_counts_optional(self):
        inst = AgentInstance(
            type="agent_instance",
            id="inst-1",
            account_id="acct-1",
            agent_id="agent-1",
            agent_version_id="ver-1",
            environment_id="env-1",
            agent_deployment_id="depl-1",
            status="active",
            inserted_at=NOW,
            updated_at=NOW,
        )
        assert inst.span_counts is None


class TestAgentVersionForRegister:
    """Tests for AgentVersionForRegister optional fields."""

    def test_all_fields_optional(self):
        v = AgentVersionForRegister()
        assert v.name is None
        assert v.external_identifier is None
        assert v.description is None

    def test_with_values(self):
        v = AgentVersionForRegister(
            name="my-agent", external_identifier="v1.0.0", description="desc"
        )
        assert v.name == "my-agent"
        assert v.external_identifier == "v1.0.0"


class TestAgentSchemaVersionForRegister:
    """Tests for AgentSchemaVersionForRegister optional fields and new fields."""

    def test_all_fields_optional(self):
        s = AgentSchemaVersionForRegister()
        assert s.external_identifier is None
        assert s.span_schemas is None
        assert s.span_result_schemas is None
        assert s.span_type_schemas is None

    def test_with_span_result_schemas(self):
        s = AgentSchemaVersionForRegister(
            span_result_schemas={"tool_call": {"type": "object"}}
        )
        assert s.span_result_schemas == {"tool_call": {"type": "object"}}

    def test_with_span_type_schemas(self):
        schema = SpanTypeSchemaForCreate(
            name="tool_call",
            params_schema={"type": "object"},
            title="Tool Call",
        )
        s = AgentSchemaVersionForRegister(span_type_schemas=[schema])
        assert len(s.span_type_schemas) == 1
        assert s.span_type_schemas[0].name == "tool_call"
        assert s.span_type_schemas[0].title == "Tool Call"


class TestSpanTypeSchemaForCreate:
    """Tests for SpanTypeSchemaForCreate model."""

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            SpanTypeSchemaForCreate()

    def test_minimal(self):
        s = SpanTypeSchemaForCreate(name="tool_call", params_schema={"type": "object"})
        assert s.name == "tool_call"
        assert s.result_schema is None
        assert s.title is None
        assert s.description is None
        assert s.template is None

    def test_all_fields(self):
        s = SpanTypeSchemaForCreate(
            name="tool_call",
            params_schema={"type": "object"},
            result_schema={"type": "string"},
            title="Tool Call",
            description="A tool call span",
            template="Called {{name}}",
        )
        assert s.result_schema == {"type": "string"}
        assert s.template == "Called {{name}}"


class TestFinishInstanceRequest:
    """Tests for FinishInstanceRequest model."""

    def test_all_optional(self):
        r = FinishInstanceRequest()
        assert r.status is None
        assert r.timestamp is None
        assert r.idempotency_key is None

    def test_with_status(self):
        r = FinishInstanceRequest(status="failed")
        assert r.status == "failed"

    def test_accepts_finish_statuses(self):
        for status in ("complete", "failed", "cancelled"):
            r = FinishInstanceRequest(status=status)
            assert r.status == status

    def test_rejects_non_finish_status(self):
        with pytest.raises(ValidationError):
            FinishInstanceRequest(status="active")

    def test_exclude_none_serialization(self):
        r = FinishInstanceRequest(status="complete")
        data = r.model_dump(exclude_none=True)
        assert data == {"status": "complete"}
        assert "timestamp" not in data


class TestCreateAgentSpanRequest:
    """Tests for CreateAgentSpanRequest with status field."""

    def test_status_required(self):
        with pytest.raises(ValidationError):
            CreateAgentSpanRequest(
                agent_instance_id="inst-1",
                schema_name="test",
            )

    def test_with_status(self):
        r = CreateAgentSpanRequest(
            agent_instance_id="inst-1",
            schema_name="test",
            status="active",
        )
        assert r.status == "active"

    def test_with_result_payload(self):
        r = CreateAgentSpanRequest(
            agent_instance_id="inst-1",
            schema_name="test",
            status="complete",
            result_payload={"output": "hello"},
        )
        assert r.result_payload == {"output": "hello"}

    def test_result_payload_optional(self):
        r = CreateAgentSpanRequest(
            agent_instance_id="inst-1",
            schema_name="test",
            status="active",
        )
        assert r.result_payload is None


class TestFinishSpanRequest:
    """Tests for FinishSpanRequest with status and result_payload fields."""

    def test_all_optional(self):
        r = FinishSpanRequest()
        assert r.status is None
        assert r.result_payload is None
        assert r.timestamp is None

    def test_with_status(self):
        r = FinishSpanRequest(status="failed")
        assert r.status == "failed"

    def test_with_result_payload(self):
        r = FinishSpanRequest(status="complete", result_payload={"result": 42})
        assert r.result_payload == {"result": 42}

    def test_rejects_non_finish_status(self):
        with pytest.raises(ValidationError):
            FinishSpanRequest(status="pending")


class TestAgentSpanNewFields:
    """Tests for new fields on AgentSpan model."""

    def _make_span(self, **overrides):
        base = {
            "type": "agent_span",
            "id": "span-1",
            "account_id": "acct-1",
            "agent_id": "agent-1",
            "agent_instance_id": "inst-1",
            "parent_span_id": None,
            "schema_name": "test",
            "schema_title": "Test",
            "status": "active",
            "payload": {},
            "started_at": NOW,
            "inserted_at": NOW,
            "updated_at": NOW,
        }
        base.update(overrides)
        return AgentSpan(**base)

    def test_schema_title_optional(self):
        span = AgentSpan(
            type="agent_span",
            id="span-1",
            account_id="acct-1",
            agent_id="agent-1",
            agent_instance_id="inst-1",
            parent_span_id=None,
            schema_name="test",
            status="active",
            payload={},
            started_at=NOW,
            inserted_at=NOW,
            updated_at=NOW,
        )
        assert span.schema_title is None

    def test_result_payload_optional(self):
        span = self._make_span()
        assert span.result_payload is None

    def test_result_payload_present(self):
        span = self._make_span(result_payload={"answer": 42})
        assert span.result_payload == {"answer": 42}

    def test_summary_optional(self):
        span = self._make_span()
        assert span.summary is None

    def test_summary_present(self):
        span = self._make_span(summary="Completed tool call")
        assert span.summary == "Completed tool call"
