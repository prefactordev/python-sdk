"""Tests for LangChain schema compilation and registration."""

from __future__ import annotations

import pytest
from prefactor_core import SchemaRegistry
from prefactor_langchain.schemas import (
    DEFAULT_LANGCHAIN_AGENT_SCHEMA,
    LangChainToolSchemaConfig,
    compile_langchain_agent_schema,
    register_langchain_schemas,
)


class TestCompileLangChainAgentSchema:
    """Tests for compile_langchain_agent_schema()."""

    def test_normalizes_tool_span_type_variants(self):
        """Bare, tool-prefixed, and fully-qualified span types normalize equally."""
        _, tool_span_types = compile_langchain_agent_schema(
            tool_schemas={
                "send_email": LangChainToolSchemaConfig(
                    span_type="send-email",
                    input_schema={"type": "object"},
                ),
                "lookup_customer": LangChainToolSchemaConfig(
                    span_type="tool:lookup-customer",
                    input_schema={"type": "object"},
                ),
                "create_ticket": LangChainToolSchemaConfig(
                    span_type="langchain:tool:create-ticket",
                    input_schema={"type": "object"},
                ),
            }
        )

        assert tool_span_types == {
            "send_email": "langchain:tool:send-email",
            "lookup_customer": "langchain:tool:lookup-customer",
            "create_ticket": "langchain:tool:create-ticket",
        }

    def test_strips_embedded_tool_schema_config_from_compiled_output(self):
        """Embedded tool schema config should not appear in the compiled schema."""
        compiled_schema, tool_span_types = compile_langchain_agent_schema(
            agent_schema={
                "external_identifier": "custom-schema",
                "span_schemas": {},
                "span_result_schemas": {},
                "toolSchemas": {
                    "send_email": {
                        "spanType": "send-email",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"to": {"type": "string"}},
                        },
                    }
                },
                "tool_schemas": {
                    "ignored": {
                        "span_type": "ignored",
                        "input_schema": {"type": "object"},
                    }
                },
            }
        )

        assert compiled_schema["external_identifier"] == "custom-schema"
        assert "toolSchemas" not in compiled_schema
        assert "tool_schemas" not in compiled_schema
        assert tool_span_types["send_email"] == "langchain:tool:send-email"
        assert compiled_schema["span_schemas"]["langchain:tool:send-email"][
            "properties"
        ]["inputs"] == {
            "type": "object",
            "properties": {"to": {"type": "string"}},
        }

    def test_explicit_tool_schemas_override_embedded_config(self):
        """Python-first tool_schemas should override embedded tool schema entries."""
        compiled_schema, tool_span_types = compile_langchain_agent_schema(
            agent_schema={
                "toolSchemas": {
                    "send_email": {
                        "spanType": "tool:old-send-email",
                        "inputSchema": {"type": "object"},
                    }
                }
            },
            tool_schemas={
                "send_email": LangChainToolSchemaConfig(
                    span_type="send-email",
                    input_schema={
                        "type": "object",
                        "properties": {"to": {"type": "string"}},
                    },
                )
            },
        )

        assert tool_span_types["send_email"] == "langchain:tool:send-email"
        assert compiled_schema["span_schemas"]["langchain:tool:send-email"][
            "properties"
        ]["inputs"] == {
            "type": "object",
            "properties": {"to": {"type": "string"}},
        }
        assert "langchain:tool:old-send-email" not in compiled_schema["span_schemas"]

    def test_rejects_colliding_normalized_span_types(self):
        """Colliding normalized span types should raise a clear error."""
        with pytest.raises(ValueError, match='conflicts with "get_customer_profile"'):
            compile_langchain_agent_schema(
                tool_schemas={
                    "get_customer_profile": {
                        "span_type": "get-customer-profile",
                        "input_schema": {"type": "object"},
                    },
                    "lookup_customer": {
                        "span_type": "langchain:tool:get-customer-profile",
                        "input_schema": {"type": "object"},
                    },
                }
            )

    @pytest.mark.parametrize(
        ("tool_schemas", "error_match"),
        [
            (
                {"send_email": "invalid"},
                r"Invalid tool_schemas\.send_email: expected an object with span_type",
            ),
            (
                {"send_email": {"span_type": "", "input_schema": {"type": "object"}}},
                (
                    r"Invalid tool_schemas\.send_email\.span_type: expected a "
                    r"non-empty string"
                ),
            ),
            (
                {"send_email": {"span_type": "send-email", "input_schema": []}},
                r"Invalid tool_schemas\.send_email\.input_schema: expected an object",
            ),
            (
                None,
                None,
            ),
        ],
    )
    def test_validates_tool_schema_shapes(self, tool_schemas, error_match):
        """Invalid tool schema inputs should raise clear validation errors."""
        if error_match is None:
            compiled_schema, tool_span_types = compile_langchain_agent_schema()
            assert compiled_schema == DEFAULT_LANGCHAIN_AGENT_SCHEMA
            assert tool_span_types == {}
            return

        with pytest.raises(ValueError, match=error_match):
            compile_langchain_agent_schema(tool_schemas=tool_schemas)


class TestRegisterLangChainSchemas:
    """Tests for register_langchain_schemas()."""

    def test_registers_tool_specific_span_schemas(self):
        """Tool-specific schemas should be added to the registry output."""
        registry = SchemaRegistry()

        tool_span_types = register_langchain_schemas(
            registry,
            tool_schemas={
                "send_email": LangChainToolSchemaConfig(
                    span_type="send-email",
                    input_schema={
                        "type": "object",
                        "properties": {"to": {"type": "string"}},
                        "required": ["to"],
                    },
                )
            },
        )

        schema_version = registry.to_agent_schema_version("schema-v1")
        assert tool_span_types == {"send_email": "langchain:tool:send-email"}
        assert (
            schema_version["span_type_schemas"][-1]["name"]
            == "langchain:tool:send-email"
        )
        assert schema_version["span_type_schemas"][-1]["params_schema"]["properties"][
            "inputs"
        ] == {
            "type": "object",
            "properties": {"to": {"type": "string"}},
            "required": ["to"],
        }
        assert schema_version["span_type_schemas"][-1]["result_schema"] == {
            "type": "object",
            "additionalProperties": True,
        }

    def test_rejects_conflicting_pre_registered_tool_span_types(self):
        """Conflicting shared registries should fail instead of silently diverging."""
        registry = SchemaRegistry()
        registry.register_type(
            name="langchain:tool:send-email",
            params_schema={
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string"},
                    "inputs": {
                        "type": "object",
                        "properties": {"recipient": {"type": "string"}},
                        "additionalProperties": False,
                    },
                },
            },
            result_schema={"type": "object"},
        )

        with pytest.raises(
            ValueError,
            match="Schema 'langchain:tool:send-email' is already registered",
        ):
            register_langchain_schemas(
                registry,
                tool_schemas={
                    "send_email": LangChainToolSchemaConfig(
                        span_type="send-email",
                        input_schema={
                            "type": "object",
                            "properties": {"to": {"type": "string"}},
                            "required": ["to"],
                            "additionalProperties": False,
                        },
                    )
                },
            )

    def test_invalid_tool_schemas_do_not_mutate_registry(self):
        """Validation failures should leave the target registry unchanged."""
        registry = SchemaRegistry()

        with pytest.raises(
            ValueError,
            match=(
                r"Invalid tool_schemas\.send_email: expected an object "
                r"with span_type"
            ),
        ):
            register_langchain_schemas(
                registry,
                tool_schemas={"send_email": "invalid"},
            )

        assert registry.to_agent_schema_version("schema-v1") == {
            "external_identifier": "schema-v1"
        }
