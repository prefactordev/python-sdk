"""STDIO transport for emitting spans to stdout."""

import sys
import threading
from dataclasses import asdict

import orjson

from prefactor_core.tracing.span import Span
from prefactor_core.transport.base import Transport
from prefactor_core.utils.logging import get_logger
from prefactor_core.utils.serialization import serialize_value

logger = get_logger("transport.stdio")


class StdioTransport(Transport):
    """
    Transport that emits spans as newline-delimited JSON to stdout.

    Thread-safe implementation using a lock for concurrent writes.
    """

    def __init__(self):
        """Initialize the STDIO transport."""
        self._lock = threading.Lock()
        self._closed = False

    def emit(self, span: Span) -> None:
        """
        Emit a span as JSON to stdout.

        Args:
            span: The span to emit.
        """
        if self._closed:
            logger.warning("Attempted to emit span after transport closed")
            return

        try:
            # Convert span to dict
            span_dict = asdict(span)

            # Serialize values to handle non-JSON-serializable objects
            span_dict = serialize_value(span_dict)

            # Serialize to JSON
            json_bytes = orjson.dumps(span_dict)

            # Write to stdout with thread safety
            with self._lock:
                # Check if stdout has a buffer attribute (real stdout)
                # or if it's a StringIO (for testing)
                if hasattr(sys.stdout, "buffer"):
                    sys.stdout.buffer.write(json_bytes)
                    sys.stdout.buffer.write(b"\n")
                    sys.stdout.buffer.flush()
                else:
                    # For StringIO or other file-like objects
                    sys.stdout.write(json_bytes.decode("utf-8"))
                    sys.stdout.write("\n")
                    sys.stdout.flush()

        except Exception as e:
            # Never raise - fail gracefully
            logger.error(f"Failed to emit span: {e}", exc_info=True)

    def close(self) -> None:
        """Close the transport."""
        self._closed = True
        # Ensure stdout is flushed
        try:
            sys.stdout.flush()
        except Exception as e:
            logger.error(f"Failed to flush stdout: {e}", exc_info=True)
