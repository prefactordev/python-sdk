"""Termination demo — runs a LangChain agent in a service loop and demonstrates
automatic detection of p2-initiated termination.

Required env vars:
    PREFACTOR_API_URL       e.g. http://localhost:4000
    PREFACTOR_AGENT_ID      agent ID on the target p2 instance
    PREFACTOR_API_TOKEN     deployment/BA token for SDK (span creation etc.)
    PREFACTOR_BA_TOKEN      BA token for terminate API (falls back to PREFACTOR_API_TOKEN)

Optional env vars:
    PREFACTOR_AUTO_TERMINATE_DELAY  seconds before demo calls terminate API (default: 6)
    PREFACTOR_RESTART_DELAY         seconds to wait between runs (default: 75)

Usage:
    PREFACTOR_API_URL=http://localhost:4000 \\
        PREFACTOR_AGENT_ID=<agent-id> \\
        PREFACTOR_API_TOKEN=<token> \\
        PREFACTOR_AUTO_TERMINATE_DELAY=6 \\
        PREFACTOR_RESTART_DELAY=75 \\
        python packages/langchain/examples/termination_demo.py
"""

from __future__ import annotations

import asyncio
import logging
import os

import aiohttp
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool

from prefactor_core import PrefactorTerminatedError
from prefactor_langchain.middleware import PrefactorMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("termination-demo")


@tool
def get_current_time() -> str:
    """Return the current UTC time as a string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def terminate_after_delay(
    api_url: str,
    ba_token: str,
    instance_id: str,
    delay: float,
) -> None:
    await asyncio.sleep(delay)
    url = f"{api_url.rstrip('/')}/api/v1/agent_instance/{instance_id}/terminate"
    logger.info("Calling terminate API: POST %s", url)
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers={"Authorization": f"Bearer {ba_token}", "Content-Type": "application/json"},
            json={"reason": "demo termination"},
        ) as resp:
            body = await resp.json()
            logger.info("Terminate API: status=%s body=%s", resp.status, body)


async def run_once(
    run_number: int,
    api_url: str,
    api_token: str,
    agent_id: str,
    auto_terminate_delay: float,
) -> None:
    middleware = PrefactorMiddleware.from_config(
        api_url=api_url,
        api_token=api_token,
        agent_id=agent_id,
        agent_name="termination-demo-agent",
    )

    model = ChatAnthropic(model="claude-haiku-4-5-20251001")
    agent = create_agent(model, tools=[get_current_time], middleware=[middleware], checkpointer=None)

    instance = await middleware.ensure_initialized()
    logger.info("Run #%d — Agent instance: %s", run_number, instance.id)
    logger.info("Auto-terminate in %.0fs...", auto_terminate_delay)

    ba_token = os.environ.get("PREFACTOR_BA_TOKEN", api_token)
    terminate_task = asyncio.create_task(
        terminate_after_delay(api_url, ba_token, instance.id, auto_terminate_delay)
    )

    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "What time is it? Then keep asking me every 2 seconds."}]},
        )
        logger.info("Run #%d completed normally: %s", run_number, result)
    except PrefactorTerminatedError as e:
        logger.info("Run #%d terminated: %s", run_number, e)
        raise
    finally:
        terminate_task.cancel()
        try:
            await terminate_task
        except (asyncio.CancelledError, Exception):
            pass
        await middleware.close()


async def main() -> None:
    api_url = os.environ["PREFACTOR_API_URL"]
    api_token = os.environ["PREFACTOR_API_TOKEN"]
    agent_id = os.environ["PREFACTOR_AGENT_ID"]
    auto_terminate_delay = float(os.environ.get("PREFACTOR_AUTO_TERMINATE_DELAY", "6"))
    restart_delay = float(os.environ.get("PREFACTOR_RESTART_DELAY", "75"))

    run_number = 0
    while True:
        run_number += 1
        try:
            await run_once(run_number, api_url, api_token, agent_id, auto_terminate_delay)
        except PrefactorTerminatedError:
            logger.info("Service continues — next run in %.0fs.", restart_delay)
            await asyncio.sleep(restart_delay)
        except KeyboardInterrupt:
            logger.info("Stopped by user.")
            break
        except Exception as e:
            logger.exception("Unexpected error in run #%d: %s", run_number, e)
            await asyncio.sleep(restart_delay)


if __name__ == "__main__":
    asyncio.run(main())
