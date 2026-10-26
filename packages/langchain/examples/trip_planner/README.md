# Trip planner (LangGraph)

A LangGraph agent that plans a road trip between two places and writes the plan as a Markdown document. Before it saves a plan, it asks the agent's Prefactor judges to review each draft, records their verdicts in Prefactor as quality, and revises the plan until every judge passes it. It is traced in Prefactor with `PrefactorCallbackHandler`.

The planner uses free public APIs that need no key:

- [Nominatim](https://nominatim.org/) (OpenStreetMap) to find places, the towns along a route and places to stay
- [OSRM](https://project-osrm.org/) for driving routes
- [Wikipedia](https://www.mediawiki.org/wiki/API:Main_page) for place summaries and nearby attractions
- [Open-Meteo](https://open-meteo.com/) for weather forecasts

Responses are cached for the life of the process, and Nominatim requests are spaced one second apart to follow its [usage policy](https://operations.osmfoundation.org/policies/nominatim/).

## The graph

```mermaid
flowchart LR
    START --> parse_request --> plan_route --> research_stops --> draft_itinerary --> evaluate
    evaluate -- failed, fewer than 3 drafts --> draft_itinerary
    evaluate -- passed, or 3 drafts --> finalise --> END
```

| Node | What it does |
|---|---|
| `parse_request` | Extracts the origin, destination, number of days and interests from the request |
| `plan_route` | An agent with `geocode`, `get_route` and `find_towns_along_route` that chooses 2 to 6 stops |
| `research_stops` | Runs a research agent for each stop in turn, with `wikipedia_summary` and `nearby_attractions`, then gets the stop's 16-day forecast with `weather_forecast` and, for every stop except the destination, places to stay within 20 km with `find_accommodation`, which also checks whether each place's website loads |
| `draft_itinerary` | Writes the day-by-day plan in Markdown, with a date and the forecast for each day and up to two places to stay for each night, using the judges' feedback on later drafts |
| `evaluate` | Asks the agent's Prefactor judges to review the run so far, records their verdicts as `trip_plan_quality` quality, and sends the graph back to `draft_itinerary` when a judge fails the draft |
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
| `TOGETHER_API_KEY` | Together AI API key |
| `TOGETHER_MODEL` | Together AI model; defaults to `moonshotai/Kimi-K3`; any model you use must support tool calling |
| `PREFACTOR_API_URL` | Prefactor API URL, for example `http://localhost:4000` for a local server |
| `PREFACTOR_API_TOKEN` | Prefactor API token |
| `PREFACTOR_AGENT_ID` | Prefactor agent ID; omit it when the token is scoped to an agent deployment |
| `PREFACTOR_ENVIRONMENT_ID` | Prefactor environment ID; needed only for the first run of an agent that has no deployments |

## Run

From `packages/langchain/examples/trip_planner`:

```bash
uv run python main.py Melbourne Adelaide
uv run python main.py "San Francisco" "Los Angeles" --days 3
```

Without `--days`, the planner uses the fewest days that keep each day within 400 km of driving.

A run takes a few minutes, mostly in route lookups, research and judging. When it finishes, the script prints the plan in the terminal, then each judge's verdict on the final draft, and saves the plan as Markdown.

The plan starts with a short summary, then a "Before you go" note when the trip is a poor idea as asked, and an "At a glance" list with one line per day: date, route, driving distance, weather and where to stay. It uses no Markdown tables, because Prefactor's conversation view renders plain CommonMark. A section for each day follows, with a line giving the date, driving distance and weather, then "See and do" and "Where to stay" lists.

## What you see in Prefactor

Open the agent instance and choose the conversation view:

- one user message with the request
- an agent run divider for the graph run (`langchain:agent`)
- a card for each node in order (`langchain:node`), named by the node
- under each node, its model calls (`langchain:llm`), tool calls and tool results (`langchain:tool`); calls made by the route and research agents appear under the node that ran them
- the trip plan is the reply to the last `draft_itinerary` model call
- a `trip_plan_quality` quality entry for each draft, with its score, attempt number and every judge's verdict
- a quality entry from each judge; it holds the latest verdict, from the last draft or from the review after the run completes

## Evals

The evals are Prefactor judges. A judge is an agent in Prefactor that reads the whole record of a run, including the model calls, tool calls, tool results and the model's thinking, and gives a pass or fail verdict with an explanation.

The `evaluate` node runs every judge associated with the trip planner agent on each draft, before the plan is saved:

1. It waits until the draft's model and tool calls have reached Prefactor. The SDK sends span updates from a background queue.
2. It asks each judge to score the running instance through `POST /api/v1/agent_instance/{id}/judge`, and waits for the verdicts.
3. It records the verdicts as `trip_plan_quality` quality. The score is the share of judges that passed, out of 100.
4. When a judge fails the draft, the graph sends its explanation back to `draft_itinerary` as feedback. After 3 drafts the graph saves the last draft whether or not it passed.

Set the judges up in the Prefactor app. Create a judge agent with a hosted version, then associate it with the trip planner agent. With the trigger set to on completion, the judge also reviews the finished run. The criterion for each judge is in [`judges/`](judges/). The judges used for this example are:

| Judge | Fails the draft when |
|---|---|
| Trip plan rules | The plan does not start and end where asked, has the wrong number of days, ends a day somewhere the route tools did not return, has a day with more than 400 km of driving, or gives a date or weather that does not match the forecast at that day's end stop. Day 1 is the day of the run and Day N is N - 1 days later |
| Trip plan accommodation | A night has no "Where to stay" section, or names a place that `find_accommodation` did not return for that day's end stop, or gives its type, town or distance wrongly, or links a website whose check was not `ok` (a judge cannot open links, so it relies on the check in the tool result), or ends at a stop with nowhere to stay when another stop within the driving limit had somewhere |
| Trip plan hallucination | The latest draft states something about a place that is not in the run's tool results |
| Trip plan locations | `geocode` found no place, or a different place from the one the user meant, or there is no driving route, and the plan does not say so; or the plan says a place could not be found when it was |
| Trip worth taking | The trip is a poor idea as asked and the plan has no "Before you go" note saying why. It is a poor idea when the route is over 400 km a day or under 250 km a day, rain is likely on most days, the weather is extreme, or there are few places to stop or stay |
| Trip plan makes sense | A "See and do" suggestion is something a traveller would not choose to do: a place not open to visitors, such as a hospital, prison, school or plain railway station, a place named with no reason to go, or filler such as visiting "between showers" or "stock up on food" |

When `plan_route` cannot find a place or a driving route, it leaves the stops empty and the plan is a short "Before you go" note saying why. The other judges pass a plan like this and leave it to the locations judge.

`nearby_attractions` returns each Wikipedia article's short description, such as "Australian medium security prison" or "Psychiatric prison now museum", so the researcher can leave out places that are not for visitors.

The unit tests for the judge client use a fake Prefactor API. From the repository root:

```bash
mise run test packages/langchain/examples/trip_planner/test_evals.py
```

### Run the eval set

`run_evals.py` runs three fixed routes, each as an agent instance with the `eval` purpose, and exits with status 1 when any final plan fails. From `packages/langchain/examples/trip_planner`:

```bash
uv run python run_evals.py
```

In Prefactor, these runs carry an eval label in the agent's list of instances, which sets them apart from live runs.

Each span is created with an HTTP request before the step continues, which adds a little latency to every step.
