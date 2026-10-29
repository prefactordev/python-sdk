"""Evals for trip plans, run by Prefactor judges.

``PrefactorJudges`` asks every judge associated with the trip planner agent
to score the run so far, through Prefactor's on-demand judge API, and waits
for their verdicts. Each judge reads the whole run record, including the
model calls, tool calls and the latest draft. ``quality_payload`` turns the
verdicts into the ``trip_plan_quality`` payload recorded on the Prefactor
agent instance.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx

DAILY_DRIVING_LIMIT_KM = 400
# Below this, the trip has more days than the drive needs.
MIN_DAILY_KM = 250

QUALITY_SCHEMA_NAME = "trip_plan_quality"
QUALITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean", "description": "Whether every judge passed"},
        "score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Share of judges that passed, out of 100",
        },
        "attempt": {"type": "integer", "description": "Draft attempt number"},
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "passed": {"type": "boolean"},
                    "detail": {"type": "string"},
                },
                "required": ["name", "passed", "detail"],
            },
        },
    },
    "required": ["passed", "score", "attempt", "checks"],
}

FINISHED_STATUSES = {"complete", "failed", "cancelled", "terminated"}
# The SDK sends span updates from a background queue. A judge reads the spans
# Prefactor has, so wait until the model and tool calls have arrived.
SETTLING_SCHEMAS = {"langchain:llm", "langchain:tool"}
SPANS_TIMEOUT_SECONDS = 60
# Prefactor builds a judge's record from the spans it has moved to ClickHouse
# plus the buffered spans it has not moved yet. A span moved while it was still
# active shows as active until its finished version is moved too, which takes
# up to 2.5 seconds, so wait a little longer than that before asking.
FLUSH_SECONDS = 5
JUDGE_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class Check:
    """One judge's verdict on a draft."""

    name: str
    passed: bool
    detail: str


class PrefactorJudges:
    """Asks the agent's Prefactor judges to score a running agent instance."""

    def __init__(
        self,
        api_url: str,
        api_token: str,
        poll_seconds: float = 2,
        flush_seconds: float = FLUSH_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create the client.

        Args:
            api_url: Prefactor API URL, for example ``http://localhost:4000``.
            api_token: Prefactor API token.
            poll_seconds: How long to wait between status checks.
            flush_seconds: How long to wait after the spans have arrived,
                so that Prefactor has moved them to ClickHouse.
            transport: HTTP transport, for tests.
        """
        self._base_url = f"{api_url.rstrip('/')}/api/v1"
        self._headers = {"Authorization": f"Bearer {api_token}"}
        self._poll_seconds = poll_seconds
        self._flush_seconds = flush_seconds
        self._transport = transport

    async def __call__(self, instance_id: str) -> list[Check]:
        """Ask every judge of the instance's agent and wait for the verdicts.

        Args:
            instance_id: The running trip planner instance.

        Returns:
            One check per judge, named after the judge.
        """
        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=30,
            transport=self._transport,
        ) as http:
            instance = await _details(http, f"/agent_instance/{instance_id}")
            judges = await self._judges(http, instance["agent_id"])
            await self._wait_for_spans(http, instance_id)
            await asyncio.sleep(self._flush_seconds)
            return list(
                await asyncio.gather(
                    *(
                        self._ask(http, instance_id, judge_id, name)
                        for judge_id, name in judges
                    )
                )
            )

    async def _judges(
        self, http: httpx.AsyncClient, agent_id: str
    ) -> list[tuple[str, str]]:
        response = await http.get(
            "/agent_association/to", params={"agent_id": agent_id}
        )
        response.raise_for_status()
        judge_ids = [
            association["from_agent_id"]
            for association in response.json()["summaries"]
            if association["association_type"] == "judge"
        ]
        judges = []
        for judge_id in judge_ids:
            judge = await _details(http, f"/agent/{judge_id}")
            judges.append((judge_id, judge["name"]))
        return judges

    async def _wait_for_spans(self, http: httpx.AsyncClient, instance_id: str) -> None:
        deadline = time.monotonic() + SPANS_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            response = await http.get(
                "/agent_spans",
                params={
                    "agent_instance_id": instance_id,
                    "pagination[page_size]": 100,
                    "sorting[field]": "started_at",
                    "sorting[direction]": "desc",
                },
            )
            response.raise_for_status()
            if not any(
                span["schema_name"] in SETTLING_SCHEMAS and span["status"] == "active"
                for span in response.json()["summaries"]
            ):
                return
            await asyncio.sleep(self._poll_seconds)

    async def _ask(
        self, http: httpx.AsyncClient, instance_id: str, judge_id: str, name: str
    ) -> Check:
        response = await http.post(
            f"/agent_instance/{instance_id}/judge",
            json={"judge_agent_id": judge_id},
        )
        response.raise_for_status()
        run_id = response.json()["summary"]["id"]
        deadline = time.monotonic() + JUDGE_TIMEOUT_SECONDS
        run: dict[str, Any] = {"status": "preparing"}
        while time.monotonic() < deadline:
            run = await _details(http, f"/agent_instance/{run_id}")
            if run["status"] in FINISHED_STATUSES:
                break
            await asyncio.sleep(self._poll_seconds)
        verdict = run.get("result_payload") or {}
        if run["status"] != "complete" or "verdict" not in verdict:
            return Check(
                name, False, f"The judge gave no verdict (status {run['status']})."
            )
        return Check(name, verdict["verdict"] == "pass", verdict["explanation"])


async def _details(http: httpx.AsyncClient, path: str) -> dict[str, Any]:
    response = await http.get(path)
    response.raise_for_status()
    return response.json()["details"]


def quality_payload(checks: list[Check], attempt: int) -> dict[str, Any]:
    """Build the ``trip_plan_quality`` payload.

    Args:
        checks: Every judge's verdict on one draft.
        attempt: The draft attempt number, starting at 1.

    Returns:
        The quality payload.
    """
    passed = sum(check.passed for check in checks)
    return {
        "passed": passed == len(checks),
        "score": round(100 * passed / len(checks)) if checks else 0,
        "attempt": attempt,
        "checks": [asdict(check) for check in checks],
    }
