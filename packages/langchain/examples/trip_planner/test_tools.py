"""Tests for the trip planner's tool helpers.

Run from the repository root:
    mise run test packages/langchain/examples/trip_planner/test_tools.py
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
import tools
from tools import accommodation_options, attraction_list, check_website

STOP = (-36.333, 141.65)


def place(
    name: str,
    kind: str,
    lat: float,
    lon: float,
    category: str = "tourism",
    town: str = "Nhill",
) -> dict[str, Any]:
    return {
        "osm_type": "node",
        "osm_id": hash(name),
        "name": name,
        "category": category,
        "type": kind,
        "lat": str(lat),
        "lon": str(lon),
        "address": {"town": town},
        "extratags": {"website": "https://example.com"} if kind == "motel" else {},
    }


def test_keeps_named_places_to_stay_within_the_radius_nearest_first():
    results = [
        place("Nhill Caravan Park", "camp_site", -36.335, 141.652),
        place("Acacia Motor Inn", "motel", -36.333, 141.651),
        place("Nhill Caravan Park", "toilets", -36.335, 141.652, category="amenity"),
        place("", "motel", -36.334, 141.65),
        place("Far Away Hotel", "hotel", -37.5, 141.65),
    ]

    options = accommodation_options(results, *STOP, radius_km=20)

    assert options == [
        {
            "name": "Acacia Motor Inn",
            "type": "motel",
            "town": "Nhill",
            "distance_km": 0.1,
            "website": "https://example.com",
        },
        {
            "name": "Nhill Caravan Park",
            "type": "camp_site",
            "town": "Nhill",
            "distance_km": 0.3,
            "website": None,
        },
    ]


def test_lists_a_place_found_by_two_searches_once():
    motel = place("Zero Inn Motel", "motel", -36.333, 141.66)

    options = accommodation_options([motel, dict(motel)], *STOP, radius_km=20)

    assert [option["name"] for option in options] == ["Zero Inn Motel"]


def test_lists_attractions_with_what_they_are_nearest_first():
    pages = [
        {
            "title": "Hopkins Correctional Centre",
            "description": "Australian medium security prison",
            "coordinates": [{"dist": 4590.3}],
        },
        {
            "title": "J Ward",
            "description": "Psychiatric prison now museum in Victoria, Australia",
            "coordinates": [{"dist": 467.8}],
        },
        {"title": "Electoral district of Ararat"},
    ]

    assert attraction_list(pages) == [
        {
            "title": "J Ward",
            "description": "Psychiatric prison now museum in Victoria, Australia",
            "distance_m": 468,
        },
        {
            "title": "Hopkins Correctional Centre",
            "description": "Australian medium security prison",
            "distance_m": 4590,
        },
        {
            "title": "Electoral district of Ararat",
            "description": None,
            "distance_m": None,
        },
    ]


def respond_with(status: int, location: str | None = None) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/moved":
            return httpx.Response(status)
        if location:
            return httpx.Response(302, headers={"location": location})
        return httpx.Response(status)

    return httpx.MockTransport(handle)


@pytest.mark.parametrize(
    ("status", "location", "expected"),
    [
        (200, None, "ok"),
        (404, None, "dead"),
        (410, None, "dead"),
        (503, "https://hotel.test/moved", "dead"),
        (403, None, "unverified"),
        (429, None, "unverified"),
    ],
)
async def test_check_website_follows_redirects_and_sorts_by_status(
    status, location, expected
):
    check = await check_website(
        "https://hotel.test/", transport=respond_with(status, location)
    )

    assert check == expected


async def test_check_website_reports_a_site_that_cannot_be_reached_as_dead():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    check = await check_website(
        "https://gone.test/", transport=httpx.MockTransport(refuse)
    )

    assert check == "dead"


async def test_route_tools_report_when_there_is_no_driving_route(monkeypatch):
    async def no_route(url: str, params: dict[str, Any] | None = None) -> Any:
        request = httpx.Request("GET", url)
        response = httpx.Response(
            400, json={"code": "NoRoute", "message": "Impossible route"}
        )
        raise httpx.HTTPStatusError("400", request=request, response=response)

    monkeypatch.setattr(tools, "_get_json", no_route)
    points = {"origin_lat": -37.8, "origin_lon": 145.0, "dest_lat": 14.6}
    points["dest_lon"] = 121.0

    route = await tools.get_route.ainvoke(points)
    towns = await tools.find_towns_along_route.ainvoke(points)

    assert route == {"error": "No driving route found: NoRoute"}
    assert towns == {"error": "No driving route found: NoRoute"}


async def test_nominatim_waits_for_a_request_made_by_another_process(
    monkeypatch, tmp_path
):
    lock_path = tmp_path / "nominatim.lock"
    lock_path.write_text(str(time.time()))
    waits: list[float] = []

    async def record_wait(seconds: float) -> None:
        waits.append(seconds)

    async def found(url: str, params: dict[str, Any] | None = None) -> Any:
        return []

    monkeypatch.setattr(tools, "NOMINATIM_LOCK_PATH", lock_path)
    monkeypatch.setattr(tools.asyncio, "sleep", record_wait)
    monkeypatch.setattr(tools, "_get_json", found)

    await tools._get_nominatim("/search", {"q": "Ararat"})

    assert len(waits) == 1
    assert 0.9 < waits[0] <= 1.0
    assert float(lock_path.read_text()) >= time.time() - 1


async def test_get_json_retries_a_request_that_times_out(monkeypatch):
    calls = 0

    def flaky(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(200, json={"ok": True})

    async def no_wait(seconds: float) -> None:
        pass

    monkeypatch.setattr(tools, "_transport", httpx.MockTransport(flaky))
    monkeypatch.setattr(tools.asyncio, "sleep", no_wait)

    assert await tools._get_json("https://api.test/flaky") == {"ok": True}
    assert calls == 3
