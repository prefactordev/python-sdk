"""Example of using the HTTP transport to send spans to Prefactor backend."""

import os
import sys

# Add parent directory to path for local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import prefactor_sdk
from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.prompts import ChatPromptTemplate
from langchain.tools import tool


# Define a simple tool
@tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers together."""
    return a * b


@tool
def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


def main():
    """Run example with HTTP transport."""

    # Option 1: Configure via environment variables
    # os.environ["PREFACTOR_TRANSPORT"] = "http"
    # os.environ["PREFACTOR_API_URL"] = "https://p2demo.prefactor.dev"
    # os.environ["PREFACTOR_API_TOKEN"] = "your-token-here"
    # middleware = prefactor_sdk.init()

    # Option 2: Configure via code
    config = prefactor_sdk.Config(
        transport_type="http",
        api_url=os.getenv("PREFACTOR_API_URL", "https://p2demo.prefactor.dev"),
        api_token=os.getenv("PREFACTOR_API_TOKEN", "your-token-here"),
        agent_id=os.getenv("PREFACTOR_AGENT_ID", "example-agent"),
        agent_version=os.getenv("PREFACTOR_AGENT_VERSION", "1.0.0"),
    )

    # Initialize Prefactor SDK with HTTP transport
    middleware = prefactor_sdk.init(config)

    print(f"✓ Prefactor SDK initialized with {config.transport_type} transport")
    print(f"  API URL: {config.http_config.api_url if config.http_config else 'N/A'}")
    print(f"  Agent ID: {config.http_config.agent_id if config.http_config else 'N/A'}")
    print()

    # Create LangChain agent with tools
    tools = [multiply, add]

    # Create prompt
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a helpful assistant that can do math."),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}"),
        ]
    )

    # Create model
    llm = ChatAnthropic(
        model="claude-3-5-sonnet-20241022",
        temperature=0,
    )

    # Create agent
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
    )

    # Run agent (this will be traced and sent to Prefactor backend)
    print("Running agent...")
    print("-" * 60)

    result = agent_executor.invoke(
        {"input": "What is 15 multiplied by 7, and then add 10 to the result?"}
    )

    print("-" * 60)
    print(f"\nResult: {result['output']}")
    print()
    print("✓ Agent execution complete. Spans sent to Prefactor backend.")
    print("  Check your Prefactor dashboard to see the traces!")


if __name__ == "__main__":
    main()
