"""LiveKit session wrapper for Prefactor observability."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Mapping
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
        self._pending_tasks: list[asyncio.Task[None]] = []
        self._session: Any | None = None
        self._bound_handlers: dict[str, Any] = {}

        self._session_span_cm: Any | None = None
        self._session_span_context: SpanContext | None = None
        self._session_span_id: str | None = None

        self._assistant_span_cm: Any | None = None
        self._assistant_span_context: SpanContext | None = None

        self._partial_transcripts: list[dict[str, Any]] = []
        self._conversation_summary: dict[str, Any] = {
            "items_seen": 0,
            "assistant_messages": 0,
            "user_messages": 0,
            "function_calls": 0,
        }
        self._usage_summary: dict[str, Any] = {}
        self._closed = False

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
        wrapper._pending_tasks = []
        wrapper._session = None
        wrapper._bound_handlers = {}
        wrapper._session_span_cm = None
        wrapper._session_span_context = None
        wrapper._session_span_id = None
        wrapper._assistant_span_cm = None
        wrapper._assistant_span_context = None
        wrapper._partial_transcripts = []
        wrapper._conversation_summary = {
            "items_seen": 0,
            "assistant_messages": 0,
            "user_messages": 0,
            "function_calls": 0,
        }
        wrapper._usage_summary = {}
        wrapper._closed = False
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

        await self._drain_pending_tasks()
        await self._detach_session(final_status="completed")

        if self._instance is not None and self._owns_instance:
            await self._instance.finish()
            self._instance = None
            self._owns_instance = False

        if self._client is not None and self._owns_client:
            await self._client.close()
            self._client = None
            self._owns_client = False

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

    async def _detach_session(self, final_status: str) -> None:
        if self._closed:
            return

        self._closed = True
        self._unbind_session_events()
        await self._close_assistant_turn(status=final_status)
        await self._finish_session_span(status=final_status)
        self._session = None

    async def _finish_session_span(
        self,
        status: str,
        error: dict[str, Any] | None = None,
    ) -> None:
        if self._session_span_context is None or self._session_span_cm is None:
            return

        result: dict[str, Any] = {
            "status": status,
            "usage": self._usage_summary or {},
            "conversation": {
                **self._conversation_summary,
                "partial_transcripts": list(self._partial_transcripts),
            },
        }
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

    def _schedule(self, coro: Any) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        def _spawn() -> None:
            task = loop.create_task(coro)
            self._pending_tasks.append(task)

            def _cleanup(done: asyncio.Task[None]) -> None:
                if done in self._pending_tasks:
                    self._pending_tasks.remove(done)

            task.add_done_callback(_cleanup)

        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop is loop:
            _spawn()
        else:
            loop.call_soon_threadsafe(_spawn)

    async def _drain_pending_tasks(self) -> None:
        if not self._pending_tasks:
            return
        await asyncio.gather(*self._pending_tasks, return_exceptions=True)
        self._pending_tasks.clear()

    async def _emit_span(
        self,
        schema_name: str,
        params: dict[str, Any],
        result: dict[str, Any],
        *,
        failed: bool = False,
    ) -> None:
        instance = self._instance
        if instance is None:
            return
        async with instance.span(
            schema_name,
            parent_span_id=self._session_span_id,
        ) as ctx:
            await ctx.start(params)
            if failed:
                await ctx.fail(result)
            else:
                await ctx.complete(result)

    async def _open_assistant_turn(self, event: Any) -> None:
        await self._close_assistant_turn(status="completed")
        instance = await self._ensure_initialized()
        self._assistant_span_cm = instance.span(
            "livekit:assistant_turn",
            parent_span_id=self._session_span_id,
        )
        self._assistant_span_context = await self._assistant_span_cm.__aenter__()
        payload = {
            "name": "assistant_turn",
            "source": getattr(event, "source", "unknown"),
            "user_initiated": getattr(event, "user_initiated", False),
            "created_at": getattr(event, "created_at", None),
            "metadata": {},
        }
        await self._assistant_span_context.start(payload)

    async def _close_assistant_turn(
        self,
        *,
        status: str,
        outputs: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        if self._assistant_span_context is None or self._assistant_span_cm is None:
            return

        result: dict[str, Any] = {"status": status}
        if outputs is not None:
            result["outputs"] = outputs
        if error is not None:
            result["error"] = error

        if status == "failed":
            await self._assistant_span_context.fail(result)
        elif status == "cancelled":
            await self._assistant_span_context.cancel()
        else:
            await self._assistant_span_context.complete(result)
        await self._assistant_span_cm.__aexit__(None, None, None)
        self._assistant_span_cm = None
        self._assistant_span_context = None

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

    def _on_user_input_transcribed(self, event: Any) -> None:
        if not getattr(event, "is_final", False):
            self._partial_transcripts.append(
                {
                    "transcript": getattr(event, "transcript", ""),
                    "created_at": getattr(event, "created_at", None),
                }
            )
            return

        params = {
            "name": "user_turn",
            "transcript": getattr(event, "transcript", ""),
            "speaker_id": getattr(event, "speaker_id", None),
            "language": getattr(event, "language", None),
            "is_final": True,
            "created_at": getattr(event, "created_at", None),
            "metadata": {},
        }
        result = {"status": "completed", "metadata": {}}
        self._schedule(self._emit_span("livekit:user_turn", params, result))

    def _on_conversation_item_added(self, event: Any) -> None:
        item = getattr(event, "item", None)
        item_dict = self._conversation_item_to_dict(item)
        self._conversation_summary["items_seen"] += 1
        role = item_dict.get("role")
        if role == "assistant":
            self._conversation_summary["assistant_messages"] += 1
            outputs = {"message": item_dict}
            self._schedule(
                self._close_assistant_turn(status="completed", outputs=outputs)
            )
        elif role == "user":
            self._conversation_summary["user_messages"] += 1

    def _on_function_tools_executed(self, event: Any) -> None:
        zipped = event.zipped() if hasattr(event, "zipped") else []
        for function_call, function_output in zipped:
            self._conversation_summary["function_calls"] += 1
            tool_name = getattr(function_call, "name", "unknown")
            params = {
                "name": tool_name,
                "tool_name": tool_name,
                "call_id": getattr(function_call, "call_id", None),
                "group_id": getattr(function_call, "group_id", None),
                "inputs": self._parse_arguments(
                    getattr(function_call, "arguments", {})
                ),
                "created_at": getattr(function_call, "created_at", None),
                "metadata": getattr(function_call, "extra", {}),
            }
            is_error = getattr(function_output, "is_error", False)
            result = {
                "status": "failed" if is_error else "completed",
                "outputs": {
                    "output": getattr(function_output, "output", None),
                    "name": getattr(function_output, "name", None),
                },
                "is_error": is_error,
            }
            self._schedule(
                self._emit_span(
                    self._resolve_tool_schema_name(tool_name),
                    params,
                    result,
                    failed=is_error,
                )
            )

    def _metrics_to_span(
        self, metrics: Any
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        payload = self._safe_model_dump(metrics)
        metadata = payload.pop("metadata", None) or {}
        if metrics.type in {"llm_metrics", "realtime_model_metrics"}:
            schema_name = "livekit:llm"
        elif metrics.type == "stt_metrics":
            schema_name = "livekit:stt"
        elif metrics.type == "tts_metrics":
            schema_name = "livekit:tts"
        else:
            schema_name = "livekit:state"

        params = {
            "name": metrics.type,
            "label": payload.get("label"),
            "request_id": payload.get("request_id"),
            "model_name": metadata.get("model_name"),
            "provider": metadata.get("model_provider"),
            "timestamp": payload.get("timestamp"),
            "event_type": metrics.type,
            "metadata": metadata,
        }
        result = {"status": "completed", "metrics": payload}
        return schema_name, params, result

    def _on_metrics_collected(self, event: Any) -> None:
        metrics = getattr(event, "metrics", None)
        if metrics is None:
            return
        schema_name, params, result = self._metrics_to_span(metrics)
        self._schedule(self._emit_span(schema_name, params, result))

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
        params = {
            "name": "agent_state_changed",
            "actor": "agent",
            "old_state": getattr(event, "old_state", None),
            "new_state": getattr(event, "new_state", None),
            "event_type": "agent_state_changed",
            "created_at": getattr(event, "created_at", None),
            "metadata": {},
        }
        self._schedule(
            self._emit_span("livekit:state", params, {"status": "completed"})
        )

    def _on_user_state_changed(self, event: Any) -> None:
        params = {
            "name": "user_state_changed",
            "actor": "user",
            "old_state": getattr(event, "old_state", None),
            "new_state": getattr(event, "new_state", None),
            "event_type": "user_state_changed",
            "created_at": getattr(event, "created_at", None),
            "metadata": {},
        }
        self._schedule(
            self._emit_span("livekit:state", params, {"status": "completed"})
        )

    def _on_speech_created(self, event: Any) -> None:
        self._schedule(self._open_assistant_turn(event))

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
        self._schedule(self._close_assistant_turn(status="failed", error=error_dict))

    def _on_close(self, event: Any) -> None:
        reason = getattr(
            getattr(event, "reason", None),
            "value",
            getattr(event, "reason", None),
        )
        error = getattr(event, "error", None)

        if reason == "error":
            error_dict = self._safe_error_dict(error) if error is not None else None
            self._schedule(self._detach_session(final_status="failed"))
            if error_dict is not None:
                self._schedule(self._finish_session_span("failed", error=error_dict))
            return

        if reason in {"job_shutdown", "participant_disconnected", "user_initiated"}:
            self._schedule(self._detach_session(final_status="cancelled"))
            return

        self._schedule(self._detach_session(final_status="completed"))


__all__ = ["PrefactorLiveKitSession"]
