"""AgentSpan endpoint client."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import ValidationError

from prefactor_http.exceptions import PrefactorResponseContractError
from prefactor_http.models.agent_span import (
    AgentSpan,
    CreateAgentSpanRequest,
    FinishSpanRequest,
)
from prefactor_http.models.base import ApiResponse
from prefactor_http.models.types import AgentStatus, FinishStatus

if TYPE_CHECKING:
    from prefactor_http.client import PrefactorHttpClient


def _validate_idempotency_key(key: str) -> None:
    """Validate that an idempotency key is at most 64 characters.

    Args:
        key: The idempotency key to validate.

    Raises:
        ValueError: If the key exceeds 64 characters.
    """
    if len(key) > 64:
        raise ValueError(
            f"Idempotency key must be at most 64 characters, got {len(key)}"
        )


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

    def _parse_response(self, response: dict, operation: str) -> AgentSpan:
        """Parse a typed API response and wrap schema mismatches."""
        try:
            api_response = ApiResponse[AgentSpan](**response)
        except ValidationError as exc:
            raise PrefactorResponseContractError(
                f"Invalid response payload for {operation}",
                cause=exc,
            ) from exc
        return api_response.details

    async def create(
        self,
        agent_instance_id: str,
        schema_name: str,
        status: AgentStatus,
        payload: dict | None = None,
        result_payload: dict | None = None,
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
            status: Status for the span
            payload: Optional span payload data
            result_payload: Optional result payload data
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
        if idempotency_key is not None:
            _validate_idempotency_key(idempotency_key)

        create_request = CreateAgentSpanRequest(
            agent_instance_id=agent_instance_id,
            schema_name=schema_name,
            status=status,
            payload=payload or {},
            result_payload=result_payload,
            id=id,
            parent_span_id=parent_span_id,
            started_at=started_at.isoformat() if started_at else None,
            finished_at=finished_at.isoformat() if finished_at else None,
            idempotency_key=idempotency_key,
        )

        details = create_request.model_dump(exclude_none=True)
        body = {"details": details}

        response = await self._client.request(
            "POST",
            "/api/v1/agent_spans",
            json_data=body,
        )

        return self._parse_response(response, "agent_spans.create")

    async def finish(
        self,
        agent_span_id: str,
        status: FinishStatus | None = None,
        result_payload: dict | None = None,
        timestamp: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> AgentSpan:
        """Finish an agent span.

        POST /api/v1/agent_spans/{agent_span_id}/finish

        Args:
            agent_span_id: The span ID
            status: Optional finish status (complete, failed, cancelled)
            result_payload: Optional result payload data
            timestamp: Optional finish time (defaults to now)
            idempotency_key: Optional idempotency key

        Returns:
            The updated agent span

        Raises:
            PrefactorNotFoundError: If span not found
            PrefactorApiError: On other errors
        """
        if idempotency_key is not None:
            _validate_idempotency_key(idempotency_key)

        finish_request = FinishSpanRequest(
            status=status,
            result_payload=result_payload,
            timestamp=timestamp.isoformat() if timestamp else None,
            idempotency_key=idempotency_key,
        )

        response = await self._client.request(
            "POST",
            f"/api/v1/agent_spans/{agent_span_id}/finish",
            json_data=finish_request.model_dump(exclude_none=True),
        )

        return self._parse_response(response, "agent_spans.finish")
