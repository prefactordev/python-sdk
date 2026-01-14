"""Context propagation for spans using contextvars."""

import contextvars
from typing import Optional

from prefactor_sdk.tracing.span import Span

# ContextVar for storing the current span
_current_span: contextvars.ContextVar[Optional[Span]] = contextvars.ContextVar(
    "current_span",
    default=None,
)


class SpanContext:
    """Manages span context using contextvars for async-safe propagation."""

    @staticmethod
    def get_current() -> Optional[Span]:
        """
        Get the current span from the context.

        Returns:
            The current span, or None if no span is set.
        """
        return _current_span.get()

    @staticmethod
    def set_current(span: Span) -> None:
        """
        Set the current span in the context.

        Args:
            span: The span to set as current.
        """
        _current_span.set(span)

    @staticmethod
    def clear() -> None:
        """Clear the current span from the context."""
        _current_span.set(None)
