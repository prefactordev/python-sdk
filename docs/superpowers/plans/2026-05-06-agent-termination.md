# Agent Termination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement automatic agent termination detection so that when p2 terminates an instance, `PrefactorTerminatedError` is raised inside the user's next LLM/tool/agent call with no new public API required.

**Architecture:** A `TerminationMonitor` (owned by `PrefactorCoreClient`) watches for termination via two paths: control signals embedded in span API responses (fast), and a 30s fallback poll of the instance status endpoint. On detection it sets an `asyncio.Event`; the LangChain middleware checks this event at every async hook entry and raises `PrefactorTerminatedError`. `AgentInstanceHandle.finish()` resets the monitor (fence + new event) before enqueueing the HTTP finish so stale span responses from the dying run cannot kill the next run.

**Tech Stack:** Python 3.11+, asyncio, pytest-asyncio (auto mode), unittest.mock, aiohttp, pydantic, prefactor-core/http/langchain packages.

---

## File Map

### New files
| File | Responsibility |
|------|----------------|
| `packages/core/src/prefactor_core/monitoring/__init__.py` | Package init |
| `packages/core/src/prefactor_core/monitoring/termination_monitor.py` | `TerminationMonitor` state machine |
| `packages/core/tests/monitoring/__init__.py` | Test package init |
| `packages/core/tests/monitoring/test_termination_monitor.py` | 19 unit tests for `TerminationMonitor` |
| `packages/langchain/examples/termination_demo.py` | End-to-end demo script |

### Modified files
| File | Change |
|------|--------|
| `packages/core/src/prefactor_core/exceptions.py` | Add `PrefactorTerminatedError` |
| `packages/core/src/prefactor_core/__init__.py` | Export `PrefactorTerminatedError` |
| `packages/http/src/prefactor_http/models/agent_instance.py` | Add `terminated_reason: str \| None = None` to `AgentInstance` |
| `packages/http/src/prefactor_http/endpoints/agent_instance.py` | Add `get()` method |
| `packages/http/src/prefactor_http/endpoints/agent_span.py` | Add `control_signal_callback` param to `create()` and `finish()` |
| `packages/core/src/prefactor_core/client.py` | Add monitor, sync task, instance tracking, 409 swallow, control signal callback |
| `packages/core/src/prefactor_core/managers/agent_instance.py` | `finish()` calls `monitor.reset()` before enqueueing |
| `packages/langchain/src/prefactor_langchain/middleware.py` | Add `_throw_if_terminated()` + getter wiring at every hook entry |

---

## Task 1: PrefactorTerminatedError exception

**Files:**
- Modify: `packages/core/src/prefactor_core/exceptions.py`
- Modify: `packages/core/src/prefactor_core/__init__.py`
- Test: `packages/core/tests/test_imports.py`

- [ ] **Step 1: Add the exception class**

Open `packages/core/src/prefactor_core/exceptions.py`. Add after `PrefactorTelemetryFailureError`:

```python
class PrefactorTerminatedError(PrefactorCoreError):
    """Raised when the agent instance has been terminated by p2."""

    def __init__(self, reason: str | None = None) -> None:
        msg = (
            f"Agent instance terminated by p2: {reason}"
            if reason
            else "Agent instance terminated by p2"
        )
        super().__init__(msg)
        self.reason = reason
```

Also add `"PrefactorTerminatedError"` to the `__all__` list at the bottom of that file.

- [ ] **Step 2: Export from prefactor_core**

Open `packages/core/src/prefactor_core/__init__.py`. Add `PrefactorTerminatedError` to the exceptions import block:

```python
from .exceptions import (
    ClientAlreadyInitializedError,
    ClientNotInitializedError,
    InstanceNotFoundError,
    OperationError,
    PrefactorCoreError,
    PrefactorTelemetryFailureError,
    PrefactorTerminatedError,
    SpanNotFoundError,
)
```

Also add `"PrefactorTerminatedError"` to the `__all__` list under the `# Exceptions` comment.

- [ ] **Step 3: Verify import works**

```bash
cd /Users/mcb/code/python-sdk/.worktrees/pre-301-implement-agent-termination-in-python-sdk
python -c "from prefactor_core import PrefactorTerminatedError; e = PrefactorTerminatedError('test'); print(e.reason, str(e))"
```

Expected output: `test Agent instance terminated by p2: test`

- [ ] **Step 4: Run existing import test**

```bash
pytest packages/core/tests/test_imports.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add packages/core/src/prefactor_core/exceptions.py packages/core/src/prefactor_core/__init__.py
git commit -m "feat(core): add PrefactorTerminatedError exception"
```

---

## Task 2: AgentInstance model + GET endpoint

**Files:**
- Modify: `packages/http/src/prefactor_http/models/agent_instance.py`
- Modify: `packages/http/src/prefactor_http/endpoints/agent_instance.py`
- Test: `packages/http/tests/test_models.py` (add one test)
- Test: `packages/http/tests/test_endpoints.py` (add one test)

- [ ] **Step 1: Write failing model test**

Open `packages/http/tests/test_models.py`. Add at the end:

```python
class TestAgentInstanceTerminatedReason:
    def test_terminated_reason_defaults_none(self):
        from prefactor_http.models.agent_instance import AgentInstance
        from datetime import datetime, timezone
        instance = AgentInstance(
            type="agent_instance",
            id="inst-1",
            account_id="acc-1",
            agent_id="agent-1",
            agent_version_id="ver-1",
            environment_id="env-1",
            agent_deployment_id="dep-1",
            status="active",
            inserted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        assert instance.terminated_reason is None

    def test_terminated_reason_parsed(self):
        from prefactor_http.models.agent_instance import AgentInstance
        from datetime import datetime, timezone
        instance = AgentInstance(
            type="agent_instance",
            id="inst-1",
            account_id="acc-1",
            agent_id="agent-1",
            agent_version_id="ver-1",
            environment_id="env-1",
            agent_deployment_id="dep-1",
            status="terminated",
            inserted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            terminated_reason="admin action",
        )
        assert instance.terminated_reason == "admin action"
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest packages/http/tests/test_models.py::TestAgentInstanceTerminatedReason -v
```

Expected: FAIL — `AgentInstance` has no `terminated_reason` field.

- [ ] **Step 3: Add field to AgentInstance model**

Open `packages/http/src/prefactor_http/models/agent_instance.py`. In the `AgentInstance` class, add after `finished_at`:

```python
    terminated_reason: str | None = None
```

- [ ] **Step 4: Run to verify model tests pass**

```bash
pytest packages/http/tests/test_models.py::TestAgentInstanceTerminatedReason -v
```

Expected: PASS.

- [ ] **Step 5: Write failing endpoint GET test**

Open `packages/http/tests/test_endpoints.py`. Add at the end:

```python
class TestAgentInstanceGet:
    async def test_get_returns_agent_instance(self, http_client, mock_session):
        from aioresponses import aioresponses
        from datetime import datetime, timezone

        instance_data = {
            "status": "success",
            "details": {
                "type": "agent_instance",
                "id": "inst-123",
                "account_id": "acc-1",
                "agent_id": "agent-1",
                "agent_version_id": "ver-1",
                "environment_id": "env-1",
                "agent_deployment_id": "dep-1",
                "status": "terminated",
                "terminated_reason": "admin terminated",
                "inserted_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        with aioresponses() as m:
            m.get(
                "http://test.example.com/api/v1/agent_instance/inst-123",
                payload=instance_data,
            )
            result = await http_client.agent_instances.get("inst-123")

        assert result.id == "inst-123"
        assert result.status == "terminated"
        assert result.terminated_reason == "admin terminated"
```

Note: check `test_endpoints.py` for the existing `http_client` fixture signature and adapt if needed.

- [ ] **Step 6: Run to verify it fails**

```bash
pytest packages/http/tests/test_endpoints.py::TestAgentInstanceGet -v
```

Expected: FAIL — `AgentInstanceClient` has no `get()` method.

- [ ] **Step 7: Add get() method to AgentInstanceClient**

Open `packages/http/src/prefactor_http/endpoints/agent_instance.py`. Add after the `finish()` method:

```python
    async def get(self, agent_instance_id: str) -> AgentInstance:
        """Fetch an agent instance by ID.

        GET /api/v1/agent_instance/{agent_instance_id}

        Args:
            agent_instance_id: The instance ID to fetch.

        Returns:
            The agent instance.

        Raises:
            PrefactorNotFoundError: If instance not found.
            PrefactorApiError: On other errors.
        """
        response = await self._client.request(
            "GET",
            f"/api/v1/agent_instance/{agent_instance_id}",
        )
        return self._parse_response(response, "agent_instances.get")
```

- [ ] **Step 8: Run to verify endpoint tests pass**

```bash
pytest packages/http/tests/test_endpoints.py::TestAgentInstanceGet -v
```

Expected: PASS.

- [ ] **Step 9: Run full test suite**

```bash
pytest packages/http/tests/ -v
```

Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add packages/http/src/prefactor_http/models/agent_instance.py packages/http/src/prefactor_http/endpoints/agent_instance.py packages/http/tests/test_models.py packages/http/tests/test_endpoints.py
git commit -m "feat(http): add AgentInstance.terminated_reason field and get() endpoint"
```

---

## Task 3: AgentSpanClient control signal callback

**Files:**
- Modify: `packages/http/src/prefactor_http/endpoints/agent_span.py`
- Test: `packages/http/tests/test_endpoints.py` (add tests)

- [ ] **Step 1: Write failing tests**

Open `packages/http/tests/test_endpoints.py`. Add:

```python
class TestAgentSpanControlSignal:
    async def test_create_calls_callback_when_control_signal_present(self, http_client):
        from aioresponses import aioresponses
        from datetime import datetime, timezone
        from unittest.mock import MagicMock

        span_data = {
            "status": "success",
            "details": {
                "type": "agent_span",
                "id": "span-1",
                "agent_instance_id": "inst-1",
                "schema_name": "langchain:llm",
                "status": "pending",
                "payload": {},
            },
            "control": {"terminate": True, "reason": "demo termination"},
        }

        callback = MagicMock()
        with aioresponses() as m:
            m.post(
                "http://test.example.com/api/v1/agent_spans",
                payload=span_data,
            )
            await http_client.agent_spans.create(
                agent_instance_id="inst-1",
                schema_name="langchain:llm",
                status="pending",
                control_signal_callback=callback,
            )

        callback.assert_called_once_with("demo termination")

    async def test_create_no_callback_when_control_absent(self, http_client):
        from aioresponses import aioresponses
        from unittest.mock import MagicMock

        span_data = {
            "status": "success",
            "details": {
                "type": "agent_span",
                "id": "span-1",
                "agent_instance_id": "inst-1",
                "schema_name": "langchain:llm",
                "status": "pending",
                "payload": {},
            },
        }

        callback = MagicMock()
        with aioresponses() as m:
            m.post(
                "http://test.example.com/api/v1/agent_spans",
                payload=span_data,
            )
            await http_client.agent_spans.create(
                agent_instance_id="inst-1",
                schema_name="langchain:llm",
                status="pending",
                control_signal_callback=callback,
            )

        callback.assert_not_called()

    async def test_finish_calls_callback_when_control_signal_present(self, http_client):
        from aioresponses import aioresponses
        from unittest.mock import MagicMock

        span_data = {
            "status": "success",
            "details": {
                "type": "agent_span",
                "id": "span-1",
                "agent_instance_id": "inst-1",
                "schema_name": "langchain:llm",
                "status": "complete",
                "payload": {},
            },
            "control": {"terminate": True, "reason": None},
        }

        callback = MagicMock()
        with aioresponses() as m:
            m.post(
                "http://test.example.com/api/v1/agent_spans/span-1/finish",
                payload=span_data,
            )
            await http_client.agent_spans.finish(
                agent_span_id="span-1",
                control_signal_callback=callback,
            )

        callback.assert_called_once_with(None)
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest packages/http/tests/test_endpoints.py::TestAgentSpanControlSignal -v
```

Expected: FAIL — `create()` and `finish()` don't accept `control_signal_callback`.

- [ ] **Step 3: Add _check_control_signal helper and update create/finish**

Open `packages/http/src/prefactor_http/endpoints/agent_span.py`. Add after the imports:

```python
from typing import Callable


def _check_control_signal(
    response: dict,
    callback: Callable[[str | None], None],
) -> None:
    control = response.get("control")
    if control and control.get("terminate"):
        callback(control.get("reason"))
```

In `create()`, change the signature to add the optional param:

```python
    async def create(
        self,
        agent_instance_id: str,
        schema_name: str,
        status: AgentStatus,
        payload: dict | None = None,
        result_payload: dict | None = None,
        id: str | None = None,
        parent_span_id: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        idempotency_key: str | None = None,
        control_signal_callback: Callable[[str | None], None] | None = None,
    ) -> AgentSpan:
```

After `response = await self._client.request(...)`, before `return self._parse_response(...)`:

```python
        if control_signal_callback is not None:
            _check_control_signal(response, control_signal_callback)
```

In `finish()`, same pattern — add `control_signal_callback: Callable[[str | None], None] | None = None` to the signature, and after the response call add:

```python
        if control_signal_callback is not None:
            _check_control_signal(response, control_signal_callback)
```

- [ ] **Step 4: Run to verify tests pass**

```bash
pytest packages/http/tests/test_endpoints.py::TestAgentSpanControlSignal -v
```

Expected: PASS.

- [ ] **Step 5: Run full http test suite**

```bash
pytest packages/http/tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/http/src/prefactor_http/endpoints/agent_span.py packages/http/tests/test_endpoints.py
git commit -m "feat(http): add control signal callback to span create/finish"
```

---

## Task 4: TerminationMonitor — 19 unit tests + implementation

**Files:**
- Create: `packages/core/src/prefactor_core/monitoring/__init__.py`
- Create: `packages/core/src/prefactor_core/monitoring/termination_monitor.py`
- Create: `packages/core/tests/monitoring/__init__.py`
- Create: `packages/core/tests/monitoring/test_termination_monitor.py`

- [ ] **Step 1: Create package init files**

```bash
touch packages/core/src/prefactor_core/monitoring/__init__.py
touch packages/core/tests/monitoring/__init__.py
```

- [ ] **Step 2: Write all 19 failing tests**

Create `packages/core/tests/monitoring/test_termination_monitor.py`:

```python
"""Tests for TerminationMonitor — 19 tests covering primary path, fallback poll,
reset(), and callback lifecycle."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from prefactor_core.monitoring.termination_monitor import TerminationMonitor


def _make_monitor(fetch_instance=None) -> TerminationMonitor:
    if fetch_instance is None:
        fetch_instance = AsyncMock(return_value=MagicMock(status="active", terminated_reason=None))
    return TerminationMonitor(fetch_instance=fetch_instance)


def _terminated_instance(reason: str | None = "test reason"):
    inst = MagicMock()
    inst.status = "terminated"
    inst.terminated_reason = reason
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
        await asyncio.sleep(0.15)  # let poll fire a couple times
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
        await asyncio.sleep(0.15)  # let poll fire with old generation

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
```

- [ ] **Step 3: Run to verify all 19 fail**

```bash
pytest packages/core/tests/monitoring/test_termination_monitor.py -v
```

Expected: 19 failures — `prefactor_core.monitoring.termination_monitor` not found.

- [ ] **Step 4: Implement TerminationMonitor**

Create `packages/core/src/prefactor_core/monitoring/termination_monitor.py`:

```python
"""TerminationMonitor — detects agent instance termination via span signals and fallback poll."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    pass

logger = logging.getLogger("prefactor_core.termination_monitor")

_DEFAULT_POLL_INTERVAL = 30.0


class TerminationMonitor:
    """Watches for agent instance termination via two paths:
    1. Control signals embedded in span API responses (fast, primary).
    2. Periodic polling of the agent instance status endpoint (slow, fallback).

    State machine:
        Initial:    fenced=False, generation=0, terminated=False
        detect():   guard terminated/destroyed/fenced → set event, latch, fire callbacks
        sync(id):   guard destroyed/terminated → lift fence if new id; start/stop poll
        reset():    generation++, fenced=True, new event, cleared terminated state
        destroy():  destroyed=True, cancel poll, clear callbacks
    """

    def __init__(
        self,
        fetch_instance: Callable[[str], Awaitable],
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
    ) -> None:
        self._fetch_instance = fetch_instance
        self._poll_interval = poll_interval

        self._event: asyncio.Event = asyncio.Event()
        self._generation: int = 0
        self._fenced: bool = False
        self._poll_task: asyncio.Task | None = None
        self._tracking_instance_id: str | None = None
        self._terminated: bool = False
        self._destroyed: bool = False
        self._reason: str | None = None
        self._callbacks: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def termination_reason(self) -> str | None:
        return self._reason

    def get_termination_event(self) -> asyncio.Event:
        """Return the current termination event. Always call this — never capture."""
        return self._event

    def detect_termination(self, reason: str | None) -> None:
        if self._terminated or self._destroyed or self._fenced:
            return
        logger.debug(
            "[prefactor:termination-monitor] Termination signalled via span response. Reason: %s",
            reason,
        )
        self._terminated = True
        self._reason = reason
        self._event.set()
        self._stop_poll()
        for cb in list(self._callbacks):
            try:
                cb()
            except Exception:
                logger.exception("Termination callback raised")

    def sync(self, instance_id: str | None) -> None:
        if self._destroyed or self._terminated:
            return
        if self._fenced and instance_id is not None:
            self._fenced = False
        if instance_id != self._tracking_instance_id:
            self._tracking_instance_id = instance_id
            self._stop_poll()
            if instance_id is not None:
                self._start_poll(instance_id, self._generation)

    def reset(self) -> None:
        self._generation += 1
        self._fenced = True
        self._stop_poll()
        self._event = asyncio.Event()
        self._terminated = False
        self._reason = None
        self._tracking_instance_id = None

    def destroy(self) -> None:
        self._destroyed = True
        self._stop_poll()
        self._callbacks.clear()

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a termination callback. Returns an unsubscribe callable."""
        self._callbacks.append(callback)

        def unsubscribe() -> None:
            try:
                self._callbacks.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _start_poll(self, instance_id: str, generation: int) -> None:
        self._poll_task = asyncio.create_task(
            self._poll(instance_id, generation),
            name=f"termination-poll-{instance_id}",
        )

    def _stop_poll(self) -> None:
        if self._poll_task is not None and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = None

    async def _poll(self, instance_id: str, poll_generation: int) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            if self._generation != poll_generation:
                return
            try:
                instance = await self._fetch_instance(instance_id)
            except Exception:
                logger.debug(
                    "[prefactor:termination-monitor] Fallback poll error for %s — retrying",
                    instance_id,
                    exc_info=True,
                )
                continue
            if self._generation != poll_generation:
                return
            if instance.status == "terminated":
                self.detect_termination(getattr(instance, "terminated_reason", None))
                return
```

- [ ] **Step 5: Update monitoring __init__.py**

```python
# packages/core/src/prefactor_core/monitoring/__init__.py
from .termination_monitor import TerminationMonitor

__all__ = ["TerminationMonitor"]
```

- [ ] **Step 6: Run all 19 tests**

```bash
pytest packages/core/tests/monitoring/test_termination_monitor.py -v
```

Expected: all 19 pass. If `test_poll_survives_transient_http_errors` or `test_stale_poll_response_discarded_after_reset` are flaky, increase the sleep durations in those tests.

- [ ] **Step 7: Run full core test suite**

```bash
pytest packages/core/tests/ -v
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add packages/core/src/prefactor_core/monitoring/ packages/core/tests/monitoring/
git commit -m "feat(core): implement TerminationMonitor with 19 tests"
```

---

## Task 5: PrefactorCoreClient wiring

**Files:**
- Modify: `packages/core/src/prefactor_core/client.py`
- Test: `packages/core/tests/test_agent_instance_finish_status.py` (add 409 test)

This task wires the `TerminationMonitor` into the client: creates it in `initialize()`, starts the 1s sync loop, passes the control signal callback to span operations, tracks the current instance ID, and swallows 409 on `FINISH_AGENT_INSTANCE`.

- [ ] **Step 1: Write failing 409 swallow test**

Open `packages/core/tests/test_agent_instance_finish_status.py`. Add at the end:

```python
class TestFinishAgentInstance409Handling:
    async def test_409_on_finish_treated_as_success(self):
        """FINISH_AGENT_INSTANCE with 409 response should not raise."""
        from prefactor_http.exceptions import PrefactorApiError
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_http = MagicMock()
        mock_http.agent_instances = MagicMock()
        mock_http.agent_instances.finish = AsyncMock(
            side_effect=PrefactorApiError("already terminated", "conflict", 409)
        )
        mock_http.agent_spans = MagicMock()
        mock_http.agent_spans.create = AsyncMock()
        mock_http.agent_spans.finish = AsyncMock()

        from prefactor_core.client import PrefactorCoreClient
        from prefactor_core.config import PrefactorCoreConfig
        from prefactor_http.config import HttpClientConfig

        config = PrefactorCoreConfig(
            http_config=HttpClientConfig(api_url="http://fake", api_token="tok")
        )
        client = PrefactorCoreClient(config)
        client._http = mock_http
        client._initialized = True

        from prefactor_core.operations import Operation, OperationType
        from datetime import datetime, timezone

        op = Operation(
            type=OperationType.FINISH_AGENT_INSTANCE,
            payload={"instance_id": "inst-1", "idempotency_key": "key-1", "status": "complete"},
            timestamp=datetime.now(timezone.utc),
        )
        # Should not raise
        await client._process_operation(op)
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest packages/core/tests/test_agent_instance_finish_status.py::TestFinishAgentInstance409Handling -v
```

Expected: FAIL — 409 is re-raised.

- [ ] **Step 3: Modify PrefactorCoreClient**

Open `packages/core/src/prefactor_core/client.py`. Apply all changes:

**3a. Add imports at top:**

```python
import asyncio

from .monitoring.termination_monitor import TerminationMonitor
```

**3b. Add new instance fields in `__init__` after `self._telemetry_failure_observed = False`:**

```python
        self._termination_monitor: TerminationMonitor | None = None
        self._sync_task: asyncio.Task | None = None
        self._current_instance_id: str | None = None
```

**3c. In `initialize()`, after `self._initialized = True`, add:**

```python
        self._termination_monitor = TerminationMonitor(
            fetch_instance=self._fetch_instance_for_poll,
        )
        self._sync_task = asyncio.create_task(
            self._run_sync_loop(), name="prefactor-termination-sync"
        )
```

**3d. In `close()`, after `if not self._initialized: return`, add:**

```python
        if self._sync_task is not None and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

        if self._termination_monitor is not None:
            self._termination_monitor.destroy()
            self._termination_monitor = None
```

**3e. Add new methods to `PrefactorCoreClient` class:**

```python
    async def _fetch_instance_for_poll(self, instance_id: str):
        """Fetch instance for fallback termination poll."""
        if self._http is None:
            return None
        return await self._http.agent_instances.get(instance_id)

    async def _run_sync_loop(self) -> None:
        """Background 1s loop passing current instance ID to the termination monitor."""
        while True:
            await asyncio.sleep(1)
            if self._termination_monitor is not None:
                self._termination_monitor.sync(self._current_instance_id)

    def _on_control_signal(self, reason: str | None) -> None:
        """Called by span endpoints when a control signal is detected."""
        if self._termination_monitor is not None:
            self._termination_monitor.detect_termination(reason)

    def _set_current_instance(self, instance_id: str | None) -> None:
        self._current_instance_id = instance_id

    def _clear_current_instance(self, instance_id: str) -> None:
        if self._current_instance_id == instance_id:
            self._current_instance_id = None
```

**3f. In `create_agent_instance()`, after `instance_id = await self._instance_manager.register(...)`, add:**

```python
        self._set_current_instance(instance_id)
```

**3g. In `_process_operation()`, update the `FINISH_AGENT_INSTANCE` branch to swallow 409:**

```python
            elif operation.type == OperationType.FINISH_AGENT_INSTANCE:
                try:
                    await self._http.agent_instances.finish(
                        agent_instance_id=operation.payload["instance_id"],
                        status=operation.payload.get("status", "complete"),
                        timestamp=operation.timestamp,
                        idempotency_key=operation.payload.get("idempotency_key"),
                    )
                except PrefactorApiError as finish_err:
                    if finish_err.status_code == 409:
                        logger.debug(
                            "[prefactor:http] Agent instance %s already in terminal state; skipping finish.",
                            operation.payload["instance_id"],
                        )
                        return
                    raise
```

Add `PrefactorApiError` to the existing import from `prefactor_http.exceptions`:

```python
from prefactor_http.exceptions import PrefactorApiError, is_permanent_http_error, is_transient_http_error
```

**3h. In `_process_operation()`, update `CREATE_SPAN` and `FINISH_SPAN` to pass the callback:**

```python
            elif operation.type == OperationType.CREATE_SPAN:
                await self._http.agent_spans.create(
                    agent_instance_id=operation.payload["instance_id"],
                    schema_name=operation.payload["schema_name"],
                    status=operation.payload.get("status", "pending"),
                    id=operation.payload.get("span_id"),
                    parent_span_id=operation.payload.get("parent_span_id"),
                    payload=operation.payload.get("payload"),
                    control_signal_callback=self._on_control_signal,
                )

            elif operation.type == OperationType.FINISH_SPAN:
                await self._http.agent_spans.finish(
                    agent_span_id=operation.payload["span_id"],
                    status=operation.payload.get("status", "complete"),
                    result_payload=operation.payload.get("result_payload"),
                    timestamp=operation.timestamp,
                    idempotency_key=operation.payload.get("idempotency_key"),
                    control_signal_callback=self._on_control_signal,
                )
```

- [ ] **Step 4: Run the 409 test**

```bash
pytest packages/core/tests/test_agent_instance_finish_status.py::TestFinishAgentInstance409Handling -v
```

Expected: PASS.

- [ ] **Step 5: Run full core test suite**

```bash
pytest packages/core/tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/core/src/prefactor_core/client.py packages/core/tests/test_agent_instance_finish_status.py
git commit -m "feat(core): wire TerminationMonitor into PrefactorCoreClient"
```

---

## Task 6: AgentInstanceHandle.finish() calls monitor.reset()

**Files:**
- Modify: `packages/core/src/prefactor_core/managers/agent_instance.py`
- Test: `packages/core/tests/monitoring/test_termination_monitor.py` (already covers reset via unit tests; add integration test here)

- [ ] **Step 1: Write failing integration test**

Open `packages/core/tests/test_agent_instance_finish_status.py`. Add:

```python
class TestAgentInstanceHandleFinishResetsMonitor:
    async def test_finish_resets_termination_monitor(self):
        """handle.finish() should reset the termination monitor before enqueueing."""
        from unittest.mock import AsyncMock, MagicMock
        from prefactor_core.managers.agent_instance import AgentInstanceHandle
        from prefactor_core.monitoring.termination_monitor import TerminationMonitor

        fetch = AsyncMock(return_value=MagicMock(status="active", terminated_reason=None))
        monitor = TerminationMonitor(fetch_instance=fetch)
        monitor.detect_termination("run 1")
        assert monitor.get_termination_event().is_set()

        mock_client = MagicMock()
        mock_client._termination_monitor = monitor
        mock_client.instance_manager = MagicMock()
        mock_client.instance_manager.finish_with_idempotency_key = AsyncMock()

        handle = AgentInstanceHandle(instance_id="inst-1", client=mock_client)
        await handle.finish()

        # Monitor should be reset (new unset event)
        assert not monitor.get_termination_event().is_set()
        # finish_with_idempotency_key should still be called
        mock_client.instance_manager.finish_with_idempotency_key.assert_called_once()
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest packages/core/tests/test_agent_instance_finish_status.py::TestAgentInstanceHandleFinishResetsMonitor -v
```

Expected: FAIL — `finish()` doesn't call `monitor.reset()`.

- [ ] **Step 3: Update AgentInstanceHandle.finish()**

Open `packages/core/src/prefactor_core/managers/agent_instance.py`. Replace the `finish()` method:

```python
    async def finish(self, status: "FinishStatus" = "complete") -> None:
        """Mark the instance as finished.

        Resets the termination monitor (fence + new event) before enqueueing
        the HTTP finish so stale span responses from the dying run cannot
        trigger termination on the next run.

        Args:
            status: Terminal status for the instance — one of ``"complete"``,
                ``"failed"``, or ``"cancelled"``. Defaults to ``"complete"``.
        """
        monitor = getattr(self._client, "_termination_monitor", None)
        if monitor is not None:
            monitor.reset()
        self._client._clear_current_instance(self._instance_id)
        manager = self._client.instance_manager
        assert manager is not None
        await manager.finish_with_idempotency_key(
            self._instance_id,
            self._finish_idempotency_key,
            status=status,
        )
```

Note: `_clear_current_instance` is the method added to `PrefactorCoreClient` in Task 5.

- [ ] **Step 4: Run to verify test passes**

```bash
pytest packages/core/tests/test_agent_instance_finish_status.py::TestAgentInstanceHandleFinishResetsMonitor -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest packages/core/tests/ packages/http/tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add packages/core/src/prefactor_core/managers/agent_instance.py packages/core/tests/test_agent_instance_finish_status.py
git commit -m "feat(core): AgentInstanceHandle.finish() resets TerminationMonitor before enqueueing"
```

---

## Task 7: PrefactorMiddleware throwIfTerminated

**Files:**
- Modify: `packages/langchain/src/prefactor_langchain/middleware.py`
- Test: `packages/langchain/tests/test_middleware.py` (add tests)

- [ ] **Step 1: Write failing middleware termination tests**

Open `packages/langchain/tests/test_middleware.py`. Add at the end:

```python
class TestMiddlewareThrowIfTerminated:
    """Tests that middleware raises PrefactorTerminatedError when monitor is set."""

    def _make_middleware_with_monitor(self, terminated: bool = False, reason: str | None = "test reason"):
        """Build a PrefactorMiddleware with a mock monitor in the given state."""
        import asyncio
        from unittest.mock import MagicMock
        from prefactor_core.monitoring.termination_monitor import TerminationMonitor
        from prefactor_langchain.middleware import PrefactorMiddleware

        fetch = AsyncMock(return_value=MagicMock(status="active", terminated_reason=None))
        monitor = TerminationMonitor(fetch_instance=fetch)
        if terminated:
            monitor.detect_termination(reason)

        mock_client = MagicMock()
        mock_client._initialized = True
        mock_client._termination_monitor = monitor

        middleware = PrefactorMiddleware.__new__(PrefactorMiddleware)
        middleware._client = mock_client
        middleware._agent_id = None
        middleware._agent_name = None
        middleware._instance = MagicMock()
        middleware._owns_instance = False
        middleware._owns_client = False
        middleware._agent_span_cm = None
        middleware._agent_span_context = None
        middleware._agent_span_id = None
        middleware._current_parent_span_id = None
        middleware._loop = asyncio.get_event_loop()
        middleware._pending_emit_futures = []
        middleware._pending_emit_error = None
        middleware._tool_span_types = {}
        middleware._get_termination_event = monitor.get_termination_event

        return middleware, monitor

    async def test_throw_if_terminated_raises_when_event_set(self):
        from prefactor_core import PrefactorTerminatedError
        middleware, monitor = self._make_middleware_with_monitor(terminated=True, reason="test")
        with pytest.raises(PrefactorTerminatedError) as exc_info:
            middleware._throw_if_terminated()
        assert exc_info.value.reason == "test"

    async def test_throw_if_terminated_noop_when_not_terminated(self):
        middleware, _ = self._make_middleware_with_monitor(terminated=False)
        middleware._throw_if_terminated()  # should not raise

    async def test_throw_if_terminated_noop_when_getter_is_none(self):
        from prefactor_langchain.middleware import PrefactorMiddleware
        middleware = PrefactorMiddleware.__new__(PrefactorMiddleware)
        middleware._get_termination_event = None
        middleware._client = None
        middleware._throw_if_terminated()  # should not raise

    async def test_awrap_model_call_raises_when_terminated(self):
        from unittest.mock import AsyncMock
        from prefactor_core import PrefactorTerminatedError
        middleware, monitor = self._make_middleware_with_monitor(terminated=True, reason="terminated")
        with pytest.raises(PrefactorTerminatedError):
            await middleware.awrap_model_call(MagicMock(), AsyncMock())

    async def test_awrap_tool_call_raises_when_terminated(self):
        from unittest.mock import AsyncMock
        from prefactor_core import PrefactorTerminatedError
        middleware, monitor = self._make_middleware_with_monitor(terminated=True, reason="terminated")
        with pytest.raises(PrefactorTerminatedError):
            await middleware.awrap_tool_call(MagicMock(), AsyncMock())
```

Note: add `from unittest.mock import AsyncMock, MagicMock` at top of the test file if not already present.

- [ ] **Step 2: Run to verify they fail**

```bash
pytest packages/langchain/tests/test_middleware.py::TestMiddlewareThrowIfTerminated -v
```

Expected: FAIL — `_throw_if_terminated` not defined, `_get_termination_event` not wired.

- [ ] **Step 3: Add _throw_if_terminated to PrefactorMiddleware**

Open `packages/langchain/src/prefactor_langchain/middleware.py`.

**3a. Add import at top (with other prefactor_core imports):**

```python
from prefactor_core import (
    AgentInstanceHandle,
    PrefactorCoreClient,
    PrefactorCoreConfig,
    PrefactorTerminatedError,
    PrefactorTelemetryFailureError,
    SchemaRegistry,
    SpanContext,
)
```

**3b. In `__init__` for the `instance is not None` branch**, add before `return`:

```python
            self._get_termination_event = None
```

**3c. In `__init__` for the `client is not None` branch**, add near the other `self._` assignments:

```python
        self._get_termination_event = None
```

**3d. In `from_config()` classmethod**, add after the other `middleware._` assignments:

```python
        middleware._get_termination_event = None
```

**3e. In `_ensure_initialized()`**, after `await self._instance.start()`, add:

```python
            if (
                self._client is not None
                and hasattr(self._client, "_termination_monitor")
                and self._client._termination_monitor is not None
            ):
                self._get_termination_event = self._client._termination_monitor.get_termination_event
```

**3f. Add `_throw_if_terminated` method** (add it near the top of the class methods, after `_prefer_shutdown_error`):

```python
    def _throw_if_terminated(self) -> None:
        if self._get_termination_event is None:
            return
        event = self._get_termination_event()
        if event.is_set():
            monitor = (
                self._client._termination_monitor
                if self._client and hasattr(self._client, "_termination_monitor")
                else None
            )
            reason = monitor.termination_reason if monitor is not None else None
            raise PrefactorTerminatedError(reason)
```

**3g. Add `_throw_if_terminated()` calls at entry of async hooks:**

In `awrap_model_call()`, add as the first line of the method body (before `instance = await self._ensure_initialized()`):

```python
        self._throw_if_terminated()
```

In `awrap_tool_call()`, same — first line:

```python
        self._throw_if_terminated()
```

In `abefore_agent()`, add inside the `try` block before `instance = await self._ensure_initialized()`:

```python
            self._throw_if_terminated()
```

In `wrap_model_call()` (sync), add before `inputs = self._extract_model_inputs(request)`:

```python
        self._throw_if_terminated()
```

In `wrap_tool_call()` (sync), add before `inputs = self._extract_tool_inputs(request)`:

```python
        self._throw_if_terminated()
```

In `before_agent()` (sync), add inside the `try` block before `if self._instance is None:`:

```python
            self._throw_if_terminated()
```

- [ ] **Step 4: Run middleware termination tests**

```bash
pytest packages/langchain/tests/test_middleware.py::TestMiddlewareThrowIfTerminated -v
```

Expected: all 5 pass.

- [ ] **Step 5: Run full langchain test suite**

```bash
pytest packages/langchain/tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Run complete test suite**

```bash
pytest -v
```

Expected: all 250+ tests pass.

- [ ] **Step 7: Commit**

```bash
git add packages/langchain/src/prefactor_langchain/middleware.py packages/langchain/tests/test_middleware.py
git commit -m "feat(langchain): add _throw_if_terminated() to middleware hooks"
```

---

## Task 8: Demo script

**Files:**
- Create: `packages/langchain/examples/termination_demo.py`

- [ ] **Step 1: Create the demo**

Create `packages/langchain/examples/termination_demo.py`:

```python
"""Termination demo — runs a LangChain agent in a service loop and demonstrates
automatic detection of p2-initiated termination.

Required env vars:
    PREFACTOR_API_URL       e.g. http://localhost:4000
    PREFACTOR_AGENT_ID      agent ID on the target p2 instance
    PREFACTOR_API_TOKEN     API token

Optional env vars:
    PREFACTOR_AUTO_TERMINATE_DELAY  seconds before demo calls terminate API (default: 6)
    PREFACTOR_RESTART_DELAY         seconds to wait between runs (default: 75)

Usage:
    source .env && \\
        PREFACTOR_API_URL=http://localhost:4000 \\
        PREFACTOR_AGENT_ID=<agent-id> \\
        PREFACTOR_API_TOKEN=<token> \\
        PREFACTOR_AUTO_TERMINATE_DELAY=6 \\
        PREFACTOR_RESTART_DELAY=75 \\
        python packages/langchain/examples/termination_demo.py
"""

from __future__ import annotations

import asyncio
import logging
import os

import aiohttp
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from prefactor_core import PrefactorTerminatedError
from prefactor_langchain.middleware import PrefactorMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("termination-demo")


@tool
def get_current_time() -> str:
    """Return the current UTC time as a string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def terminate_after_delay(
    api_url: str,
    api_token: str,
    instance_id: str,
    delay: float,
) -> None:
    await asyncio.sleep(delay)
    url = f"{api_url.rstrip('/')}/api/v1/agent_instance/{instance_id}/terminate"
    logger.info("Calling terminate API: POST %s", url)
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
            json={},
        ) as resp:
            body = await resp.json()
            logger.info("Terminate API: status=%s", body.get("status"))


async def run_once(run_number: int, api_url: str, api_token: str, agent_id: str, auto_terminate_delay: float) -> None:
    middleware = PrefactorMiddleware.from_config(
        api_url=api_url,
        api_token=api_token,
        agent_id=agent_id,
        agent_name="termination-demo-agent",
    )

    model = ChatAnthropic(model="claude-haiku-4-5-20251001")
    agent = create_react_agent(model, tools=[get_current_time], checkpointer=None)
    agent.middleware = [middleware]

    instance = await middleware.ensure_initialized()
    logger.info("Run #%d — Agent instance: %s", run_number, instance.id)
    logger.info("Auto-terminate in %.0fs...", auto_terminate_delay)

    terminate_task = asyncio.create_task(
        terminate_after_delay(api_url, api_token, instance.id, auto_terminate_delay)
    )

    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "What time is it? Then keep asking me every 2 seconds."}]},
        )
        logger.info("Run #%d completed normally: %s", run_number, result)
    except PrefactorTerminatedError as e:
        logger.info("Run #%d terminated: %s", run_number, e)
        raise
    finally:
        terminate_task.cancel()
        try:
            await terminate_task
        except (asyncio.CancelledError, Exception):
            pass
        await middleware.close()


async def main() -> None:
    api_url = os.environ["PREFACTOR_API_URL"]
    api_token = os.environ["PREFACTOR_API_TOKEN"]
    agent_id = os.environ["PREFACTOR_AGENT_ID"]
    auto_terminate_delay = float(os.environ.get("PREFACTOR_AUTO_TERMINATE_DELAY", "6"))
    restart_delay = float(os.environ.get("PREFACTOR_RESTART_DELAY", "75"))

    run_number = 0
    while True:
        run_number += 1
        try:
            await run_once(run_number, api_url, api_token, agent_id, auto_terminate_delay)
        except PrefactorTerminatedError:
            logger.info("Service continues — next run in %.0fs.", restart_delay)
            await asyncio.sleep(restart_delay)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            break
        except Exception as e:
            logger.exception("Unexpected error in run #%d: %s", run_number, e)
            await asyncio.sleep(restart_delay)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add packages/langchain/examples/termination_demo.py
git commit -m "feat(langchain): add termination demo script"
```

---

## Task 9: End-to-end test against local p2

**Prerequisites:** Local p2 running at `http://localhost:4000`, valid API token.

This task validates the full termination detection path against real p2 responses. Use the CLI to create the agent and inspect spans.

- [ ] **Step 1: Create a test agent via CLI**

```bash
# Log in to mukil-01 account on localhost
pfctr login --url http://localhost:4000

# Create a new agent for this feature
pfctr agents create --name "termination-sdk-test" --description "Agent Termination SDK Test"
# Note the agent ID from output
```

- [ ] **Step 2: Create a deployment-scoped API token via CLI**

```bash
pfctr tokens create --agent <agent-id> --name "termination-test-token"
# Note the token
```

- [ ] **Step 3: Run the unit test suite one final time to confirm clean baseline**

```bash
pytest -v
```

Expected: all 250+ tests pass, 0 failures.

- [ ] **Step 4: Run the termination demo against local p2**

```bash
cd /Users/mcb/code/python-sdk/.worktrees/pre-301-implement-agent-termination-in-python-sdk
PREFACTOR_API_URL=http://localhost:4000 \
  PREFACTOR_AGENT_ID=<agent-id-from-step-1> \
  PREFACTOR_API_TOKEN=<token-from-step-2> \
  PREFACTOR_AUTO_TERMINATE_DELAY=6 \
  PREFACTOR_RESTART_DELAY=30 \
  python packages/langchain/examples/termination_demo.py
```

Expected log output per run:

```
Run #1 — Agent instance: <instance-id>
Auto-terminate in 6s...
Calling terminate API: POST http://localhost:4000/api/v1/agent_instance/<id>/terminate
Terminate API: status=success
[prefactor_core.termination_monitor] Termination signalled via span response. Reason: <reason>
Run #1 terminated: Agent instance terminated by p2: <reason>
Service continues — next run in 30s.
```

- [ ] **Step 5: Verify spans via CLI**

```bash
# List agent instances for the agent
pfctr instances list --agent <agent-id>

# Inspect spans for the terminated instance
pfctr spans list --instance <instance-id-from-run>
```

Verify: spans exist for LLM/tool calls during the run before termination.

- [ ] **Step 6: Verify run #2 starts fresh (new instance)**

Let the demo run a second cycle. Confirm in the logs that a different instance ID is created for run #2, and the previous run's termination event did not bleed into the new run.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "test(e2e): verify agent termination against local p2 (manual)"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| `PrefactorTerminatedError` with `reason` | Task 1 |
| `AgentInstance.terminated_reason` field | Task 2 |
| `AgentInstanceClient.get()` for fallback poll | Task 2 |
| `control_signal_callback` on span create/finish | Task 3 |
| `TerminationMonitor` full state machine | Task 4 |
| 19 unit tests | Task 4 |
| Monitor in `PrefactorCoreClient`, sync task | Task 5 |
| 409 swallow on FINISH_AGENT_INSTANCE | Task 5 |
| Control signal callback wired in `_process_operation` | Task 5 |
| `create_agent_instance` sets `_current_instance_id` | Task 5 |
| `AgentInstanceHandle.finish()` calls `monitor.reset()` | Task 6 |
| `_throw_if_terminated()` at all middleware hook entries | Task 7 |
| Getter pattern (`_get_termination_event`) | Task 7 |
| Demo script | Task 8 |
| E2E test with CLI span inspection | Task 9 |
| Instance-only constructor path: `_get_termination_event = None` | Task 7 |
| `termination_reason` public property on monitor | Task 4 |
| `_clear_current_instance` on client | Task 5 |
