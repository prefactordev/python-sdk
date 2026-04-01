"""Tests for SpanContext finish behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from prefactor_core.span_context import SpanContext


@pytest.mark.asyncio
async def test_explicit_complete_then_finish_is_a_no_op():
    """An already-finished span should not enqueue a duplicate finish."""
    span_manager = AsyncMock()
    span_manager.start = AsyncMock(return_value="api-span-id")
    span_manager.finish = AsyncMock()

    context = SpanContext("temp-span-id", span_manager)

    await context.complete({"ok": True})
    await context.finish()

    assert span_manager.start.await_count == 1
    assert span_manager.finish.await_count == 1


@pytest.mark.asyncio
async def test_failed_finish_can_retry_same_request():
    """The same finish request should be retryable until it succeeds."""
    span_manager = AsyncMock()
    span_manager.start = AsyncMock(return_value="api-span-id")
    span_manager.finish = AsyncMock(side_effect=[RuntimeError("boom"), None])

    context = SpanContext("temp-span-id", span_manager)

    with pytest.raises(RuntimeError, match="boom"):
        await context.complete({"ok": True})

    await context.finish()

    assert span_manager.start.await_count == 1
    assert span_manager.finish.await_count == 2
