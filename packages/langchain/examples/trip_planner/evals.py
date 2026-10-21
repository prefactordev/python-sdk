"""Evals for trip plans.

``run_checks`` runs the deterministic checks against the draft and the data
the graph gathered. ``judge`` asks a model whether the plan's claims are
backed by the research notes. ``quality_payload`` turns the results into the
``trip_plan_quality`` payload recorded on the Prefactor agent instance.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

DAILY_DRIVING_LIMIT_KM = 400

DAY_HEADING = re.compile(r"^## Day (\d+): (.+?) to (.+?)\s*$", re.MULTILINE)
BOLD = re.compile(r"\*\*(.+?)\*\*")

QUALITY_SCHEMA_NAME = "trip_plan_quality"
QUALITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean", "description": "Whether every check passed"},
        "score": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Share of checks that passed, out of 100",
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

JUDGE_PROMPT = """\
You check a road trip plan against the research notes it was written from.

Pass the plan only if every fact it states about a place (what is there, \
what to do, the weather) appears in the research notes. Travel advice that \
states no fact about a place is fine. If anything is not in the notes, fail \
the plan and name the unsupported claims in the reason.

Plan:
{draft}

Research notes:
{research}"""


@dataclass(frozen=True)
class Check:
    """The result of one eval check."""

    name: str
    passed: bool
    detail: str


class Judgement(BaseModel):
    """The judge's verdict."""

    passed: bool = Field(description="Whether every claim is in the research notes")
    reason: str = Field(description="One or two sentences explaining the verdict")


def _short_name(place: str) -> str:
    return place.split(",")[0].strip()


def _days(draft: str) -> list[tuple[int, str, str, str]]:
    """Split the draft into (number, start, end, section text) per day."""
    matches = list(DAY_HEADING.finditer(draft))
    days = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(draft)
        days.append(
            (
                int(match.group(1)),
                match.group(2).strip(),
                match.group(3).strip(),
                draft[match.start() : end],
            )
        )
    return days


def _endpoints_named(state: dict[str, Any]) -> Check:
    draft = state["draft"].lower()
    missing = [
        _short_name(state["request"][key])
        for key in ("origin", "destination")
        if _short_name(state["request"][key]).lower() not in draft
    ]
    if missing:
        return Check(
            "endpoints_named", False, f"The plan never names {' or '.join(missing)}."
        )
    return Check("endpoints_named", True, "The plan names the origin and destination.")


def _day_count(state: dict[str, Any]) -> Check:
    wanted = state["request"]["days"]
    found = len(_days(state["draft"]))
    if found != wanted:
        return Check(
            "day_count", False, f"Asked for {wanted} days but the plan has {found}."
        )
    return Check("day_count", True, f"The plan has {found} days.")


def _stops_per_day(state: dict[str, Any]) -> Check:
    stops = {stop["name"].lower() for stop in state["stops"]}
    failures = [
        f"Day {number} names no stop in bold."
        for number, _, _, text in _days(state["draft"])
        if not any(name.lower() in stops for name in BOLD.findall(text))
    ]
    if failures:
        return Check("stops_per_day", False, " ".join(failures))
    return Check("stops_per_day", True, "Every day names a stop.")


def _only_researched_stops(state: dict[str, Any]) -> Check:
    allowed = {name.lower() for name in state["research"]}
    allowed.add(_short_name(state["request"]["origin"]).lower())
    allowed.add(_short_name(state["request"]["destination"]).lower())
    unknown = sorted(
        {name for name in BOLD.findall(state["draft"]) if name.lower() not in allowed}
    )
    if unknown:
        return Check(
            "only_researched_stops",
            False,
            f"The plan names places that were not researched: {', '.join(unknown)}.",
        )
    return Check("only_researched_stops", True, "Every place in bold was researched.")


def _daily_driving_limit(state: dict[str, Any]) -> Check:
    km_by_stop = {
        stop["name"].lower(): stop["km_from_start"] for stop in state["stops"]
    }
    km_by_stop[_short_name(state["request"]["origin"]).lower()] = 0
    failures = []
    previous_km = 0.0
    for number, _, end, _ in sorted(_days(state["draft"])):
        end_km = km_by_stop.get(_short_name(end).lower())
        if end_km is None:
            failures.append(f"Day {number} ends at {end}, which is not a stop.")
            continue
        driving = round(end_km - previous_km)
        if driving > DAILY_DRIVING_LIMIT_KM:
            failures.append(
                f"Day {number} has {driving} km of driving, over the "
                f"{DAILY_DRIVING_LIMIT_KM} km limit."
            )
        previous_km = end_km
    if failures:
        return Check("daily_driving_limit", False, " ".join(failures))
    return Check(
        "daily_driving_limit",
        True,
        f"Every day is within {DAILY_DRIVING_LIMIT_KM} km.",
    )


def run_checks(state: dict[str, Any]) -> list[Check]:
    """Run the deterministic checks against the draft.

    Args:
        state: Graph state with ``request``, ``stops``, ``research`` and
            ``draft``.

    Returns:
        One result per check, in a fixed order.
    """
    return [
        _endpoints_named(state),
        _day_count(state),
        _stops_per_day(state),
        _only_researched_stops(state),
        _daily_driving_limit(state),
    ]


async def judge(
    model: BaseChatModel,
    state: dict[str, Any],
    request: HumanMessage,
    config: RunnableConfig,
) -> Check:
    """Ask a model whether the plan's claims are backed by the research notes.

    Args:
        model: The judge model.
        state: Graph state with ``draft`` and ``research``.
        request: The user's original request message.
        config: The run config, so the call is traced under the current node.

    Returns:
        The ``grounded`` check.
    """
    prompt = JUDGE_PROMPT.format(
        draft=state["draft"], research=json.dumps(state["research"], indent=2)
    )
    judgement = await model.with_structured_output(Judgement).ainvoke(
        [SystemMessage(prompt), request], config
    )
    assert isinstance(judgement, Judgement)
    return Check("grounded", judgement.passed, judgement.reason)


def quality_payload(checks: list[Check], attempt: int) -> dict[str, Any]:
    """Build the ``trip_plan_quality`` payload.

    Args:
        checks: Every check result for one draft.
        attempt: The draft attempt number, starting at 1.

    Returns:
        The quality payload.
    """
    passed = sum(check.passed for check in checks)
    return {
        "passed": passed == len(checks),
        "score": round(100 * passed / len(checks)),
        "attempt": attempt,
        "checks": [asdict(check) for check in checks],
    }
