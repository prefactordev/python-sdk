"""Tests for SchemaRegistry quality schema support."""

from __future__ import annotations

import pytest
from prefactor_core.schema_registry import SchemaRegistry


class TestQualitySchemaRegistration:
    """Tests for register_quality_schema and to_agent_schema_version."""

    def test_register_single_quality_schema(self):
        """register_quality_schema stores a named quality schema."""
        registry = SchemaRegistry()
        registry.register_quality_schema(
            name="summary_quality",
            schema={"type": "object", "properties": {"score": {"type": "number"}}},
            title="Summary Quality",
            description="Evaluates summary quality",
            template="Score: {{score}}",
        )

        version = registry.to_agent_schema_version("v1")
        assert "quality_schemas" in version
        assert len(version["quality_schemas"]) == 1
        entry = version["quality_schemas"][0]
        assert entry["name"] == "summary_quality"
        assert entry["schema"] == {
            "type": "object",
            "properties": {"score": {"type": "number"}},
        }
        assert entry["title"] == "Summary Quality"
        assert entry["description"] == "Evaluates summary quality"
        assert entry["template"] == "Score: {{score}}"

    def test_register_multiple_quality_schemas(self):
        """register_quality_schema can be called multiple times with different names."""
        registry = SchemaRegistry()
        registry.register_quality_schema("accuracy", {"type": "object"})
        registry.register_quality_schema("fluency", {"type": "object"})

        version = registry.to_agent_schema_version("v1")
        assert len(version["quality_schemas"]) == 2
        names = {q["name"] for q in version["quality_schemas"]}
        assert names == {"accuracy", "fluency"}

    def test_register_duplicate_quality_schema_name_raises(self):
        """register_quality_schema raises ValueError for duplicate names."""
        registry = SchemaRegistry()
        registry.register_quality_schema("accuracy", {"type": "object"})

        with pytest.raises(
            ValueError, match="Quality schema 'accuracy' is already registered"
        ):
            registry.register_quality_schema("accuracy", {"type": "object"})

    def test_register_quality_schema_with_data_risk(self):
        """register_quality_schema accepts data_risk parameter."""
        registry = SchemaRegistry()
        data_risk = {
            "action_profile": {"read_data": "allowed"},
            "params_data_categories": {},
            "result_data_categories": {},
        }
        registry.register_quality_schema(
            name="safety",
            schema={"type": "object"},
            data_risk=data_risk,
        )

        version = registry.to_agent_schema_version("v1")
        assert version["quality_schemas"][0]["data_risk"] == data_risk

    def test_register_quality_schema_minimal(self):
        """register_quality_schema works with only name and schema."""
        registry = SchemaRegistry()
        registry.register_quality_schema("minimal", {"type": "object"})

        version = registry.to_agent_schema_version("v1")
        entry = version["quality_schemas"][0]
        assert entry["name"] == "minimal"
        assert entry["schema"] == {"type": "object"}
        assert "title" not in entry
        assert "description" not in entry
        assert "template" not in entry
        assert "data_risk" not in entry

    def test_no_quality_schemas_omits_field(self):
        """to_agent_schema_version omits quality_schemas when none registered."""
        registry = SchemaRegistry()
        version = registry.to_agent_schema_version("v1")
        assert "quality_schemas" not in version


class TestQualitySchemaMerge:
    """Tests for merging quality schemas across registries."""

    def test_merge_quality_schemas(self):
        """merge() combines quality schemas from both registries."""
        r1 = SchemaRegistry()
        r1.register_quality_schema("accuracy", {"type": "object"})

        r2 = SchemaRegistry()
        r2.register_quality_schema("fluency", {"type": "object"})

        r1.merge(r2)
        version = r1.to_agent_schema_version("v1")
        names = {q["name"] for q in version["quality_schemas"]}
        assert names == {"accuracy", "fluency"}

    def test_merge_duplicate_quality_schema_name_raises(self):
        """merge() raises ValueError for conflicting quality schema names."""
        r1 = SchemaRegistry()
        r1.register_quality_schema("accuracy", {"type": "object"})

        r2 = SchemaRegistry()
        r2.register_quality_schema("accuracy", {"type": "object"})

        with pytest.raises(ValueError, match="quality_schemas/accuracy"):
            r1.merge(r2)

    def test_merge_empty_quality_schemas_no_conflict(self):
        """merge() works when one registry has no quality schemas."""
        r1 = SchemaRegistry()
        r1.register_quality_schema("accuracy", {"type": "object"})

        r2 = SchemaRegistry()

        r1.merge(r2)
        version = r1.to_agent_schema_version("v1")
        assert len(version["quality_schemas"]) == 1

    def test_merge_into_empty_quality_schemas(self):
        """merge() works when target registry has no quality schemas."""
        r1 = SchemaRegistry()

        r2 = SchemaRegistry()
        r2.register_quality_schema("accuracy", {"type": "object"})

        r1.merge(r2)
        version = r1.to_agent_schema_version("v1")
        assert len(version["quality_schemas"]) == 1
        assert version["quality_schemas"][0]["name"] == "accuracy"
