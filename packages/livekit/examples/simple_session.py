"""Minimal LiveKit example using prefactor-livekit."""

from __future__ import annotations

import asyncio
import os

from livekit.agents import Agent, AgentSession, inference
from prefactor_livekit import PrefactorLiveKitSession


class DemoAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions="You are a concise demo voice agent.")


async def main() -> None:
    session = AgentSession(
        llm=inference.LLM("openai/gpt-4.1-mini"),
        stt=inference.STT(model="deepgram/flux-general", language="en"),
        tts=inference.TTS(model="deepgram/aura-2", voice="athena"),
    )

    tracer = PrefactorLiveKitSession.from_config(
        api_url=os.environ["PREFACTOR_API_URL"],
        api_token=os.environ["PREFACTOR_API_TOKEN"],
        agent_id="livekit-demo",
        agent_name="LiveKit Demo",
    )

    try:
        await tracer.start(session=session, agent=DemoAgent())
    finally:
        await tracer.close()


if __name__ == "__main__":
    asyncio.run(main())
