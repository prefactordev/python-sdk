"""LangChain callback handler for tracing LangGraph graphs."""

from __future__ import annotations

import functools
import logging
import sys
import traceback
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.outputs import LLMResult
from prefactor_core import (
    AgentInstanceHandle,
    PrefactorCoreClient,
    PrefactorCoreConfig,
    PrefactorTelemetryFailureError,
    PrefactorTerminatedError,
)

from . import payloads
from .metadata_extractor import extract_token_usage
from .middleware import LANGCHAIN_SDK_HEADER_ENTRY
from .spans import AgentSpan, ErrorInfo, LLMSpan, ToolSpan

logger = logging.getLogger("prefactor_langchain.callback_handler")


@dataclass
class _OpenSpan:
    """A span that has started and is waiting for its run to end."""

    manager: Any
    context: Any
    schema_name: str
    data: Any = None


def _guarded(
    callback: Callable[..., Awaitable[None]],
) -> Callable[..., Awaitable[None]]:
    """Log a callback's errors instead of letting them stop the graph.

    Termination and latched telemetry failures still propagate. When the
    callback leaves its run's span open, the span is closed as failed.
    """

    name = getattr(callback, "__name__", "callback")

    @functools.wraps(callback)
    async def guarded(
        self: PrefactorCallbackHandler, *args: Any, run_id: UUID, **kwargs: Any
    ) -> None:
        try:
            await callback(self, *args, run_id=run_id, **kwargs)
        except PrefactorTerminatedError:
            raise
        except Exception as e:
            _raise_if_telemetry_failure(e)
            logger.error("Error in %s: %s", name, e, exc_info=True)
            await self._close_after_error(run_id, e)

    return guarded


class PrefactorCallbackHandler(AsyncCallbackHandler):
    """Trace a LangGraph graph through LangChain callbacks.

    Pass the handler in the run config:
    ``await graph.ainvoke(state, config={"callbacks": [handler]})``.

    The handler records these spans on the given agent instance:

    - ``langchain:agent`` for each graph run with no parent run
    - ``langchain:node`` for each node of that graph
    - ``langchain:llm`` for each chat model call
    - ``langchain:tool`` (or a tool-specific type) for each tool call

    Nodes of nested graphs, such as a ``create_agent`` subagent called from a
    node, get no span of their own. Their model and tool calls appear under
    the outer node. The caller owns the instance lifecycle.

    Do not use this handler and ``PrefactorMiddleware`` on the same agent; each
    model and tool call would be recorded twice.

    Example:
        registry = SchemaRegistry()
        tool_span_types = register_langchain_schemas(registry)
        config = PrefactorCoreConfig(http_config=..., schema_registry=registry)
        client = PrefactorCallbackHandler.create_client(config)
        await client.initialize()

        instance = await client.create_agent_instance(
            agent_id="my-agent",
            agent_version={"name": "My Graph", "external_identifier": "v1"},
        )
        await instance.start()

        handler = PrefactorCallbackHandler(
            instance=instance, tool_span_types=tool_span_types
        )
        await graph.ainvoke(state, config={"callbacks": [handler]})

        await instance.finish()
        await client.close()
    """

    # Lets the termination check stop the graph. Every other error is caught
    # and logged by ``_guarded``.
    raise_error = True

    @staticmethod
    def create_client(config: PrefactorCoreConfig) -> PrefactorCoreClient:
        """Create a PrefactorCoreClient configured for use with this handler.

        Args:
            config: Core configuration for the client.

        Returns:
            A PrefactorCoreClient ready for ``await client.initialize()``.
        """
        return PrefactorCoreClient(config, sdk_header_entry=LANGCHAIN_SDK_HEADER_ENTRY)

    def __init__(
        self,
        instance: AgentInstanceHandle,
        tool_span_types: Mapping[str, str] | None = None,
    ) -> None:
        """Initialise the handler.

        Args:
            instance: A started agent instance that receives the spans.
            tool_span_types: Tool name to span type, as returned by
                ``register_langchain_schemas``.
        """
        super().__init__()
        self._instance = instance
        self._tool_span_types = dict(tool_span_types or {})
        self._parents: dict[UUID, UUID | None] = {}
        self._open_spans: dict[UUID, _OpenSpan] = {}

    # Chains: graph runs and graph nodes

    @_guarded
    async def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Start an agent span for a graph run or a node span for a node."""
        self._parents[run_id] = parent_run_id
        name = kwargs.get("name")
        metadata = metadata or {}

        if parent_run_id is None:
            span_data = AgentSpan(
                name=name or "agent",
                agent_name=name,
                inputs=payloads.state_to_json(inputs),
            )
            await self._start_span(
                run_id,
                "langchain:agent",
                payloads.build_agent_params(span_data),
                span_data,
            )
        elif self._is_node_run(parent_run_id, name, metadata):
            self._throw_if_terminated()
            await self._start_span(
                run_id,
                "langchain:node",
                {"node": name, "step": metadata.get("langgraph_step")},
            )

    @_guarded
    async def on_chain_end(
        self,
        outputs: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Complete the span for a graph run or node."""
        open_span = self._open_spans.get(run_id)
        if open_span is None:
            self._parents.pop(run_id, None)
            return

        if open_span.schema_name == "langchain:agent":
            open_span.data.complete(outputs=payloads.state_to_json(outputs))
            result = payloads.build_agent_result(open_span.data)
        elif isinstance(outputs, Mapping):
            result = {"status": "completed", "updated_keys": sorted(outputs)}
        else:
            result = {"status": "completed"}
        await self._finish_span(run_id, result, failed=False)

    @_guarded
    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Fail the span for a graph run or node."""
        open_span = self._open_spans.get(run_id)
        if open_span is None:
            self._parents.pop(run_id, None)
            return

        error_info = _error_info(error).to_dict()
        if open_span.schema_name == "langchain:agent":
            result = {"error": error_info}
        else:
            result = {"status": "error", "error": error_info}
        await self._finish_span(run_id, result, failed=True)

    # Chat models

    @_guarded
    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Start an LLM span for a chat model call."""
        self._parents[run_id] = parent_run_id
        prompt = messages[0] if messages else []
        model_name = _model_name(kwargs.get("invocation_params"), metadata)

        inputs: dict[str, Any] = {}
        if model_name:
            inputs["model"] = model_name
        conversation = [m for m in prompt if not isinstance(m, SystemMessage)]
        if conversation:
            inputs["messages"] = [payloads.message_to_dict(m) for m in conversation]
        system = next((m for m in prompt if isinstance(m, SystemMessage)), None)
        if system is not None:
            inputs["system"] = system.content

        span_data = LLMSpan(
            name=model_name or "llm", inputs=inputs, model_name=model_name
        )
        await self._start_span(
            run_id, "langchain:llm", payloads.build_llm_params(span_data), span_data
        )

    @_guarded
    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Complete the LLM span with the model's reply and token usage."""
        open_span = self._open_spans.get(run_id)
        if open_span is None:
            self._parents.pop(run_id, None)
            return

        span_data = open_span.data
        generation = response.generations[0][0] if response.generations else None
        message = getattr(generation, "message", None)
        if message is not None:
            span_data.complete(
                outputs={"messages": [payloads.message_to_dict(message)]}
            )
            span_data.token_usage = extract_token_usage(
                SimpleNamespace(result=[message])
            )
        elif generation is not None:
            span_data.complete(outputs={"content": generation.text})
        await self._finish_span(
            run_id, payloads.build_llm_result(span_data), failed=False
        )

    @_guarded
    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Fail the LLM span."""
        await self._fail_data_span(run_id, error, payloads.build_llm_result)

    # Tools

    @_guarded
    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Start a tool span."""
        self._parents[run_id] = parent_run_id
        tool_name = (serialized or {}).get("name") or kwargs.get("name") or "unknown"
        arguments = inputs if inputs is not None else {"input": input_str}
        span_data = ToolSpan(
            name=tool_name,
            inputs={"tool_name": tool_name, "arguments": arguments},
            tool_name=tool_name,
            arguments=arguments,
        )
        schema_name = self._tool_span_types.get(tool_name, "langchain:tool")
        await self._start_span(
            run_id,
            schema_name,
            payloads.build_tool_params(span_data, schema_name),
            span_data,
        )

    @_guarded
    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Complete the tool span with the tool's output."""
        open_span = self._open_spans.get(run_id)
        if open_span is None:
            self._parents.pop(run_id, None)
            return

        content = getattr(output, "content", None)
        open_span.data.complete(
            outputs={"output": content if content is not None else str(output)}
        )
        await self._finish_span(
            run_id, payloads.build_tool_result(open_span.data), failed=False
        )

    @_guarded
    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Fail the tool span."""
        await self._fail_data_span(run_id, error, payloads.build_tool_result)

    # Span bookkeeping

    def _is_node_run(
        self, parent_run_id: UUID, name: str | None, metadata: Mapping[str, Any]
    ) -> bool:
        """Whether a chain run is a node of a top-level graph."""
        return (
            name is not None
            and name == metadata.get("langgraph_node")
            and parent_run_id in self._parents
            and self._parents[parent_run_id] is None
        )

    def _parent_span_id(self, run_id: UUID) -> str | None:
        """Return the span ID of the nearest ancestor run that has a span."""
        ancestor = self._parents.get(run_id)
        while ancestor is not None:
            open_span = self._open_spans.get(ancestor)
            if open_span is not None:
                return open_span.context.id
            ancestor = self._parents.get(ancestor)
        return None

    async def _start_span(
        self,
        run_id: UUID,
        schema_name: str,
        params: dict[str, Any],
        data: Any = None,
    ) -> None:
        try:
            manager = self._instance.span(
                schema_name, parent_span_id=self._parent_span_id(run_id)
            )
            context = await manager.__aenter__()
            try:
                await context.start(params)
            except BaseException:
                await manager.__aexit__(*sys.exc_info())
                raise
            self._open_spans[run_id] = _OpenSpan(manager, context, schema_name, data)
        except Exception as e:
            _raise_if_telemetry_failure(e)
            logger.error("Failed to start %s span: %s", schema_name, e, exc_info=True)

    async def _finish_span(
        self, run_id: UUID, result: dict[str, Any], *, failed: bool
    ) -> None:
        self._parents.pop(run_id, None)
        open_span = self._open_spans.pop(run_id, None)
        if open_span is None:
            return
        try:
            if failed:
                await open_span.context.fail(result)
            else:
                await open_span.context.complete(result)
            await open_span.manager.__aexit__(None, None, None)
        except Exception as e:
            _raise_if_telemetry_failure(e)
            logger.error(
                "Failed to finish %s span: %s",
                open_span.schema_name,
                e,
                exc_info=True,
            )

    async def _fail_data_span(
        self, run_id: UUID, error: BaseException, build_result: Any
    ) -> None:
        open_span = self._open_spans.get(run_id)
        if open_span is None:
            self._parents.pop(run_id, None)
            return
        open_span.data.status = "failed"
        open_span.data.error = _error_info(error)
        await self._finish_span(run_id, build_result(open_span.data), failed=True)

    async def _close_after_error(self, run_id: UUID, error: Exception) -> None:
        """Close the run's span as failed after its callback raised."""
        open_span = self._open_spans.get(run_id)
        if open_span is None:
            return
        result: dict[str, Any] = {"error": _error_info(error).to_dict()}
        if open_span.schema_name == "langchain:node":
            result["status"] = "error"
        await self._finish_span(run_id, result, failed=True)

    def _throw_if_terminated(self) -> None:
        monitor = getattr(self._instance._client, "_termination_monitor", None)
        if monitor is None:
            return
        if monitor.get_termination_event().is_set():
            raise PrefactorTerminatedError(monitor.termination_reason)


def _raise_if_telemetry_failure(error: BaseException) -> None:
    """Re-raise latched core telemetry failures."""
    if isinstance(error, PrefactorTelemetryFailureError):
        raise error


def _error_info(error: BaseException) -> ErrorInfo:
    return ErrorInfo(
        error_type=type(error).__name__,
        message=str(error),
        stacktrace="".join(traceback.format_exception(error)),
    )


def _model_name(
    invocation_params: Mapping[str, Any] | None,
    metadata: Mapping[str, Any] | None,
) -> str | None:
    params = invocation_params or {}
    for key in ("model", "model_name"):
        value = params.get(key)
        if isinstance(value, str):
            return value
    value = (metadata or {}).get("ls_model_name")
    return value if isinstance(value, str) else None


__all__ = ["PrefactorCallbackHandler"]
