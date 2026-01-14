"""
Simple Anthropic Agent Example for Prefactor SDK

This example demonstrates end-to-end tracing of a LangChain agent using
Anthropic's Claude model with the Prefactor SDK. It shows how the SDK
captures LLM calls, tool executions, and chain operations.
"""

import os
from datetime import datetime

from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool

import prefactor_sdk


# Define simple tools for the agent
@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        result = eval(expression)  # Simple for demo purposes
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    """Run the simple agent example."""
    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is required. "
            "Please set it before running this example."
        )

    print("=" * 80)
    print("Prefactor SDK - Anthropic Agent Example")
    print("=" * 80)
    print()

    print("Configure Prefactor SDK...")
    config = prefactor_sdk.Config(
        transport_type="http",
    )

    # Initialize Prefactor SDK (Middleware API)
    print("Initializing Prefactor SDK...")
    # middleware = prefactor_sdk.init()
    middleware = prefactor_sdk.init(config)
    print("✓ Prefactor middleware initialized")
    print()

    # Create Claude model
    print("Creating ChatAnthropic model (claude-haiku-4-5-20251001)...")
    llm = ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        temperature=0,
    )
    print("✓ Model initialized")
    print()

    # Create tools list
    tools = [calculator, get_current_time]

    # Create agent using the create_agent API with middleware
    print("Creating agent with create_agent API and Prefactor middleware...")
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt="You are a helpful assistant. Use the available tools to answer questions.",
        middleware=[middleware],
    )
    print("✓ Agent created with Prefactor tracing")
    print()

    # Run test interactions
    print("=" * 80)
    print("Example 1: Getting Current Time")
    print("=" * 80)
    print()

    try:
        result = agent.invoke(
            {"messages": [("user", "What is the current date and time?")]},
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
        result = agent.invoke(
            {"messages": [("user", "What is 42 multiplied by 17?")]},
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
    print("The trace spans have been emitted to stdout as newline-delimited JSON.")
    print("You should see spans for:")
    print("  - AGENT: Root agent execution span")
    print("  - LLM: ChatAnthropic API calls with token usage")
    print("  - TOOL: calculator and get_current_time executions")
    print()
    print("Check parent_span_id fields to see the span hierarchy.")
    print()
    print("Note: This example now uses the middleware API (LangChain 1.0+).")
    print("For legacy callback usage, use prefactor_sdk.init_callback() instead.")
    print()


if __name__ == "__main__":
    main()
