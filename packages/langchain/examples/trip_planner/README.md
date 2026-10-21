# Trip planner (LangGraph)

A LangGraph agent that plans a road trip between two places and writes the plan as a Markdown document. It is traced in Prefactor with `PrefactorCallbackHandler`.

The planner uses free public APIs that need no key:

- [Nominatim](https://nominatim.org/) (OpenStreetMap) to find places and the towns along a route
- [OSRM](https://project-osrm.org/) for driving routes
- [Wikipedia](https://www.mediawiki.org/wiki/API:Main_page) for place summaries and nearby attractions
- [Open-Meteo](https://open-meteo.com/) for weather forecasts

Responses are cached for the life of the process, and Nominatim requests are spaced one second apart to follow its [usage policy](https://operations.osmfoundation.org/policies/nominatim/).

## The graph

```mermaid
flowchart LR
    START --> parse_request --> plan_route --> research_stops --> draft_itinerary --> finalise --> END
```

| Node | What it does |
|---|---|
| `parse_request` | Extracts the origin, destination, number of days and interests from the request |
| `plan_route` | An agent with `geocode`, `get_route` and `find_towns_along_route` that chooses 2 to 6 stops |
| `research_stops` | Runs a research agent for each stop in turn, with `wikipedia_summary`, `nearby_attractions` and `weather_forecast` |
| `draft_itinerary` | Writes the day-by-day plan in Markdown |
| `finalise` | Saves the plan to `out/<origin>-to-<destination>.md` |

Every model call sends the node's task as the system message and the original request as the only human message.

## Setup

From the repository root:

```bash
mise run install
cp packages/langchain/examples/trip_planner/.env.example .env  # then fill it in
```

| Variable | Meaning |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `PREFACTOR_API_URL` | Prefactor API URL, for example `http://localhost:4000` for a local server |
| `PREFACTOR_API_TOKEN` | Prefactor API token |
| `PREFACTOR_AGENT_ID` | Prefactor agent ID; omit it when the token is scoped to an agent deployment |

## Run

From `packages/langchain/examples/trip_planner`:

```bash
uv run python main.py "Plan a 4-day road trip from Melbourne to Adelaide. I like wine and the coast."
```

A run takes a few minutes, mostly in route lookups and research.

## What you see in Prefactor

Open the agent instance and choose the conversation view:

- one user message with the request
- an agent run divider for the graph run (`langchain:agent`)
- a card for each node in order (`langchain:node`), named by the node
- under each node, its model calls (`langchain:llm`), tool calls and tool results (`langchain:tool`); calls made by the route and research agents appear under the node that ran them
- the last model call's reply is the trip plan

Each span is created with an HTTP request before the step continues, which adds a little latency to every step.
