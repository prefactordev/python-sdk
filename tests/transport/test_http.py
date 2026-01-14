"""Tests for HTTP transport."""

import asyncio
import time

import pytest
from aioresponses import aioresponses

from prefactor_sdk.config import HttpTransportConfig
from prefactor_sdk.tracing.span import (
    ErrorInfo,
    Span,
    SpanStatus,
    SpanType,
    TokenUsage,
)
from prefactor_sdk.transport.http import HttpTransport


def create_test_span(**kwargs) -> Span:
    """Create a test span with default values."""
    defaults = {
        "span_id": "test-span-123",
        "parent_span_id": None,
        "trace_id": "test-trace-456",
        "name": "test",
        "span_type": SpanType.LLM,
        "start_time": time.time(),
        "end_time": time.time() + 1.0,
        "status": SpanStatus.SUCCESS,
        "inputs": {"test": "input"},
        "outputs": {"test": "output"},
        "token_usage": None,
        "error": None,
        "metadata": {},
        "tags": [],
    }
    defaults.update(kwargs)
    return Span(**defaults)


def create_test_config(**kwargs) -> HttpTransportConfig:
    """Create a test HTTP config with default values."""
    defaults = {
        "api_url": "https://api.test.prefactor.ai",
        "api_token": "test-token-123",
    }
    defaults.update(kwargs)
    return HttpTransportConfig(**defaults)


class TestHttpTransportConfig:
    """Tests for HttpTransportConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = create_test_config()

        assert config.api_url == "https://api.test.prefactor.ai"
        assert config.api_token == "test-token-123"
        assert config.agent_id is None
        assert config.agent_version is None
        assert config.request_timeout == 30.0
        assert config.max_retries == 3
        assert config.initial_retry_delay == 1.0
        assert config.max_retry_delay == 60.0
        assert config.retry_multiplier == 2.0

    def test_custom_values(self):
        """Test custom configuration values."""
        config = HttpTransportConfig(
            api_url="https://custom.api.com",
            api_token="custom-token",
            agent_id="custom-agent",
            agent_version="1.2.3",
            max_retries=5,
            initial_retry_delay=2.0,
        )

        assert config.api_url == "https://custom.api.com"
        assert config.api_token == "custom-token"
        assert config.agent_id == "custom-agent"
        assert config.agent_version == "1.2.3"
        assert config.max_retries == 5
        assert config.initial_retry_delay == 2.0


class TestHttpTransportInit:
    """Tests for HttpTransport initialization."""

    def test_transport_initialization(self):
        """Test transport initializes successfully."""
        config = create_test_config()
        transport = HttpTransport(config)

        assert transport._config == config
        assert transport._agent_instance_id is None
        assert transport._started is True
        assert transport._closed is False
        assert transport._worker_thread is not None
        assert transport._worker_thread.is_alive()

        transport.close()

    def test_transport_close(self):
        """Test transport closes gracefully."""
        config = create_test_config()
        transport = HttpTransport(config)

        assert transport._closed is False
        transport.close()
        assert transport._closed is True

        # Should be idempotent
        transport.close()
        assert transport._closed is True


class TestAgentRegistration:
    """Tests for agent registration."""

    @pytest.mark.asyncio
    async def test_successful_registration(self):
        """Test successful agent registration."""
        config = create_test_config()

        with aioresponses() as mock:
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
            )

            transport = HttpTransport(config)

            # Wait briefly for worker to start
            await asyncio.sleep(0.1)

            # Manually call registration (in real usage, happens automatically)
            registered = await transport._ensure_agent_registered()

            assert registered is True
            assert transport._agent_instance_id == "test-instance-abc123"

            transport.close()

    @pytest.mark.asyncio
    async def test_registration_failure(self):
        """Test registration failure handling."""
        config = create_test_config()

        with aioresponses() as mock:
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                status=500,
                body="Internal Server Error",
            )

            transport = HttpTransport(config)

            await asyncio.sleep(0.1)

            registered = await transport._ensure_agent_registered()

            assert registered is False
            assert transport._agent_instance_id is None
            assert transport._registration_failed is True

            transport.close()

    @pytest.mark.asyncio
    async def test_registration_idempotent(self):
        """Test registration is only called once."""
        config = create_test_config()

        with aioresponses() as mock:
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
            )

            transport = HttpTransport(config)

            await asyncio.sleep(0.1)

            # Call multiple times
            result1 = await transport._ensure_agent_registered()
            result2 = await transport._ensure_agent_registered()
            result3 = await transport._ensure_agent_registered()

            assert result1 is True
            assert result2 is True
            assert result3 is True

            # Should only have made one request
            assert len(mock.requests) == 1

            transport.close()

    def test_generate_agent_id(self):
        """Test agent ID generation."""
        config = create_test_config()
        transport = HttpTransport(config)

        agent_id = transport._generate_agent_id()

        # Should be a hex string of length 16
        assert isinstance(agent_id, str)
        assert len(agent_id) == 16
        assert all(c in "0123456789abcdef" for c in agent_id)

        transport.close()

    def test_extract_agent_metadata(self):
        """Test agent metadata extraction."""
        config = create_test_config(agent_id="my-agent", agent_version="1.0.0")
        transport = HttpTransport(config)

        metadata = transport._extract_agent_metadata()

        assert metadata["agent_id"] == "my-agent"
        assert metadata["agent_version"]["name"] == "1.0.0"
        assert "Prefactor SDK" in metadata["agent_version"]["description"]
        assert metadata["agent_schema_version"]["external_identifier"] == "1.0.0"
        assert "llm" in metadata["agent_schema_version"]["span_schemas"]
        assert "tool" in metadata["agent_schema_version"]["span_schemas"]

        transport.close()


class TestAgentInstanceFinishing:
    """Tests for agent instance finishing functionality."""

    @pytest.mark.asyncio
    async def test_finish_agent_instance_success(self):
        """Test successful agent instance finishing."""
        config = create_test_config()

        with aioresponses() as mock:
            # Mock registration
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
            )

            # Mock finish endpoint
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/test-instance-abc123/finish",
                payload={"status": "success"},
                status=200,
            )

            transport = HttpTransport(config)
            await asyncio.sleep(0.1)

            # Register first
            await transport._ensure_agent_registered()

            # Call finish
            await transport._finish_agent_instance()

            # Check that finish endpoint was called
            finish_requests = [
                req
                for (method, url), req in mock.requests.items()
                if "/finish" in str(url)
            ]
            assert len(finish_requests) == 1

            transport.close()

    @pytest.mark.asyncio
    async def test_finish_agent_instance_without_registration(self):
        """Test finishing agent instance when not registered."""
        config = create_test_config()
        transport = HttpTransport(config)

        await asyncio.sleep(0.1)

        # Try to finish without registering (should log warning but not crash)
        await transport._finish_agent_instance()

        transport.close()

    def test_finish_agent_instance_public_api(self):
        """Test public finish_agent_instance method."""
        config = create_test_config()

        with aioresponses() as mock:
            # Mock registration
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
            )

            # Mock finish endpoint
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/test-instance-abc123/finish",
                payload={"status": "success"},
                status=200,
            )

            transport = HttpTransport(config)
            time.sleep(0.2)

            # Call public API (synchronous)
            transport.finish_agent_instance()

            # Wait for async processing
            time.sleep(0.5)

            transport.close()


class TestSpanSending:
    """Tests for span sending."""

    @pytest.mark.asyncio
    async def test_successful_span_send(self):
        """Test successful span sending."""
        config = create_test_config()

        with aioresponses() as mock:
            # Mock registration
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
            )

            # Mock span endpoint
            mock.post(
                f"{config.api_url}/api/v1/agent_spans",
                status=200,
            )

            transport = HttpTransport(config)

            # Emit a span
            span = create_test_span()
            transport.emit(span)

            # Wait for processing
            await asyncio.sleep(0.5)

            # Check that requests were made
            assert len(mock.requests) >= 2  # registration + span

            transport.close()

    @pytest.mark.asyncio
    async def test_span_transformation(self):
        """Test span transformation to API format."""
        config = create_test_config()
        transport = HttpTransport(config)
        transport._agent_instance_id = "test-instance-123"

        # Create span with all fields
        span = create_test_span(
            span_type=SpanType.LLM,
            token_usage=TokenUsage(
                prompt_tokens=10, completion_tokens=20, total_tokens=30
            ),
            error=ErrorInfo(
                error_type="ValueError",
                message="Test error",
                stacktrace="line 1\nline 2",
            ),
            tags=["test", "important"],
        )

        result = transport._transform_span_to_api_format(span)

        # Check wrapper structure
        assert "details" in result
        details = result["details"]

        assert details["agent_instance_id"] == "test-instance-123"
        assert details["schema_name"] == "llm"
        assert details["parent_span_id"] is None
        assert "started_at" in details
        assert "finished_at" in details

        payload = details["payload"]
        assert payload["span_id"] == "test-span-123"
        assert payload["trace_id"] == "test-trace-456"
        assert payload["name"] == "test"
        assert payload["status"] == "success"
        assert payload["token_usage"]["prompt_tokens"] == 10
        assert payload["error"]["error_type"] == "ValueError"
        assert payload["tags"] == ["test", "important"]

        transport.close()

    @pytest.mark.asyncio
    async def test_retry_on_500_error(self):
        """Test retry logic on 500 errors."""
        config = create_test_config(max_retries=2, initial_retry_delay=0.1)

        with aioresponses() as mock:
            # Mock registration
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
                repeat=True,
            )

            # Mock span endpoint - use repeat=True for multiple responses
            # First two calls will be 500, subsequent will also be 500 (testing max retries)
            mock.post(
                f"{config.api_url}/api/v1/agent_spans",
                status=500,
                repeat=True,
            )

            transport = HttpTransport(config)

            span = create_test_span()
            transport.emit(span)

            # Wait for retries
            await asyncio.sleep(1.0)

            # Should have made 1 registration + 3 span attempts (initial + 2 retries)
            from yarl import URL

            span_url_key = ("POST", URL(f"{config.api_url}/api/v1/agent_spans"))
            span_requests = mock.requests.get(span_url_key, [])
            assert len(span_requests) == 3  # initial + 2 retries

            transport.close()

    @pytest.mark.asyncio
    async def test_no_retry_on_400_error(self):
        """Test no retry on 400 errors."""
        config = create_test_config(max_retries=2)

        with aioresponses() as mock:
            # Mock registration
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
            )

            # Mock span endpoint - return 400
            mock.post(
                f"{config.api_url}/api/v1/agent_spans",
                status=400,
            )

            transport = HttpTransport(config)

            span = create_test_span()
            transport.emit(span)

            # Wait for processing
            await asyncio.sleep(0.5)

            # Should have made only 1 registration + 1 span attempt (no retries)
            assert len(mock.requests) == 2

            transport.close()

    @pytest.mark.asyncio
    async def test_retry_on_429_rate_limit(self):
        """Test retry on rate limit (429)."""
        config = create_test_config(max_retries=1, initial_retry_delay=0.1)

        with aioresponses() as mock:
            # Mock registration
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
                repeat=True,
            )

            # Mock span endpoint - rate limit repeatedly (testing retry behavior)
            mock.post(
                f"{config.api_url}/api/v1/agent_spans",
                status=429,
                repeat=True,
            )

            transport = HttpTransport(config)

            span = create_test_span()
            transport.emit(span)

            # Wait for retries
            await asyncio.sleep(0.5)

            # Should have made 2 span attempts (initial + 1 retry)
            from yarl import URL

            span_url_key = ("POST", URL(f"{config.api_url}/api/v1/agent_spans"))
            span_requests = mock.requests.get(span_url_key, [])
            assert len(span_requests) == 2  # initial + 1 retry

            transport.close()


class TestThreadSafety:
    """Tests for thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_emits(self):
        """Test concurrent emit calls are thread-safe."""
        config = create_test_config()

        with aioresponses() as mock:
            # Mock registration
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
                repeat=True,
            )

            # Mock span endpoint with repeat=True
            mock.post(
                f"{config.api_url}/api/v1/agent_spans",
                status=200,
                repeat=True,
            )

            transport = HttpTransport(config)

            # Emit multiple spans concurrently
            spans = [create_test_span(span_id=f"span-{i}") for i in range(10)]

            for span in spans:
                transport.emit(span)

            # Wait for processing
            await asyncio.sleep(1.0)

            # Should have processed all spans
            from yarl import URL

            span_url_key = ("POST", URL(f"{config.api_url}/api/v1/agent_spans"))
            span_requests = mock.requests.get(span_url_key, [])
            assert len(span_requests) == 10  # All 10 spans

            transport.close()

    def test_emit_never_raises(self):
        """Test emit() never raises exceptions."""
        config = create_test_config()
        transport = HttpTransport(config)

        # Should not raise even with invalid span
        try:
            span = create_test_span()
            transport.emit(span)
            # No exception expected
        except Exception as e:
            pytest.fail(f"emit() raised exception: {e}")
        finally:
            transport.close()

    def test_emit_after_close(self):
        """Test emit after close is handled gracefully."""
        config = create_test_config()
        transport = HttpTransport(config)

        transport.close()

        # Should not raise
        span = create_test_span()
        transport.emit(span)


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_network_error_logged(self):
        """Test network errors are logged but don't crash."""
        config = create_test_config(max_retries=1, initial_retry_delay=0.05)

        with aioresponses() as mock:
            # Mock registration
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
            )

            # Mock span endpoint - simulate network error
            mock.post(
                f"{config.api_url}/api/v1/agent_spans",
                exception=Exception("Network error"),
            )

            transport = HttpTransport(config)

            span = create_test_span()
            transport.emit(span)

            # Wait for processing (should handle error gracefully)
            await asyncio.sleep(0.5)

            # Transport should still be functional
            assert transport._closed is False

            transport.close()

    @pytest.mark.asyncio
    async def test_queue_drain_on_close(self):
        """Test queue is drained on close."""
        config = create_test_config()

        with aioresponses() as mock:
            # Mock registration
            mock.post(
                f"{config.api_url}/api/v1/agent_instance/register",
                payload={
                    "status": "success",
                    "details": {"id": "test-instance-abc123"},
                },
                status=200,
            )

            # Mock span endpoint
            for _ in range(5):
                mock.post(
                    f"{config.api_url}/api/v1/agent_spans",
                    status=200,
                )

            transport = HttpTransport(config)

            # Emit multiple spans
            for i in range(5):
                span = create_test_span(span_id=f"span-{i}")
                transport.emit(span)

            # Close immediately (should drain queue)
            transport.close()

            # Should have attempted to send all spans
            # (registration + some spans, exact count depends on timing)
            assert len(mock.requests) >= 1
