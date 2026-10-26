"""Tests for running the trip plan evals through Prefactor judges.

Run from the repository root:
    mise run test packages/langchain/examples/trip_planner/test_evals.py
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from evals import Check, PrefactorJudges, quality_payload

INSTANCE_ID = "instance-1"
AGENT_ID = "trip-planner"
JUDGES = {"judge-rules": "Trip plan rules", "judge-grounded": "Trip plan grounded"}


def span(schema_name: str, status: str, node: str | None = None) -> dict[str, Any]:
    payload = {"node": node} if node else {}
    return {"schema_name": schema_name, "status": status, "payload": payload}


SETTLED_SPANS = [
    span("langchain:agent", "active"),
    span("langchain:node", "complete", "draft_itinerary"),
    span("langchain:llm", "complete"),
    span("langchain:tool", "complete"),
    span("langchain:node", "active", "evaluate"),
]


class FakePrefactor:
    """Answers the Prefactor API calls that ``PrefactorJudges`` makes."""

    def __init__(
        self,
        span_pages: list[list[dict[str, Any]]],
        judge_runs: dict[str, list[dict[str, Any]]],
    ) -> None:
        self.span_pages = span_pages
        self.judge_runs = judge_runs
        self.asked: list[str] = []
        self.span_lists = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1")
        if path == f"/agent_instance/{INSTANCE_ID}":
            return ok({"details": {"id": INSTANCE_ID, "agent_id": AGENT_ID}})
        if path == "/agent_association/to":
            assert request.url.params["agent_id"] == AGENT_ID
            summaries = [
                {"from_agent_id": judge_id, "association_type": "judge"}
                for judge_id in JUDGES
            ]
            return ok({"summaries": summaries})
        if path.startswith("/agent/"):
            judge_id = path.removeprefix("/agent/")
            return ok({"details": {"id": judge_id, "name": JUDGES[judge_id]}})
        if path == "/agent_spans":
            assert request.url.params["agent_instance_id"] == INSTANCE_ID
            page = self.span_pages[min(self.span_lists, len(self.span_pages) - 1)]
            self.span_lists += 1
            return ok({"summaries": page})
        if path == f"/agent_instance/{INSTANCE_ID}/judge":
            judge_id = json.loads(request.content)["judge_agent_id"]
            self.asked.append(judge_id)
            return ok({"details": {"id": f"run-{judge_id}", "status": "preparing"}})
        if path.startswith("/agent_instance/run-"):
            runs = self.judge_runs[path.removeprefix("/agent_instance/run-")]
            return ok({"details": runs.pop(0) if len(runs) > 1 else runs[0]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")


def ok(body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"status": "success", **body})


def finished(verdict: str, explanation: str) -> dict[str, Any]:
    return {
        "status": "complete",
        "result_payload": {"verdict": verdict, "explanation": explanation},
    }


def judges_for(fake: FakePrefactor) -> PrefactorJudges:
    return PrefactorJudges(
        api_url="http://prefactor.test",
        api_token="token",
        poll_seconds=0,
        flush_seconds=0,
        transport=httpx.MockTransport(fake.handle),
    )


async def test_asks_every_judge_of_the_agent_and_returns_their_verdicts():
    fake = FakePrefactor(
        [SETTLED_SPANS],
        {
            "judge-rules": [
                {"status": "active"},
                finished("pass", "Every rule holds."),
            ],
            "judge-grounded": [finished("fail", "Gold history is not in the record.")],
        },
    )

    checks = await judges_for(fake)(INSTANCE_ID)

    assert sorted(fake.asked) == sorted(JUDGES)
    assert sorted(checks, key=lambda check: check.name) == [
        Check("Trip plan grounded", False, "Gold history is not in the record."),
        Check("Trip plan rules", True, "Every rule holds."),
    ]


async def test_waits_for_model_and_tool_spans_to_finish_before_asking():
    still_sending = [*SETTLED_SPANS[:2], span("langchain:llm", "active")]
    fake = FakePrefactor(
        [still_sending, SETTLED_SPANS],
        {judge_id: [finished("pass", "Fine.")] for judge_id in JUDGES},
    )

    await judges_for(fake)(INSTANCE_ID)

    assert fake.span_lists == 2


async def test_a_judge_that_does_not_finish_fails_its_check():
    fake = FakePrefactor(
        [SETTLED_SPANS],
        {
            "judge-rules": [{"status": "failed", "result_payload": None}],
            "judge-grounded": [finished("pass", "Fine.")],
        },
    )

    checks = await judges_for(fake)(INSTANCE_ID)

    assert (
        Check("Trip plan rules", False, "The judge gave no verdict (status failed).")
        in checks
    )


@pytest.mark.parametrize(
    ("passed", "expected_score"),
    [((True, True, True, True), 100), ((True, False, True, False), 50)],
)
def test_quality_payload_scores_the_share_of_checks_passed(passed, expected_score):
    checks = [Check(f"check_{i}", ok, "detail") for i, ok in enumerate(passed)]

    payload = quality_payload(checks, attempt=2)

    assert payload == {
        "passed": all(passed),
        "score": expected_score,
        "attempt": 2,
        "checks": [
            {"name": check.name, "passed": check.passed, "detail": "detail"}
            for check in checks
        ],
    }
