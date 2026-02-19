"""
E2E example for prefactor-core.

Demonstrates:
  - SchemaRegistry with multiple span types
  - Hierarchical spans (root → child → grandchild)
  - Parallel sibling spans
  - set_result() usage
  - Manual parent_span_id override

Current vs. desired lifecycle note:
  The current API uses the span context manager for creation and
  set_result() + automatic context-exit finish for completion.
  A future API may expose explicit span.start(payload) to trigger the HTTP
  POST separately, and status-based methods (span.complete(), span.fail(),
  span.cancel()) instead of a generic finish. See TODO comments below.

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
        # Register the agent instance — schema version is derived automatically
        # from the registry attached to the config.
        instance = await client.create_agent_instance(
            agent_id=agent_id,
            agent_version={"name": "Example Agent", "external_identifier": "v1.0.0"},
        )

        await instance.start()

        # ------------------------------------------------------------------
        # Root span — represents the entire agent run
        # ------------------------------------------------------------------
        # TODO: future API — span.start(payload) triggers HTTP POST here
        async with instance.span(
            "agent:run",
            payload={"task": "summarise recent news"},
        ) as root:
            # --------------------------------------------------------------
            # 1. Planning LLM call (child of root — parent auto-detected from
            #    SpanContextStack)
            # --------------------------------------------------------------
            # TODO: future API — span.start(payload) triggers HTTP POST here
            async with instance.span(
                "agent:llm_call",
                payload={"model": "claude-3-5-sonnet", "prompt": "Plan the task"},
            ) as plan_span:
                plan_result = await simulate_llm("claude-3-5-sonnet", "Plan the task")

                # ----------------------------------------------------------
                # 1a. Tool call — grandchild of root, child of plan_span.
                #     Parent is auto-detected from the stack.
                # ----------------------------------------------------------
                # TODO: future API — span.start(payload) triggers HTTP POST here
                async with instance.span(
                    "agent:tool_call",
                    payload={"tool_name": "web_search", "input": "recent news"},
                ) as tool_span:
                    tool_result = await simulate_tool("web_search", "recent news")
                    # TODO: future API — tool_span.complete(result) / .fail(result)
                    tool_span.set_result({"output": tool_result, "success": True})

                # TODO: future API — plan_span.complete(result) / .fail(result)
                plan_span.set_result({"response": plan_result, "tokens": 150})

            # --------------------------------------------------------------
            # 2. Knowledge retrieval — child of root.
            #    parent_span_id is passed explicitly here to demonstrate
            #    manual wiring (equivalent to the auto-detected behaviour).
            # --------------------------------------------------------------
            # TODO: future API — span.start(payload) triggers HTTP POST here
            async with client.span(
                instance_id=instance.id,
                schema_name="agent:retrieval",
                parent_span_id=root.id,  # explicit override — same as auto-detected
                payload={"query": "recent news"},
            ) as ret_span:
                docs = await simulate_retrieval("recent news")
                # TODO: future API — ret_span.complete(result) / .fail(result)
                ret_span.set_result({"documents": docs, "count": len(docs)})

            # --------------------------------------------------------------
            # 3. Final synthesis LLM call (child of root — auto-detected)
            # --------------------------------------------------------------
            # TODO: future API — span.start(payload) triggers HTTP POST here
            async with instance.span(
                "agent:llm_call",
                payload={"model": "claude-3-5-sonnet", "prompt": "Summarise"},
            ) as final_span:
                summary = await simulate_llm("claude-3-5-sonnet", "Summarise")
                # TODO: future API — final_span.complete(result) / .fail(result)
                final_span.set_result({"response": summary, "tokens": 200})

            # TODO: future API — root.complete(result) / .fail(result)
            root.set_result({"summary": summary})

        await instance.finish()

    print("Done — all spans submitted to Prefactor.")


if __name__ == "__main__":
    asyncio.run(main())
