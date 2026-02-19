"""
Simple Anthropic Agent Example for Prefactor SDK

This example demonstrates a LangChain agent embedded inside a broader agentic
workflow that is manually instrumented with prefactor-core spans.  The outer
workflow spans (input validation, post-processing) are created directly on the
shared AgentInstanceHandle, while the LangChain agent's internal LLM and tool
calls are traced automatically by PrefactorMiddleware.  This illustrates the
typical real-world pattern where a LangChain agent is one step inside a larger
pipeline.

Prerequisites:
    - ANTHROPIC_API_KEY environment variable set
    - PREFACTOR_API_URL environment variable set (or pass directly)
    - PREFACTOR_API_TOKEN environment variable set (or pass directly)
    - pip install prefactor-langchain langchain langchain-anthropic

Example:
    export ANTHROPIC_API_KEY=sk-ant-...
    export PREFACTOR_API_URL=https://api.prefactor.ai
    export PREFACTOR_API_TOKEN=your_token
    python simple_agent.py
"""

import asyncio
import os
from datetime import datetime

from langchain.agents import create_agent
from langchain_core.tools import tool
from prefactor_core import SchemaRegistry
from prefactor_langchain import PrefactorMiddleware

# ---------------------------------------------------------------------------
# LangChain tools
# ---------------------------------------------------------------------------


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        result = eval(expression)  # noqa: S307
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Outer workflow helpers (manually instrumented)
# ---------------------------------------------------------------------------


async def validate_input(instance, query: str) -> dict:
    """Validate and normalise the user query before passing it to the agent.

    Represented as an explicit 'workflow:validate_input' span so the
    validation step is visible in the trace alongside the langchain spans.
    """
    async with instance.span("workflow:validate_input") as ctx:
        await ctx.start({"query": query})
        await asyncio.sleep(0.01)  # simulate async validation logic
        normalised = query.strip()
        if not normalised:
            await ctx.fail({"error": "empty query"})
            raise ValueError("Query must not be empty")
        await ctx.complete({"normalised_query": normalised, "valid": True})
    return {"query": normalised}


async def post_process(instance, raw_response: str) -> str:
    """Apply post-processing to the agent's response.

    Represented as an explicit 'workflow:post_process' span so this step
    is visible alongside the auto-instrumented langchain spans.
    """
    async with instance.span("workflow:post_process") as ctx:
        await ctx.start({"raw_response": raw_response})
        await asyncio.sleep(0.01)  # simulate async formatting / filtering
        processed = raw_response.strip()
        await ctx.complete({"processed_response": processed})
    return processed


async def run_agent_step(
    middleware: PrefactorMiddleware, agent, messages: list
) -> dict:
    """Run the LangChain agent inside a 'workflow:agent_step' span.

    The middleware's auto-instrumentation creates langchain:llm and
    langchain:tool child spans automatically beneath this span.
    """
    import functools

    instance = await middleware._ensure_initialized()

    async with instance.span("workflow:agent_step") as ctx:
        await ctx.start({"message_count": len(messages)})
        # Tell the middleware which span to use as the parent for langchain:agent.
        # before_agent() runs in a worker thread where contextvars are not
        # inherited, so the parent must be wired explicitly before the executor.
        middleware.set_parent_span(ctx.id)
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None, functools.partial(agent.invoke, {"messages": messages})
            )
            await ctx.complete({"status": "ok"})
        except Exception as e:
            await ctx.fail({"error": str(e)})
            raise
    return result


# ---------------------------------------------------------------------------
# Top-level workflow runner
# ---------------------------------------------------------------------------


async def run_workflow(
    middleware: PrefactorMiddleware,
    agent,
    query: str,
    *,
    label: str,
) -> str:
    """Run the full workflow for a single query.

    Span hierarchy produced:
        workflow:run          ← outer span, wraps everything
          workflow:validate_input
          workflow:agent_step ← langchain auto-instrumentation fires here
            langchain:agent
              langchain:llm
              langchain:tool  (if the agent calls a tool)
          workflow:post_process
    """
    instance = await middleware._ensure_initialized()

    async with instance.span("workflow:run") as root:
        await root.start({"label": label, "query": query})
        try:
            validated = await validate_input(instance, query)
            result = await run_agent_step(
                middleware,
                agent,
                [{"role": "user", "content": validated["query"]}],
            )
            response = result["messages"][-1].content
            processed = await post_process(instance, response)
            await root.complete({"response": processed})
        except Exception as e:
            await root.fail({"error": str(e)})
            raise

    return processed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main_async():
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is required.\n"
            "Get your API key from: https://console.anthropic.com/"
        )

    api_url = os.getenv("PREFACTOR_API_URL", "https://api.prefactor.ai")
    api_token = os.getenv("PREFACTOR_API_TOKEN")
    if not api_token:
        raise ValueError(
            "PREFACTOR_API_TOKEN environment variable is required.\n"
            "Get your token from the Prefactor dashboard."
        )

    agent_id = os.getenv("PREFACTOR_AGENT_ID", "langchain-agent")

    print("=" * 80)
    print("Prefactor SDK - LangChain agent inside a manually-instrumented workflow")
    print("=" * 80)
    print()

    # Build a shared schema registry that includes both the custom workflow
    # span types and the standard langchain:* types.  The middleware's
    # from_config() derives a stable agent-version ID from the registry
    # contents, so adding workflow span types here is enough — no manual
    # instance creation needed.
    registry = SchemaRegistry()
    str_prop = {"type": "string"}
    registry.register_type(
        name="workflow:run",
        params_schema={
            "type": "object",
            "properties": {"label": str_prop, "query": str_prop},
        },
        result_schema={
            "type": "object",
            "properties": {"response": str_prop},
        },
        title="Workflow Run",
        description="Top-level workflow execution",
    )
    registry.register_type(
        name="workflow:validate_input",
        params_schema={
            "type": "object",
            "properties": {"query": str_prop},
        },
        result_schema={
            "type": "object",
            "properties": {
                "normalised_query": str_prop,
                "valid": {"type": "boolean"},
            },
        },
        title="Validate Input",
        description="Input validation and normalisation step",
    )
    registry.register_type(
        name="workflow:agent_step",
        params_schema={
            "type": "object",
            "properties": {"message_count": {"type": "integer"}},
        },
        result_schema={
            "type": "object",
            "properties": {"status": str_prop},
        },
        title="Agent Step",
        description="LangChain agent invocation step",
    )
    registry.register_type(
        name="workflow:post_process",
        params_schema={
            "type": "object",
            "properties": {"raw_response": str_prop},
        },
        result_schema={
            "type": "object",
            "properties": {"processed_response": str_prop},
        },
        title="Post-Process",
        description="Response post-processing step",
    )

    # from_config() owns the client and instance lifecycle.  It derives a
    # stable agent-version ID from the registry, so re-runs are idempotent.
    # After _ensure_initialized() the instance is available via _instance and
    # is shared between our manual workflow spans and the auto-instrumented
    # langchain spans.
    middleware = PrefactorMiddleware.from_config(
        api_url=api_url,
        api_token=api_token,
        agent_id=agent_id,
        agent_name="Anthropic Calculator Agent",
        schema_registry=registry,
    )

    tools = [calculator, get_current_time]

    print("Creating agent with Prefactor tracing enabled...")
    agent = create_agent(
        model="claude-haiku-4-5-20251001",
        tools=tools,
        system_prompt=(
            "You are a helpful assistant. "
            "Use the available tools to answer questions accurately."
        ),
        middleware=[middleware],
    )
    print("✓ Agent created with tracing enabled")
    print()

    examples = [
        ("Example 1: Getting Current Time", "What is the current date and time?"),
        ("Example 2: Simple Calculation", "What is 42 multiplied by 17?"),
    ]

    for label, query in examples:
        print("=" * 80)
        print(label)
        print("=" * 80)
        print()
        try:
            response = await run_workflow(middleware, agent, query, label=label)
            print("Agent Response:")
            print(response)
            print()
        except Exception as e:
            print(f"Error: {e}")
            print()

    print("=" * 80)
    print("Example Complete!")
    print("=" * 80)
    print()
    print("Flushing spans and shutting down...")
    await middleware.close()
    print("✓ Complete")
    print()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
