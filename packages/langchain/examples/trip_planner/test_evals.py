"""Tests for the trip planner's deterministic checks.

Run from the repository root:
    mise run test packages/langchain/examples/trip_planner/test_evals.py
"""

from __future__ import annotations

from typing import Any

import pytest
from evals import Check, quality_payload, run_checks

GOOD_DRAFT = """\
# Melbourne to Adelaide

Two days of wineries and coast.

## Day 1: Melbourne to Horsham

Driving: 285 km

- Stop for lunch in **Beaufort**
- Walk along the Wimmera River in **Horsham**

## Day 2: Horsham to Adelaide

Driving: 441 km

- Arrive in **Adelaide** for dinner
"""


def make_state(draft: str = GOOD_DRAFT, days: int = 2) -> dict[str, Any]:
    return {
        "request": {
            "origin": "Melbourne",
            "destination": "Adelaide",
            "days": days,
            "interests": ["wine"],
        },
        "stops": [
            {"name": "Beaufort", "lat": 0, "lon": 0, "km_from_start": 153},
            {"name": "Horsham", "lat": 0, "lon": 0, "km_from_start": 285},
            {"name": "Coombe", "lat": 0, "lon": 0, "km_from_start": 502},
            {"name": "Adelaide", "lat": 0, "lon": 0, "km_from_start": 726},
        ],
        "research": {
            "Beaufort": {"name": "Beaufort"},
            "Horsham": {"name": "Horsham"},
            "Coombe": {"name": "Coombe"},
            "Adelaide": {"name": "Adelaide"},
        },
        "draft": draft,
    }


def check_named(checks: list[Check], name: str) -> Check:
    return next(check for check in checks if check.name == name)


def test_runs_every_check_in_order():
    checks = run_checks(make_state())

    assert [(check.name, check.passed) for check in checks] == [
        ("endpoints_named", True),
        ("day_count", True),
        ("stops_per_day", True),
        ("only_researched_stops", True),
        ("daily_driving_limit", False),
    ]


def test_endpoints_named_fails_without_destination():
    draft = GOOD_DRAFT.replace("Adelaide", "the city")

    check = check_named(run_checks(make_state(draft)), "endpoints_named")

    assert check == Check("endpoints_named", False, "The plan never names Adelaide.")


def test_day_count_fails_when_days_are_missing():
    check = check_named(run_checks(make_state(days=3)), "day_count")

    assert check == Check("day_count", False, "Asked for 3 days but the plan has 2.")


def test_stops_per_day_fails_when_a_day_names_no_stop():
    draft = GOOD_DRAFT.replace("**Adelaide**", "Adelaide")

    check = check_named(run_checks(make_state(draft)), "stops_per_day")

    assert check == Check("stops_per_day", False, "Day 2 names no stop in bold.")


def test_only_researched_stops_fails_on_an_unresearched_place():
    draft = GOOD_DRAFT.replace("**Beaufort**", "**Ararat**")

    check = check_named(run_checks(make_state(draft)), "only_researched_stops")

    assert check == Check(
        "only_researched_stops",
        False,
        "The plan names places that were not researched: Ararat.",
    )


def test_daily_driving_limit_uses_route_distances():
    check = check_named(run_checks(make_state()), "daily_driving_limit")

    assert check == Check(
        "daily_driving_limit",
        False,
        "Day 2 has 441 km of driving, over the 400 km limit.",
    )


def test_daily_driving_limit_passes_when_days_are_short():
    draft = GOOD_DRAFT.replace(
        "## Day 2: Horsham to Adelaide", "## Day 2: Horsham to Coombe\n\n**Coombe**"
    )
    state = make_state(draft + "\n## Day 3: Coombe to Adelaide\n\n**Adelaide**\n", 3)

    check = check_named(run_checks(state), "daily_driving_limit")

    assert check == Check("daily_driving_limit", True, "Every day is within 400 km.")


def test_daily_driving_limit_fails_when_a_day_ends_off_the_route():
    draft = GOOD_DRAFT.replace("Horsham to Adelaide", "Horsham to Ararat")

    check = check_named(run_checks(make_state(draft)), "daily_driving_limit")

    assert check == Check(
        "daily_driving_limit", False, "Day 2 ends at Ararat, which is not a stop."
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
