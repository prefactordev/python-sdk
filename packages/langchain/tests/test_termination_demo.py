"""Tests for the LangChain termination demo."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import aiohttp
import pytest
from aioresponses import aioresponses


def _load_termination_demo():
    module_path = (
        Path(__file__).parents[1] / "examples" / "termination_demo.py"
    ).resolve()
    spec = importlib.util.spec_from_file_location("termination_demo", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_terminate_after_delay_raises_for_non_success_response():
    """Terminate API failures should be visible to the demo caller."""
    demo = _load_termination_demo()
    url = "https://api.test.com/api/v1/agent_instance/inst-1/terminate"

    with aioresponses() as responses:
        responses.post(url, status=500, payload={"error": "failed"})

        with pytest.raises(aiohttp.ClientResponseError):
            await demo.terminate_after_delay(
                api_url="https://api.test.com",
                ba_token="token",
                instance_id="inst-1",
                delay=0,
            )


@pytest.mark.asyncio
async def test_cancel_and_await_terminate_task_reraises_completed_failures():
    """Completed terminate task failures should not be swallowed."""
    demo = _load_termination_demo()

    async def fail():
        raise RuntimeError("terminate failed")

    task = asyncio.create_task(fail())
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="terminate failed"):
        await demo._cancel_and_await_terminate_task(task)


@pytest.mark.asyncio
async def test_cancel_and_await_terminate_task_ignores_normal_cancellation():
    """Cancelling an unfinished terminate task should not fail cleanup."""
    demo = _load_termination_demo()

    async def wait_forever():
        await asyncio.Event().wait()

    task = asyncio.create_task(wait_forever())

    await demo._cancel_and_await_terminate_task(task)

    assert task.cancelled()
