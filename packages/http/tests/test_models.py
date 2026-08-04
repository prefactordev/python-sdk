"""Tests for Prefactor HTTP Client models."""

from __future__ import annotations

import pytest
from prefactor_http.models.agent_instance import (
    AgentInstance,
    AgentInstanceRecordQuality,
    AgentSchemaVersionForRegister,
    QualitySchemaForCreate,
)
from prefactor_http.models.agent_span import (
    AgentSpan,
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
        for status in ("pending", "active", "complete", "failed", "cancelled"):
            span = AgentSpan(**{**base, "status": status})
            assert span.status == status

    def test_agent_span_rejects_invalid_status(self):
        """AgentSpan rejects invalid status values."""
        base = {
            "type": "agent_span",
            "id": "span-1",
            "account_id": "acct-1",
            "agent_id": "agent-1",
            "agent_instance_id": "inst-1",
            "parent_span_id": None,
            "schema_name": "tool_call",
            "schema_title": "Tool Call",
            "payload": {},
            "result_payload": None,
            "summary": None,
            "started_at": NOW,
            "inserted_at": NOW,
            "updated_at": NOW,
            "finished_at": None,
        }
        with pytest.raises(ValidationError):
            AgentSpan(**{**base, "status": "unknown"})

    def test_agent_instance_accepts_all_purposes(self):
        """AgentInstance.purpose accepts live, smoke_test, eval."""
        base = {
            "type": "agent_instance",
            "id": "inst-1",
            "account_id": "acct-1",
            "agent_id": "agent-1",
            "agent_version_id": "ver-1",
            "environment_id": "env-1",
            "agent_deployment_id": "depl-1",
            "status": "active",
            "inserted_at": NOW,
            "updated_at": NOW,
        }
        for purpose in ("live", "smoke_test", "eval"):
            inst = AgentInstance(**{**base, "purpose": purpose})
            assert inst.purpose == purpose

    def test_agent_instance_purpose_defaults_none(self):
        """AgentInstance.purpose defaults to None when omitted."""
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
        assert inst.purpose is None

    def test_agent_instance_accepts_terminated_status(self):
        """AgentInstance.status accepts terminated."""
        inst = AgentInstance(
            type="agent_instance",
            id="inst-1",
            account_id="acct-1",
            agent_id="agent-1",
            agent_version_id="ver-1",
            environment_id="env-1",
            agent_deployment_id="depl-1",
            status="terminated",
            inserted_at=NOW,
            updated_at=NOW,
            termination_reason="User requested termination",
        )
        assert inst.status == "terminated"
        assert inst.termination_reason == "User requested termination"


class TestTerminationReason:
    """Tests for termination_reason field on AgentInstance."""

    @staticmethod
    def _make_instance(**kwargs):
        from datetime import datetime, timezone

        status = kwargs.pop("status", "active")
        return AgentInstance(
            type="agent_instance",
            id="inst-1",
            account_id="acct-1",
            agent_id="agent-1",
            agent_version_id="ver-1",
            environment_id="env-1",
            agent_deployment_id="depl-1",
            status=status,
            inserted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            **kwargs,
        )

    def test_termination_reason_defaults_none(self):
        """Termination reason defaults to None for non-terminated instances."""
        instance = self._make_instance()
        assert instance.termination_reason is None

    def test_termination_reason_parsed(self):
        """Termination reason is parsed when present on a terminated instance."""
        instance = self._make_instance(
            status="terminated", termination_reason="admin action"
        )
        assert instance.termination_reason == "admin action"


class TestQualitySchemaModels:
    """Tests for named quality schema models."""

    def test_quality_schema_for_create_requires_name(self):
        """QualitySchemaForCreate requires a name field."""
        with pytest.raises(ValidationError):
            QualitySchemaForCreate(schema_={"type": "object"})

    def test_quality_schema_for_create_requires_schema(self):
        """QualitySchemaForCreate requires a schema field."""
        with pytest.raises(ValidationError):
            QualitySchemaForCreate(name="accuracy")

    def test_quality_schema_for_create_accepts_alias(self):
        """QualitySchemaForCreate accepts schema via alias for backward compat."""
        q = QualitySchemaForCreate(name="accuracy", schema={"type": "object"})
        assert q.schema_ == {"type": "object"}

    def test_quality_schema_for_create_accepts_field_name(self):
        """QualitySchemaForCreate accepts schema_ field name."""
        q = QualitySchemaForCreate(name="accuracy", schema_={"type": "object"})
        assert q.schema_ == {"type": "object"}

    def test_quality_schema_for_create_minimal(self):
        """QualitySchemaForCreate accepts name and schema only."""
        q = QualitySchemaForCreate(name="accuracy", schema_={"type": "object"})
        assert q.name == "accuracy"
        assert q.schema_ == {"type": "object"}
        assert q.title is None
        assert q.description is None
        assert q.template is None
        assert q.data_risk is None

    def test_quality_schema_for_create_full(self):
        """QualitySchemaForCreate accepts all optional fields."""
        q = QualitySchemaForCreate(
            name="safety",
            schema_={"type": "object"},
            title="Safety Check",
            description="Evaluates safety",
            template="Safe: {{score}}",
            data_risk={
                "action_profile": {"read_data": "allowed"},
                "params_data_categories": {},
                "result_data_categories": {},
            },
        )
        assert q.name == "safety"
        assert q.title == "Safety Check"
        assert q.description == "Evaluates safety"
        assert q.template == "Safe: {{score}}"
        assert q.data_risk is not None

    def test_agent_schema_version_quality_schemas_is_list(self):
        """AgentSchemaVersionForRegister.quality_schemas is a list."""
        sv = AgentSchemaVersionForRegister(
            quality_schemas=[
                QualitySchemaForCreate(name="accuracy", schema_={"type": "object"}),
                QualitySchemaForCreate(name="fluency", schema_={"type": "object"}),
            ]
        )
        assert sv.quality_schemas is not None
        assert len(sv.quality_schemas) == 2
        assert sv.quality_schemas[0].name == "accuracy"
        assert sv.quality_schemas[1].name == "fluency"

    def test_agent_schema_version_quality_schemas_defaults_none(self):
        """AgentSchemaVersionForRegister.quality_schemas defaults to None."""
        sv = AgentSchemaVersionForRegister()
        assert sv.quality_schemas is None

    def test_agent_instance_quality_payloads_map(self):
        """AgentInstance.quality_payloads is a map of name to payload."""
        base = {
            "type": "agent_instance",
            "id": "inst-1",
            "account_id": "acct-1",
            "agent_id": "agent-1",
            "agent_version_id": "ver-1",
            "environment_id": "env-1",
            "agent_deployment_id": "depl-1",
            "status": "complete",
            "inserted_at": NOW,
            "updated_at": NOW,
            "quality_payloads": {
                "accuracy": {"score": 0.95},
                "fluency": {"score": 0.88},
            },
            "quality_summaries": {
                "accuracy": "Score: 0.95",
            },
        }
        inst = AgentInstance(**base)
        assert inst.quality_payloads == {
            "accuracy": {"score": 0.95},
            "fluency": {"score": 0.88},
        }
        assert inst.quality_summaries == {"accuracy": "Score: 0.95"}

    def test_agent_instance_quality_fields_default_none(self):
        """AgentInstance quality fields default to None when omitted."""
        base = {
            "type": "agent_instance",
            "id": "inst-1",
            "account_id": "acct-1",
            "agent_id": "agent-1",
            "agent_version_id": "ver-1",
            "environment_id": "env-1",
            "agent_deployment_id": "depl-1",
            "status": "active",
            "inserted_at": NOW,
            "updated_at": NOW,
        }
        inst = AgentInstance(**base)
        assert inst.quality_payloads is None
        assert inst.quality_summaries is None

    def test_agent_instance_record_quality_requires_name(self):
        """AgentInstanceRecordQuality requires a name field."""
        with pytest.raises(ValidationError):
            AgentInstanceRecordQuality(payload={"score": 0.9})

    def test_agent_instance_record_quality_with_payload(self):
        """AgentInstanceRecordQuality accepts name and payload."""
        req = AgentInstanceRecordQuality(name="accuracy", payload={"score": 0.9})
        assert req.name == "accuracy"
        assert req.payload == {"score": 0.9}

    def test_agent_instance_record_quality_null_payload(self):
        """AgentInstanceRecordQuality accepts null payload to remove entry."""
        req = AgentInstanceRecordQuality(name="accuracy", payload=None)
        assert req.name == "accuracy"
        assert req.payload is None
