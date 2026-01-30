"""Bulk endpoint client for the Prefactor API."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    """Client for bulk query/action operations.

    Execute multiple API queries and actions in a single HTTP request.
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
        - Each item can be a different type of query or action

    Example:
        ```python
        request = BulkRequest(
            items=[
                BulkItem(  # type: ignore[call-arg]
                    _type="agents/list",
                    idempotency_key="list-agents-001",
                    environment_id="env_abc123"
                ),
                BulkItem(  # type: ignore[call-arg]
                    _type="agents/create",
                    idempotency_key="create-agent-001",
                    details={
                        "name": "Customer Support Bot",
                        "description": "Handles customer inquiries"
                    },
                    environment_id="prod_env"
                )
            ]
        )
        response = await client.bulk.execute(request)
        print(response.outputs["create-agent-001"].status)
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

        return BulkResponse.model_validate(response)
