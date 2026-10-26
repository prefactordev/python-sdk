"""The trip planner LangGraph graph.

START -> parse_request -> plan_route -> research_stops -> draft_itinerary
      -> evaluate -> finalise -> END

When ``plan_route`` cannot find a place or a driving route, the stops are
empty and ``draft_itinerary`` tells the traveller why instead of planning.

``evaluate`` asks the agent's Prefactor judges to score each draft before
the plan is saved, and sends the graph back to ``draft_itinerary`` with their
feedback when a judge fails it, up to ``MAX_ATTEMPTS`` drafts.

Every model call sends the node's task as the system message and the user's
original request as the only human message, so Prefactor's conversation view
shows one user message for the whole run.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TypedDict

from evals import (
    DAILY_DRIVING_LIMIT_KM,
    MIN_DAILY_KM,
    QUALITY_SCHEMA_NAME,
    Check,
    quality_payload,
)
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, model_validator
from tools import RESEARCH_TOOLS, ROUTE_TOOLS, find_accommodation, weather_forecast

OUT_DIR = Path(__file__).parent / "out"
MAX_ATTEMPTS = 3
MAX_DAYS = 14


class TripRequest(BaseModel):
    """What the user asked for."""

    origin: str = Field(description="Where the trip starts")
    destination: str = Field(description="Where the trip ends")
    days: int | None = Field(
        default=None,
        ge=1,
        le=14,
        description="Number of days for the trip, or null when the user gave none",
    )
    interests: list[str] = Field(description="What the traveller likes")


class Stop(BaseModel):
    """A town to stop at along the route."""

    name: str
    lat: float
    lon: float
    km_from_start: float


class RoutePlan(BaseModel):
    """The driving route and the stops chosen along it."""

    origin_found: str = Field(description="The place name geocode gave the origin")
    destination_found: str = Field(
        description="The place name geocode gave the destination"
    )
    distance_km: float
    duration_hours: float
    stops: list[Stop] = Field(
        max_length=6,
        description="2 to 6 stops in driving order, ending at the destination. "
        "Empty when there is a problem.",
    )
    problem: str | None = Field(
        default=None,
        description="Why the trip cannot be planned, when a place was not "
        "found, geocode found a different place from the one the user meant, "
        "or there is no driving route. Otherwise null.",
    )

    @model_validator(mode="after")
    def _stops_unless_problem(self) -> RoutePlan:
        if self.problem is None and len(self.stops) < 2:
            raise ValueError("Choose at least 2 stops, or explain the problem")
        return self


class StopResearch(BaseModel):
    """What the researcher found about one stop."""

    name: str
    summary: str = Field(description="Two or three sentences about the place")
    attractions: list[str] = Field(
        description="Places open to visitors nearby, each as "
        '"<title>: <what it is>", using the description nearby_attractions gave'
    )


class TripState(TypedDict, total=False):
    """Graph state."""

    messages: list[BaseMessage]
    request: dict[str, Any]
    start_date: str
    route: dict[str, Any]
    stops: list[dict[str, Any]]
    research: dict[str, dict[str, Any]]
    draft: str
    feedback: str
    quality: dict[str, Any]
    attempt: int
    output_path: str


PARSE_PROMPT = """\
Read the user's trip request and extract the origin, the destination, the \
number of days and the traveller's interests. If the request gives no number \
of days, set days to null; the planner works it out from the route. If it \
gives no interests, use ["food", "history"]."""

ROUTE_PROMPT = """\
Plan the driving route from {origin} to {destination} for {length}.

1. Geocode the origin and the destination.
2. Get the route between them.
3. Find the towns along the route.
4. Choose 2 to 6 stops in driving order so that no day has more than about \
350 km of driving. The last stop must be the destination. Use only towns \
returned by the tools, plus the destination.

Report the place names geocode found. If geocode finds no place, finds a \
place other than the one the user meant (such as a town of the same name in \
another country), or there is no driving route, explain why in the problem \
field and leave the stops empty."""

RESEARCH_PROMPT = """\
Research {name} (lat {lat}, lon {lon}) as a stop on a road trip for someone \
who likes {interests}.

Use the Wikipedia summary and the nearby attractions. Report only what the \
tools returned.

List only attractions that a visitor would choose to go to and that are open \
to visitors, such as museums, galleries, parks, lookouts, heritage sites, \
wineries and beaches. Use each one's description to decide. Leave out \
schools, hospitals, prisons, government areas, electoral districts, \
airports, roads, suburbs and localities, and railway stations unless the \
description says they are a museum or a heritage site to visit."""

DRAFT_PROMPT = """\
Write a {days}-day road trip plan from {origin} to {destination} in Markdown \
for someone who likes {interests}. Make it easy to scan: short sentences, \
one idea per bullet, and no more than four bullets in a list.

Use exactly this structure:

# {origin} to {destination}

One or two sentences: the total distance, the number of days and the trip's \
highlights.

## Before you go

- Only when the trip is a poor idea as asked: one or two bullets saying why, \
and what would work better.

## At a glance

- **Day 1, <short date, such as Fri 23 Oct>:** <start town> to <end town>, \
<km> km, <max>°C / <min>°C, <rain>% rain. Stay: <first place to stay, or "no \
accommodation found", or "trip ends">

## Day 1: <start town> to <end town>

**<full date> | <km> km driving | <max>°C / <min>°C, <rain>% chance of rain**

### See and do

- One to four bullets on what to see and do, suited to that day's weather.

### Where to stay

- <name>: <type> in <town>, <distance> km from <end town> \
([website](<website>), only when its website_check is "ok")

Do not use Markdown tables. Repeat the "At a glance" bullet and the day \
section for every day, numbered from 1 to \
{days}. The dates are:
{day_dates}
Round temperatures to whole degrees. Take each day's weather from the \
forecast at that day's end stop for that day's date.

Every day except the last ends with a night away. In its "Where to stay" \
list, give one or two places from the end stop's accommodation list, nearest \
first, with their type, town and distance as listed. Link a place's \
website only when its website_check is "ok"; leave out links that are \
"dead" or "unverified". If the list is empty, \
write one bullet saying no accommodation was found within 20 km of the end \
town. The last day ends at {destination}, so it has no "Where to stay" \
section. When you can, end each day at a stop that has accommodation, as \
long as no day goes over the driving limit.

Each day must end at one of the stops below, and the last day must end at \
{destination}. Work out each day's driving from the stops' km_from_start \
values. No day may have more than {limit_km} km of driving, so choose each \
day's end stop to keep within it.

The route is {distance_km} km and about {duration_hours} hours of driving. \
Add the "Before you go" section only when the trip is a poor idea as asked, \
and otherwise leave it out. A trip is a poor idea when:
- the days are too few to keep every day within {limit_km} km of driving
- the days are more than the drive needs: the route divided by the days is \
under {min_daily_km} km a day
- rain is likely (70% or more) on most days, or the forecast is extreme heat \
or cold
- the route has few places to stop or stay
Base the reasons only on the route, the forecasts and the research notes.

In "See and do", suggest only things a traveller who likes {interests} would \
choose to spend time on, at places open to visitors. Say what each place is. \
Never suggest places that are not for visitors, such as hospitals, prisons, \
schools or plain railway stations, or places that are only a name on a map. \
Do not pad the list with filler such as visiting between showers, checking \
whether an event is on or stocking up on food. If nothing near the end town \
is worth a visit, write one bullet saying it is a driving day with little to \
see.

Use only the facts in the research notes. Do not add history or other \
details from your own knowledge, including in the opening sentences. If the \
research notes do not say it, leave it out.

Stops, in driving order:
{stops}

Research notes:
{research}"""

PROBLEM_PROMPT = """\
The road trip from {origin} to {destination} cannot be planned: {problem}

Write a short Markdown reply with exactly this structure, and no day plan:

# {origin} to {destination}

## Before you go

- One or two bullets saying why the trip cannot be planned, and what the \
traveller could ask for instead.

Use only the problem above. Do not invent a route, stops or places."""

FEEDBACK_PROMPT = """

Judges reviewed the previous draft and failed it. Fix what they found in \
this draft:
{feedback}"""


def _day_dates(start_date: str, days: int) -> str:
    """List each day's date, starting from the trip's start date."""
    start = date.fromisoformat(start_date)
    dates = [start + timedelta(days=offset) for offset in range(days)]
    return "\n".join(
        f"- Day {number}: {day:%A} {day.day} {day:%B %Y}"
        for number, day in enumerate(dates, start=1)
    )


def _request_message(state: TripState) -> HumanMessage:
    message = state["messages"][0]
    assert isinstance(message, HumanMessage)
    return message


Judges = Callable[[str], Awaitable[list[Check]]]


def build_graph(model: BaseChatModel, judges: Judges) -> Any:
    """Build and compile the trip planner graph.

    Args:
        model: The chat model used by every node.
        judges: Asks the Prefactor judges to score the running instance,
            given its ID.

    Returns:
        The compiled graph.
    """

    async def parse_request(state: TripState, config: RunnableConfig) -> TripState:
        parser = model.with_structured_output(TripRequest, method="function_calling")
        request = await parser.ainvoke(
            [SystemMessage(PARSE_PROMPT), _request_message(state)], config
        )
        assert isinstance(request, TripRequest)
        return {
            "request": request.model_dump(),
            "start_date": date.today().isoformat(),
        }

    async def plan_route(state: TripState, config: RunnableConfig) -> TripState:
        request = state["request"]
        agent = create_agent(
            model=model,
            tools=ROUTE_TOOLS,
            system_prompt=ROUTE_PROMPT.format(
                origin=request["origin"],
                destination=request["destination"],
                length=(
                    f"a {request['days']}-day trip"
                    if request["days"]
                    else "a trip of as many days as the distance needs"
                ),
            ),
            response_format=ToolStrategy(RoutePlan),
        )
        result = await agent.ainvoke({"messages": [_request_message(state)]}, config)
        plan: RoutePlan = result["structured_response"]
        # With no number of days from the user, use the fewest days that
        # keep each day within the driving limit.
        days = request["days"] or min(
            MAX_DAYS, max(1, math.ceil(plan.distance_km / DAILY_DRIVING_LIMIT_KM))
        )
        return {
            "request": {**request, "days": days},
            "route": plan.model_dump(exclude={"stops"}),
            "stops": [stop.model_dump() for stop in plan.stops],
        }

    async def research_stops(state: TripState, config: RunnableConfig) -> TripState:
        interests = ", ".join(state["request"]["interests"])
        research: dict[str, dict[str, Any]] = {}
        for stop in state["stops"]:
            agent = create_agent(
                model=model,
                tools=RESEARCH_TOOLS,
                system_prompt=RESEARCH_PROMPT.format(interests=interests, **stop),
                response_format=ToolStrategy(StopResearch),
            )
            result = await agent.ainvoke(
                {"messages": [_request_message(state)]}, config
            )
            findings: StopResearch = result["structured_response"]
            point = {"lat": stop["lat"], "lon": stop["lon"]}
            notes = {
                **findings.model_dump(),
                "forecast": await weather_forecast.ainvoke(point, config),
            }
            # The trip ends at the destination, so no one stays the night there.
            if stop is not state["stops"][-1]:
                notes["accommodation"] = await find_accommodation.ainvoke(point, config)
            research[stop["name"]] = notes
        return {"research": research}

    async def draft_itinerary(state: TripState, config: RunnableConfig) -> TripState:
        request = state["request"]
        route = state["route"]
        if route.get("problem"):
            prompt = PROBLEM_PROMPT.format(
                origin=request["origin"],
                destination=request["destination"],
                problem=route["problem"],
            )
        else:
            prompt = DRAFT_PROMPT.format(
                origin=request["origin"],
                destination=request["destination"],
                days=request["days"],
                day_dates=_day_dates(state["start_date"], request["days"]),
                interests=", ".join(request["interests"]),
                limit_km=DAILY_DRIVING_LIMIT_KM,
                min_daily_km=MIN_DAILY_KM,
                distance_km=round(route["distance_km"]),
                duration_hours=route["duration_hours"],
                stops=json.dumps(state["stops"], indent=2),
                research=json.dumps(state["research"], indent=2),
            )
        if state.get("feedback"):
            prompt += FEEDBACK_PROMPT.format(feedback=state["feedback"])
        response = await model.ainvoke(
            [SystemMessage(prompt), _request_message(state)], config
        )
        return {"draft": response.text}

    async def evaluate(state: TripState, config: RunnableConfig) -> TripState:
        instance = config["configurable"]["prefactor_instance"]
        checks = await judges(instance.id)
        attempt = state.get("attempt", 0) + 1
        payload = quality_payload(checks, attempt)
        await instance.record_quality(QUALITY_SCHEMA_NAME, payload)
        return {
            "quality": payload,
            "attempt": attempt,
            "feedback": "\n".join(
                f"- {check.name}: {check.detail}"
                for check in checks
                if not check.passed
            ),
        }

    def after_evaluate(state: TripState) -> Literal["draft_itinerary", "finalise"]:
        if state["quality"]["passed"] or state["attempt"] >= MAX_ATTEMPTS:
            return "finalise"
        return "draft_itinerary"

    async def finalise(state: TripState) -> TripState:
        request = state["request"]
        slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            f"{request['origin']} to {request['destination']}".lower(),
        ).strip("-")
        OUT_DIR.mkdir(exist_ok=True)
        # A timestamp keeps plans from separate runs in separate files.
        path = OUT_DIR / f"{slug}-{datetime.now():%Y%m%d-%H%M%S}.md"
        path.write_text(state["draft"])
        return {"output_path": str(path)}

    # ty does not match TypedDict classes to LangGraph's StateLike bound.
    graph = StateGraph(TripState)  # ty: ignore[invalid-argument-type]
    graph.add_node("parse_request", parse_request)
    graph.add_node("plan_route", plan_route)
    graph.add_node("research_stops", research_stops)
    graph.add_node("draft_itinerary", draft_itinerary)
    graph.add_node("evaluate", evaluate)
    graph.add_node("finalise", finalise)
    graph.add_edge(START, "parse_request")
    graph.add_edge("parse_request", "plan_route")
    graph.add_edge("plan_route", "research_stops")
    graph.add_edge("research_stops", "draft_itinerary")
    graph.add_edge("draft_itinerary", "evaluate")
    graph.add_conditional_edges("evaluate", after_evaluate)
    graph.add_edge("finalise", END)
    return graph.compile()
