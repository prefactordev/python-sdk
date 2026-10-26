"""Plan a road trip between two places, traced in Prefactor.

Usage:
    python main.py "Plan a 4-day road trip from Melbourne to Adelaide."

Environment:
    TOGETHER_API_KEY     Together AI API key
    TOGETHER_MODEL       Together AI model (optional)
    PREFACTOR_API_URL    Prefactor API URL
    PREFACTOR_API_TOKEN  Prefactor API token
    PREFACTOR_AGENT_ID   Prefactor agent ID (omit for deployment-scoped tokens)
    PREFACTOR_ENVIRONMENT_ID  Prefactor environment ID (needed for an agent
                         with no deployments yet)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from typing import Literal

from graph import TripState, build_graph
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from prefactor_core import PrefactorCoreConfig, SchemaRegistry
from prefactor_http.config import HttpClientConfig
from prefactor_langchain import PrefactorCallbackHandler, register_langchain_schemas
from pydantic import SecretStr

TOGETHER_API_URL = "https://api.together.xyz/v1"
DEFAULT_MODEL = "moonshotai/Kimi-K3"
AGENT_NAME = "Trip planner"

Purpose = Literal["live", "smoke_test", "eval"]


def build_registry() -> tuple[SchemaRegistry, dict[str, str]]:
    """Register the span schemas the trip planner sends."""
    registry = SchemaRegistry()
    tool_span_types = register_langchain_schemas(registry)
    return registry, tool_span_types


def schema_version_id(registry: SchemaRegistry) -> str:
    """Derive a stable schema version ID from the registered schemas."""
    schemas = registry.to_agent_schema_version("trip-planner")
    digest = hashlib.sha1(json.dumps(schemas, sort_keys=True).encode()).hexdigest()[:8]
    return f"trip-planner-{digest}"


async def run_trip(request: str, purpose: Purpose = "live") -> TripState:
    """Run the trip planner once as a Prefactor agent instance.

    Args:
        request: The user's trip request in plain language.
        purpose: Why this run happened, recorded on the agent instance.

    Returns:
        The final graph state.
    """
    registry, tool_span_types = build_registry()
    version_id = schema_version_id(registry)

    client = PrefactorCallbackHandler.create_client(
        PrefactorCoreConfig(
            http_config=HttpClientConfig(
                api_url=os.environ["PREFACTOR_API_URL"],
                api_token=os.environ["PREFACTOR_API_TOKEN"],
            ),
            schema_registry=registry,
        )
    )
    await client.initialize()

    try:
        instance = await client.create_agent_instance(
            agent_id=os.environ.get("PREFACTOR_AGENT_ID"),
            environment_id=os.environ.get("PREFACTOR_ENVIRONMENT_ID"),
            agent_version={"name": AGENT_NAME, "external_identifier": version_id},
            external_schema_version_id=version_id,
            purpose=purpose,
        )
        await instance.start()

        # Setup failures, such as a missing API key, also fail the instance.
        try:
            handler = PrefactorCallbackHandler(
                instance=instance, tool_span_types=tool_span_types
            )
            model = ChatOpenAI(
                model=os.environ.get("TOGETHER_MODEL", DEFAULT_MODEL),
                base_url=TOGETHER_API_URL,
                api_key=SecretStr(os.environ["TOGETHER_API_KEY"]),
                max_completion_tokens=8000,
            )
            graph = build_graph(model)
            state = await graph.ainvoke(
                {"messages": [HumanMessage(request)]},
                config={"callbacks": [handler]},
            )
        except BaseException:
            await instance.finish("failed")
            raise
        await instance.finish("complete")
        return state
    finally:
        await client.close()


def main() -> None:
    """Parse the command line and run one trip."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("request", help="The trip request, in plain language")
    args = parser.parse_args()

    state = asyncio.run(run_trip(args.request))
    print(f"Trip plan written to {state['output_path']}")


if __name__ == "__main__":
    main()
