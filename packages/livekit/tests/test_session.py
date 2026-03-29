"""Tests for the LiveKit session wrapper."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import prefactor_livekit
import pytest
from prefactor_livekit import LiveKitToolSchemaConfig, PrefactorLiveKitSession
from prefactor_livekit._version import PACKAGE_VERSION


class RecordingSpanContext:
    """Async context manager that records span payloads."""

    def __init__(self, call: dict[str, object], span_id: str) -> None:
        self._call = call
        self._id = span_id
        self._result_payload: dict[str, object] = {}

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

    def span(self, schema_name: str, parent_span_id=None, payload=None):
        call = {
            "schema_name": schema_name,
            "parent_span_id": parent_span_id,
            "payload": payload,
        }
        self.calls.append(call)
        return RecordingSpanContext(call, span_id=f"span-{len(self.calls)}")

    async def finish(self) -> None:
        self.finished = True


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
        assert instance.calls[-1]["start_payload"]["transcript"] == "hello world"

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

    async def test_metrics_emit_expected_span_types(self) -> None:
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

        assert instance.calls[-1]["schema_name"] == "livekit:llm"
        assert instance.calls[-1]["start_payload"]["provider"] == "openai"

    async def test_state_changes_emit_state_spans(self) -> None:
        instance = RecordingInstance()
        wrapper = PrefactorLiveKitSession(instance=instance)
        session = FakeSession()
        await wrapper.attach(session)

        session.emit(
            "agent_state_changed",
            SimpleNamespace(old_state="idle", new_state="thinking", created_at=10.0),
        )
        await wrapper._drain_pending_tasks()

        assert instance.calls[-1]["schema_name"] == "livekit:state"
        assert instance.calls[-1]["start_payload"]["actor"] == "agent"

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
        assert wrapper._pending_assistant_turn is not None

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

        assert wrapper._pending_assistant_turn is None
        assert instance.calls[-1]["schema_name"] == "livekit:assistant_turn"
        assert (
            instance.calls[-1]["result_payload"]["outputs"]["message"]["role"]
            == "assistant"
        )

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


class TestVersionHelpers:
    """Tests for package version exports."""

    def test_package_version_matches_public_export(self) -> None:
        """Test that the package version export matches the internal constant."""
        assert prefactor_livekit.__version__ == PACKAGE_VERSION
