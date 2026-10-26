"""Tools for the trip planner, backed by free public APIs that need no key.

- Nominatim (OpenStreetMap) for geocoding, reverse geocoding and places to stay
- OSRM for driving routes
- Wikipedia for place summaries and nearby attractions
- Open-Meteo for weather forecasts

Responses are cached in memory for the life of the process, and Nominatim
requests are spaced at least one second apart to respect its usage policy.
The spacing is shared through a lock file, so several runs at once still send
one request a second between them.
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import math
import tempfile
import time
from pathlib import Path
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

# Nominatim searches for each kind of place to stay. Each returns its own
# OpenStreetMap types, so ACCOMMODATION_TYPES filters out other matches, such
# as the toilets at a caravan park.
ACCOMMODATION_SEARCHES = ["hotel", "motel", "guest house", "caravan park"]
ACCOMMODATION_TYPES = {
    "hotel",
    "motel",
    "guest_house",
    "hostel",
    "apartment",
    "chalet",
    "caravan_site",
    "camp_site",
}
MAX_ACCOMMODATION_OPTIONS = 8
# Statuses from sites that block automated requests. The page may still work
# in a browser, so these links are neither confirmed nor dead.
BLOCKED_STATUSES = {401, 403, 429}
WEBSITE_TIMEOUT_SECONDS = 10

_cache: dict[str, Any] = {}
NOMINATIM_LOCK_PATH = (
    Path(tempfile.gettempdir()) / "prefactor-trip-planner-nominatim.lock"
)
_nominatim_lock = asyncio.Lock()
# Public APIs sometimes time out or drop connections, so retry those.
REQUEST_ATTEMPTS = 3
RETRY_SECONDS = 2
_transport: httpx.AsyncBaseTransport | None = None


async def _get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    """GET a JSON document, using the in-memory cache."""
    key = f"{url}?{json.dumps(params or {}, sort_keys=True)}"
    if key in _cache:
        return _cache[key]

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=30.0, transport=_transport
    ) as client:
        for attempt in range(1, REQUEST_ATTEMPTS + 1):
            try:
                response = await client.get(url, params=params)
                break
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == REQUEST_ATTEMPTS:
                    raise
                await asyncio.sleep(RETRY_SECONDS * attempt)
        response.raise_for_status()
        data = response.json()

    _cache[key] = data
    return data


def _lock_nominatim() -> Any:
    """Open the lock file and wait until no other process holds it."""
    file = NOMINATIM_LOCK_PATH.open("a+")
    fcntl.flock(file, fcntl.LOCK_EX)
    return file


async def _get_nominatim(path: str, params: dict[str, Any]) -> Any:
    """GET from Nominatim, at most one request per second across processes.

    The lock file holds the time of the last request made by any run.
    """
    url = f"{NOMINATIM_URL}{path}"
    key = f"{url}?{json.dumps(params, sort_keys=True)}"
    if key in _cache:
        return _cache[key]

    async with _nominatim_lock:
        file = await asyncio.to_thread(_lock_nominatim)
        try:
            file.seek(0)
            last = float(file.read().strip() or 0)
            wait = 1.0 - (time.time() - last)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await _get_json(url, params)
            finally:
                file.seek(0)
                file.truncate()
                file.write(str(time.time()))
                file.flush()
        finally:
            fcntl.flock(file, fcntl.LOCK_UN)
            file.close()


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
    try:
        data = await _get_json(
            f"{OSRM_URL}/route/v1/driving/{coordinates}",
            {"overview": "simplified", "geometries": "geojson"},
        )
    except httpx.HTTPStatusError as e:
        # OSRM answers 400 with a code such as NoRoute when the points
        # cannot be joined by road.
        data = e.response.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError(f"No driving route found: {data.get('code')}")
    return data["routes"][0]


def _sample_route(route: dict[str, Any], every_km: float) -> list[dict[str, float]]:
    """Return points along the route every ``every_km`` kilometres.

    A long straight segment can cross several sample distances, so each point
    is interpolated along the segment that crosses it.
    """
    points = [(lat, lon) for lon, lat in route["geometry"]["coordinates"]]
    samples: list[dict[str, float]] = []
    travelled = 0.0
    next_sample = every_km
    for previous, current in zip(points, points[1:]):
        length = _haversine_km(previous, current)
        while length > 0 and travelled + length >= next_sample:
            share = (next_sample - travelled) / length
            samples.append(
                {
                    "lat": previous[0] + share * (current[0] - previous[0]),
                    "lon": previous[1] + share * (current[1] - previous[1]),
                    "km_from_start": round(next_sample),
                }
            )
            next_sample += every_km
        travelled += length
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
    try:
        route = await _route(origin_lat, origin_lon, dest_lat, dest_lon)
    except ValueError as e:
        return {"error": str(e)}
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
) -> list[dict[str, Any]] | dict[str, Any]:
    """List towns along the driving route, with their distance from the start.

    Args:
        origin_lat: Latitude of the start.
        origin_lon: Longitude of the start.
        dest_lat: Latitude of the destination.
        dest_lon: Longitude of the destination.
        every_km: How often to look for a town along the route, in kilometres.
    """
    try:
        route = await _route(origin_lat, origin_lon, dest_lat, dest_lon)
    except ValueError as e:
        return {"error": str(e)}
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


def attraction_list(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Turn Wikipedia geosearch pages into attractions, nearest first.

    Each attraction keeps Wikipedia's short description, so the planner can
    tell a museum from a prison or a school.
    """
    attractions = [
        {
            "title": page["title"],
            "description": page.get("description"),
            "distance_m": (
                round(page["coordinates"][0]["dist"])
                if page.get("coordinates")
                else None
            ),
        }
        for page in pages
    ]
    return sorted(
        attractions,
        key=lambda item: (item["distance_m"] is None, item["distance_m"] or 0),
    )


@tool
async def nearby_attractions(lat: float, lon: float) -> list[dict[str, Any]]:
    """List Wikipedia articles about places within 10 km of a point.

    Each article has a short description of what the place is.

    Args:
        lat: Latitude.
        lon: Longitude.
    """
    point = f"{lat}|{lon}"
    data = await _get_json(
        f"{WIKIPEDIA_URL}/w/api.php",
        {
            "action": "query",
            "generator": "geosearch",
            "ggscoord": point,
            "ggsradius": 10000,
            "ggslimit": 15,
            "prop": "description|coordinates",
            "codistancefrompoint": point,
            "format": "json",
            "formatversion": 2,
        },
    )
    return attraction_list(data.get("query", {}).get("pages", []))


def accommodation_options(
    results: list[dict[str, Any]], lat: float, lon: float, radius_km: float
) -> list[dict[str, Any]]:
    """Turn Nominatim search results into places to stay near a point.

    Keeps named accommodation within ``radius_km``, lists each place once and
    sorts them nearest first.
    """
    options: dict[tuple[str, Any], dict[str, Any]] = {}
    for result in results:
        if (
            result.get("category") != "tourism"
            or result.get("type") not in ACCOMMODATION_TYPES
            or not result.get("name")
        ):
            continue
        distance = _haversine_km(
            (lat, lon), (float(result["lat"]), float(result["lon"]))
        )
        if distance > radius_km:
            continue
        address = result.get("address") or {}
        extratags = result.get("extratags") or {}
        options[(result["osm_type"], result["osm_id"])] = {
            "name": result["name"],
            "type": result["type"],
            "town": next(
                (
                    address[key]
                    for key in ("town", "city", "village", "suburb", "hamlet")
                    if address.get(key)
                ),
                None,
            ),
            "distance_km": round(distance, 1),
            "website": extratags.get("website") or extratags.get("contact:website"),
        }
    return sorted(options.values(), key=lambda option: option["distance_km"])[
        :MAX_ACCOMMODATION_OPTIONS
    ]


async def check_website(
    url: str, transport: httpx.AsyncBaseTransport | None = None
) -> str:
    """Check whether a website loads, following redirects.

    Returns ``ok`` when the final page loads, ``unverified`` when the site
    blocks automated requests, and ``dead`` when it cannot be reached or
    returns another error, such as 404 or 503.
    """
    try:
        async with (
            httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                timeout=WEBSITE_TIMEOUT_SECONDS,
                follow_redirects=True,
                transport=transport,
            ) as client,
            client.stream("GET", url) as response,
        ):
            status = response.status_code
    except httpx.HTTPError:
        return "dead"
    if status < 400:
        return "ok"
    return "unverified" if status in BLOCKED_STATUSES else "dead"


@tool
async def find_accommodation(
    lat: float, lon: float, radius_km: float = 20
) -> list[dict[str, Any]]:
    """Find hotels, motels, guest houses and caravan parks near a point.

    Each place's website is checked, and ``website_check`` says whether it
    loads: ``ok``, ``unverified`` or ``dead``.

    Args:
        lat: Latitude.
        lon: Longitude.
        radius_km: How far from the point to look.
    """
    lat_delta = radius_km / 111
    lon_delta = radius_km / (111 * math.cos(math.radians(lat)))
    viewbox = f"{lon - lon_delta},{lat + lat_delta},{lon + lon_delta},{lat - lat_delta}"
    results = []
    for search in ACCOMMODATION_SEARCHES:
        results += await _get_nominatim(
            "/search",
            {
                "q": search,
                "format": "jsonv2",
                "viewbox": viewbox,
                "bounded": 1,
                "limit": 20,
                "addressdetails": 1,
                "extratags": 1,
            },
        )
    options = accommodation_options(results, lat, lon, radius_km)
    with_website = [option for option in options if option["website"]]
    checks = await asyncio.gather(
        *(check_website(option["website"]) for option in with_website)
    )
    for option, check in zip(with_website, checks, strict=True):
        option["website_check"] = check
    return options


@tool
async def weather_forecast(lat: float, lon: float) -> list[dict[str, Any]]:
    """Get the 16-day daily weather forecast for a point.

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
            "forecast_days": 16,
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
RESEARCH_TOOLS = [wikipedia_summary, nearby_attractions]
