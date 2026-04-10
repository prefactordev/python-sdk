"""Tests for the LiveKit session wrapper."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import prefactor_livekit
import pytest
from prefactor_core import PrefactorTelemetryFailureError
from prefactor_livekit import LiveKitToolSchemaConfig, PrefactorLiveKitSession
from prefactor_livekit._version import PACKAGE_VERSION


class RecordingSpanContext:
    """Async context manager that records span payloads."""

    def __init__(self, call: dict[str, object], span_id: str) -> None:
        self._call = call
        self._id = span_id
        self._result_payload: dict[str, object] = {}
        self._call["span_id"] = span_id

    async def __aenter__(self) -> "RecordingSpanContext":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    @property
    def id(self) -> str:
        return self._id

    async def start(self, payload: dict[str, object]) -> None:
        self._call["start_payload"] = payload

    def set_result(self, payload: dict[str, object]) -> None:
        self._result_payload.update(payload)
        self._call["set_result"] = dict(self._result_payload)

    async def complete(self, result_payload: dict[str, object]) -> None:
        merged = {**self._result_payload, **result_payload}
        self._call["status"] = "completed"
        self._call["result_payload"] = merged

    async def fail(self, result_payload: dict[str, object]) -> None:
        merged = {**self._result_payload, **result_payload}
        self._call["status"] = "failed"
        self._call["result_payload"] = merged

    async def cancel(self) -> None:
        self._call["status"] = "cancelled"
        self._call["result_payload"] = dict(self._result_payload)


class RecordingInstance:
    """Minimal AgentInstanceHandle stand-in for wrapper tests."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.finished = False
        self.finish_calls = 0

    def span(self, schema_name: str, parent_span_id=None, payload=None):
        call = {
            "schema_name": schema_name,
            "parent_span_id": parent_span_id,
            "payload": payload,
        }
        self.calls.append(call)
        return RecordingSpanContext(call, span_id=f"span-{len(self.calls)}")

    async def finish(self) -> None:
        self.finish_calls += 1
        self.finished = True


class FailingRecordingInstance(RecordingInstance):
    """Instance stand-in that raises on finish."""

    async def finish(self) -> None:
        raise PrefactorTelemetryFailureError(
            "telemetry failed",
            cause=RuntimeError("boom"),
            operation_type="FINISH_AGENT_INSTANCE",
        )


class FailingStartRecordingSpanContext(RecordingSpanContext):
    """Span context that raises when started."""

    async def start(self, payload: dict[str, object]) -> None:
        await super().start(payload)
        raise PrefactorTelemetryFailureError(
            "telemetry failed",
            cause=RuntimeError("boom"),
            operation_type="CREATE_SPAN",
        )


class FailingSpanRecordingInstance(RecordingInstance):
    """Instance stand-in that fails when creating spans of a given schema."""

    def __init__(self, failing_schema: str) -> None:
        super().__init__()
        self._failing_schema = failing_schema

    def span(self, schema_name: str, parent_span_id=None, payload=None):
        call = {
            "schema_name": schema_name,
            "parent_span_id": parent_span_id,
            "payload": payload,
        }
        self.calls.append(call)
        if schema_name == self._failing_schema:
            return FailingStartRecordingSpanContext(
                call, span_id=f"span-{len(self.calls)}"
            )
        return RecordingSpanContext(call, span_id=f"span-{len(self.calls)}")


class RecordingClient:
    """Minimal PrefactorCoreClient stand-in for wrapper lifecycle tests."""

    def __init__(self) -> None:
        self._initialized = True
        self._config = SimpleNamespace(schema_registry=None)
        self.close = AsyncMock()


class FakeSession:
    """Simple event emitter used by tests."""

    def __init__(self) -> None:
        self.handlers: dict[str, list] = {}
        self.start = AsyncMock(return_value="started")

    def on(self, event: str, callback) -> None:
        self.handlers.setdefault(event, []).append(callback)

    def off(self, event: str, callback) -> None:
        callbacks = self.handlers.get(event, [])
        if callback in callbacks:
            callbacks.remove(callback)

    def emit(self, event: str, payload) -> None:
        for callback in list(self.handlers.get(event, [])):
            callback(payload)


def build_owned_wrapper() -> tuple[
    PrefactorLiveKitSession,
    RecordingInstance,
    RecordingClient,
]:
    """Create a wrapper that owns a fake instance/client for shutdown tests."""

    wrapper = PrefactorLiveKitSession.from_config(
        api_url="http://test",
        api_token="test-token",
        agent_id="owned-agent",
    )
    instance = RecordingInstance()
    client = RecordingClient()
    wrapper._instance = instance
    wrapper._client = client
    wrapper._owns_instance = True
    wrapper._owns_client = True
    return wrapper, instance, client


@pytest.mark.asyncio
class TestPrefactorLiveKitSession:
    """Tests for PrefactorLiveKitSession."""

    async def test_factory_pattern_basic(self) -> None:
        wrapper = PrefactorLiveKitSession.from_config(
            api_url="http://test",
            api_token="test-token",
            agent_id="test-agent",
        )

        assert wrapper._client is not None
        assert wrapper._agent_id == "test-agent"
        assert wrapper._owns_client is True
        assert wrapper._owns_instance is True

    async def test_factory_pattern_with_tool_schemas(self) -> None:
        wrapper = PrefactorLiveKitSession.from_config(
            api_url="http://test",
            api_token="test-token",
            tool_schemas={
                "send_email": LiveKitToolSchemaConfig(
                    span_type="send-email",
                    input_schema={"type": "object"},
                )
            },
        )

        assert wrapper._tool_span_types == {"send_email": "livekit:tool:send-email"}

    async def test_configuration_mode(self) -> None:
        client = Mock()
        client._initialized = True

        wrapper = PrefactorLiveKitSession(
            client=client,
            agent_id="cfg-agent",
            agent_name="Config Agent",
        )

        assert wrapper._client is client
        assert wrapper._agent_id == "cfg-agent"
        assert wrapper._agent_name == "Config Agent"

    async def test_pre_configured_instance(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)

        assert wrapper._instance is instance
        assert wrapper._client is None
        assert wrapper._owns_instance is False

    async def test_attach_opens_root_session_span(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()

        await wrapper.attach(session)

        assert instance.calls[0]["schema_name"] == "livekit:session"
        assert session.handlers["close"]

    async def test_start_delegates_to_livekit_session(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        agent = Mock()

        result = await wrapper.start(session=session, agent=agent, capture_run=True)

        assert result == "started"
        session.start.assert_awaited_once()

    async def test_close_surfaces_telemetry_failure_from_instance_finish(self) -> None:
        instance = FailingRecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        wrapper._owns_instance = True

        with pytest.raises(PrefactorTelemetryFailureError):
            await wrapper.close()

    async def test_drain_pending_tasks_completes_after_queued_telemetry_failure(
        self,
    ) -> None:
        instance = FailingSpanRecordingInstance("livekit:user_turn")
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        event = SimpleNamespace(
            transcript="hello world",
            is_final=True,
            speaker_id="user-1",
            language="en",
            created_at=123.0,
        )
        session.emit("user_input_transcribed", event)
        session.emit("user_input_transcribed", event)

        await asyncio.wait_for(wrapper._drain_pending_tasks(), timeout=0.2)

        assert wrapper._event_queue is not None
        assert wrapper._event_queue.qsize() == 0
        assert wrapper._event_worker_task is not None
        assert not wrapper._event_worker_task.done()

    async def test_close_raises_latched_telemetry_failure_after_draining(self) -> None:
        instance = FailingSpanRecordingInstance("livekit:user_turn")
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        event = SimpleNamespace(
            transcript="hello world",
            is_final=True,
            speaker_id="user-1",
            language="en",
            created_at=123.0,
        )
        session.emit("user_input_transcribed", event)
        session.emit("user_input_transcribed", event)

        with pytest.raises(PrefactorTelemetryFailureError):
            await asyncio.wait_for(wrapper.close(), timeout=0.2)

        assert wrapper._event_queue is None
        assert wrapper._event_worker_task is None

    async def test_final_transcript_creates_user_turn_span(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "user_input_transcribed",
            SimpleNamespace(
                transcript="hello world",
                is_final=True,
                speaker_id="user-1",
                language="en",
                created_at=123.0,
            ),
        )
        await wrapper._drain_pending_tasks()

        assert instance.calls[-1]["schema_name"] == "livekit:user_turn"
        assert instance.calls[-1]["result_payload"]["transcript"] == "hello world"
        assert instance.calls[-1]["result_payload"]["language"] == "en"

    async def test_tool_execution_emits_one_span_per_function_call(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(
            instance=instance,
            tool_schemas={
                "calculate": LiveKitToolSchemaConfig(
                    span_type="calculate",
                    input_schema={"type": "object"},
                )
            },
        )
        session = FakeSession()
        await wrapper.attach(session)
        session.emit(
            "speech_created",
            SimpleNamespace(
                source="generate_reply",
                user_initiated=True,
                created_at=1.0,
            ),
        )
        await wrapper._drain_pending_tasks()
        assistant_turn_call = instance.calls[-1]

        event = SimpleNamespace(
            zipped=lambda: [
                (
                    SimpleNamespace(
                        name="calculate",
                        call_id="call-1",
                        group_id="group-1",
                        arguments='{"x": 1}',
                        created_at=1.0,
                        extra={"provider": "test"},
                    ),
                    SimpleNamespace(
                        name="calculate",
                        output='{"value": 2}',
                        is_error=False,
                    ),
                )
            ]
        )

        session.emit("function_tools_executed", event)
        await wrapper._drain_pending_tasks()

        assert instance.calls[-1]["schema_name"] == "livekit:tool:calculate"
        assert instance.calls[-1]["start_payload"]["inputs"] == {"x": 1}
        assert instance.calls[-1]["parent_span_id"] == assistant_turn_call["span_id"]

    async def test_metrics_emit_expected_span_types(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)
        session.emit(
            "speech_created",
            SimpleNamespace(
                source="generate_reply",
                user_initiated=True,
                created_at=40.0,
            ),
        )
        await wrapper._drain_pending_tasks()
        assistant_turn_call = instance.calls[-1]

        metrics = SimpleNamespace(
            type="llm_metrics",
            label="openai",
            request_id="req-1",
            timestamp=42.0,
            metadata=SimpleNamespace(
                model_name="gpt-4.1-mini",
                model_provider="openai",
            ),
            model_dump=lambda: {
                "type": "llm_metrics",
                "label": "openai",
                "request_id": "req-1",
                "timestamp": 42.0,
                "metadata": {
                    "model_name": "gpt-4.1-mini",
                    "model_provider": "openai",
                },
            },
        )

        session.emit("metrics_collected", SimpleNamespace(metrics=metrics))
        await wrapper._drain_pending_tasks()

        assert instance.calls[-1]["schema_name"] == "livekit:llm"
        assert instance.calls[-1]["start_payload"]["provider"] == "openai"
        assert instance.calls[-1]["parent_span_id"] == assistant_turn_call["span_id"]

    async def test_state_changes_do_not_emit_state_spans(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "agent_state_changed",
            SimpleNamespace(old_state="idle", new_state="thinking", created_at=10.0),
        )
        await wrapper._drain_pending_tasks()

        assert [call["schema_name"] for call in instance.calls] == ["livekit:session"]

    async def test_speech_created_then_assistant_message_closes_assistant_turn(
        self,
    ) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "speech_created",
            SimpleNamespace(
                source="generate_reply", user_initiated=True, created_at=1.0
            ),
        )
        await wrapper._drain_pending_tasks()

        assert wrapper._active_assistant_turn is not None

        session.emit(
            "conversation_item_added",
            SimpleNamespace(
                item=SimpleNamespace(
                    type="message",
                    role="assistant",
                    content="hello there",
                )
            ),
        )
        await wrapper._drain_pending_tasks()
        assert wrapper._active_assistant_turn is not None

        session.emit(
            "agent_state_changed",
            SimpleNamespace(
                old_state="speaking",
                new_state="listening",
                created_at=2.0,
            ),
        )
        await wrapper._drain_pending_tasks()

        assert wrapper._active_assistant_turn is None
        assert instance.calls[-1]["schema_name"] == "livekit:assistant_turn"
        assert (
            instance.calls[-1]["result_payload"]["outputs"]["message"]["role"]
            == "assistant"
        )
        assert instance.calls[-1]["result_payload"]["finished_at"] == 2.0

    async def test_text_only_assistant_turn_finishes_on_message(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        metrics = SimpleNamespace(
            type="llm_metrics",
            label="openai",
            request_id="req-1",
            timestamp=42.0,
            metadata=SimpleNamespace(
                model_name="gpt-4.1-mini",
                model_provider="openai",
            ),
            model_dump=lambda: {
                "type": "llm_metrics",
                "label": "openai",
                "request_id": "req-1",
                "timestamp": 42.0,
                "metadata": {
                    "model_name": "gpt-4.1-mini",
                    "model_provider": "openai",
                },
            },
        )
        session.emit("metrics_collected", SimpleNamespace(metrics=metrics))
        await wrapper._drain_pending_tasks()

        session.emit(
            "conversation_item_added",
            SimpleNamespace(
                item=SimpleNamespace(
                    type="message",
                    role="assistant",
                    content="hello there",
                    created_at=43.0,
                ),
                created_at=43.0,
            ),
        )
        await wrapper._drain_pending_tasks()

        assistant_turn_call = next(
            call
            for call in reversed(instance.calls)
            if call["schema_name"] == "livekit:assistant_turn"
        )
        assert assistant_turn_call["schema_name"] == "livekit:assistant_turn"
        assert (
            assistant_turn_call["result_payload"]["outputs"]["message"]["role"]
            == "assistant"
        )
        assert assistant_turn_call["result_payload"]["status"] == "completed"

    async def test_user_turn_captures_story_metrics_without_standalone_stt_span(
        self,
    ) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "user_state_changed",
            SimpleNamespace(
                old_state="listening",
                new_state="speaking",
                created_at=10.0,
            ),
        )
        await wrapper._drain_pending_tasks()

        stt_metrics = SimpleNamespace(
            type="stt_metrics",
            label="stt",
            request_id="stt-1",
            timestamp=11.0,
            metadata=SimpleNamespace(
                model_name="nova",
                model_provider="deepgram",
            ),
            model_dump=lambda: {
                "type": "stt_metrics",
                "label": "stt",
                "request_id": "stt-1",
                "timestamp": 11.0,
                "audio_duration": 2.5,
                "metadata": {
                    "model_name": "nova",
                    "model_provider": "deepgram",
                },
            },
        )
        session.emit("metrics_collected", SimpleNamespace(metrics=stt_metrics))
        await wrapper._drain_pending_tasks()

        session.emit(
            "user_input_transcribed",
            SimpleNamespace(
                transcript="hello world",
                is_final=True,
                speaker_id="user-1",
                language="en",
                created_at=12.0,
            ),
        )
        await wrapper._drain_pending_tasks()

        assert instance.calls[-1]["schema_name"] == "livekit:user_turn"
        assert "stt" in instance.calls[-1]["result_payload"]["metrics"]
        assert "livekit:stt" not in {call["schema_name"] for call in instance.calls}

    async def test_interruption_finishes_active_assistant_turn(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "speech_created",
            SimpleNamespace(
                source="generate_reply",
                user_initiated=True,
                created_at=1.0,
            ),
        )
        session.emit(
            "conversation_item_added",
            SimpleNamespace(
                item=SimpleNamespace(
                    type="message",
                    role="assistant",
                    content="hello there",
                    created_at=1.2,
                ),
                created_at=1.2,
            ),
        )
        await wrapper._drain_pending_tasks()

        interruption_metrics = SimpleNamespace(
            type="interruption_metrics",
            model_dump=lambda: {
                "type": "interruption_metrics",
                "timestamp": 2.0,
                "duration": 0.1,
                "metadata": {},
            },
        )
        session.emit("metrics_collected", SimpleNamespace(metrics=interruption_metrics))
        await wrapper._drain_pending_tasks()

        assert wrapper._active_assistant_turn is None
        assert instance.calls[-1]["schema_name"] == "livekit:assistant_turn"
        assert instance.calls[-1]["result_payload"]["interrupted"] is True

    async def test_error_and_close_fail_session(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "error",
            SimpleNamespace(
                error=RuntimeError("boom"),
                source=SimpleNamespace(),
                created_at=2.0,
            ),
        )
        await wrapper._drain_pending_tasks()
        assert any(call["schema_name"] == "livekit:error" for call in instance.calls)

        session.emit(
            "close",
            SimpleNamespace(
                reason=SimpleNamespace(value="error"), error=RuntimeError("boom")
            ),
        )
        await wrapper._drain_pending_tasks()

        assert instance.calls[0]["status"] == "failed"
        assert (
            instance.calls[0]["result_payload"]["metadata"]["close_reason"] == "error"
        )

    async def test_close_event_finalizes_owned_instance_and_client(self) -> None:
        wrapper, instance, client = build_owned_wrapper()
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "close",
            SimpleNamespace(reason=SimpleNamespace(value="user_initiated"), error=None),
        )
        await asyncio.wait_for(wrapper._drain_pending_tasks(), timeout=1.0)

        assert instance.calls[0]["status"] == "completed"
        assert instance.finish_calls == 1
        client.close.assert_awaited_once()
        assert wrapper._instance is None
        assert wrapper._client is None
        assert wrapper._event_queue is None
        assert wrapper._event_worker_task is None

    async def test_close_after_internal_close_is_idempotent(self) -> None:
        wrapper, instance, client = build_owned_wrapper()
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "close",
            SimpleNamespace(reason=SimpleNamespace(value="user_initiated"), error=None),
        )
        await asyncio.wait_for(wrapper._drain_pending_tasks(), timeout=1.0)

        await wrapper.close()

        assert instance.finish_calls == 1
        client.close.assert_awaited_once()

    async def test_error_close_finalizes_owned_resources(self) -> None:
        wrapper, instance, client = build_owned_wrapper()
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "error",
            SimpleNamespace(
                error=RuntimeError("boom"),
                source=SimpleNamespace(),
                created_at=2.0,
            ),
        )
        session.emit(
            "close",
            SimpleNamespace(
                reason=SimpleNamespace(value="error"),
                error=RuntimeError("boom"),
            ),
        )
        await asyncio.wait_for(wrapper._drain_pending_tasks(), timeout=1.0)

        assert instance.calls[0]["status"] == "failed"
        assert instance.finish_calls == 1
        client.close.assert_awaited_once()

    async def test_user_initiated_close_completes_session(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "close",
            SimpleNamespace(reason=SimpleNamespace(value="user_initiated"), error=None),
        )
        await wrapper._drain_pending_tasks()

        assert instance.calls[0]["status"] == "completed"
        assert (
            instance.calls[0]["result_payload"]["metadata"]["close_reason"]
            == "user_initiated"
        )
        turns = instance.calls[0]["result_payload"]["conversation"]["turns"]
        assert turns == []

    async def test_job_shutdown_close_completes_session(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "close",
            SimpleNamespace(reason=SimpleNamespace(value="job_shutdown"), error=None),
        )
        await wrapper._drain_pending_tasks()

        assert instance.calls[0]["status"] == "completed"
        assert (
            instance.calls[0]["result_payload"]["metadata"]["close_reason"]
            == "job_shutdown"
        )

    async def test_post_close_events_are_ignored_and_do_not_restart_worker(
        self,
    ) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "close",
            SimpleNamespace(reason=SimpleNamespace(value="user_initiated"), error=None),
        )
        await asyncio.wait_for(wrapper._drain_pending_tasks(), timeout=1.0)
        call_count = len(instance.calls)

        session.emit(
            "agent_state_changed",
            SimpleNamespace(old_state="idle", new_state="thinking", created_at=10.0),
        )
        await asyncio.sleep(0)

        assert len(instance.calls) == call_count
        assert wrapper._event_queue is None
        assert wrapper._event_worker_task is None

    async def test_preconfigured_instance_does_not_finish_external_resources(
        self,
    ) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "close",
            SimpleNamespace(reason=SimpleNamespace(value="user_initiated"), error=None),
        )
        await asyncio.wait_for(wrapper._drain_pending_tasks(), timeout=1.0)

        assert instance.finish_calls == 0
        assert wrapper._instance is instance

    async def test_session_usage_updates_root_span_result(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        usage = SimpleNamespace(
            model_usage=[
                SimpleNamespace(
                    model_dump=lambda: {
                        "type": "llm_usage",
                        "provider": "openai",
                        "model": "gpt-4.1-mini",
                        "input_tokens": 10,
                        "output_tokens": 5,
                    }
                )
            ]
        )
        session.emit("session_usage_updated", SimpleNamespace(usage=usage))

        assert (
            instance.calls[0]["set_result"]["usage"]["model_usage"][0]["model"]
            == "gpt-4.1-mini"
        )

    async def test_session_result_includes_ordered_turn_story(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "user_state_changed",
            SimpleNamespace(
                old_state="listening",
                new_state="speaking",
                created_at=1.0,
            ),
        )
        session.emit(
            "user_input_transcribed",
            SimpleNamespace(
                transcript="hello",
                is_final=True,
                speaker_id="user-1",
                language="en",
                created_at=2.0,
            ),
        )
        session.emit(
            "speech_created",
            SimpleNamespace(
                source="generate_reply",
                user_initiated=True,
                created_at=3.0,
            ),
        )
        session.emit(
            "conversation_item_added",
            SimpleNamespace(
                item=SimpleNamespace(
                    type="message",
                    role="assistant",
                    content="hi there",
                    created_at=4.0,
                ),
                created_at=4.0,
            ),
        )
        session.emit(
            "agent_state_changed",
            SimpleNamespace(
                old_state="speaking",
                new_state="listening",
                created_at=5.0,
            ),
        )
        session.emit(
            "close",
            SimpleNamespace(reason=SimpleNamespace(value="user_initiated"), error=None),
        )
        await wrapper._drain_pending_tasks()

        turns = instance.calls[0]["result_payload"]["conversation"]["turns"]
        assert [turn["role"] for turn in turns] == ["user", "assistant"]
        assert [turn["turn_index"] for turn in turns] == [1, 2]


class TestVersionHelpers:
    """Tests for package version exports."""

    def test_package_version_matches_public_export(self) -> None:
        """Test that the package version export matches the internal constant."""
        assert prefactor_livekit.__version__ == PACKAGE_VERSION
