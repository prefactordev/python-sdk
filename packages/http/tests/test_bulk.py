"""Tests for Bulk API endpoints."""

import pytest
from aioresponses import aioresponses
from prefactor_http import BulkItem, BulkRequest, HttpClientConfig, PrefactorHttpClient
from prefactor_http.exceptions import (
    PrefactorValidationError,
)


class TestBulkClient:
    """Tests for BulkClient class."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return HttpClientConfig(
            api_url="https://api.test.com",
            api_token="test-token",
            max_retries=0,
        )

    @pytest.mark.asyncio
    async def test_execute_bulk_request(self, config):
        """Test executing a bulk request successfully."""
        with aioresponses() as m:
            mock_response = {
                "status": "success",
                "outputs": {
                    "list-agents-001": {
                        "status": "success",
                        "summaries": [
                            {
                                "type": "agent",
                                "id": "agent_123",
                                "name": "Test Agent",
                            }
                        ],
                    },
                    "create-agent-001": {
                        "status": "success",
                        "details": {
                            "type": "agent",
                            "id": "agent_new",
                            "name": "New Agent",
                            "environment_id": "env_123",
                        },
                    },
                },
            }

            m.post(
                "https://api.test.com/api/v1/bulk",
                payload=mock_response,
                status=200,
            )

            async with PrefactorHttpClient(config) as client:
                request = BulkRequest(
                    items=[
                        BulkItem(
                            _type="agents/list",
                            idempotency_key="list-agents-001",
                            environment_id="env_123",
                        ),
                        BulkItem(
                            _type="agents/create",
                            idempotency_key="create-agent-001",
                            environment_id="env_123",
                            details={
                                "name": "New Agent",
                                "description": "Test",
                            },
                        ),
                    ]
                )

                response = await client.bulk.execute(request)

            assert response.status == "success"
            assert "list-agents-001" in response.outputs
            assert "create-agent-001" in response.outputs

            list_output = response.outputs["list-agents-001"]
            assert list_output.status == "success"

            create_output = response.outputs["create-agent-001"]
            assert create_output.status == "success"

    @pytest.mark.asyncio
    async def test_execute_bulk_with_errors(self, config):
        """Test executing bulk request with some failing items."""
        with aioresponses() as m:
            mock_response = {
                "status": "success",
                "outputs": {
                    "success-item": {
                        "status": "success",
                        "details": {"id": "agent_1"},
                    },
                    "error-item": {
                        "status": "error",
                        "code": "not_found",
                        "message": "Agent not found",
                    },
                },
            }

            m.post(
                "https://api.test.com/api/v1/bulk",
                payload=mock_response,
                status=200,
            )

            async with PrefactorHttpClient(config) as client:
                request = BulkRequest(
                    items=[
                        BulkItem(
                            _type="agents/show",
                            idempotency_key="success-item",
                            agent_id="agent_1",
                        ),
                        BulkItem(
                            _type="agents/show",
                            idempotency_key="error-item",
                            agent_id="non_existent",
                        ),
                    ]
                )

                response = await client.bulk.execute(request)

            assert response.status == "success"
            assert response.outputs["success-item"].status == "success"
            assert response.outputs["error-item"].status == "error"

    @pytest.mark.asyncio
    async def test_bulk_validation_error(self, config):
        """Test bulk request validation error."""
        with aioresponses() as m:
            mock_error = {
                "status": "error",
                "code": "validation_errors",
                "message": "Validation failed",
                "errors": {
                    "items": {
                        "status": "error",
                        "code": "required",
                        "message": "At least one item required",
                    }
                },
            }

            m.post(
                "https://api.test.com/api/v1/bulk",
                payload=mock_error,
                status=422,
            )

            async with PrefactorHttpClient(config) as client:
                from prefactor_http.models.bulk import BulkItem, BulkRequest

                request = BulkRequest(
                    items=[
                        BulkItem(
                            _type="agents/create",
                            idempotency_key="test-key-001",
                        ),
                    ]
                )

                with pytest.raises(PrefactorValidationError):
                    await client.bulk.execute(request)

    def test_bulk_request_unique_idempotency_keys(self, config):
        """Test that bulk request validates unique idempotency keys."""
        with pytest.raises(ValueError, match="unique"):
            BulkRequest(
                items=[
                    BulkItem(
                        _type="agents/list",
                        idempotency_key="duplicate-key",
                        environment_id="env_1",
                    ),
                    BulkItem(
                        _type="agents/list",
                        idempotency_key="duplicate-key",
                        environment_id="env_2",
                    ),
                ]
            )


class TestBulkItemValidation:
    """Tests for BulkItem validation."""

    def test_bulk_item_min_idempotency_key_length(self):
        """Test that idempotency key must be at least 8 characters."""
        with pytest.raises(ValueError):
            BulkItem(
                _type="agents/list",
                idempotency_key="short",  # Less than 8 chars
                environment_id="env_123",
            )

    def test_bulk_item_max_idempotency_key_length(self):
        """Test that idempotency key cannot exceed 64 characters."""
        with pytest.raises(ValueError):
            BulkItem(
                _type="agents/list",
                idempotency_key="a" * 65,  # More than 64 chars
                environment_id="env_123",
            )

    def test_bulk_item_extra_fields_allowed(self):
        """Test that BulkItem allows extra fields for operation-specific params."""
        item = BulkItem(
            _type="agents/create",
            idempotency_key="create-agent-123",
            environment_id="env_123",
            details={"name": "Test Agent"},
            foo="bar",
        )

        assert item.type == "agents/create"
        assert item.idempotency_key == "create-agent-123"
        # Extra fields should be included in model dump
        data = item.model_dump(by_alias=True)
        assert data["environment_id"] == "env_123"
        assert data["details"]["name"] == "Test Agent"
        assert data["foo"] == "bar"


class TestBulkRequestValidation:
    """Tests for BulkRequest validation."""

    def test_bulk_request_min_items(self):
        """Test that bulk request requires at least one item."""
        with pytest.raises(ValueError):
            BulkRequest(items=[])

    def test_bulk_request_valid_items(self):
        """Test creating valid bulk request."""
        request = BulkRequest(
            items=[
                BulkItem(
                    _type="agents/list",
                    idempotency_key="list-key-001",
                    environment_id="env_123",
                ),
            ]
        )

        assert len(request.items) == 1
        assert request.items[0].type == "agents/list"
