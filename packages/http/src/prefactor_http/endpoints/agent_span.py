"""AgentSpan endpoint client."""

from datetime import datetime
from typing import TYPE_CHECKING

from prefactor_http.models.agent_span import (
    AgentSpan,
    CreateAgentSpanRequest,
    FinishSpanRequest,
)
from prefactor_http.models.base import ApiResponse

if TYPE_CHECKING:
    from prefactor_http.client import PrefactorHttpClient


class AgentSpanClient:
    """Client for AgentSpan POST endpoints.

    Provides methods to interact with agent spans including:
    - create: Create a new agent span
    - finish: Mark a span as finished
    """

    def __init__(self, http_client: "PrefactorHttpClient"):
        """Initialize the client.

        Args:
            http_client: The main HTTP client instance.
        """
        self._client = http_client

    async def create(
        self,
        agent_instance_id: str,
        schema_name: str,
        payload: dict | None = None,
        id: str | None = None,
        parent_span_id: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> AgentSpan:
        """Create a new agent span.

        POST /api/v1/agent_spans

        Args:
            agent_instance_id: ID of the agent instance this span belongs to
            schema_name: Name of the schema for this span
            payload: Optional span payload data
            id: Optional custom ID for the span
            parent_span_id: Optional parent span ID
            started_at: Optional start time
            finished_at: Optional finish time
            idempotency_key: Optional idempotency key

        Returns:
            The created agent span

        Raises:
            PrefactorApiError: On API errors
            PrefactorValidationError: On validation errors
        """
        create_request = CreateAgentSpanRequest(
            agent_instance_id=agent_instance_id,
            schema_name=schema_name,
            payload=payload or {},
            id=id,
            parent_span_id=parent_span_id,
            started_at=started_at.isoformat() if started_at else None,
            finished_at=finished_at.isoformat() if finished_at else None,
            idempotency_key=idempotency_key,
        )

        response = await self._client.request(
            "POST",
            "/api/v1/agent_spans",
            json_data=create_request.model_dump(exclude_none=True),
        )

        api_response = ApiResponse[AgentSpan](**response)
        return api_response.details

    async def finish(
        self,
        agent_span_id: str,
        timestamp: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> AgentSpan:
        """Finish an agent span.

        POST /api/v1/agent_spans/{agent_span_id}/finish

        Args:
            agent_span_id: The span ID
            timestamp: Optional finish time (defaults to now)
            idempotency_key: Optional idempotency key

        Returns:
            The updated agent span

        Raises:
            PrefactorNotFoundError: If span not found
            PrefactorApiError: On other errors
        """
        finish_request = FinishSpanRequest(
            timestamp=timestamp.isoformat() if timestamp else None,
            idempotency_key=idempotency_key,
        )

        response = await self._client.request(
            "POST",
            f"/api/v1/agent_spans/{agent_span_id}/finish",
            json_data=finish_request.model_dump(exclude_none=True),
        )

        api_response = ApiResponse[AgentSpan](**response)
        return api_response.details
