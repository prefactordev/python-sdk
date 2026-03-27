"""Tests for LiveKit schema registration and compilation."""

from __future__ import annotations

import pytest
from prefactor_core import SchemaRegistry
from prefactor_livekit.schemas import (
    DEFAULT_LIVEKIT_AGENT_SCHEMA,
    LiveKitToolSchemaConfig,
    compile_livekit_agent_schema,
    register_livekit_schemas,
)


class TestCompileLiveKitAgentSchema:
    """Tests for compile_livekit_agent_schema()."""

    def test_default_schema_matches_constant_shape(self) -> None:
        compiled_schema, tool_span_types = compile_livekit_agent_schema()

        assert compiled_schema["external_identifier"] == "livekit-schema"
        assert tool_span_types == {}
        assert len(compiled_schema["span_type_schemas"]) == len(
            DEFAULT_LIVEKIT_AGENT_SCHEMA["span_type_schemas"]
        )

    def test_normalizes_tool_span_type_variants(self) -> None:
        _, tool_span_types = compile_livekit_agent_schema(
            tool_schemas={
                "send_email": LiveKitToolSchemaConfig(
                    span_type="send-email",
                    input_schema={"type": "object"},
                ),
                "lookup_customer": LiveKitToolSchemaConfig(
                    span_type="tool:lookup-customer",
                    input_schema={"type": "object"},
                ),
                "create_ticket": LiveKitToolSchemaConfig(
                    span_type="livekit:tool:create-ticket",
                    input_schema={"type": "object"},
                ),
            }
        )

        assert tool_span_types == {
            "send_email": "livekit:tool:send-email",
            "lookup_customer": "livekit:tool:lookup-customer",
            "create_ticket": "livekit:tool:create-ticket",
        }

    def test_rejects_colliding_normalized_span_types(self) -> None:
        with pytest.raises(ValueError, match='conflicts with "get_customer_profile"'):
            compile_livekit_agent_schema(
                tool_schemas={
                    "get_customer_profile": {
                        "span_type": "get-customer-profile",
                        "input_schema": {"type": "object"},
                    },
                    "lookup_customer": {
                        "span_type": "livekit:tool:get-customer-profile",
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
                {
                    "send_email": {
                        "span_type": "send-email",
                        "input_schema": {"type": "object"},
                        "result_schema": [],
                    }
                },
                r"Invalid tool_schemas\.send_email\.result_schema: expected an object",
            ),
        ],
    )
    def test_validates_tool_schema_shapes(self, tool_schemas, error_match) -> None:
        with pytest.raises(ValueError, match=error_match):
            compile_livekit_agent_schema(tool_schemas=tool_schemas)


class TestRegisterLiveKitSchemas:
    """Tests for register_livekit_schemas()."""

    def test_registers_tool_specific_span_schemas(self) -> None:
        registry = SchemaRegistry()

        tool_span_types = register_livekit_schemas(
            registry,
            tool_schemas={
                "send_email": LiveKitToolSchemaConfig(
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
        assert tool_span_types == {"send_email": "livekit:tool:send-email"}
        assert (
            schema_version["span_type_schemas"][-1]["name"] == "livekit:tool:send-email"
        )
        assert schema_version["span_type_schemas"][-1]["params_schema"]["properties"][
            "inputs"
        ] == {
            "type": "object",
            "properties": {"to": {"type": "string"}},
            "required": ["to"],
        }

    def test_rejects_conflicting_pre_registered_tool_span_types(self) -> None:
        registry = SchemaRegistry()
        registry.register_type(
            name="livekit:tool:send-email",
            params_schema={"type": "object"},
            result_schema={"type": "object"},
        )

        with pytest.raises(
            ValueError,
            match="Span type schema 'livekit:tool:send-email' is already registered",
        ):
            register_livekit_schemas(
                registry,
                tool_schemas={
                    "send_email": LiveKitToolSchemaConfig(
                        span_type="send-email",
                        input_schema={"type": "object"},
                    )
                },
            )
