"""Tests for Prefactor HTTP Client and idempotency functionality."""

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from prefactor_http import (
    HttpClientConfig,
    PrefactorAuthError,
    PrefactorHttpClient,
    PrefactorNotFoundError,
    PrefactorResponseContractError,
    PrefactorRetryExhaustedError,
    PrefactorValidationError,
)
from prefactor_http._version import PACKAGE_NAME, PACKAGE_VERSION


@pytest.fixture
def config():
    """Create test configuration."""
    return HttpClientConfig(
        api_url="https://api.test.com",
        api_token="test-token",
        max_retries=1,
        initial_retry_delay=0.01,
        max_retry_delay=0.1,
    )


@pytest.fixture
async def client(config):
    """Create test client."""
    client = PrefactorHttpClient(config)
    await client._ensure_session()
    yield client
    await client.close()


class TestIdempotencyKey:
    """Tests for idempotency key functionality."""

    @pytest.mark.asyncio
    async def test_idempotency_key_header_set(self, client, config):
        """Test that idempotency key is set as header when provided."""

        test_key = "test-idempotency-key-123"

        # Mock the session.request method
        with patch.object(client._session, "request") as mock_request:
            # Setup mock response
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

            # Make request with idempotency key
            await client.request(
                method="POST",
                path="/api/v1/agent_instance/register",
                json_data={"agent_id": "test"},
                idempotency_key=test_key,
            )

            # Verify the header was set
            call_args = mock_request.call_args
            headers = call_args[1].get("headers", {})
            assert headers.get("Idempotency-Key") == test_key

    @pytest.mark.asyncio
    async def test_idempotency_key_not_set_when_none(self, client, config):
        """Test that idempotency key header is not present when not provided."""

        with patch.object(client._session, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

            # Make request without idempotency key
            await client.request(
                method="POST",
                path="/api/v1/agent_spans",
                json_data={"agent_instance_id": "test"},
            )

            # Verify the header is not present
            call_args = mock_request.call_args
            headers = call_args[1].get("headers", {})
            assert "Idempotency-Key" not in headers

    @pytest.mark.asyncio
    async def test_idempotency_key_preserves_original_request(self, config):
        """Test that idempotency key is preserved across retries."""
        import aiohttp

        # Create a config with enough retries for this test
        test_config = HttpClientConfig(
            api_url=config.api_url,
            api_token=config.api_token,
            max_retries=2,  # Need 2 retries for 3 total attempts
            initial_retry_delay=0.01,
            max_retry_delay=0.1,
        )

        test_key = "unique-idempotency-key-abc123"
        call_count = 0

        # Create a mock async context manager class
        class MockResponseContext:
            def __init__(self, response_data):
                self._response = AsyncMock()
                self._response.status = 200
                self._response.json = AsyncMock(return_value=response_data)

            async def __aenter__(self):
                return self._response

            async def __aexit__(self, exc_type, exc, tb):
                return None

        # Create a mock request function that returns the context manager
        def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            headers = kwargs.get("headers", {})

            # Verify key is present in all attempts
            assert headers.get("Idempotency-Key") == test_key

            if call_count < 3:
                raise aiohttp.ClientError("Network error")

            return MockResponseContext({"success": True})

        async with PrefactorHttpClient(test_config) as client:
            with patch.object(client._session, "request", mock_request):
                await client.request(
                    method="POST",
                    path="/api/v1/agent_spans",
                    json_data={"agent_instance_id": "test"},
                    idempotency_key=test_key,
                )

                # Should have been called 3 times (initial + 2 retries)
                assert call_count == 3

    @pytest.mark.asyncio
    async def test_idempotency_key_guid_generation_example(self, client):
        """Test example of generating idempotency keys."""
        # Example: How users can generate idempotency keys

        # Generate a unique key for this operation
        idempotency_key = str(uuid.uuid4())

        with patch.object(
            client, "_make_request", return_value={"success": True}
        ) as mock_request:
            await client.request(
                method="POST",
                path="/api/v1/agent_instance/register",
                json_data={"agent_id": "test"},
                idempotency_key=idempotency_key,
            )

            # Verify key was used
            assert mock_request.called
            call_kwargs = mock_request.call_args[1]
            assert call_kwargs.get("idempotency_key") == idempotency_key


class TestHTTPClientRequest:
    """Tests for HTTP client request functionality."""

    @pytest.mark.asyncio
    async def test_successful_post_request(self, client):
        """Test successful POST request."""

        expected_response = {"status": "success", "details": {"id": "123"}}

        with patch.object(client._session, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=expected_response)
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

            response = await client.request(
                method="POST", path="/api/v1/test", json_data={"data": "test"}
            )

            assert response == expected_response

    @pytest.mark.asyncio
    async def test_404_error_raises_not_found(self, client):
        """Test that 404 error raises PrefactorNotFoundError."""

        with patch.object(client._session, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 404
            mock_response.json = AsyncMock(
                return_value={"code": "not_found", "message": "Resource not found"}
            )
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(PrefactorNotFoundError) as exc_info:
                await client.request(
                    method="POST", path="/api/v1/agent_instance/unknown-id"
                )

            assert exc_info.value.status_code == 404
            assert exc_info.value.code == "not_found"

    @pytest.mark.asyncio
    async def test_401_error_raises_auth_error(self, client):
        """Test that 401 error raises PrefactorAuthError."""

        with patch.object(client._session, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 401
            mock_response.json = AsyncMock(
                return_value={"code": "unauthorized", "message": "Invalid credentials"}
            )
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(PrefactorAuthError) as exc_info:
                await client.request(method="POST", path="/api/v1/test")

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_422_error_raises_validation_error(self, client):
        """Test that 422 error raises PrefactorValidationError with details."""

        with patch.object(client._session, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 422
            mock_response.json = AsyncMock(
                return_value={
                    "code": "validation_error",
                    "message": "Invalid input",
                    "errors": {
                        "agent_id": ["Required field"],
                        "schema_name": ["Invalid schema"],
                    },
                }
            )
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(PrefactorValidationError) as exc_info:
                await client.request(method="POST", path="/api/v1/agent_spans")

            assert exc_info.value.status_code == 422
            assert "agent_id" in exc_info.value.errors
            assert ["Required field"] == exc_info.value.errors["agent_id"]

    @pytest.mark.asyncio
    async def test_network_error_triggers_retry_then_exhausted(self, client):
        """Test network errors trigger retry and raise PrefactorRetryExhaustedError."""
        import aiohttp

        with patch.object(client._session, "request") as mock_request:
            mock_request.side_effect = aiohttp.ClientError("Connection failed")

            with pytest.raises(PrefactorRetryExhaustedError) as exc_info:
                await client.request(method="POST", path="/api/v1/test")

            # Should have been called initial + max_retries times
            assert mock_request.call_count == 2  # 1 + max_retries (1)
            assert "failed after" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_error_triggers_retry_then_exhausted(self, client):
        """Timeout errors should be treated as transient and retried."""

        with patch.object(client._session, "request") as mock_request:
            mock_request.side_effect = asyncio.TimeoutError("timed out")

            with pytest.raises(PrefactorRetryExhaustedError) as exc_info:
                await client.request(method="POST", path="/api/v1/test")

            assert mock_request.call_count == 2
            assert isinstance(exc_info.value.last_error, asyncio.TimeoutError)

    @pytest.mark.asyncio
    async def test_malformed_success_body_raises_contract_error(self, client):
        """Invalid JSON on a successful response should raise a contract error."""

        with patch.object(client._session, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.text = AsyncMock(return_value="<html>ok</html>")
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(PrefactorResponseContractError) as exc_info:
                await client.request(method="POST", path="/api/v1/test")

            assert exc_info.value.status_code == 200
            assert "html" in (exc_info.value.body_snippet or "")

    @pytest.mark.asyncio
    async def test_malformed_error_body_raises_contract_error(self, client):
        """Invalid JSON on an error response should preserve body context."""

        with patch.object(client._session, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 500
            mock_response.text = AsyncMock(return_value="<html>server error</html>")
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(PrefactorResponseContractError) as exc_info:
                await client.request(method="POST", path="/api/v1/test")

            assert exc_info.value.status_code == 500
            assert "server error" in (exc_info.value.body_snippet or "")


class TestAuthorizationHeader:
    """Tests for authorization header."""

    @pytest.mark.asyncio
    async def test_authorization_header_set(self, client, config):
        """Test that Authorization header is set correctly."""

        with patch.object(client._session, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

            await client.request(method="POST", path="/api/v1/test")

            call_args = mock_request.call_args
            headers = call_args[1].get("headers", {})
            assert headers.get("Authorization") == f"Bearer {config.api_token}"

    @pytest.mark.asyncio
    async def test_sdk_header_set(self, client):
        """Test that the default SDK header is set correctly."""

        with patch.object(client._session, "request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"success": True})
            mock_request.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

            await client.request(method="POST", path="/api/v1/test")

            call_args = mock_request.call_args
            headers = call_args[1].get("headers", {})
            assert headers.get("X-Prefactor-SDK") == f"{PACKAGE_NAME}@{PACKAGE_VERSION}"

    @pytest.mark.asyncio
    async def test_sdk_header_override_set(self, config):
        """Test that a custom SDK header override is used when provided."""

        client = PrefactorHttpClient(
            config,
            sdk_header="test-sdk@0.0.0",
        )
        await client._ensure_session()

        try:
            with patch.object(client._session, "request") as mock_request:
                mock_response = AsyncMock()
                mock_response.status = 200
                mock_response.json = AsyncMock(return_value={"success": True})
                mock_request.return_value.__aenter__ = AsyncMock(
                    return_value=mock_response
                )
                mock_request.return_value.__aexit__ = AsyncMock(return_value=None)

                await client.request(method="POST", path="/api/v1/test")

                call_args = mock_request.call_args
                headers = call_args[1].get("headers", {})
                assert headers.get("X-Prefactor-SDK") == "test-sdk@0.0.0"
        finally:
            await client.close()


class TestVersionHelpers:
    """Tests for package version exports."""

    def test_package_version_matches_public_export(self):
        """Test that the package version export matches the internal constant."""
        import prefactor_http

        assert prefactor_http.__version__ == PACKAGE_VERSION
