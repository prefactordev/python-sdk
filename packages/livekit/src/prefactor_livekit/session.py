"""LiveKit session wrapper for Prefactor observability."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from prefactor_core import (
    AgentInstanceHandle,
    PrefactorCoreClient,
    PrefactorCoreConfig,
    SchemaRegistry,
    SpanContext,
)
from prefactor_http.config import HttpClientConfig

from prefactor_livekit.schemas import LiveKitToolSchemaConfig, register_livekit_schemas

if TYPE_CHECKING:
    from livekit.agents import Agent, AgentSession

logger = logging.getLogger("prefactor_livekit.session")


@dataclass
class _OpenTurnState:
    """In-flight story span tracked across multiple LiveKit events."""

    schema_name: str
    turn_index: int
    span_cm: Any
    span_context: SpanContext
    payload: dict[str, Any]
    story: dict[str, Any]
    result: dict[str, Any] = field(default_factory=dict)
    auto_finish_on_message: bool = False
    finished: bool = False

    @property
    def span_id(self) -> str:
        return self.span_context.id


class PrefactorLiveKitSession:
    """High-level LiveKit session wrapper for Prefactor tracing."""

    def __init__(
        self,
        client: PrefactorCoreClient | None = None,
        agent_id: str = "livekit-agent",
        agent_name: str | None = None,
        instance: AgentInstanceHandle | None = None,
        tool_schemas: Mapping[str, LiveKitToolSchemaConfig | Mapping[str, Any]]
        | None = None,
    ) -> None:
        if instance is not None and client is not None:
            raise ValueError("Provide either 'client' or 'instance', not both.")

        if instance is None and client is None:
            msg = (
                "Either 'client' or 'instance' is required"
                " - use PrefactorLiveKitSession.from_config() for quick setup"
            )
            raise ValueError(msg)

        if client is not None and (
            not hasattr(client, "_initialized") or not client._initialized
        ):
            msg = (
                "Client must be initialized before being"
                " passed to session wrapper"
                " - call await client.initialize() first"
            )
            raise ValueError(msg)

        self._client = client
        self._agent_id = agent_id
        self._agent_name = agent_name
        self._instance = instance
        self._owns_client = False
        self._owns_instance = instance is None
        self._tool_span_types = (
            self._register_tool_schemas(client, tool_schemas) if tool_schemas else {}
        )

        self._loop: asyncio.AbstractEventLoop | None = None
        self._event_queue: asyncio.Queue[Any] | None = None
        self._event_worker_task: asyncio.Task[None] | None = None
        self._session: Any | None = None
        self._bound_handlers: dict[str, Any] = {}

        self._session_span_cm: Any | None = None
        self._session_span_context: SpanContext | None = None
        self._session_span_id: str | None = None

        self._active_user_turn: _OpenTurnState | None = None
        self._active_assistant_turn: _OpenTurnState | None = None
        self._conversation_turns: list[dict[str, Any]] = []
        self._turn_index = 0

        self._partial_transcripts: list[dict[str, Any]] = []
        self._conversation_summary: dict[str, Any] = {
            "items_seen": 0,
            "assistant_messages": 0,
            "user_messages": 0,
            "function_calls": 0,
        }
        self._usage_summary: dict[str, Any] = {}
        self._closed = False
        self._resources_finalized = False
        self._terminal_shutdown_requested = False
        self._event_worker_stopping = False
        self._event_worker_stopped = False

    @classmethod
    def from_config(
        cls,
        api_url: str,
        api_token: str,
        agent_id: str = "livekit-agent",
        agent_name: str | None = None,
        schema_registry: SchemaRegistry | None = None,
        include_livekit_schemas: bool = True,
        tool_schemas: Mapping[str, LiveKitToolSchemaConfig | Mapping[str, Any]]
        | None = None,
    ) -> "PrefactorLiveKitSession":
        """Create a wrapper from raw configuration."""

        http_config = HttpClientConfig(api_url=api_url, api_token=api_token)
        registry = schema_registry or SchemaRegistry()
        tool_span_types: dict[str, str] = {}
        if include_livekit_schemas or tool_schemas:
            tool_span_types = register_livekit_schemas(
                registry,
                tool_schemas=tool_schemas,
            )

        client = PrefactorCoreClient(
            PrefactorCoreConfig(http_config=http_config, schema_registry=registry)
        )
        wrapper = cls.__new__(cls)
        wrapper._client = client
        wrapper._agent_id = agent_id
        wrapper._agent_name = agent_name
        wrapper._instance = None
        wrapper._owns_client = True
        wrapper._owns_instance = True
        wrapper._tool_span_types = tool_span_types
        wrapper._loop = None
        wrapper._event_queue = None
        wrapper._event_worker_task = None
        wrapper._session = None
        wrapper._bound_handlers = {}
        wrapper._session_span_cm = None
        wrapper._session_span_context = None
        wrapper._session_span_id = None
        wrapper._active_user_turn = None
        wrapper._active_assistant_turn = None
        wrapper._conversation_turns = []
        wrapper._turn_index = 0
        wrapper._partial_transcripts = []
        wrapper._conversation_summary = {
            "items_seen": 0,
            "assistant_messages": 0,
            "user_messages": 0,
            "function_calls": 0,
        }
        wrapper._usage_summary = {}
        wrapper._closed = False
        wrapper._resources_finalized = False
        wrapper._terminal_shutdown_requested = False
        wrapper._event_worker_stopping = False
        wrapper._event_worker_stopped = False
        return wrapper

    def _register_tool_schemas(
        self,
        client: PrefactorCoreClient | None,
        tool_schemas: Mapping[str, LiveKitToolSchemaConfig | Mapping[str, Any]],
    ) -> dict[str, str]:
        if client is None:
            return register_livekit_schemas(
                SchemaRegistry(),
                tool_schemas=tool_schemas,
            )

        registry = client._config.schema_registry
        if registry is None:
            registry = SchemaRegistry()
            client._config.schema_registry = registry
        return register_livekit_schemas(registry, tool_schemas=tool_schemas)

    async def _ensure_initialized(self) -> AgentInstanceHandle:
        if self._instance is not None:
            return self._instance

        if self._client is None:
            raise ValueError("Client is not available - wrapper has been closed")

        if self._owns_client and not self._client._initialized:
            await self._client.initialize()

        self._loop = asyncio.get_running_loop()
        agent_version_name = self._agent_name or "livekit-agent"
        schema_version_id = f"livekit-{self._agent_id}"
        if self._client._config.schema_registry is not None:
            raw = self._client._config.schema_registry.to_agent_schema_version(
                schema_version_id
            )
            digest = hashlib.sha1(
                json.dumps({"name": agent_version_name, **raw}, sort_keys=True).encode()
            ).hexdigest()[:8]
            schema_version_id = f"livekit-{self._agent_id}-{digest}"

        self._instance = await self._client.create_agent_instance(
            agent_id=self._agent_id,
            agent_version={
                "name": agent_version_name,
                "external_identifier": schema_version_id,
            },
            agent_schema_version=None,
            external_schema_version_id=schema_version_id,
        )
        self._owns_instance = True
        await self._instance.start()
        return self._instance

    async def ensure_initialized(self) -> AgentInstanceHandle:
        """Initialize and return the active Prefactor instance."""

        return await self._ensure_initialized()

    async def attach(self, session: "AgentSession[Any]") -> AgentInstanceHandle:
        """Attach to an existing LiveKit session."""

        if self._session is session and self._session_span_context is not None:
            return await self._ensure_initialized()

        if self._session is not None and self._session is not session:
            await self._detach_session(final_status="completed")

        instance = await self._ensure_initialized()
        self._loop = asyncio.get_running_loop()
        self._session = session
        self._closed = False

        self._bind_session_events(session)
        await self._open_session_span(session=session, agent=None)
        return instance

    async def start(
        self,
        session: "AgentSession[Any]",
        agent: "Agent",
        **kwargs: Any,
    ) -> Any:
        """Attach and delegate to ``AgentSession.start()``."""

        await self.attach(session)
        await self._open_session_span(session=session, agent=agent)
        return await session.start(agent, **kwargs)

    async def close(self) -> None:
        """Flush pending tasks and release wrapper-owned resources."""

        self._terminal_shutdown_requested = True
        await self._drain_pending_tasks()
        await self._finalize_terminal_shutdown(final_status="completed")

    def _bind_session_events(self, session: Any) -> None:
        self._bound_handlers = {
            "user_input_transcribed": self._on_user_input_transcribed,
            "conversation_item_added": self._on_conversation_item_added,
            "function_tools_executed": self._on_function_tools_executed,
            "metrics_collected": self._on_metrics_collected,
            "session_usage_updated": self._on_session_usage_updated,
            "agent_state_changed": self._on_agent_state_changed,
            "user_state_changed": self._on_user_state_changed,
            "speech_created": self._on_speech_created,
            "error": self._on_error,
            "close": self._on_close,
        }
        for event_name, handler in self._bound_handlers.items():
            session.on(event_name, handler)

    def _unbind_session_events(self) -> None:
        if self._session is None or not hasattr(self._session, "off"):
            self._bound_handlers.clear()
            return
        for event_name, handler in self._bound_handlers.items():
            self._session.off(event_name, handler)
        self._bound_handlers.clear()

    async def _open_session_span(self, session: Any, agent: Any) -> None:
        if self._session_span_context is not None:
            if agent is not None:
                self._session_span_context.set_result(
                    {"conversation": {"agent_class": agent.__class__.__name__}}
                )
            return

        instance = await self._ensure_initialized()
        payload = {
            "name": self._agent_name or "livekit-session",
            "agent_name": self._agent_name or self._agent_id,
            "session_class": session.__class__.__name__,
            "metadata": {
                "tool_span_types": dict(self._tool_span_types),
                "agent_id": self._agent_id,
            },
        }
        if agent is not None:
            payload["agent_class"] = agent.__class__.__name__

        self._session_span_cm = instance.span("livekit:session")
        self._session_span_context = await self._session_span_cm.__aenter__()
        await self._session_span_context.start(payload)
        self._session_span_id = self._session_span_context.id

    async def _detach_session(
        self,
        final_status: str,
        *,
        close_reason: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        if self._closed:
            return

        self._closed = True
        self._unbind_session_events()
        await self._finish_active_assistant_turn(
            status="failed" if final_status == "failed" else "cancelled",
            error=error,
        )
        await self._finish_active_user_turn(
            status="failed" if final_status == "failed" else "cancelled",
            error=error,
        )
        await self._finish_session_span(
            status=final_status,
            error=error,
            close_reason=close_reason,
        )
        self._session = None

    async def _finish_session_span(
        self,
        status: str,
        error: dict[str, Any] | None = None,
        close_reason: str | None = None,
    ) -> None:
        if self._session_span_context is None or self._session_span_cm is None:
            return

        conversation = {
            **self._conversation_summary,
            "partial_transcripts": list(self._partial_transcripts),
            "turns": list(self._conversation_turns),
        }
        result: dict[str, Any] = {
            "status": status,
            "usage": self._usage_summary or {},
            "conversation": conversation,
        }
        if close_reason is not None:
            result["metadata"] = {"close_reason": close_reason}
        if error is not None:
            result["error"] = error

        if status == "failed":
            await self._session_span_context.fail(result)
        elif status == "cancelled":
            await self._session_span_context.cancel()
        else:
            await self._session_span_context.complete(result)

        await self._session_span_cm.__aexit__(None, None, None)
        self._session_span_cm = None
        self._session_span_context = None
        self._session_span_id = None

    async def _finalize_owned_resources(self) -> None:
        if self._resources_finalized:
            return

        self._resources_finalized = True

        if self._instance is not None and self._owns_instance:
            await self._instance.finish()
            self._instance = None
            self._owns_instance = False

        if self._client is not None and self._owns_client:
            await self._client.close()
            self._client = None
            self._owns_client = False

    async def _finalize_terminal_shutdown(
        self,
        *,
        final_status: str,
        close_reason: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        await self._detach_session(
            final_status=final_status,
            close_reason=close_reason,
            error=error,
        )
        await self._finalize_owned_resources()
        await self._shutdown_event_worker()

    def _schedule(self, coro: Any, *, allow_during_shutdown: bool = False) -> None:
        loop = self._loop
        if (
            loop is None
            or loop.is_closed()
            or self._event_worker_stopping
            or self._event_worker_stopped
            or (self._terminal_shutdown_requested and not allow_during_shutdown)
        ):
            coro.close()
            return

        def _spawn() -> None:
            if (
                self._event_worker_stopping
                or self._event_worker_stopped
                or (self._terminal_shutdown_requested and not allow_during_shutdown)
            ):
                coro.close()
                return
            self._ensure_event_worker()
            if self._event_queue is None:
                coro.close()
                return
            self._event_queue.put_nowait(coro)

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is loop:
            _spawn()
        else:
            loop.call_soon_threadsafe(_spawn)

    def _ensure_event_worker(self) -> None:
        if (
            self._loop is None
            or self._event_worker_stopping
            or self._event_worker_stopped
        ):
            return
        if self._event_queue is None:
            self._event_queue = asyncio.Queue()
        if self._event_worker_task is None or self._event_worker_task.done():
            self._event_worker_task = self._loop.create_task(self._event_worker())

    async def _event_worker(self) -> None:
        queue = self._event_queue
        assert queue is not None
        try:
            while True:
                coro = await queue.get()
                try:
                    if coro is None:
                        return
                    await coro
                except Exception:
                    logger.exception("Error processing prefactor-livekit event")
                finally:
                    queue.task_done()
        finally:
            if self._event_queue is queue:
                self._event_queue = None
            if self._event_worker_task is asyncio.current_task():
                self._event_worker_task = None
            self._event_worker_stopped = True
            self._event_worker_stopping = False

    async def _drain_pending_tasks(self) -> None:
        if self._event_queue is None:
            return
        await self._event_queue.join()

    async def _shutdown_event_worker(self) -> None:
        if self._event_queue is None or self._event_worker_task is None:
            return

        queue = self._event_queue
        task = self._event_worker_task
        current_task = asyncio.current_task()

        if self._event_worker_stopping:
            if current_task is task:
                return
            await task
            return

        self._event_worker_stopping = True

        if current_task is task:
            queue.put_nowait(None)
            return

        await queue.join()
        queue.put_nowait(None)
        await task

    def _next_turn_index(self) -> int:
        self._turn_index += 1
        return self._turn_index

    def _safe_model_dump(self, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return value

    def _safe_error_dict(self, error: Any) -> dict[str, Any]:
        return {
            "error_type": type(error).__name__,
            "message": str(error),
        }

    def _conversation_item_to_dict(self, item: Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return item.model_dump()
        result: dict[str, Any] = {"type": getattr(item, "type", type(item).__name__)}
        for key in ("id", "role", "content", "name", "call_id", "arguments", "output"):
            if hasattr(item, key):
                result[key] = getattr(item, key)
        return result

    def _parse_arguments(self, arguments: Any) -> Any:
        if not isinstance(arguments, str):
            return arguments
        try:
            return json.loads(arguments)
        except json.JSONDecodeError:
            return arguments

    def _resolve_tool_schema_name(self, tool_name: str) -> str:
        return self._tool_span_types.get(tool_name, "livekit:tool")

    async def _open_turn_span(
        self,
        schema_name: str,
        payload: dict[str, Any],
        story: dict[str, Any],
        *,
        parent_span_id: str | None = None,
        auto_finish_on_message: bool = False,
    ) -> _OpenTurnState:
        instance = await self._ensure_initialized()
        span_cm = instance.span(
            schema_name,
            parent_span_id=parent_span_id or self._session_span_id,
        )
        span_context = await span_cm.__aenter__()
        await span_context.start(payload)
        return _OpenTurnState(
            schema_name=schema_name,
            turn_index=int(payload["turn_index"]),
            span_cm=span_cm,
            span_context=span_context,
            payload=payload,
            story=story,
            auto_finish_on_message=auto_finish_on_message,
        )

    async def _emit_span(
        self,
        schema_name: str,
        params: dict[str, Any],
        result: dict[str, Any],
        *,
        parent_span_id: str | None = None,
        failed: bool = False,
    ) -> None:
        instance = self._instance
        if instance is None:
            return
        async with instance.span(
            schema_name,
            parent_span_id=parent_span_id or self._session_span_id,
        ) as ctx:
            await ctx.start(params)
            if failed:
                await ctx.fail(result)
            else:
                await ctx.complete(result)

    def _build_turn_story(
        self,
        *,
        turn_index: int,
        role: str,
        created_at: float | None,
        started_at: float | None,
        source: str | None = None,
        user_initiated: bool | None = None,
    ) -> dict[str, Any]:
        story: dict[str, Any] = {
            "turn_index": turn_index,
            "role": role,
            "status": "active",
            "created_at": created_at,
            "started_at": started_at,
            "metrics": {},
        }
        if source is not None:
            story["source"] = source
        if user_initiated is not None:
            story["user_initiated"] = user_initiated
        return story

    def _turn_result_metrics(self, turn: _OpenTurnState) -> dict[str, Any]:
        return turn.result.setdefault("metrics", {})

    def _turn_story_metrics(self, turn_story: dict[str, Any]) -> dict[str, Any]:
        metrics = turn_story.get("metrics")
        if not isinstance(metrics, dict):
            metrics = {}
            turn_story["metrics"] = metrics
        return metrics

    def _current_assistant_parent_span_id(self) -> str | None:
        if self._active_assistant_turn is not None:
            return self._active_assistant_turn.span_id
        return self._session_span_id

    async def _finish_turn(
        self,
        turn: _OpenTurnState,
        *,
        status: str,
        finished_at: float | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        if turn.finished:
            return

        result = dict(turn.result)
        result["status"] = status
        if finished_at is not None:
            result.setdefault("finished_at", finished_at)
            turn.story["finished_at"] = finished_at
        if error is not None:
            result["error"] = error
            turn.story["error"] = error
        turn.story["status"] = status

        if status == "failed":
            await turn.span_context.fail(result)
        else:
            await turn.span_context.complete(result)
        await turn.span_cm.__aexit__(None, None, None)
        turn.finished = True

    async def _finish_active_user_turn(
        self,
        *,
        status: str,
        finished_at: float | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        if self._active_user_turn is None:
            return
        turn = self._active_user_turn
        self._active_user_turn = None
        await self._finish_turn(
            turn,
            status=status,
            finished_at=finished_at,
            error=error,
        )

    async def _finish_active_assistant_turn(
        self,
        *,
        status: str,
        finished_at: float | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        if self._active_assistant_turn is None:
            return
        turn = self._active_assistant_turn
        self._active_assistant_turn = None
        await self._finish_turn(
            turn,
            status=status,
            finished_at=finished_at,
            error=error,
        )

    async def _start_user_turn(self, event: Any) -> None:
        created_at = getattr(event, "created_at", None)
        if self._active_user_turn is not None:
            await self._finish_active_user_turn(
                status="cancelled", finished_at=created_at
            )

        turn_index = self._next_turn_index()
        payload = {
            "name": "user_turn",
            "turn_index": turn_index,
            "created_at": created_at,
            "started_at": created_at,
            "metadata": {},
        }
        story = self._build_turn_story(
            turn_index=turn_index,
            role="user",
            created_at=created_at,
            started_at=created_at,
        )
        self._conversation_turns.append(story)
        self._active_user_turn = await self._open_turn_span(
            "livekit:user_turn",
            payload,
            story,
        )

    async def _start_assistant_turn(
        self,
        *,
        source: str,
        created_at: float | None,
        user_initiated: bool,
        auto_finish_on_message: bool,
    ) -> _OpenTurnState:
        if self._active_assistant_turn is not None:
            fallback_status = (
                "completed"
                if self._active_assistant_turn.result.get("outputs")
                else "cancelled"
            )
            await self._finish_active_assistant_turn(
                status=fallback_status,
                finished_at=created_at,
            )

        turn_index = self._next_turn_index()
        payload = {
            "name": "assistant_turn",
            "turn_index": turn_index,
            "source": source,
            "user_initiated": user_initiated,
            "created_at": created_at,
            "started_at": created_at,
            "metadata": {},
        }
        story = self._build_turn_story(
            turn_index=turn_index,
            role="assistant",
            created_at=created_at,
            started_at=created_at,
            source=source,
            user_initiated=user_initiated,
        )
        self._conversation_turns.append(story)
        turn = await self._open_turn_span(
            "livekit:assistant_turn",
            payload,
            story,
            auto_finish_on_message=auto_finish_on_message,
        )
        self._active_assistant_turn = turn
        return turn

    def _assistant_turn_result_from_item(
        self, item_dict: dict[str, Any]
    ) -> dict[str, Any]:
        outputs = {"message": item_dict}
        metrics = item_dict.get("metrics")
        result: dict[str, Any] = {"outputs": outputs}
        if isinstance(metrics, dict):
            turn_metrics: dict[str, Any] = {}
            if metrics.get("started_speaking_at") is not None:
                turn_metrics["started_speaking_at"] = metrics["started_speaking_at"]
            if metrics.get("stopped_speaking_at") is not None:
                turn_metrics["stopped_speaking_at"] = metrics["stopped_speaking_at"]
            if metrics.get("llm_node_ttft") is not None:
                turn_metrics["llm_node_ttft"] = metrics["llm_node_ttft"]
            if metrics.get("tts_node_ttfb") is not None:
                turn_metrics["tts_node_ttfb"] = metrics["tts_node_ttfb"]
            if metrics.get("e2e_latency") is not None:
                turn_metrics["e2e_latency"] = metrics["e2e_latency"]
            if turn_metrics:
                result["metrics"] = turn_metrics
        return result

    def _record_user_metric(self, metric_type: str, payload: dict[str, Any]) -> None:
        target_turn = self._active_user_turn
        if target_turn is None:
            return
        metrics = self._turn_result_metrics(target_turn)
        story_metrics = self._turn_story_metrics(target_turn.story)
        metrics[metric_type] = payload
        story_metrics[metric_type] = payload

    def _record_assistant_metric(
        self, metric_type: str, payload: dict[str, Any]
    ) -> None:
        target_turn = self._active_assistant_turn
        if target_turn is None:
            return
        metrics = self._turn_result_metrics(target_turn)
        story_metrics = self._turn_story_metrics(target_turn.story)
        metrics.setdefault(metric_type, []).append(payload)
        story_metrics.setdefault(metric_type, []).append(payload)

    def _metrics_payload(self, metrics: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        payload = self._safe_model_dump(metrics)
        metadata = payload.pop("metadata", None) or {}
        if not isinstance(metadata, dict):
            metadata = self._safe_model_dump(metadata)
        return payload, metadata

    def _on_user_input_transcribed(self, event: Any) -> None:
        if not getattr(event, "is_final", False):
            self._partial_transcripts.append(
                {
                    "transcript": getattr(event, "transcript", ""),
                    "created_at": getattr(event, "created_at", None),
                }
            )
            return

        self._schedule(self._handle_final_user_transcript(event))

    async def _handle_final_user_transcript(self, event: Any) -> None:
        created_at = getattr(event, "created_at", None)
        transcript = getattr(event, "transcript", "")
        language = getattr(event, "language", None)
        speaker_id = getattr(event, "speaker_id", None)

        if self._active_user_turn is None:
            turn_index = self._next_turn_index()
            payload = {
                "name": "user_turn",
                "turn_index": turn_index,
                "created_at": created_at,
                "started_at": created_at,
                "metadata": {},
            }
            story = self._build_turn_story(
                turn_index=turn_index,
                role="user",
                created_at=created_at,
                started_at=created_at,
            )
            story.update(
                {
                    "transcript": transcript,
                    "language": language,
                    "speaker_id": speaker_id,
                    "finished_at": created_at,
                    "is_final": True,
                    "status": "completed",
                }
            )
            self._conversation_turns.append(story)
            result = {
                "status": "completed",
                "transcript": transcript,
                "speaker_id": speaker_id,
                "language": language,
                "is_final": True,
                "finished_at": created_at,
                "metadata": {},
            }
            await self._emit_span("livekit:user_turn", payload, result)
            self._conversation_summary["user_messages"] += 1
            return

        turn = self._active_user_turn
        turn.result.update(
            {
                "transcript": transcript,
                "speaker_id": speaker_id,
                "language": language,
                "is_final": True,
                "metadata": {},
            }
        )
        turn.story.update(
            {
                "transcript": transcript,
                "speaker_id": speaker_id,
                "language": language,
                "is_final": True,
            }
        )
        self._conversation_summary["user_messages"] += 1
        await self._finish_active_user_turn(status="completed", finished_at=created_at)

    def _on_conversation_item_added(self, event: Any) -> None:
        item = getattr(event, "item", None)
        item_dict = self._conversation_item_to_dict(item)
        self._conversation_summary["items_seen"] += 1
        role = item_dict.get("role")
        if role == "assistant":
            self._schedule(self._handle_assistant_item_added(event, item_dict))

    async def _handle_assistant_item_added(
        self,
        event: Any,
        item_dict: dict[str, Any],
    ) -> None:
        if self._active_assistant_turn is None:
            await self._start_assistant_turn(
                source="conversation_item_added",
                created_at=getattr(event, "created_at", None),
                user_initiated=False,
                auto_finish_on_message=True,
            )

        turn = self._active_assistant_turn
        assert turn is not None
        turn_result = self._assistant_turn_result_from_item(item_dict)
        turn.result["outputs"] = turn_result["outputs"]
        if "metrics" in turn_result:
            self._turn_result_metrics(turn).update(turn_result["metrics"])
            self._turn_story_metrics(turn.story).update(turn_result["metrics"])
        turn.story["outputs"] = turn_result["outputs"]
        self._conversation_summary["assistant_messages"] += 1

        if turn.auto_finish_on_message:
            await self._finish_active_assistant_turn(
                status="completed",
                finished_at=item_dict.get("created_at")
                or getattr(event, "created_at", None),
            )

    def _on_function_tools_executed(self, event: Any) -> None:
        zipped = event.zipped() if hasattr(event, "zipped") else []
        for function_call, function_output in zipped:
            self._conversation_summary["function_calls"] += 1
            self._schedule(
                self._emit_function_tool_span(function_call, function_output)
            )

    async def _emit_function_tool_span(
        self,
        function_call: Any,
        function_output: Any,
    ) -> None:
        tool_name = getattr(function_call, "name", "unknown")
        params = {
            "name": tool_name,
            "tool_name": tool_name,
            "call_id": getattr(function_call, "call_id", None),
            "group_id": getattr(function_call, "group_id", None),
            "inputs": self._parse_arguments(getattr(function_call, "arguments", {})),
            "created_at": getattr(function_call, "created_at", None),
            "metadata": getattr(function_call, "extra", {}),
        }
        if self._active_assistant_turn is not None:
            params["turn_index"] = self._active_assistant_turn.turn_index

        is_error = getattr(function_output, "is_error", False)
        result = {
            "status": "failed" if is_error else "completed",
            "outputs": {
                "output": getattr(function_output, "output", None),
                "name": getattr(function_output, "name", None),
            },
            "is_error": is_error,
        }
        await self._emit_span(
            self._resolve_tool_schema_name(tool_name),
            params,
            result,
            parent_span_id=self._current_assistant_parent_span_id(),
            failed=is_error,
        )

        if self._active_assistant_turn is not None:
            tool_story = {
                "tool_name": tool_name,
                "call_id": getattr(function_call, "call_id", None),
                "created_at": getattr(function_call, "created_at", None),
                "inputs": params["inputs"],
                "is_error": is_error,
            }
            self._active_assistant_turn.story.setdefault("tool_calls", []).append(
                tool_story
            )

    def _on_metrics_collected(self, event: Any) -> None:
        metrics = getattr(event, "metrics", None)
        if metrics is None:
            return
        self._schedule(self._handle_metrics_collected(metrics))

    async def _handle_metrics_collected(self, metrics: Any) -> None:
        payload, metadata = self._metrics_payload(metrics)
        metric_type = getattr(metrics, "type", None)

        if metric_type in {"llm_metrics", "realtime_model_metrics"}:
            if self._active_assistant_turn is None:
                await self._start_assistant_turn(
                    source="llm_metrics",
                    created_at=payload.get("timestamp"),
                    user_initiated=True,
                    auto_finish_on_message=True,
                )
            turn = self._active_assistant_turn
            assert turn is not None
            llm_summary = {
                "request_id": payload.get("request_id"),
                "timestamp": payload.get("timestamp"),
                "label": payload.get("label"),
                "model_name": metadata.get("model_name"),
                "provider": metadata.get("model_provider"),
                "metrics": payload,
            }
            self._record_assistant_metric("llm", llm_summary)
            params = {
                "name": metric_type,
                "turn_index": turn.turn_index,
                "label": payload.get("label"),
                "request_id": payload.get("request_id"),
                "model_name": metadata.get("model_name"),
                "provider": metadata.get("model_provider"),
                "timestamp": payload.get("timestamp"),
                "metadata": metadata,
            }
            result = {"status": "completed", "metrics": payload}
            await self._emit_span(
                "livekit:llm",
                params,
                result,
                parent_span_id=turn.span_id,
            )
            return

        if metric_type == "stt_metrics":
            self._record_user_metric(
                "stt",
                {
                    "request_id": payload.get("request_id"),
                    "timestamp": payload.get("timestamp"),
                    "label": payload.get("label"),
                    "model_name": metadata.get("model_name"),
                    "provider": metadata.get("model_provider"),
                    "metrics": payload,
                },
            )
            return

        if metric_type == "tts_metrics":
            self._record_assistant_metric(
                "tts",
                {
                    "request_id": payload.get("request_id"),
                    "timestamp": payload.get("timestamp"),
                    "label": payload.get("label"),
                    "model_name": metadata.get("model_name"),
                    "provider": metadata.get("model_provider"),
                    "metrics": payload,
                },
            )
            return

        if metric_type == "eou_metrics":
            self._record_user_metric(
                "eou",
                {
                    "timestamp": payload.get("timestamp"),
                    "metrics": payload,
                },
            )
            return

        if metric_type == "interruption_metrics":
            if self._active_assistant_turn is not None:
                interruption_summary = {
                    "timestamp": payload.get("timestamp"),
                    "metrics": payload,
                }
                self._record_assistant_metric("interruptions", interruption_summary)
                self._active_assistant_turn.result["interrupted"] = True
                self._active_assistant_turn.story["interrupted"] = True
                await self._finish_active_assistant_turn(
                    status="completed",
                    finished_at=payload.get("timestamp"),
                )

    def _on_session_usage_updated(self, event: Any) -> None:
        usage = getattr(event, "usage", None)
        if usage is None:
            return
        self._usage_summary = {
            "model_usage": [
                self._safe_model_dump(item)
                for item in getattr(usage, "model_usage", [])
            ]
        }
        if self._session_span_context is not None:
            self._session_span_context.set_result({"usage": self._usage_summary})

    def _on_agent_state_changed(self, event: Any) -> None:
        self._schedule(self._handle_agent_state_changed(event))

    async def _handle_agent_state_changed(self, event: Any) -> None:
        old_state = getattr(event, "old_state", None)
        new_state = getattr(event, "new_state", None)
        created_at = getattr(event, "created_at", None)

        if old_state == "speaking" and new_state == "listening":
            await self._finish_active_assistant_turn(
                status="completed",
                finished_at=created_at,
            )

    def _on_user_state_changed(self, event: Any) -> None:
        self._schedule(self._handle_user_state_changed(event))

    async def _handle_user_state_changed(self, event: Any) -> None:
        old_state = getattr(event, "old_state", None)
        new_state = getattr(event, "new_state", None)

        if old_state == "listening" and new_state == "speaking":
            await self._start_user_turn(event)

    def _on_speech_created(self, event: Any) -> None:
        self._schedule(self._handle_speech_created(event))

    async def _handle_speech_created(self, event: Any) -> None:
        created_at = getattr(event, "created_at", None)
        source = getattr(event, "source", "unknown")
        user_initiated = getattr(event, "user_initiated", False)

        if (
            self._active_assistant_turn is not None
            and self._active_assistant_turn.payload.get("source") == "llm_metrics"
            and not self._active_assistant_turn.result.get("outputs")
        ):
            turn = self._active_assistant_turn
            turn.payload.update(
                {
                    "source": source,
                    "user_initiated": user_initiated,
                    "created_at": created_at,
                    "started_at": created_at,
                }
            )
            turn.story.update(
                {
                    "source": source,
                    "user_initiated": user_initiated,
                    "created_at": created_at,
                    "started_at": created_at,
                }
            )
            turn.auto_finish_on_message = False
            return

        await self._start_assistant_turn(
            source=source,
            created_at=created_at,
            user_initiated=user_initiated,
            auto_finish_on_message=False,
        )

    def _on_error(self, event: Any) -> None:
        error = getattr(event, "error", None)
        source = getattr(event, "source", None)
        error_dict = self._safe_error_dict(error)
        params = {
            "name": "livekit_error",
            "source": type(source).__name__ if source is not None else None,
            "error_type": error_dict["error_type"],
            "message": error_dict["message"],
            "created_at": getattr(event, "created_at", None),
            "metadata": {},
        }
        self._schedule(
            self._emit_span(
                "livekit:error",
                params,
                {"status": "failed", "error": error_dict},
                failed=True,
            )
        )
        self._schedule(
            self._finish_active_assistant_turn(status="failed", error=error_dict)
        )
        self._schedule(self._finish_active_user_turn(status="failed", error=error_dict))

    def _on_close(self, event: Any) -> None:
        reason = getattr(
            getattr(event, "reason", None),
            "value",
            getattr(event, "reason", None),
        )
        error = getattr(event, "error", None)

        if self._terminal_shutdown_requested:
            return
        self._terminal_shutdown_requested = True

        if reason == "error":
            error_dict = self._safe_error_dict(error) if error is not None else None
            self._schedule(
                self._finalize_terminal_shutdown(
                    final_status="failed",
                    close_reason=reason,
                    error=error_dict,
                ),
                allow_during_shutdown=True,
            )
            return

        if reason in {"job_shutdown", "participant_disconnected", "user_initiated"}:
            self._schedule(
                self._finalize_terminal_shutdown(
                    final_status="completed",
                    close_reason=reason,
                ),
                allow_during_shutdown=True,
            )
            return

        self._schedule(
            self._finalize_terminal_shutdown(
                final_status="completed",
                close_reason=reason if isinstance(reason, str) else None,
            ),
            allow_during_shutdown=True,
        )


__all__ = ["PrefactorLiveKitSession"]
