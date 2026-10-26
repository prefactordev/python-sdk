"""Tests for the trip planner graph's structured results.

Run from the repository root:
    mise run test packages/langchain/examples/trip_planner/test_graph.py
"""

from __future__ import annotations

import pytest
from graph import RoutePlan
from pydantic import ValidationError

ROUTE = {
    "origin_found": "Melbourne, Victoria, Australia",
    "destination_found": "Adelaide, South Australia, Australia",
    "distance_km": 726,
    "duration_hours": 9.2,
}
STOP = {"name": "Horsham", "lat": -36.7, "lon": 142.2, "km_from_start": 300}


def test_route_plan_needs_two_stops_when_there_is_no_problem():
    with pytest.raises(ValidationError, match="at least 2 stops"):
        RoutePlan.model_validate({**ROUTE, "stops": [STOP]})


def test_route_plan_allows_no_stops_when_it_explains_the_problem():
    plan = RoutePlan.model_validate(
        {**ROUTE, "stops": [], "problem": "No driving route found: NoRoute"}
    )

    assert plan.stops == []


def test_route_plan_allows_at_most_six_stops():
    with pytest.raises(ValidationError):
        RoutePlan.model_validate({**ROUTE, "stops": [STOP] * 7})
