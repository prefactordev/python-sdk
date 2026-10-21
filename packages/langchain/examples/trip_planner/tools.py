"""Tools for the trip planner, backed by free public APIs that need no key.

- Nominatim (OpenStreetMap) for geocoding and reverse geocoding
- OSRM for driving routes
- Wikipedia for place summaries and nearby attractions
- Open-Meteo for weather forecasts

Responses are cached in memory for the life of the process, and Nominatim
requests are spaced at least one second apart to respect its usage policy.
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any
from urllib.parse import quote

import httpx
from langchain_core.tools import tool

USER_AGENT = (
    "prefactor-trip-planner-example/1.0 (https://github.com/prefactordev/python-sdk)"
)
NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OSRM_URL = "https://router.project-osrm.org"
WIKIPEDIA_URL = "https://en.wikipedia.org"
OPEN_METEO_URL = "https://api.open-meteo.com"

_cache: dict[str, Any] = {}
_nominatim_lock = asyncio.Lock()
_last_nominatim_request = 0.0


async def _get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    """GET a JSON document, using the in-memory cache."""
    key = f"{url}?{json.dumps(params or {}, sort_keys=True)}"
    if key in _cache:
        return _cache[key]

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=30.0
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    _cache[key] = data
    return data


async def _get_nominatim(path: str, params: dict[str, Any]) -> Any:
    """GET from Nominatim, at most one request per second."""
    global _last_nominatim_request

    url = f"{NOMINATIM_URL}{path}"
    key = f"{url}?{json.dumps(params, sort_keys=True)}"
    if key in _cache:
        return _cache[key]

    async with _nominatim_lock:
        wait = 1.0 - (time.monotonic() - _last_nominatim_request)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            return await _get_json(url, params)
        finally:
            _last_nominatim_request = time.monotonic()


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lon) points in kilometres."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * 6371.0 * math.asin(math.sqrt(h))


async def _route(
    origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float
) -> dict[str, Any]:
    """Fetch the OSRM driving route between two points."""
    coordinates = f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    data = await _get_json(
        f"{OSRM_URL}/route/v1/driving/{coordinates}",
        {"overview": "simplified", "geometries": "geojson"},
    )
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError(f"No driving route found: {data.get('code')}")
    return data["routes"][0]


def _sample_route(route: dict[str, Any], every_km: float) -> list[dict[str, float]]:
    """Return points along the route roughly every ``every_km`` kilometres."""
    points = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    samples: list[dict[str, float]] = []
    travelled = 0.0
    next_sample = every_km
    for previous, current in zip(points, points[1:]):
        travelled += _haversine_km(previous, current)
        if travelled >= next_sample:
            samples.append(
                {
                    "lat": current[0],
                    "lon": current[1],
                    "km_from_start": round(travelled),
                }
            )
            next_sample += every_km
    return samples


# Nominatim address types that name a settlement rather than a region.
SETTLEMENT_TYPES = {
    "city",
    "town",
    "village",
    "hamlet",
    "suburb",
    "city_district",
    "locality",
    "municipality",
}

# Address fields that name a settlement, from largest to smallest.
SETTLEMENT_ADDRESS_KEYS = ("city", "town", "village", "hamlet")


async def _settlement_near(lat: float, lon: float) -> str | None:
    """Name the settlement at a point, or None when there is none nearby."""
    params = {"lat": lat, "lon": lon, "format": "json"}
    result = await _get_nominatim("/reverse", {**params, "zoom": 12})
    if result.get("addresstype") in SETTLEMENT_TYPES and result.get("name"):
        return result["name"]
    # On rural roads zoom 12 names the county; a closer look finds small towns
    address = (await _get_nominatim("/reverse", {**params, "zoom": 14})).get(
        "address", {}
    )
    return next(
        (address[key] for key in SETTLEMENT_ADDRESS_KEYS if address.get(key)), None
    )


@tool
async def geocode(place: str) -> dict[str, Any]:
    """Find the coordinates of a place by name.

    Args:
        place: A place name, for example "Ballarat, Victoria".
    """
    results = await _get_nominatim(
        "/search", {"q": place, "format": "json", "limit": 1}
    )
    if not results:
        return {"error": f"No place found for {place!r}"}
    match = results[0]
    return {
        "name": match["display_name"],
        "lat": float(match["lat"]),
        "lon": float(match["lon"]),
    }


@tool
async def get_route(
    origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float
) -> dict[str, Any]:
    """Get the driving distance and time between two points.

    Args:
        origin_lat: Latitude of the start.
        origin_lon: Longitude of the start.
        dest_lat: Latitude of the destination.
        dest_lon: Longitude of the destination.
    """
    route = await _route(origin_lat, origin_lon, dest_lat, dest_lon)
    return {
        "distance_km": round(route["distance"] / 1000),
        "duration_hours": round(route["duration"] / 3600, 1),
    }


@tool
async def find_towns_along_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    every_km: float = 80,
) -> list[dict[str, Any]]:
    """List towns along the driving route, with their distance from the start.

    Args:
        origin_lat: Latitude of the start.
        origin_lon: Longitude of the start.
        dest_lat: Latitude of the destination.
        dest_lon: Longitude of the destination.
        every_km: How often to look for a town along the route, in kilometres.
    """
    route = await _route(origin_lat, origin_lon, dest_lat, dest_lon)
    towns: list[dict[str, Any]] = []
    seen: set[str] = set()
    for point in _sample_route(route, every_km):
        name = await _settlement_near(point["lat"], point["lon"])
        if name and name not in seen:
            seen.add(name)
            towns.append({"name": name, **point})
    return towns


@tool
async def wikipedia_summary(title: str) -> dict[str, Any]:
    """Get the Wikipedia summary for a place.

    Args:
        title: The Wikipedia article title, for example "Ballarat".
    """
    try:
        data = await _get_json(
            f"{WIKIPEDIA_URL}/api/rest_v1/page/summary/{quote(title)}"
        )
    except httpx.HTTPStatusError as e:
        return {
            "error": f"No Wikipedia article for {title!r}: {e.response.status_code}"
        }
    return {
        "title": data.get("title"),
        "description": data.get("description"),
        "extract": data.get("extract"),
    }


@tool
async def nearby_attractions(lat: float, lon: float) -> list[dict[str, Any]]:
    """List Wikipedia articles about places within 10 km of a point.

    Args:
        lat: Latitude.
        lon: Longitude.
    """
    data = await _get_json(
        f"{WIKIPEDIA_URL}/w/api.php",
        {
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": 10000,
            "gslimit": 8,
            "format": "json",
        },
    )
    return [
        {"title": item["title"], "distance_m": round(item["dist"])}
        for item in data.get("query", {}).get("geosearch", [])
    ]


@tool
async def weather_forecast(lat: float, lon: float) -> list[dict[str, Any]]:
    """Get the 7-day weather forecast for a point.

    Args:
        lat: Latitude.
        lon: Longitude.
    """
    data = await _get_json(
        f"{OPEN_METEO_URL}/v1/forecast",
        {
            "latitude": lat,
            "longitude": lon,
            "daily": (
                "temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            ),
            "forecast_days": 7,
            "timezone": "auto",
        },
    )
    daily = data["daily"]
    return [
        {
            "date": date,
            "max_c": daily["temperature_2m_max"][i],
            "min_c": daily["temperature_2m_min"][i],
            "rain_chance_pct": daily["precipitation_probability_max"][i],
        }
        for i, date in enumerate(daily["time"])
    ]


ROUTE_TOOLS = [geocode, get_route, find_towns_along_route]
RESEARCH_TOOLS = [wikipedia_summary, nearby_attractions, weather_forecast]
