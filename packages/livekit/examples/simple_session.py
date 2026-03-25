"""
LiveKit example for prefactor-livekit.

This example has two modes:

1. ``smoke``: emits representative public LiveKit session events into
   ``PrefactorLiveKitSession`` without requiring STT/TTS credentials or a room.
   Use this to validate that Prefactor tracing is wired correctly.
2. ``live``: starts a real ``AgentSession`` and runs one text turn with a
   model-backed agent. Use this when you want to see the wrapper around an
   actual LiveKit session.

Examples:
    uv run python packages/livekit/examples/simple_session.py --mode smoke

    uv run python packages/livekit/examples/simple_session.py \
        --mode live \
        --model anthropic/claude-sonnet-4-5-20250929
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time
import warnings
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from livekit.agents import Agent, AgentSession, function_tool
from prefactor_livekit import LiveKitToolSchemaConfig, PrefactorLiveKitSession

DEFAULT_MODEL = os.getenv("LIVEKIT_LLM_MODEL", "anthropic/claude-sonnet-4-5-20250929")


class WeatherAssistant(Agent):
    """Simple deterministic agent used by the live example."""

    def __init__(self, model: str) -> None:
        super().__init__(
            instructions=(
                "You are a concise voice assistant. Use the weather tool when the "
                "user asks about forecast details, then respond in one or two "
                "sentences."
            ),
            llm=model,
        )

    @function_tool
    async def lookup_weather(self, city: str, unit: str = "celsius") -> str:
        """Return a deterministic weather summary for a city."""
        forecasts = {
            "melbourne": (
                "Melbourne is 21 degrees with scattered cloud and a light wind."
            ),
            "sydney": "Sydney is 25 degrees and sunny with a sea breeze.",
            "brisbane": "Brisbane is 27 degrees with humid afternoon showers.",
        }
        forecast = forecasts.get(
            city.strip().lower(),
            f"{city} is 22 degrees with mild conditions.",
        )
        if unit.lower() == "fahrenheit":
            forecast += " Equivalent to roughly 72 Fahrenheit."
        return forecast


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for the example."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("smoke", "live"),
        default="smoke",
        help="Run a local smoke test or a model-backed text turn.",
    )
    parser.add_argument(
        "--agent-id",
        default=os.getenv("PREFACTOR_AGENT_ID", "livekit-example"),
        help="Prefactor agent ID used when registering the example run.",
    )
    parser.add_argument(
        "--agent-name",
        default="LiveKit Example",
        help="Human-readable agent name shown in Prefactor.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Model identifier for --mode live.",
    )
    return parser


def require_env(name: str) -> str:
    """Return a required environment variable or raise a clear error."""
    value = os.getenv(name)
    if value:
        return value
    raise ValueError(f"{name} environment variable is required")


def build_tracer(agent_id: str, agent_name: str) -> PrefactorLiveKitSession:
    """Create a configured Prefactor LiveKit tracer."""
    return PrefactorLiveKitSession.from_config(
        api_url=require_env("PREFACTOR_API_URL"),
        api_token=require_env("PREFACTOR_API_TOKEN"),
        agent_id=agent_id,
        agent_name=agent_name,
        tool_schemas={
            "lookup_weather": LiveKitToolSchemaConfig(
                span_type="weather_lookup",
                input_schema={
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "unit": {"type": "string"},
                    },
                    "required": ["city"],
                },
            ),
        },
    )


@contextmanager
def suppress_livekit_deprecation_logs() -> Any:
    """Temporarily silence LiveKit's metrics_collected deprecation log."""
    logger = logging.getLogger("livekit.agents")
    previous_level = logger.level
    if previous_level == logging.NOTSET or previous_level < logging.ERROR:
        logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(previous_level)


def make_llm_metrics(model: str, now: float) -> Any:
    """Create a metrics payload compatible with the wrapper's event adapter."""
    payload = {
        "type": "llm_metrics",
        "label": "example",
        "request_id": "req-example-1",
        "timestamp": now,
        "metadata": {
            "model_name": model,
            "model_provider": model.split("/", 1)[0],
        },
        "input_tokens": 42,
        "output_tokens": 18,
    }
    return SimpleNamespace(
        type="llm_metrics",
        label="example",
        request_id="req-example-1",
        timestamp=now,
        metadata=SimpleNamespace(
            model_name=payload["metadata"]["model_name"],
            model_provider=payload["metadata"]["model_provider"],
        ),
        model_dump=lambda: payload,
    )


def extract_text_content(item: Any) -> str:
    """Extract plain text from a LiveKit message item."""
    content = getattr(item, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                fragments.append(str(part.get("text", "")))
            elif hasattr(part, "text"):
                fragments.append(str(part.text))
        return " ".join(fragment for fragment in fragments if fragment).strip()
    return ""


async def run_smoke_demo(
    tracer: PrefactorLiveKitSession,
    *,
    model: str,
) -> tuple[str, float]:
    """Emit representative LiveKit events without external model providers."""
    session = AgentSession()
    with suppress_livekit_deprecation_logs():
        instance = await tracer.attach(session)
    now = time.time()

    session.emit(
        "agent_state_changed",
        SimpleNamespace(
            old_state="initializing",
            new_state="listening",
            created_at=now,
        ),
    )
    session.emit(
        "user_input_transcribed",
        SimpleNamespace(
            transcript="What's the weather in Melbourne, and say hello to Alex.",
            is_final=True,
            speaker_id="caller-1",
            language="en",
            created_at=now + 0.1,
        ),
    )
    session.emit(
        "speech_created",
        SimpleNamespace(
            source="generate_reply",
            user_initiated=True,
            created_at=now + 0.2,
        ),
    )
    session.emit(
        "function_tools_executed",
        SimpleNamespace(
            zipped=lambda: [
                (
                    SimpleNamespace(
                        name="lookup_weather",
                        call_id="call-weather-1",
                        group_id="group-weather-1",
                        arguments='{"city":"Melbourne","unit":"celsius"}',
                        created_at=now + 0.3,
                        extra={"mode": "smoke"},
                    ),
                    SimpleNamespace(
                        name="lookup_weather",
                        output=(
                            "Melbourne is 21 degrees with scattered cloud and a "
                            "light wind."
                        ),
                        is_error=False,
                    ),
                )
            ]
        ),
    )
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="metrics_collected is deprecated.*",
        )
        session.emit(
            "metrics_collected",
            SimpleNamespace(metrics=make_llm_metrics(model=model, now=now + 0.4)),
        )
    session.emit(
        "conversation_item_added",
        SimpleNamespace(
            created_at=now + 0.5,
            item=SimpleNamespace(
                type="message",
                id="assistant-message-1",
                role="assistant",
                content=[
                    {
                        "type": "text",
                        "text": (
                            "Melbourne is 21 degrees with scattered cloud. Hello Alex."
                        ),
                    }
                ],
            ),
        ),
    )
    session.emit(
        "session_usage_updated",
        SimpleNamespace(
            usage=SimpleNamespace(
                model_usage=[
                    SimpleNamespace(
                        model_name=model,
                        prompt_tokens=42,
                        completion_tokens=18,
                        total_tokens=60,
                    )
                ]
            )
        ),
    )

    await tracer.close()
    return instance.id, now


async def run_live_demo(
    tracer: PrefactorLiveKitSession,
    *,
    model: str,
) -> tuple[str, str | None, float]:
    """Run a single model-backed text turn."""
    session = AgentSession()
    agent = WeatherAssistant(model=model)
    instance = await tracer.ensure_initialized()
    started_at = time.time()

    try:
        with suppress_livekit_deprecation_logs():
            await tracer.start(
                session=session,
                agent=agent,
                record=False,
            )
        run_result = session.run(
            user_input="What's the weather in Melbourne, and greet Alex by name?",
        )
        await run_result

        assistant_text = None
        for event in reversed(run_result.events):
            if getattr(event, "type", None) != "message":
                continue
            item = getattr(event, "item", None)
            if getattr(item, "role", None) == "assistant":
                assistant_text = extract_text_content(item)
                break

        await session.aclose()
        return instance.id, assistant_text, started_at
    finally:
        await tracer.close()


def print_cli_hints(instance_id: str, started_at: float) -> None:
    """Print follow-up Prefactor CLI commands for the created run."""
    start_time = datetime.fromtimestamp(started_at, tz=timezone.utc) - timedelta(
        seconds=30
    )
    end_time = datetime.now(tz=timezone.utc) + timedelta(seconds=30)

    print(f"INSTANCE_ID={instance_id}")
    print("Inspect the run with:")
    print(f"  prefactor agent_instances retrieve {instance_id}")
    print(
        "  prefactor agent_spans list "
        f"--agent_instance_id {instance_id} "
        f"--start_time {start_time.isoformat().replace('+00:00', 'Z')} "
        f"--end_time {end_time.isoformat().replace('+00:00', 'Z')} "
        "--include_summaries"
    )


async def main() -> None:
    args = build_parser().parse_args()
    tracer = build_tracer(agent_id=args.agent_id, agent_name=args.agent_name)

    if args.mode == "smoke":
        print("Running a local LiveKit smoke test through Prefactor.")
        instance_id, started_at = await run_smoke_demo(tracer, model=args.model)
        print_cli_hints(instance_id, started_at)
        return

    print(f"Running a model-backed LiveKit session with {args.model}.")
    instance_id, assistant_text, started_at = await run_live_demo(
        tracer,
        model=args.model,
    )
    if assistant_text:
        print(f"Assistant reply: {assistant_text}")
    print_cli_hints(instance_id, started_at)


if __name__ == "__main__":
    asyncio.run(main())
