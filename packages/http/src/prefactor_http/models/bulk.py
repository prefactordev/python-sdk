"""Models for the Bulk API."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BulkItem(BaseModel):
    """A single item in a bulk request.

    Each item must include _type and idempotency_key, plus any additional
    parameters required by the specific query/action type (e.g., environment_id for
    agents/list, details for agents/create).
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(alias="_type")
    """The type of query/action to execute (e.g., 'agents/list', 'agents/create')."""

    idempotency_key: str = Field(..., min_length=8, max_length=64)
    """Required unique idempotency key for this item. Must be at least 8
    characters long and unique within the request."""


class BulkRequest(BaseModel):
    """Request body for bulk query/action operations.

    Allows executing multiple API operations in a single request.
    """

    items: list[BulkItem] = Field(..., min_length=1)
    """List of items to process in bulk. Each item will be processed independently
    in its own transaction."""

    @field_validator("items")
    @classmethod
    def validate_unique_idempotency_keys(cls, items: list[BulkItem]) -> list[BulkItem]:
        """Validate that all idempotency keys are unique within the request."""
        keys = [item.idempotency_key for item in items]
        if len(keys) != len(set(keys)):
            raise ValueError("All idempotency keys must be unique within the request")
        return items


class BulkOutput(BaseModel):
    """Output from a query or action.

    Contains either a success response (with 'status': 'success' and
    operation-specific data) or an error response (with 'status': 'error',
    'code', 'message', and optionally 'errors').
    """

    model_config = ConfigDict(extra="allow")

    status: str
    """Status of the operation: 'success' or 'error'."""

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("success", "error"):
            raise ValueError("status must be 'success' or 'error'")
        return v


class BulkResponse(BaseModel):
    """Response from bulk query/action operations.

    Contains a map of results keyed by the idempotency_key from each request item.
    """

    status: str = "success"
    """Response status, always 'success' when the request is processed."""

    outputs: dict[str, BulkOutput]
    """Map where keys are the idempotency_key values from the request, and values
    are the corresponding query/action outputs or error responses."""
