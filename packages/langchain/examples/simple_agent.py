"""
Simple Anthropic Agent Example for Prefactor SDK

This example demonstrates end-to-end tracing of a LangChain agent using
Anthropic's Claude model with the Prefactor SDK. It shows how the SDK
captures LLM calls, tool executions, and agent operations.

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
from prefactor_langchain import PrefactorMiddleware


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def run_agent(middleware: PrefactorMiddleware, agent, messages: list) -> dict:
    """Run agent in a thread so the event loop stays free for tracing tasks."""
    import functools

    await middleware._ensure_initialized()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, functools.partial(agent.invoke, {"messages": messages})
    )


async def main_async():
    """Async main function for proper shutdown handling."""
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
    print("Prefactor SDK - Anthropic Agent Example")
    print("=" * 80)
    print()

    print("Initializing Prefactor middleware...")
    middleware = PrefactorMiddleware.from_config(
        api_url=api_url,
        api_token=api_token,
        agent_id=agent_id,
        agent_name="Anthropic Calculator Agent",
    )
    print(f"✓ Prefactor middleware initialized (Agent ID: {agent_id})")
    print()

    tools = [calculator, get_current_time]

    print("Creating agent with Prefactor tracing enabled...")
    agent = create_agent(
        model="claude-haiku-4-5-20251001",
        tools=tools,
        system_prompt="You are a helpful assistant."
        "Use the available tools to answer questions accurately.",
        middleware=[middleware],
    )
    print("✓ Agent created with tracing enabled")
    print()

    print("=" * 80)
    print("Example 1: Getting Current Time")
    print("=" * 80)
    print()

    try:
        result = await run_agent(
            middleware,
            agent,
            [{"role": "user", "content": "What is the current date and time?"}],
        )
        print("\nAgent Response:")
        print(result["messages"][-1].content)
        print()
    except Exception as e:
        print(f"Error in Example 1: {e}")
        print()

    print("=" * 80)
    print("Example 2: Simple Calculation")
    print("=" * 80)
    print()

    try:
        result = await run_agent(
            middleware,
            agent,
            [{"role": "user", "content": "What is 42 multiplied by 17?"}],
        )
        print("\nAgent Response:")
        print(result["messages"][-1].content)
        print()
    except Exception as e:
        print(f"Error in Example 2: {e}")
        print()

    print("=" * 80)
    print("Example Complete!")
    print("=" * 80)
    print()
    print("Traces have been queued for Prefactor.")
    print("Flushing queue before shutdown...")
    print()

    print("Shutting down...")
    await middleware.close()
    print("✓ Complete")
    print()


def main():
    """Entry point that runs the async main."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
