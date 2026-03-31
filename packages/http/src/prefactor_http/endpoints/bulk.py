"""Bulk endpoint client for the Prefactor API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ValidationError

from prefactor_http.exceptions import PrefactorResponseContractError

if TYPE_CHECKING:
    from prefactor_http.client import PrefactorHttpClient

from prefactor_http.models.bulk import BulkRequest, BulkResponse


def _ensure_idempotency_key(request: BulkRequest) -> bool:
    """Check if all bulk items have idempotency keys.

    Returns True if all items have non-empty idempotency keys.
    """
    return all(
        item.idempotency_key and len(item.idempotency_key) >= 8
        for item in request.items
    )


class BulkClient:
    """Client for bulk action operations.

    Execute multiple POST actions in a single HTTP request.
    This endpoint allows you to batch multiple operations together, reducing
    the number of round trips to the API.

    Key Features:
        - Each item in the request is processed independently in its own
          database transaction
        - Processing stops early if any item returns an error
        - All successfully processed items up to the error are returned
        - Any unprocessed items (after the first error) are excluded from the result
        - All items must include a unique `idempotency_key` (minimum 8 characters)
        - Results are returned as a map keyed by `idempotency_key`

    Example:
        ```python
        request = BulkRequest(
            items=[
                BulkItem(  # type: ignore[call-arg]
                    _type="agent_instances/register",
                    idempotency_key="register-instance-001",
                    agent_id="agent_123",
                    agent_version={"name": "My Agent", "external_identifier": "v1.0.0"},
                    agent_schema_version={
                        "external_identifier": "v1.0.0",
                        "span_type_schemas": [
                            {
                                "name": "agent:llm",
                                "title": "LLM Call",
                                "params_schema": {
                                    "type": "object",
                                    "properties": {
                                        "model": {"type": "string"},
                                        "prompt": {"type": "string"},
                                    },
                                    "required": ["model", "prompt"],
                                },
                                "result_schema": {
                                    "type": "object",
                                    "properties": {
                                        "response": {"type": "string"},
                                    },
                                },
                            },
                        ],
                    },
                ),
                BulkItem(  # type: ignore[call-arg]
                    _type="agent_spans/create",
                    idempotency_key="create-span-001",
                    agent_instance_id="instance_123",
                    schema_name="agent:llm",
                    status="active",
                ),
            ]
        )
        response = await client.bulk.execute(request)
        print(response.outputs["create-span-001"].status)
        ```
    """

    def __init__(self, http_client: PrefactorHttpClient) -> None:
        """Initialize the client.

        Args:
            http_client: The HTTP client to use for requests.
        """
        self._client = http_client

    async def execute(self, request: BulkRequest) -> BulkResponse:
        """Execute multiple queries/actions in a single request.

        Args:
            request: The bulk request containing items to process.

        Returns:
            BulkResponse with outputs keyed by idempotency_key.

        Raises:
            PrefactorValidationError: If the request is invalid.
            PrefactorRetryExhaustedError: If the request fails after all retries.
            PrefactorApiError: If the API returns an error response.
        """
        response = await self._client.request(
            method="POST",
            path="/api/v1/bulk",
            json_data=request.model_dump(by_alias=True),
        )

        try:
            return BulkResponse.model_validate(response)
        except ValidationError as exc:
            raise PrefactorResponseContractError(
                "Invalid response payload for bulk.execute",
                cause=exc,
            ) from exc
