"""Schema registry for span type definitions.

This module provides a SchemaRegistry that allows registration of span schemas
from multiple sources before agent instances are created.
"""

from typing import Any


class SchemaRegistry:
    """Central registry for span schemas - allows pre-registration.

    Multiple components can register their schemas independently before
    agent instance creation. The registry aggregates all into a single
    format suitable for the API.

    Example:
        registry = SchemaRegistry()

        # Register built-in schemas
        registry.register("langchain:agent", {"type": "object"}, source="langchain")

        # Register custom user schemas
        registry.register("http-api:get", {
            "type": "object",
            "properties": {"url": {"type": "string"}}
        }, source="user")

        # Convert to API format
        version = registry.to_agent_schema_version("combined-1.0.0")
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._schemas: dict[str, dict[str, Any]] = {}

    def register(
        self,
        schema_name: str,
        schema: dict[str, Any],
        source: str | None = None,
    ) -> None:
        """Register a schema for a span type.

        Args:
            schema_name: Unique identifier for this span type (e.g., "langchain:llm")
            schema: JSON Schema dict defining the span payload structure
            source: Optional identifier for the source of this schema
                   (e.g., "langchain", "user", "http-adapter")

        Raises:
            ValueError: If schema_name is already registered.
        """
        if schema_name in self._schemas:
            raise ValueError(f"Schema '{schema_name}' is already registered")

        self._schemas[schema_name] = {
            "schema": schema,
            "source": source or "unknown",
        }

    def register_unsafe(
        self,
        schema_name: str,
        schema: dict[str, Any],
        source: str | None = None,
    ) -> None:
        """Register a schema, overwriting if it already exists.

        Args:
            schema_name: Unique identifier for this span type
            schema: JSON Schema dict defining the span payload structure
            source: Optional identifier for the source of this schema
        """
        self._schemas[schema_name] = {
            "schema": schema,
            "source": source or "unknown",
        }

    def get(self, schema_name: str) -> dict[str, Any] | None:
        """Get a schema by name.

        Args:
            schema_name: The schema identifier to look up

        Returns:
            The schema dict if found, None otherwise
        """
        info = self._schemas.get(schema_name)
        return info["schema"] if info else None

    def get_source(self, schema_name: str) -> str | None:
        """Get the source of a registered schema.

        Args:
            schema_name: The schema identifier to look up

        Returns:
            The source string if found, None otherwise
        """
        info = self._schemas.get(schema_name)
        return info["source"] if info else None

    def list_schemas(self) -> list[str]:
        """List all registered schema names.

        Returns:
            List of registered schema names
        """
        return list(self._schemas.keys())

    def has_schema(self, schema_name: str) -> bool:
        """Check if a schema is registered.

        Args:
            schema_name: The schema identifier to check

        Returns:
            True if the schema is registered, False otherwise
        """
        return schema_name in self._schemas

    def to_agent_schema_version(self, external_id: str) -> dict[str, Any]:
        """Convert registry contents to API-compatible agent_schema_version format.

        Args:
            external_id: External identifier for this combined schema version

        Returns:
            Dict with 'external_identifier' and 'span_schemas' keys
        """
        return {
            "external_identifier": external_id,
            "span_schemas": {
                name: info["schema"] for name, info in self._schemas.items()
            },
        }

    def merge(self, other: "SchemaRegistry") -> None:
        """Merge schemas from another registry into this one.

        Args:
            other: Another SchemaRegistry to merge. Conflicting schemas
                  from the other registry will be ignored.

        Raises:
            ValueError: If there are conflicting schema names.
        """
        conflicts = []
        for name in other.list_schemas():
            if name in self._schemas:
                conflicts.append(name)

        if conflicts:
            msg = f"Cannot merge registries - conflicting schemas: {conflicts}"
            raise ValueError(msg)

        # Copy schemas from other registry
        for name in other.list_schemas():
            self._schemas[name] = other._schemas[name].copy()


__all__ = ["SchemaRegistry"]
