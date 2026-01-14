"""HTTP transport for sending spans to Prefactor backend API."""

import asyncio
import hashlib
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Union

import aiohttp

from prefactor_sdk.config import HttpTransportConfig
from prefactor_sdk.tracing.span import Span, SpanType
from prefactor_sdk.transport.base import Transport
from prefactor_sdk.utils.logging import get_logger
from prefactor_sdk.utils.serialization import serialize_value

logger = get_logger("transport.http")


class QueueItemType(str, Enum):
    """Types of items that can be queued."""

    SPAN = "span"
    START_AGENT = "start_agent"
    FINISH_AGENT = "finish_agent"


@dataclass
class QueueItem:
    """Item in the processing queue."""

    item_type: QueueItemType
    data: Any


class HttpTransport(Transport):
    """
    HTTP transport that sends spans to Prefactor backend API.

    Thread-safe transport with hybrid sync/async design:
    - Public API is synchronous (emit, close)
    - Internal implementation uses asyncio for non-blocking HTTP I/O
    - Background worker thread runs async event loop
    """

    def __init__(self, config: HttpTransportConfig):
        """
        Initialize HTTP transport.

        Args:
            config: HTTP transport configuration.
        """
        self._config = config

        # Agent instance management
        self._agent_instance_id: Optional[str] = None
        self._registration_lock = threading.Lock()
        self._registration_failed = False
        self._agent_instance_started = False
        self._agent_instance_finished = False

        # Async infrastructure
        self._queue: Optional[asyncio.Queue] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

        # HTTP client
        self._session: Optional[aiohttp.ClientSession] = None

        # State
        self._closed = False
        self._started = False

        # Start background worker
        self._start_worker()

    def emit(self, span: Span) -> None:
        """
        Emit a span to the queue (synchronous, non-blocking).

        Args:
            span: The span to emit.
        """
        if self._closed:
            logger.warning("Attempted to emit span after transport closed")
            return

        if not self._started:
            logger.warning("Transport not started")
            return

        try:
            # Thread-safe call to put span in asyncio queue
            item = QueueItem(item_type=QueueItemType.SPAN, data=span)
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)
        except Exception as e:
            # Never raise - fail gracefully
            logger.error(f"Failed to enqueue span: {e}", exc_info=True)

    def start_agent_instance(self) -> None:
        """
        Mark the agent instance as started (synchronous, non-blocking).

        This should be called when agent execution begins.
        """
        if self._closed:
            logger.warning("Attempted to start agent instance after transport closed")
            return

        if not self._started:
            logger.warning("Transport not started")
            return

        try:
            # Queue start request
            item = QueueItem(item_type=QueueItemType.START_AGENT, data=None)
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)
            logger.debug("Queued agent instance start request")
        except Exception as e:
            # Never raise - fail gracefully
            logger.error(f"Failed to enqueue start request: {e}", exc_info=True)

    def finish_agent_instance(self) -> None:
        """
        Mark the agent instance as finished (synchronous, non-blocking).

        This should be called when agent execution completes.
        """
        if self._closed:
            logger.warning("Attempted to finish agent instance after transport closed")
            return

        if not self._started:
            logger.warning("Transport not started")
            return

        try:
            # Queue finish request
            item = QueueItem(item_type=QueueItemType.FINISH_AGENT, data=None)
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)
            logger.debug("Queued agent instance finish request")
        except Exception as e:
            # Never raise - fail gracefully
            logger.error(f"Failed to enqueue finish request: {e}", exc_info=True)

    def close(self) -> None:
        """Close the transport and wait for pending spans to be sent."""
        if self._closed:
            return

        logger.info("Closing HTTP transport")
        self._closed = True

        # Signal shutdown to worker
        self._shutdown_event.set()

        # Wait for worker thread to finish (with timeout)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=10.0)
            if self._worker_thread.is_alive():
                logger.warning("Worker thread did not shutdown gracefully")

        logger.info("HTTP transport closed")

    def _start_worker(self) -> None:
        """Start the background worker thread."""
        # Create new event loop for worker thread
        self._loop = asyncio.new_event_loop()

        # Create unbounded queue
        asyncio.set_event_loop(self._loop)
        self._queue = asyncio.Queue()

        # Start worker thread
        self._worker_thread = threading.Thread(
            target=self._run_worker,
            name="prefactor-http-worker",
            daemon=True,
        )
        self._worker_thread.start()
        self._started = True

        logger.debug("Started HTTP transport worker thread")

    def _run_worker(self) -> None:
        """Run the worker event loop (called in worker thread)."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._worker_loop())
        except Exception as e:
            logger.error(f"Worker loop crashed: {e}", exc_info=True)
        finally:
            self._loop.close()

    async def _worker_loop(self) -> None:
        """Main worker loop that processes items from the queue."""
        # Create HTTP session
        self._session = aiohttp.ClientSession()

        try:
            while not self._shutdown_event.is_set():
                try:
                    # Wait for item with timeout (allows checking shutdown)
                    item = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                try:
                    # Ensure agent is registered before processing
                    if not await self._ensure_agent_registered():
                        logger.warning("Agent not registered, dropping item")
                        continue

                    # Process item based on type
                    if item.item_type == QueueItemType.SPAN:
                        await self._send_span(item.data)
                    elif item.item_type == QueueItemType.START_AGENT:
                        await self._start_agent_instance()
                    elif item.item_type == QueueItemType.FINISH_AGENT:
                        await self._finish_agent_instance()
                    else:
                        logger.warning(f"Unknown queue item type: {item.item_type}")

                except Exception as e:
                    logger.error(f"Error processing queue item: {e}", exc_info=True)

            # Drain remaining items with timeout
            logger.info("Draining remaining queue items...")
            await self._drain_queue(timeout=5.0)

        finally:
            await self._session.close()
            logger.debug("HTTP session closed")

    async def _drain_queue(self, timeout: float) -> None:
        """
        Drain remaining items from queue with timeout.

        Args:
            timeout: Maximum time to spend draining in seconds.
        """
        try:
            end_time = asyncio.get_event_loop().time() + timeout

            while not self._queue.empty():
                if asyncio.get_event_loop().time() > end_time:
                    logger.warning(
                        f"Drain timeout reached, {self._queue.qsize()} items remaining"
                    )
                    break

                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=0.1)

                    if await self._ensure_agent_registered():
                        if item.item_type == QueueItemType.SPAN:
                            await self._send_span(item.data)
                        elif item.item_type == QueueItemType.START_AGENT:
                            await self._start_agent_instance()
                        elif item.item_type == QueueItemType.FINISH_AGENT:
                            await self._finish_agent_instance()
                    else:
                        logger.warning("Cannot drain item, agent not registered")

                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error draining item: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in drain_queue: {e}", exc_info=True)

    async def _ensure_agent_registered(self) -> bool:
        """
        Ensure agent instance is registered (idempotent, thread-safe).

        Returns:
            True if agent is registered, False otherwise.
        """
        # Already registered
        if self._agent_instance_id is not None:
            return True

        # Registration already failed, don't retry
        if self._registration_failed:
            return False

        # Try to acquire lock (non-blocking)
        if not self._registration_lock.acquire(blocking=False):
            # Another coroutine is registering, wait briefly and check again
            await asyncio.sleep(0.1)
            return self._agent_instance_id is not None

        try:
            # Double-check after acquiring lock
            if self._agent_instance_id is not None:
                return True

            # Attempt registration
            logger.info("Registering agent instance...")
            self._agent_instance_id = await self._register_agent_instance()

            if self._agent_instance_id:
                logger.info(f"Agent registered: {self._agent_instance_id}")
                return True
            else:
                logger.error("Agent registration failed")
                self._registration_failed = True
                return False

        finally:
            self._registration_lock.release()

    async def _register_agent_instance(self) -> Optional[str]:
        """
        Register agent instance with backend.

        Returns:
            Agent instance ID if successful, None otherwise.
        """
        url = f"{self._config.api_url}/api/v1/agent_instance/register"
        headers = {
            "Authorization": f"Bearer {self._config.api_token}",
            "Content-Type": "application/json",
        }

        payload = self._extract_agent_metadata()

        try:
            async with self._session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._config.request_timeout),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("details", {}).get("id")
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Registration failed: {response.status} - {error_text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Registration error: {e}", exc_info=True)
            return None

    def _extract_agent_metadata(self) -> dict[str, Any]:
        """
        Extract agent metadata for registration.

        Returns:
            Agent metadata dict for API call.
        """
        return {
            "agent_id": self._config.agent_id or self._generate_agent_id(),
            "agent_version": {
                "name": self._config.agent_version or "unknown",
                "description": "Prefactor SDK",
                "external_identifier": self._config.agent_version
                or self._get_git_version(),
            },
            "agent_schema_version": {
                "external_identifier": "1.0.0",
                "span_schemas": {
                    "agent": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "const": "agent"}
                        },
                    },
                    "llm": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "const": "llm"}
                        },
                    },
                    "tool": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "const": "tool"}
                        },
                    },
                    "chain": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "const": "chain"}
                        },
                    },
                    "retriever": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "const": "retriever"}
                        },
                    },
                },
            },
        }

    def _generate_agent_id(self) -> str:
        """
        Generate agent ID from main module path.

        Returns:
            Generated agent ID (hash of main file path).
        """
        import __main__

        main_file = getattr(__main__, "__file__", "unknown")
        return hashlib.sha256(main_file.encode()).hexdigest()[:16]

    def _get_git_version(self) -> str:
        """
        Get git commit hash if available.

        Returns:
            Git commit hash (short form) or "unknown".
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if result.returncode == 0:
                return result.stdout.strip()[:8]
        except Exception:
            pass
        return "unknown"

    async def _start_agent_instance(self) -> None:
        """
        Mark the agent instance as started in the backend.

        This updates the agent instance status from "pending" to "active".
        Only allows starting once per agent instance.
        """
        if not self._agent_instance_id:
            logger.warning("Cannot start agent instance: not registered")
            return

        if self._agent_instance_started:
            logger.debug("Agent instance already started, skipping")
            return

        url = f"{self._config.api_url}/api/v1/agent_instance/{self._agent_instance_id}/start"
        headers = {
            "Authorization": f"Bearer {self._config.api_token}",
            "Content-Type": "application/json",
        }

        # Use current timestamp
        payload = {"timestamp": datetime.now(timezone.utc).isoformat()}

        try:
            async with self._session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._config.request_timeout),
            ) as response:
                if response.status == 200:
                    self._agent_instance_started = True
                    logger.info(
                        f"Agent instance started: {self._agent_instance_id}"
                    )
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Failed to start agent instance: {response.status} - {error_text}"
                    )

        except Exception as e:
            logger.error(
                f"Error starting agent instance: {e}", exc_info=True
            )

    async def _finish_agent_instance(self) -> None:
        """
        Mark the agent instance as finished in the backend.

        This updates the agent instance status from "active" to "complete".
        Only allows finishing once per agent instance.
        """
        if not self._agent_instance_id:
            logger.warning("Cannot finish agent instance: not registered")
            return

        if self._agent_instance_finished:
            logger.debug("Agent instance already finished, skipping")
            return

        url = f"{self._config.api_url}/api/v1/agent_instance/{self._agent_instance_id}/finish"
        headers = {
            "Authorization": f"Bearer {self._config.api_token}",
            "Content-Type": "application/json",
        }

        # Use current timestamp
        payload = {"timestamp": datetime.now(timezone.utc).isoformat()}

        try:
            async with self._session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._config.request_timeout),
            ) as response:
                if response.status == 200:
                    self._agent_instance_finished = True
                    logger.info(
                        f"Agent instance finished: {self._agent_instance_id}"
                    )
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Failed to finish agent instance: {response.status} - {error_text}"
                    )

        except Exception as e:
            logger.error(
                f"Error finishing agent instance: {e}", exc_info=True
            )

    async def _send_span(self, span: Span, retry: int = 0) -> None:
        """
        Send span to backend with exponential backoff retry.

        Args:
            span: The span to send.
            retry: Current retry attempt (0-indexed).
        """
        url = f"{self._config.api_url}/api/v1/agent_spans"
        headers = {
            "Authorization": f"Bearer {self._config.api_token}",
            "Content-Type": "application/json",
        }

        payload = self._transform_span_to_api_format(span)

        try:
            async with self._session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._config.request_timeout),
            ) as response:
                if response.status == 200:
                    logger.debug(f"Successfully sent span {span.span_id}")
                    return
                elif response.status >= 500 or response.status == 429:
                    # Server error or rate limit - retry
                    error_text = await response.text()
                    raise aiohttp.ClientError(
                        f"Retryable error: {response.status} - {error_text}"
                    )
                else:
                    # Client error - don't retry
                    error_text = await response.text()
                    logger.error(
                        f"Non-retryable error for span {span.span_id}: {response.status} - {error_text}"
                    )
                    return

        except aiohttp.ClientError as e:
            # Retry logic for retryable errors
            if retry < self._config.max_retries:
                delay = min(
                    self._config.initial_retry_delay
                    * (self._config.retry_multiplier**retry),
                    self._config.max_retry_delay,
                )
                logger.warning(
                    f"Retry {retry + 1}/{self._config.max_retries} for span {span.span_id} in {delay}s: {e}"
                )
                await asyncio.sleep(delay)
                await self._send_span(span, retry + 1)
            else:
                logger.error(
                    f"Failed to send span {span.span_id} after {self._config.max_retries + 1} attempts: {e}"
                )

        except Exception as e:
            # Other errors (network, timeout, etc.)
            logger.error(f"Error sending span {span.span_id}: {e}", exc_info=True)

    def _transform_span_to_api_format(self, span: Span) -> dict[str, Any]:
        """
        Transform SDK Span to Prefactor API format.

        Args:
            span: The span to transform.

        Returns:
            Dict in API format ready for JSON serialization.
        """
        # Map span types to schema names
        schema_name_map = {
            SpanType.AGENT: "agent",
            SpanType.LLM: "llm",
            SpanType.TOOL: "tool",
            SpanType.CHAIN: "chain",
            SpanType.RETRIEVER: "retriever",
        }

        # Convert timestamps to ISO 8601
        started_at = datetime.fromtimestamp(
            span.start_time, tz=timezone.utc
        ).isoformat()

        finished_at = None
        if span.end_time:
            finished_at = datetime.fromtimestamp(
                span.end_time, tz=timezone.utc
            ).isoformat()

        # Build payload with all span data
        payload = {
            "span_id": span.span_id,
            "trace_id": span.trace_id,
            "name": span.name,
            "status": span.status.value,
            "inputs": span.inputs,
            "outputs": span.outputs,
            "metadata": span.metadata,
            "tags": span.tags,
        }

        if span.token_usage:
            payload["token_usage"] = {
                "prompt_tokens": span.token_usage.prompt_tokens,
                "completion_tokens": span.token_usage.completion_tokens,
                "total_tokens": span.token_usage.total_tokens,
            }

        if span.error:
            payload["error"] = {
                "error_type": span.error.error_type,
                "message": span.error.message,
                "stacktrace": span.error.stacktrace,
            }

        # Return API request format
        return {
            "details": {
                "agent_instance_id": self._agent_instance_id,
                "schema_name": schema_name_map[span.span_type],
                "payload": serialize_value(payload),
                "parent_span_id": span.parent_span_id,
                "started_at": started_at,
                "finished_at": finished_at,
            }
        }
