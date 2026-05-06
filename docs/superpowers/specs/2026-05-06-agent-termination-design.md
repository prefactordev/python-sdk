# Agent Termination — Python SDK Design

**Date:** 2026-05-06  
**Branch:** pre-301-implement-agent-termination-in-python-sdk  
**Reference:** PRE-301 / PRE-285 / TypeScript implementation on pre-300

---

## Overview

When p2 terminates an agent instance, the SDK detects it and raises `PrefactorTerminatedError` so user service loops can catch it and restart. Detection is automatic — no new user-facing API calls required. Two paths: fast primary via span API responses, slow fallback via 30s poll.

All wiring lives inside the SDK (core + langchain packages). Users see only the exception.

---

## P2 Contract

Control signal appears in span_create and span_finish responses only (span_start/span_finish follow-up tracked separately):

```json
{ "status": "success", "details": { ... }, "control": { "terminate": true, "reason": "string or null" } }
```

Key absent when instance is not terminated.

GET `/api/v1/agent_instance/{id}` — fallback poll. Returns `AgentInstance` with `status: "terminated"` and an optional `terminated_reason: str | None` field. Add this field to the `AgentInstance` Pydantic model (currently absent).

409 on `agent_instance/finish` when p2 already terminated the instance — treated as success.

---

## Architecture

### Data Flow

```
p2 span response
  → AgentSpanClient.create/finish(control_signal_callback=...)
      → _check_control_signal(raw_response, callback)
          → monitor.detect_termination(reason)
              → asyncio.Event.set()
              → fire registered callbacks

asyncio.Task (1s interval in PrefactorCoreClient)
  → monitor.sync(current_instance_id)
      → if fenced + new id: lift fence
      → if id changed: start/stop fallback asyncio.Task (30s poll)
          → GET /api/v1/agent_instance/{id}
          → if terminated: detect_termination(reason)

middleware async hook entry (abefore_agent, awrap_model_call, awrap_tool_call)
  → _throw_if_terminated(get_event)
      → event = get_event()   # getter callable, not captured value
      → if event.is_set(): raise PrefactorTerminatedError(reason)

sync hook entry (before_agent, wrap_model_call, wrap_tool_call)
  → same _throw_if_terminated — asyncio.Event.is_set() is safe from threads

AgentInstanceHandle.finish()
  → client._termination_monitor.reset()   # fence first, new event, stop poll
  → enqueue FINISH_AGENT_INSTANCE         # 409 = success
```

---

## Components

### `PrefactorTerminatedError` (core/exceptions.py)

```python
class PrefactorTerminatedError(PrefactorCoreError):
    def __init__(self, reason: str | None = None) -> None:
        msg = f"Agent instance terminated by p2: {reason}" if reason else "Agent instance terminated by p2"
        super().__init__(msg)
        self.reason = reason
```

Exported from `prefactor_core.__init__`.

---

### `TerminationMonitor` (core/src/prefactor_core/monitoring/termination_monitor.py)

#### State

| Field | Type | Description |
|-------|------|-------------|
| `_event` | `asyncio.Event` | Set when terminated. Replaced on reset(). |
| `_generation` | `int` | Stale-poll guard. Incremented on reset(). |
| `_fenced` | `bool` | Blocks detect_termination() between runs. |
| `_poll_task` | `asyncio.Task \| None` | Fallback poll coroutine. |
| `_tracking_instance_id` | `str \| None` | Instance ID currently being watched. |
| `_terminated` | `bool` | Latched on first detection. |
| `_destroyed` | `bool` | Set in destroy(); no further transitions. |
| `_reason` | `str \| None` | Termination reason string from p2. |
| `_callbacks` | `list[Callable]` | Registered termination listeners. |

Constructor takes `fetch_instance: Callable[[str], Awaitable[AgentInstance]]` for fallback poll.

#### Methods

**`detect_termination(reason: str | None) -> None`**  
Guard: `terminated or destroyed or fenced → return`.  
Sets event, latches terminated+reason, stops poll, fires callbacks.

**`sync(instance_id: str | None) -> None`**  
Guard: `destroyed or terminated → return`.  
If fenced and `instance_id is not None` → `fenced = False`.  
If id changed: start or stop fallback poll task.

**`reset() -> None`**  
`generation++`, `fenced = True`, cancel poll task.  
`_event = asyncio.Event()` — new event; old captures become stale (correct).  
`_terminated = False`, `_reason = None`, `_tracking_instance_id = None`.

**`get_termination_event() -> asyncio.Event`**  
Returns `self._event`. Callable getter pattern — middleware calls this each check, never captures the event at init time.

**`destroy() -> None`**  
`destroyed = True`, cancel poll task, clear callbacks.

**`subscribe(callback: Callable[[], None]) -> Callable[[], None]`**  
Returns unsubscribe callable.

#### Fallback poll internal coroutine

```python
async def _poll(self, instance_id: str, poll_generation: int) -> None:
    while True:
        await asyncio.sleep(30)
        if self._generation != poll_generation:
            return  # stale guard
        instance = await self._fetch_instance(instance_id)
        if self._generation != poll_generation:
            return  # post-await stale guard
        if instance.status == "terminated":
            self.detect_termination(getattr(instance, "terminated_reason", None))
```

Started via `asyncio.create_task`. Cancelled on `sync(None)` / `reset()` / `destroy()`.

---

### Control Signal — AgentSpanClient

`create()` and `finish()` accept `control_signal_callback: Callable[[str | None], None] | None = None`.

After successful response:
```python
def _check_control_signal(response: dict, callback) -> None:
    control = response.get("control")
    if control and control.get("terminate"):
        callback(control.get("reason"))
```

Called before `_parse_response`. Callback is `monitor.detect_termination`.

---

### AgentInstance GET — AgentInstanceClient

New method for fallback poll:

```python
async def get(self, agent_instance_id: str) -> AgentInstance:
    """GET /api/v1/agent_instance/{agent_instance_id}"""
    response = await self._client.request("GET", f"/api/v1/agent_instance/{agent_instance_id}")
    return self._parse_response(response, "agent_instances.get")
```

---

### PrefactorCoreClient changes

**`_current_instance_id: str | None`** — tracks active instance. Set in `create_agent_instance()`, cleared via `_clear_current_instance(instance_id)` called from `AgentInstanceHandle.finish()`.

**`_termination_monitor: TerminationMonitor | None`** — created in `initialize()`.

**`_sync_task: asyncio.Task | None`** — background 1s loop created in `initialize()`, cancelled in `close()`.

```python
async def _run_sync_loop(self) -> None:
    while True:
        await asyncio.sleep(1)
        if self._termination_monitor:
            self._termination_monitor.sync(self._current_instance_id)
```

**409 swallow** in `_process_operation` for `FINISH_AGENT_INSTANCE`:
```python
try:
    await self._http.agent_instances.finish(...)
except PrefactorApiError as e:
    if e.status_code == 409:
        logger.debug("[prefactor:http] Agent instance already in terminal state; skipping finish.")
        return
    raise
```

**`_control_signal_callback`** — closure passed to span operations:
```python
def _on_control_signal(self, reason: str | None) -> None:
    if self._termination_monitor:
        self._termination_monitor.detect_termination(reason)
```

---

### AgentInstanceHandle.finish()

Reset fires before enqueue so fence goes up immediately, preventing stale span responses from the dying run from killing the next one:

```python
async def finish(self, status="complete"):
    # Fence immediately — before async queue drains
    if self._client._termination_monitor:
        self._client._termination_monitor.reset()
    self._client._clear_current_instance(self._instance_id)
    manager = self._client.instance_manager
    await manager.finish_with_idempotency_key(
        self._instance_id, self._finish_idempotency_key, status=status
    )
```

---

### PrefactorMiddleware changes

**`_get_termination_event: Callable[[], asyncio.Event] | None`** — set in `_ensure_initialized()` to `client._termination_monitor.get_termination_event` if monitor exists.

**`_throw_if_terminated()`**:
```python
def _throw_if_terminated(self) -> None:
    if self._get_termination_event is None:
        return
    event = self._get_termination_event()
    if event.is_set():
        monitor = self._client._termination_monitor if self._client else None
        reason = monitor.termination_reason if monitor else None  # public property
        raise PrefactorTerminatedError(reason)
```

`TerminationMonitor` exposes `termination_reason: str | None` as a public property.

**Instance-only constructor path** (`instance=` kwarg, no `client`): `_get_termination_event` is set to `None` — termination detection not available without a client-owned monitor. Acceptable; instance-only mode is for shared instance scenarios where the caller manages lifecycle.

Called at entry of: `abefore_agent`, `awrap_model_call`, `awrap_tool_call`, `before_agent`, `wrap_model_call`, `wrap_tool_call`.

`asyncio.Event.is_set()` is safe from sync worker threads (bool attribute read, CPython GIL).

---

## Key Design Decisions

### Getter not captured value

Middleware stores `_get_termination_event: Callable` not the event itself. After `reset()`, the monitor replaces `_event`. A captured stale event would always return `is_set() == False` for the next run — correct but only by accident. The getter ensures the check always hits the live event.

### Fence blocks between runs

`detect_termination()` is a no-op when `fenced=True`. Fence is set in `reset()` (inside `instance.finish()`) and lifted in `sync()` only when a new non-None instance ID is seen. This prevents stale span responses queued from the dying run from killing the next run's signal.

### Stale poll guard

Poll coroutine captures `poll_generation = self._generation` at start. Before and after every await, checks `self._generation != poll_generation → return`. Prevents a reset()-then-new-run scenario where an in-flight poll response for the old instance triggers termination on the new run.

### 409 = success on finish

When p2 terminates externally, calling `agent_instance/finish` returns 409 (already in terminal state). Treated as success — instance ID cleared, no error raised.

---

## File Map

### New files
- `packages/core/src/prefactor_core/monitoring/__init__.py`
- `packages/core/src/prefactor_core/monitoring/termination_monitor.py`
- `packages/core/tests/monitoring/__init__.py`
- `packages/core/tests/monitoring/test_termination_monitor.py`
- `packages/langchain/examples/termination_demo.py`

### Modified files
- `packages/core/src/prefactor_core/exceptions.py` — add `PrefactorTerminatedError`
- `packages/core/src/prefactor_core/__init__.py` — export `PrefactorTerminatedError`
- `packages/core/src/prefactor_core/client.py` — monitor, sync task, callback, instance tracking, 409 swallow
- `packages/core/src/prefactor_core/managers/agent_instance.py` — `finish()` calls monitor reset
- `packages/http/src/prefactor_http/endpoints/agent_span.py` — `control_signal_callback` param
- `packages/http/src/prefactor_http/endpoints/agent_instance.py` — `get()` method
- `packages/http/src/prefactor_http/models/agent_instance.py` — add `terminated_reason: str | None = None` to `AgentInstance`
- `packages/langchain/src/prefactor_langchain/middleware.py` — `_throw_if_terminated()` + getter wiring

---

## Tests (19)

File: `packages/core/tests/monitoring/test_termination_monitor.py`

### Primary path (5)
1. Signal fires immediately on detect_termination
2. Reason propagates to event and callbacks
3. Null reason accepted
4. Second detect_termination call is idempotent
5. detect_termination is no-op after destroy

### Fallback poll (5)
6. Poll starts when instance ID provided to sync()
7. Poll stops when sync() called with None
8. No poll started when detect_termination fires first
9. Poll stops after termination detected
10. Transient HTTP errors in poll don't crash — loop continues

### reset() (7)
11. reset() creates fresh (unset) event
12. reset() clears terminated state; new termination works after sync with new id
13. get_termination_event() returns new event after reset (getter pattern)
14. reset() cancels poll task
15. reset() preserves registered callbacks
16. Fence blocks detect_termination until sync() with non-None id
17. Stale poll response after reset discarded (generation check)

### Callback lifecycle (2)
18. Unsubscribe removes callback from future firings
19. Multiple callbacks fire in registration order

---

## Demo

`packages/langchain/examples/termination_demo.py`

Env vars: `PREFACTOR_API_URL`, `PREFACTOR_AGENT_ID`, `PREFACTOR_API_TOKEN`, `PREFACTOR_AUTO_TERMINATE_DELAY` (default 6s), `PREFACTOR_RESTART_DELAY` (default 75s).

Service loop: create middleware → run agent → catch `PrefactorTerminatedError` → log + wait → repeat. After `AUTO_TERMINATE_DELAY`, demo calls `POST /api/v1/agent_instance/{id}/terminate` in background to trigger the detection path.
