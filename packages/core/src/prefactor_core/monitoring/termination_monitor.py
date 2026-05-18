"""TerminationMonitor — detects agent instance termination via two paths:
1. Fast: control signal in span API responses (pushed via callback)
2. Slow: polling the instance status endpoint every `poll_interval` seconds
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

logger = logging.getLogger(__name__)


class TerminationMonitor:
    """Monitors an agent instance for termination.

    Thread-safety note: `detect_termination` and `get_termination_event().is_set()`
    are safe to call from sync worker threads — they only read/write a bool under
    the GIL (asyncio.Event._value is a plain bool).
    """

    def __init__(
        self,
        fetch_instance: Callable,
        poll_interval: float = 30.0,
    ) -> None:
        self._fetch_instance = fetch_instance
        self._poll_interval = poll_interval

        self._event = asyncio.Event()
        self._termination_reason: str | None = None
        self._callbacks: list[Callable[[], None]] = []

        self._current_instance_id: str | None = None
        self._poll_task: asyncio.Task | None = None
        self._destroyed = False

        # Fence blocks stale span callbacks from a previous run after reset()
        self._fenced = False
        # Generation increments on each reset so stale polls self-discard
        self._generation = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def termination_reason(self) -> str | None:
        return self._termination_reason

    def get_termination_event(self) -> asyncio.Event:
        return self._event

    def detect_termination(self, reason: str | None) -> None:
        """Signal that the instance has been terminated.

        No-op if already terminated, destroyed, or fenced (post-reset stale call).
        """
        if self._destroyed or self._event.is_set() or self._fenced:
            return
        self._termination_reason = reason
        self._event.set()
        self._stop_poll()
        for cb in list(self._callbacks):
            try:
                cb()
            except Exception:
                logger.exception("Termination callback failed: %r", cb)

    def sync(self, instance_id: str | None) -> None:
        """Update the tracked instance ID and start/stop the fallback poll.

        Idempotent: calling with the same non-None ID when a poll is already
        running does not restart it (preserving the sleep interval).
        """
        if instance_id is not None:
            self._fenced = False
        if instance_id == self._current_instance_id:
            # Same ID — no change needed; poll (if any) keeps running
            return
        self._current_instance_id = instance_id
        self._stop_poll()
        if instance_id is not None and not self._event.is_set() and not self._destroyed:
            self._start_poll(instance_id, self._generation)

    def reset(self) -> None:
        """Prepare monitor for the next agent run.

        - Creates a fresh (unset) event
        - Clears the termination reason
        - Cancels any in-flight poll
        - Sets fence so stale callbacks from the dying run are ignored
        - Increments generation so stale polls self-discard
        """
        self._stop_poll()
        self._event = asyncio.Event()
        self._termination_reason = None
        self._current_instance_id = None
        self._generation += 1
        self._fenced = True

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback invoked on termination. Returns an unsubscribe fn."""
        self._callbacks.append(callback)

        def unsubscribe() -> None:
            try:
                self._callbacks.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def destroy(self) -> None:
        """Permanently shut down the monitor (no further events will fire)."""
        self._destroyed = True
        self._stop_poll()
        self._callbacks.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_poll(self, instance_id: str, generation: int) -> None:
        self._poll_task = asyncio.get_event_loop().create_task(
            self._poll(instance_id, generation)
        )

    def _stop_poll(self) -> None:
        if self._poll_task is not None and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = None

    async def _poll(self, instance_id: str, generation: int) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            # Guard: generation changed means reset() was called
            if self._generation != generation:
                return
            try:
                instance = await self._fetch_instance(instance_id)
            except Exception:
                logger.debug("Termination poll error (transient)", exc_info=True)
                continue
            # Guard again after await
            if self._generation != generation:
                return
            if instance.status == "terminated":
                self.detect_termination(instance.termination_reason)
                return
