"""Tests for TerminationMonitor — 19 tests covering primary path, fallback poll,
reset(), and callback lifecycle."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from prefactor_core.monitoring.termination_monitor import TerminationMonitor


def _make_monitor(fetch_instance=None) -> TerminationMonitor:
    if fetch_instance is None:
        fetch_instance = AsyncMock(
            return_value=MagicMock(status="active", termination_reason=None)
        )
    return TerminationMonitor(fetch_instance=fetch_instance)


def _terminated_instance(reason: str | None = "test reason"):
    inst = MagicMock()
    inst.status = "terminated"
    inst.termination_reason = reason
    return inst


# ---------------------------------------------------------------------------
# Primary path (5 tests)
# ---------------------------------------------------------------------------


class TestPrimaryPath:
    async def test_detect_termination_sets_event(self):
        monitor = _make_monitor()
        assert not monitor.get_termination_event().is_set()
        monitor.detect_termination("reason")
        assert monitor.get_termination_event().is_set()

    async def test_reason_propagates(self):
        monitor = _make_monitor()
        monitor.detect_termination("my reason")
        assert monitor.termination_reason == "my reason"

    async def test_null_reason_accepted(self):
        monitor = _make_monitor()
        monitor.detect_termination(None)
        assert monitor.get_termination_event().is_set()
        assert monitor.termination_reason is None

    async def test_second_detect_termination_is_idempotent(self):
        callback = MagicMock()
        monitor = _make_monitor()
        monitor.subscribe(callback)
        monitor.detect_termination("first")
        monitor.detect_termination("second")
        callback.assert_called_once()
        assert monitor.termination_reason == "first"

    async def test_detect_termination_noop_after_destroy(self):
        monitor = _make_monitor()
        monitor.destroy()
        monitor.detect_termination("reason")
        assert not monitor.get_termination_event().is_set()


# ---------------------------------------------------------------------------
# Fallback poll (5 tests)
# ---------------------------------------------------------------------------


class TestFallbackPoll:
    async def test_poll_starts_when_instance_id_arrives(self):
        monitor = _make_monitor()
        monitor.sync("inst-1")
        await asyncio.sleep(0)  # yield to let task start
        assert monitor._poll_task is not None
        assert not monitor._poll_task.done()
        monitor.destroy()

    async def test_poll_stops_when_sync_called_with_none(self):
        monitor = _make_monitor()
        monitor.sync("inst-1")
        await asyncio.sleep(0)
        poll_task = monitor._poll_task
        monitor.sync(None)
        await asyncio.sleep(0)
        assert poll_task.cancelled() or poll_task.done()
        monitor.destroy()

    async def test_no_poll_without_instance_id(self):
        monitor = _make_monitor()
        monitor.sync(None)
        await asyncio.sleep(0)
        assert monitor._poll_task is None
        monitor.destroy()

    async def test_poll_stops_after_termination_detected(self):
        monitor = _make_monitor()
        monitor.sync("inst-1")
        await asyncio.sleep(0)
        poll_task = monitor._poll_task
        monitor.detect_termination("reason")
        await asyncio.sleep(0)
        assert poll_task.cancelled() or poll_task.done()
        monitor.destroy()

    async def test_poll_survives_transient_http_errors(self):
        fetch = AsyncMock(side_effect=Exception("network error"))
        monitor = TerminationMonitor(fetch_instance=fetch, poll_interval=0.05)
        monitor.sync("inst-1")
        await asyncio.sleep(0.2)  # let poll fire a couple times
        # monitor should not be terminated — error was swallowed
        assert not monitor.get_termination_event().is_set()
        monitor.destroy()


# ---------------------------------------------------------------------------
# reset() (7 tests)
# ---------------------------------------------------------------------------


class TestReset:
    async def test_reset_creates_fresh_event(self):
        monitor = _make_monitor()
        monitor.detect_termination("reason")
        old_event = monitor.get_termination_event()
        assert old_event.is_set()
        monitor.reset()
        new_event = monitor.get_termination_event()
        assert not new_event.is_set()
        assert new_event is not old_event

    async def test_reset_allows_new_termination_after_sync_with_new_id(self):
        monitor = _make_monitor()
        monitor.detect_termination("run 1")
        monitor.reset()
        # fenced — detect_termination should be blocked
        monitor.detect_termination("stale")
        assert not monitor.get_termination_event().is_set()
        # sync with new id lifts fence
        monitor.sync("inst-2")
        monitor.detect_termination("run 2")
        assert monitor.get_termination_event().is_set()
        assert monitor.termination_reason == "run 2"
        monitor.destroy()

    async def test_get_termination_event_returns_new_event_after_reset(self):
        monitor = _make_monitor()
        getter = monitor.get_termination_event
        monitor.detect_termination("reason")
        monitor.reset()
        # getter returns new (unset) event
        assert not getter().is_set()

    async def test_reset_cancels_poll_task(self):
        monitor = _make_monitor()
        monitor.sync("inst-1")
        await asyncio.sleep(0)
        poll_task = monitor._poll_task
        monitor.reset()
        await asyncio.sleep(0)
        assert poll_task.cancelled() or poll_task.done()

    async def test_reset_preserves_callbacks(self):
        callback = MagicMock()
        monitor = _make_monitor()
        monitor.subscribe(callback)
        monitor.reset()
        # sync to lift fence, then detect
        monitor.sync("inst-2")
        monitor.detect_termination("after reset")
        callback.assert_called_once()

    async def test_fence_blocks_detect_termination_until_sync_with_new_id(self):
        monitor = _make_monitor()
        monitor.detect_termination("run 1")
        monitor.reset()  # fenced = True

        # stale span response fires during queue drain
        monitor.detect_termination("stale span response")
        assert not monitor.get_termination_event().is_set()

        # sync with None doesn't lift fence
        monitor.sync(None)
        monitor.detect_termination("still stale")
        assert not monitor.get_termination_event().is_set()

        # sync with new instance id lifts fence
        monitor.sync("instance-2")
        monitor.detect_termination("run 2")
        assert monitor.get_termination_event().is_set()
        assert monitor.termination_reason == "run 2"
        monitor.destroy()

    async def test_stale_poll_response_discarded_after_reset(self):
        """Poll fires for old instance after reset — generation check discards it."""
        slow_fetch = AsyncMock(return_value=_terminated_instance("old run"))
        monitor = TerminationMonitor(fetch_instance=slow_fetch, poll_interval=0.05)
        monitor.sync("inst-1")
        await asyncio.sleep(0)  # poll task started

        # reset before poll completes
        monitor.reset()
        await asyncio.sleep(0.2)  # let poll fire with old generation

        # monitor should NOT be terminated
        assert not monitor.get_termination_event().is_set()
        monitor.destroy()


# ---------------------------------------------------------------------------
# Callback lifecycle (2 tests)
# ---------------------------------------------------------------------------


class TestCallbackLifecycle:
    async def test_unsubscribe_removes_callback(self):
        callback = MagicMock()
        monitor = _make_monitor()
        unsubscribe = monitor.subscribe(callback)
        unsubscribe()
        monitor.detect_termination("reason")
        callback.assert_not_called()

    async def test_callbacks_fire_in_registration_order(self):
        order = []
        monitor = _make_monitor()
        monitor.subscribe(lambda: order.append(1))
        monitor.subscribe(lambda: order.append(2))
        monitor.subscribe(lambda: order.append(3))
        monitor.detect_termination("reason")
        assert order == [1, 2, 3]
