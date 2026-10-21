"""The trip planner LangGraph graph.

START -> parse_request -> plan_route -> research_stops -> draft_itinerary
      -> evaluate -> finalise -> END

``evaluate`` sends the graph back to ``draft_itinerary`` with feedback when
a check fails, up to ``MAX_ATTEMPTS`` drafts.

Every model call sends the node's task as the system message and the user's
original request as the only human message, so Prefactor's conversation view
shows one user message for the whole run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, TypedDict

from evals import QUALITY_SCHEMA_NAME, judge, quality_payload, run_checks
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from tools import RESEARCH_TOOLS, ROUTE_TOOLS

OUT_DIR = Path(__file__).parent / "out"
MAX_ATTEMPTS = 3


class TripRequest(BaseModel):
    """What the user asked for."""

    origin: str = Field(description="Where the trip starts")
    destination: str = Field(description="Where the trip ends")
    days: int = Field(ge=1, le=14, description="Number of days for the trip")
    interests: list[str] = Field(description="What the traveller likes")


class Stop(BaseModel):
    """A town to stop at along the route."""

    name: str
    lat: float
    lon: float
    km_from_start: float


class RoutePlan(BaseModel):
    """The driving route and the stops chosen along it."""

    distance_km: float
    duration_hours: float
    stops: list[Stop] = Field(
        description="2 to 6 stops in driving order, ending at the destination"
    )


class StopResearch(BaseModel):
    """What the researcher found about one stop."""

    name: str
    summary: str = Field(description="Two or three sentences about the place")
    attractions: list[str] = Field(description="Places worth visiting nearby")
    weather: str = Field(description="One sentence on the forecast")


class TripState(TypedDict, total=False):
    """Graph state."""

    messages: list[BaseMessage]
    request: dict[str, Any]
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
of days, choose a sensible number for the distance. If it gives no interests, \
use ["food", "history"]."""

ROUTE_PROMPT = """\
Plan the driving route from {origin} to {destination} for a {days}-day trip.

1. Geocode the origin and the destination.
2. Get the route between them.
3. Find the towns along the route.
4. Choose 2 to 6 stops in driving order so that no day has more than about \
350 km of driving. The last stop must be the destination. Use only towns \
returned by the tools, plus the destination."""

RESEARCH_PROMPT = """\
Research {name} (lat {lat}, lon {lon}) as a stop on a road trip for someone \
who likes {interests}.

Use the Wikipedia summary, the nearby attractions and the weather forecast. \
Report only what the tools returned."""

DRAFT_PROMPT = """\
Write a {days}-day road trip plan from {origin} to {destination} in Markdown \
for someone who likes {interests}.

Use exactly this structure:

# {origin} to {destination}

One short paragraph that sums up the trip.

## Day 1: <start town> to <end town>

Driving: <km> km

Then a few bullet points on what to see and do.

Repeat the day section for every day, numbered from 1 to {days}. Each day \
must end at one of the stops below, and the last day must end at \
{destination}. Work out each day's driving from the stops' km_from_start \
values. Put only stop names in **bold**, and mention at least one stop in \
bold in each day. Use only the facts in the research notes.

Stops, in driving order:
{stops}

Research notes:
{research}"""

FEEDBACK_PROMPT = """

The previous draft failed these checks. Fix them in this draft:
{feedback}"""


def _request_message(state: TripState) -> HumanMessage:
    message = state["messages"][0]
    assert isinstance(message, HumanMessage)
    return message


def build_graph(model: BaseChatModel) -> Any:
    """Build and compile the trip planner graph.

    Args:
        model: The chat model used by every node.

    Returns:
        The compiled graph.
    """

    async def parse_request(state: TripState, config: RunnableConfig) -> TripState:
        parser = model.with_structured_output(TripRequest, method="function_calling")
        request = await parser.ainvoke(
            [SystemMessage(PARSE_PROMPT), _request_message(state)], config
        )
        assert isinstance(request, TripRequest)
        return {"request": request.model_dump()}

    async def plan_route(state: TripState, config: RunnableConfig) -> TripState:
        agent = create_agent(
            model=model,
            tools=ROUTE_TOOLS,
            system_prompt=ROUTE_PROMPT.format(**state["request"]),
            response_format=ToolStrategy(RoutePlan),
        )
        result = await agent.ainvoke({"messages": [_request_message(state)]}, config)
        plan: RoutePlan = result["structured_response"]
        return {
            "route": {
                "distance_km": plan.distance_km,
                "duration_hours": plan.duration_hours,
            },
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
            research[stop["name"]] = findings.model_dump()
        return {"research": research}

    async def draft_itinerary(state: TripState, config: RunnableConfig) -> TripState:
        request = state["request"]
        prompt = DRAFT_PROMPT.format(
            origin=request["origin"],
            destination=request["destination"],
            days=request["days"],
            interests=", ".join(request["interests"]),
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
        checks = run_checks(dict(state))
        checks.append(await judge(model, dict(state), _request_message(state), config))
        attempt = state.get("attempt", 0) + 1
        payload = quality_payload(checks, attempt)
        instance = config["configurable"]["prefactor_instance"]
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
        path = OUT_DIR / f"{slug}.md"
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
