"""Tests for the LangGraph callback handler."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any, TypedDict

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from prefactor_core import PrefactorTerminatedError
from prefactor_langchain import PrefactorCallbackHandler


class RecordingSpanContext:
    """Span context that records its lifecycle and gets an ID on start."""

    def __init__(self, record: dict[str, Any], next_id: Any) -> None:
        self._record = record
        self._next_id = next_id
        self.id = f"temp-{id(self)}"

    async def start(self, payload: dict[str, Any]) -> None:
        self.id = self._next_id()
        self._record["id"] = self.id
        self._record["params"] = payload

    async def complete(self, result: dict[str, Any]) -> None:
        self._record["status"] = "complete"
        self._record["result"] = result

    async def fail(self, result: dict[str, Any]) -> None:
        self._record["status"] = "failed"
        self._record["result"] = result


class RecordingSpanManager:
    """Async context manager returned by ``RecordingInstance.span``."""

    def __init__(self, context: RecordingSpanContext, record: dict[str, Any]):
        self._context = context
        self._record = record

    async def __aenter__(self) -> RecordingSpanContext:
        return self._context

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._record["exited"] = True


class RecordingInstance:
    """Minimal AgentInstanceHandle stand-in that records every span."""

    def __init__(self, client: Any | None = None) -> None:
        self.spans: list[dict[str, Any]] = []
        self._counter = 0
        self._client = client or SimpleNamespace(_termination_monitor=None)

    def _next_id(self) -> str:
        self._counter += 1
        return f"span-{self._counter}"

    def span(self, schema_name: str, parent_span_id=None, payload=None):
        record: dict[str, Any] = {
            "schema_name": schema_name,
            "parent_span_id": parent_span_id,
        }
        self.spans.append(record)
        return RecordingSpanManager(RecordingSpanContext(record, self._next_id), record)


class FailingStartInstance(RecordingInstance):
    """Instance whose spans fail to start."""

    def span(self, schema_name: str, parent_span_id=None, payload=None):
        manager = super().span(schema_name, parent_span_id, payload)

        async def failing_start(payload: dict[str, Any]) -> None:
            raise RuntimeError("span start failed")

        manager._context.start = failing_start
        return manager


class ToolCallingFakeModel(GenericFakeChatModel):
    """Fake chat model that accepts bound tools."""

    def bind_tools(self, tools, **kwargs):
        return self


@tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


class State(TypedDict):
    messages: list
    out: str


def build_graph(fail_in_second: bool = False):
    """Build a two-node graph: a model call, then a tool-using subagent."""

    async def first(state: State, config) -> dict[str, Any]:
        model = GenericFakeChatModel(messages=iter([AIMessage(content="hi")]))
        response = await model.ainvoke(
            [SystemMessage("be brief"), HumanMessage("q")], config
        )
        return {"out": response.content}

    async def second(state: State, config) -> dict[str, Any]:
        if fail_in_second:
            raise ValueError("second failed")
        model = ToolCallingFakeModel(
            messages=iter(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"name": "add", "args": {"a": 1, "b": 2}, "id": "c1"}
                        ],
                    ),
                    AIMessage(content="3"),
                ]
            )
        )
        agent = create_agent(model=model, tools=[add])
        result = await agent.ainvoke({"messages": [HumanMessage("add")]}, config)
        return {"out": result["messages"][-1].content}

    graph = StateGraph(State)
    graph.add_node("first", first)
    graph.add_node("second", second)
    graph.add_edge(START, "first")
    graph.add_edge("first", "second")
    graph.add_edge("second", END)
    return graph.compile()


async def run_graph(handler: PrefactorCallbackHandler, **kwargs) -> dict[str, Any]:
    graph = build_graph(**kwargs)
    return await graph.ainvoke(
        {"messages": [HumanMessage("plan")], "out": ""},
        config={"callbacks": [handler]},
    )


def spans_named(instance: RecordingInstance, schema_name: str) -> list[dict]:
    return [s for s in instance.spans if s["schema_name"] == schema_name]


class TestSpanTree:
    """The handler records graph, node, LLM and tool spans as a tree."""

    async def test_records_spans_in_order(self):
        instance = RecordingInstance()

        await run_graph(PrefactorCallbackHandler(instance=instance))

        assert [s["schema_name"] for s in instance.spans] == [
            "langchain:agent",
            "langchain:node",
            "langchain:llm",
            "langchain:node",
            "langchain:llm",
            "langchain:tool",
            "langchain:llm",
        ]

    async def test_links_children_to_nearest_span(self):
        instance = RecordingInstance()

        await run_graph(PrefactorCallbackHandler(instance=instance))

        agent, first, llm_1, second, llm_2, tool_span, llm_3 = instance.spans
        assert agent["parent_span_id"] is None
        assert first["parent_span_id"] == agent["id"]
        assert second["parent_span_id"] == agent["id"]
        assert llm_1["parent_span_id"] == first["id"]
        assert llm_2["parent_span_id"] == second["id"]
        assert tool_span["parent_span_id"] == second["id"]
        assert llm_3["parent_span_id"] == second["id"]

    async def test_finishes_every_span(self):
        instance = RecordingInstance()

        await run_graph(PrefactorCallbackHandler(instance=instance))

        assert all(s["status"] == "complete" for s in instance.spans)
        assert all(s["exited"] for s in instance.spans)


class TestPayloads:
    """Span payloads match the middleware's payload shapes."""

    async def test_agent_span_payloads(self):
        instance = RecordingInstance()

        await run_graph(PrefactorCallbackHandler(instance=instance))

        agent = spans_named(instance, "langchain:agent")[0]
        assert agent["params"] == {
            "inputs": {
                "messages": [{"role": "human", "content": "plan"}],
                "out": "",
            },
            "agent_name": "LangGraph",
        }
        assert agent["result"] == {
            "outputs": {
                "messages": [{"role": "human", "content": "plan"}],
                "out": "3",
            },
        }

    async def test_node_span_payloads(self):
        instance = RecordingInstance()

        await run_graph(PrefactorCallbackHandler(instance=instance))

        first, second = spans_named(instance, "langchain:node")
        assert first["params"] == {"node": "first", "step": 1}
        assert first["result"] == {"status": "completed", "updated_keys": ["out"]}
        assert second["params"] == {"node": "second", "step": 2}

    async def test_llm_span_payloads(self):
        instance = RecordingInstance()

        await run_graph(PrefactorCallbackHandler(instance=instance))

        llm = spans_named(instance, "langchain:llm")[0]
        assert llm["params"] == {
            "inputs": {
                "messages": [{"role": "human", "content": "q"}],
                "system": "be brief",
            },
        }
        assert llm["result"] == {
            "outputs": {"messages": [{"role": "ai", "content": "hi"}]},
        }

    async def test_tool_span_payloads(self):
        instance = RecordingInstance()

        await run_graph(PrefactorCallbackHandler(instance=instance))

        tool_span = spans_named(instance, "langchain:tool")[0]
        assert tool_span["params"] == {
            "tool_name": "add",
            "inputs": {"tool_name": "add", "arguments": {"a": 1, "b": 2}},
        }
        assert tool_span["result"] == {"outputs": {"output": "3"}}

    async def test_uses_tool_specific_span_type(self):
        instance = RecordingInstance()
        handler = PrefactorCallbackHandler(
            instance=instance,
            tool_span_types={"add": "langchain:tool:add"},
        )

        await run_graph(handler)

        tool_span = spans_named(instance, "langchain:tool:add")[0]
        assert tool_span["params"] == {
            "tool_name": "add",
            "inputs": {"a": 1, "b": 2},
        }


class TestFailures:
    """Failures finish spans as failed and never hide the original error."""

    async def test_failing_node_fails_node_and_agent_spans(self):
        instance = RecordingInstance()

        with pytest.raises(ValueError, match="second failed"):
            await run_graph(
                PrefactorCallbackHandler(instance=instance), fail_in_second=True
            )

        second = spans_named(instance, "langchain:node")[1]
        agent = spans_named(instance, "langchain:agent")[0]
        assert second["status"] == "failed"
        assert second["result"]["error"]["error_type"] == "ValueError"
        assert agent["status"] == "failed"
        assert agent["result"]["error"]["message"] == "second failed"

    async def test_span_errors_are_logged_and_do_not_stop_the_graph(self, caplog):
        instance = FailingStartInstance()

        with caplog.at_level(logging.ERROR, logger="prefactor_langchain"):
            result = await run_graph(PrefactorCallbackHandler(instance=instance))

        assert result["out"] == "3"
        assert "span start failed" in caplog.text

    async def test_terminated_instance_stops_the_graph(self):
        event = asyncio.Event()
        event.set()
        monitor = SimpleNamespace(
            get_termination_event=lambda: event,
            termination_reason="policy violation",
        )
        instance = RecordingInstance(
            client=SimpleNamespace(_termination_monitor=monitor)
        )

        with pytest.raises(PrefactorTerminatedError, match="policy violation"):
            await run_graph(PrefactorCallbackHandler(instance=instance))
