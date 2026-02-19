"""
E2E example for prefactor-core.

Demonstrates:
  - SchemaRegistry with multiple span types
  - Hierarchical spans (root → child → grandchild)
  - Sibling spans
  - Explicit span.start(payload) lifecycle
  - Status-based finish: span.complete(result) / span.fail(result) / span.cancel()
  - Manual parent_span_id override

Span lifecycle:
  1. Enter the context manager — span is *prepared* locally (no HTTP yet)
  2. ``await span.start(payload)`` — POSTs the span to the API with params
  3. Do work
  4. ``await span.complete(result)`` (or .fail() / .cancel()) — finishes span

  If start() / complete() are omitted the context manager handles them
  automatically on exit, so the API is fully opt-in.

Run via mise (env vars set automatically):
    mise exec -- python packages/core/examples/agent_e2e.py

Or manually:
    PREFACTOR_API_URL=https://api.prefactor.ai \\
    PREFACTOR_API_TOKEN=your-token \\
    PREFACTOR_AGENT_ID=your-agent-id \\
    python packages/core/examples/agent_e2e.py
"""

import asyncio
import os

from prefactor_core import PrefactorCoreClient, PrefactorCoreConfig, SchemaRegistry
from prefactor_http.config import HttpClientConfig

# ---------------------------------------------------------------------------
# Schema registry — register all span types up front
# ---------------------------------------------------------------------------

registry = SchemaRegistry()

registry.register_type(
    name="agent:run",
    params_schema={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "The high-level task description",
            },
        },
        "required": ["task"],
    },
    result_schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "Final summary produced by the agent",
            },
        },
        "required": ["summary"],
    },
    title="Agent Run",
    description="Top-level agent execution span",
    template="task: {{task}} → {{summary}}",
)

registry.register_type(
    name="agent:llm_call",
    params_schema={
        "type": "object",
        "properties": {
            "model": {"type": "string", "description": "Model identifier"},
            "prompt": {"type": "string", "description": "Input prompt"},
        },
        "required": ["model", "prompt"],
    },
    result_schema={
        "type": "object",
        "properties": {
            "response": {"type": "string", "description": "Model response text"},
            "tokens": {"type": "integer", "description": "Tokens consumed"},
        },
        "required": ["response", "tokens"],
    },
    title="LLM Call",
    description="A single invocation of a language model",
    template="{{model}}: {{prompt}} → {{response}} ({{tokens}} tokens)",
)

registry.register_type(
    name="agent:tool_call",
    params_schema={
        "type": "object",
        "properties": {
            "tool_name": {"type": "string", "description": "Name of the tool"},
            "input": {"type": "string", "description": "Tool input"},
        },
        "required": ["tool_name", "input"],
    },
    result_schema={
        "type": "object",
        "properties": {
            "output": {"type": "string", "description": "Tool output"},
            "success": {"type": "boolean", "description": "Whether the tool succeeded"},
        },
        "required": ["output", "success"],
    },
    title="Tool Call",
    description="A tool invocation triggered by an LLM response",
    template="{{tool_name}}({{input}}) → {{output}}",
)

registry.register_type(
    name="agent:retrieval",
    params_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Retrieval query"},
        },
        "required": ["query"],
    },
    result_schema={
        "type": "object",
        "properties": {
            "documents": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Retrieved document snippets",
            },
            "count": {
                "type": "integer",
                "description": "Number of documents retrieved",
            },
        },
        "required": ["documents", "count"],
    },
    title="Retrieval",
    description="RAG retrieval step",
    template="query: {{query}} → {{count}} docs",
)


# ---------------------------------------------------------------------------
# Simulated async helpers
# ---------------------------------------------------------------------------


async def simulate_llm(model: str, prompt: str) -> str:
    """Simulate an LLM call with a small async delay."""
    await asyncio.sleep(0.05)
    return f"[{model}] response to: {prompt}"


async def simulate_tool(name: str, input_text: str) -> str:
    """Simulate a tool execution with a small async delay."""
    await asyncio.sleep(0.02)
    return f"[{name}] result for: {input_text}"


async def simulate_failing_tool(name: str, input_text: str) -> None:
    """Simulate a tool that raises an exception."""
    await asyncio.sleep(0.01)
    raise RuntimeError(f"[{name}] timed out processing: {input_text}")


async def simulate_retrieval(query: str) -> list[str]:
    """Simulate a retrieval step with a small async delay."""
    await asyncio.sleep(0.03)
    return [
        f"Document 1 about '{query}'",
        f"Document 2 about '{query}'",
        f"Document 3 about '{query}'",
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    agent_id = os.environ["PREFACTOR_AGENT_ID"]

    config = PrefactorCoreConfig(
        http_config=HttpClientConfig(
            api_url=os.environ["PREFACTOR_API_URL"],
            api_token=os.environ["PREFACTOR_API_TOKEN"],
        ),
        schema_registry=registry,
    )

    async with PrefactorCoreClient(config) as client:
        # Register the agent instance — schema version derived from registry.
        instance = await client.create_agent_instance(
            agent_id=agent_id,
            agent_version={"name": "Example Agent", "external_identifier": "v8.0.0"},
        )

        await instance.start()

        # ------------------------------------------------------------------
        # Root span — represents the entire agent run
        # ------------------------------------------------------------------
        async with instance.span("agent:run") as root:
            await root.start({"task": "summarise recent news"})

            # --------------------------------------------------------------
            # 1. Planning LLM call (child of root — parent auto-detected from
            #    SpanContextStack)
            # --------------------------------------------------------------
            async with instance.span("agent:llm_call") as plan_span:
                await plan_span.start(
                    {"model": "claude-3-5-sonnet", "prompt": "Plan the task"}
                )

                plan_result = await simulate_llm("claude-3-5-sonnet", "Plan the task")

                # ----------------------------------------------------------
                # 1a. Tool call — grandchild of root, child of plan_span.
                #     Parent auto-detected from the stack.
                # ----------------------------------------------------------
                async with instance.span("agent:tool_call") as tool_span:
                    await tool_span.start(
                        {"tool_name": "web_search", "input": "recent news"}
                    )
                    tool_result = await simulate_tool("web_search", "recent news")
                    await tool_span.complete({"output": tool_result, "success": True})

                # ----------------------------------------------------------
                # 1b. A second tool call that fails — demonstrates span.fail()
                # ----------------------------------------------------------
                async with instance.span("agent:tool_call") as bad_tool_span:
                    await bad_tool_span.start(
                        {"tool_name": "database_lookup", "input": "recent news"}
                    )
                    try:
                        await simulate_failing_tool("database_lookup", "recent news")
                    except RuntimeError as exc:
                        await bad_tool_span.fail({"output": str(exc), "success": False})

                await plan_span.complete({"response": plan_result, "tokens": 150})

            # --------------------------------------------------------------
            # 2. Knowledge retrieval — child of root.
            #    parent_span_id is passed explicitly here to demonstrate
            #    manual wiring (equivalent to the auto-detected behaviour).
            # --------------------------------------------------------------
            async with client.span(
                instance_id=instance.id,
                schema_name="agent:retrieval",
                parent_span_id=root.id,  # explicit override
            ) as ret_span:
                await ret_span.start({"query": "recent news"})
                docs = await simulate_retrieval("recent news")
                await ret_span.complete({"documents": docs, "count": len(docs)})

            # --------------------------------------------------------------
            # 3. Low-priority secondary retrieval — cancelled because the
            #    primary retrieval already returned enough context.
            #    Demonstrates span.cancel(): the span is never started, so
            #    cancel() posts it directly as "cancelled" in one shot.
            # --------------------------------------------------------------
            sufficient_context = len(docs) >= 3
            async with instance.span("agent:retrieval") as extra_ret_span:
                if sufficient_context:
                    await extra_ret_span.cancel()
                else:
                    await extra_ret_span.start({"query": "background context"})
                    extra_docs = await simulate_retrieval("background context")
                    await extra_ret_span.complete(
                        {"documents": extra_docs, "count": len(extra_docs)}
                    )

            # --------------------------------------------------------------
            # 4. Final synthesis LLM call (child of root — auto-detected)
            # --------------------------------------------------------------
            async with instance.span("agent:llm_call") as final_span:
                await final_span.start(
                    {"model": "claude-3-5-sonnet", "prompt": "Summarise"}
                )
                summary = await simulate_llm("claude-3-5-sonnet", "Summarise")
                await final_span.complete({"response": summary, "tokens": 200})

            await root.complete({"summary": summary})

        await instance.finish()

    print("Done — all spans submitted to Prefactor.")


if __name__ == "__main__":
    asyncio.run(main())
