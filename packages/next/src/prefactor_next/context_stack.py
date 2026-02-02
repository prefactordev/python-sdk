"""Span context stack for managing nested span relationships.

The SpanContextStack provides a stack-based context tracking system for
nested spans. Each async context maintains its own stack of active span IDs,
allowing automatic parent detection when creating new spans.

This module uses contextvars to ensure proper isolation between concurrent
async operations.
"""

from contextvars import ContextVar
from typing import Optional

# Context variable to hold the span stack for the current async context
# Each async task gets its own copy of this variable
_current_span_stack: ContextVar[list[str]] = ContextVar("span_stack", default=[])


class SpanContextStack:
    """Manages a stack of active span IDs within an async context.

    The stack tracks the hierarchy of nested spans. The top of the stack
    is always the current (innermost) active span, which serves as the
    default parent for any new spans created within the same context.

    This class uses contextvars to ensure that each async task maintains
    its own independent stack, preventing interference between concurrent
    operations.

    Example:
        # Root span
        SpanContextStack.push("span-1")
        assert SpanContextStack.peek() == "span-1"

        # Nested span (child of span-1)
        SpanContextStack.push("span-2")
        assert SpanContextStack.peek() == "span-2"

        # Exit nested span
        SpanContextStack.pop()
        assert SpanContextStack.peek() == "span-1"

        # Exit root span
        SpanContextStack.pop()
        assert SpanContextStack.peek() is None
    """

    @classmethod
    def get_stack(cls) -> list[str]:
        """Get the current span stack for this async context.

        Returns:
            A list of span IDs, from outermost to innermost.
            Returns an empty list if no spans are active.
        """
        return _current_span_stack.get()

    @classmethod
    def push(cls, span_id: str) -> None:
        """Push a span ID onto the stack.

        This marks the span as the current (innermost) active span.

        Args:
            span_id: The ID of the span to push onto the stack.
        """
        stack = cls.get_stack()
        new_stack = stack + [span_id]
        _current_span_stack.set(new_stack)

    @classmethod
    def pop(cls) -> Optional[str]:
        """Pop and return the current span ID from the stack.

        Returns:
            The span ID that was removed from the stack, or None
            if the stack was empty.
        """
        stack = cls.get_stack()
        if not stack:
            return None

        span_id = stack[-1]
        new_stack = stack[:-1]
        _current_span_stack.set(new_stack)
        return span_id

    @classmethod
    def peek(cls) -> Optional[str]:
        """Get the current span ID without removing it from the stack.

        Returns:
            The ID of the current (innermost) span, or None if no
            spans are active in this context.
        """
        stack = cls.get_stack()
        return stack[-1] if stack else None

    @classmethod
    def depth(cls) -> int:
        """Get the current nesting depth.

        Returns:
            The number of active spans in the stack (0 if empty).
        """
        return len(cls.get_stack())

    @classmethod
    def is_empty(cls) -> bool:
        """Check if the stack is empty.

        Returns:
            True if no spans are currently active.
        """
        return len(cls.get_stack()) == 0


__all__ = ["SpanContextStack"]
