"""Schema registry for span type definitions.

This module provides a SchemaRegistry that allows registration of span schemas
from multiple packages before agent instances are created.
"""

from typing import Any


class SchemaRegistry:
    """Central registry for span schemas - allows pre-registration.

    Multiple components can register their schemas independently before
    agent instance creation. The registry aggregates all into a single
    format suitable for the API.

    The API supports three ways to define span schemas, in increasing order
    of expressiveness:

    - ``span_schemas``: flat map of span name → params JSON schema
    - ``span_result_schemas``: flat map of span name → result JSON schema
    - ``span_type_schemas``: structured list with params, result, title,
      description, and template per span type

    Use ``register()`` for simple payload schemas, ``register_result()`` to add
    a result schema for an existing entry, or ``register_type()`` for the full
    structured form. All three approaches can be mixed; ``to_agent_schema_version()``
    emits whichever fields are populated.

    Example:
        registry = SchemaRegistry()

        # Simple params-only schema
        registry.register("langchain:agent", {"type": "object"})

        # Full structured schema with result and display metadata
        registry.register_type(
            name="agent:llm",
            params_schema={
                "type": "object",
                "properties": {
                    "model": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["model", "prompt"],
            },
            result_schema={
                "type": "object",
                "properties": {"response": {"type": "string"}},
            },
            title="LLM Call",
            description="A call to a language model",
            template="{{model}}: {{prompt}} → {{response}}",
        )

        # Convert to API format
        version = registry.to_agent_schema_version("combined-1.0.0")
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        # span_schemas: name → params JSON schema (flat map)
        self._span_schemas: dict[str, dict[str, Any]] = {}
        # span_result_schemas: name → result JSON schema (flat map)
        self._span_result_schemas: dict[str, dict[str, Any]] = {}
        # span_type_schemas: name → full structured entry
        self._span_type_schemas: dict[str, dict[str, Any]] = {}

    def register(
        self,
        schema_name: str,
        schema: dict[str, Any],
    ) -> None:
        """Register a params schema for a span type.

        Adds to ``span_schemas`` (the flat params-schema map). Use
        ``register_type()`` if you also need a result schema, title,
        description, or template.

        Args:
            schema_name: Unique identifier for this span type (e.g., "langchain:llm")
            schema: JSON Schema dict defining the span payload structure

        Raises:
            ValueError: If schema_name is already registered.
        """
        if schema_name in self._span_schemas:
            raise ValueError(f"Schema '{schema_name}' is already registered")

        self._span_schemas[schema_name] = schema

    def register_unsafe(
        self,
        schema_name: str,
        schema: dict[str, Any],
    ) -> None:
        """Register a params schema, overwriting if it already exists.

        Args:
            schema_name: Unique identifier for this span type
            schema: JSON Schema dict defining the span payload structure
        """
        self._span_schemas[schema_name] = schema

    def register_result(
        self,
        schema_name: str,
        result_schema: dict[str, Any],
    ) -> None:
        """Register a result schema for a span type.

        Adds to ``span_result_schemas`` (the flat result-schema map).
        The span type does not need to have a params schema registered first.

        Args:
            schema_name: Span type identifier (e.g., "agent:llm")
            result_schema: JSON Schema dict defining the span result payload

        Raises:
            ValueError: If a result schema for schema_name is already registered.
        """
        if schema_name in self._span_result_schemas:
            raise ValueError(f"Result schema '{schema_name}' is already registered")
        self._span_result_schemas[schema_name] = result_schema

    def register_type(
        self,
        name: str,
        params_schema: dict[str, Any],
        result_schema: dict[str, Any] | None = None,
        title: str | None = None,
        description: str | None = None,
        template: str | None = None,
        data_risk: dict[str, Any] | None = None,
    ) -> None:
        """Register a full structured span type schema.

        Adds to ``span_type_schemas``. This is the richest form and supports
        all API fields: params schema, result schema, human-readable title,
        description, template, and data risk classification.

        Args:
            name: Span type name (e.g., "agent:llm")
            params_schema: JSON Schema for the span payload (params)
            result_schema: Optional JSON Schema for the span result payload
            title: Optional human-readable title (defaults to name on the API)
            description: Optional description of the span type
            template: Optional display template using ``{{field}}`` interpolation
            data_risk: Optional data risk classification dict. See DataRisk model
                in prefactor_http.models.agent_instance for structure. Must include:
                - action_profile (object): Permitted actions with keys:
                  create_data, read_data, update_data, destroy_data,
                  financial_transactions, external_communication (values:
                  "unknown" | "allowed" | "disallowed")
                - params_data_categories (object): Input data categories with keys
                  like personal_identifiers, contact_information,
                  financial_information, etc. (values: "unknown" | "included"
                  | "excluded")
                - result_data_categories (object): Output data categories,
                  same structure as params_data_categories
                Example: {"action_profile": {"read_data": "allowed"}, ...}

        Raises:
            ValueError: If name is already registered as a span type schema.
        """
        if name in self._span_type_schemas:
            raise ValueError(f"Span type schema '{name}' is already registered")

        entry: dict[str, Any] = {"name": name, "params_schema": params_schema}
        if result_schema is not None:
            entry["result_schema"] = result_schema
        if title is not None:
            entry["title"] = title
        if description is not None:
            entry["description"] = description
        if template is not None:
            entry["template"] = template
        if data_risk is not None:
            entry["data_risk"] = data_risk

        self._span_type_schemas[name] = entry

    def get(self, schema_name: str) -> dict[str, Any] | None:
        """Get a params schema by name.

        Args:
            schema_name: The schema identifier to look up

        Returns:
            The schema dict if found, None otherwise
        """
        return self._span_schemas.get(schema_name)

    def list_schemas(self) -> list[str]:
        """List all registered span schema names (params schemas only).

        Returns:
            List of registered schema names
        """
        return list(self._span_schemas.keys())

    def has_schema(self, schema_name: str) -> bool:
        """Check if a params schema is registered for a span type.

        Args:
            schema_name: The schema identifier to check

        Returns:
            True if the schema is registered, False otherwise
        """
        return (
            schema_name in self._span_schemas or schema_name in self._span_type_schemas
        )

    def to_agent_schema_version(self, external_id: str) -> dict[str, Any]:
        """Convert registry contents to API-compatible agent_schema_version format.

        Emits ``span_schemas``, ``span_result_schemas``, and ``span_type_schemas``
        for whichever have been populated.

        Args:
            external_id: External identifier for this combined schema version

        Returns:
            Dict with ``external_identifier`` and whichever schema fields are
            non-empty.
        """
        result: dict[str, Any] = {"external_identifier": external_id}

        if self._span_schemas:
            result["span_schemas"] = dict(self._span_schemas)

        if self._span_result_schemas:
            result["span_result_schemas"] = dict(self._span_result_schemas)

        if self._span_type_schemas:
            result["span_type_schemas"] = list(self._span_type_schemas.values())

        return result

    def merge(self, other: "SchemaRegistry") -> None:
        """Merge schemas from another registry into this one.

        Args:
            other: Another SchemaRegistry to merge. Conflicting schemas
                  from the other registry will be rejected.

        Raises:
            ValueError: If there are conflicting schema names in any category.
        """
        conflicts: list[str] = []

        for name in other._span_schemas:
            if name in self._span_schemas:
                conflicts.append(f"span_schemas/{name}")

        for name in other._span_result_schemas:
            if name in self._span_result_schemas:
                conflicts.append(f"span_result_schemas/{name}")

        for name in other._span_type_schemas:
            if name in self._span_type_schemas:
                conflicts.append(f"span_type_schemas/{name}")

        if conflicts:
            msg = f"Cannot merge registries - conflicting schemas: {conflicts}"
            raise ValueError(msg)

        for name, schema in other._span_schemas.items():
            self._span_schemas[name] = schema.copy()

        for name, schema in other._span_result_schemas.items():
            self._span_result_schemas[name] = schema.copy()

        for name, entry in other._span_type_schemas.items():
            self._span_type_schemas[name] = entry.copy()


__all__ = ["SchemaRegistry"]
