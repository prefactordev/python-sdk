# Criterion: trip plan makes sense

Decide whether every suggestion in the latest trip plan is something a real traveller would want to do. The plan is the last Assistant entry that starts with a `# ` heading. Earlier drafts and later entries are not the plan, and the run may still be in progress. The traveller's interests are in the `TripRequest` tool call. What each place is comes from the `description` field in the `nearby_attractions` tool results and from the `wikipedia_summary` tool results. The weather is in the `weather_forecast` tool results.

# Rubric

- pass: every bullet in every "See and do" section, and every highlight in the opening sentences, meets all of these:
  - it is something a traveller with these interests would choose to spend time on
  - the place is open to visitors; a museum, gallery, park, lookout, heritage site, winery, beach, market, walk or landmark qualifies
  - it says what the place is or what to do there, so the traveller can decide whether to go
  - it suits that day's weather; for example, it does not suggest a long outdoor walk on a day with heavy rain likely, unless it gives a shorter option
- fail: at least one suggestion breaks the rubric. These are failures:
  - a place that is not for visitors, such as a hospital, an active prison, a school, an airport, a government area, an electoral district, a suburb or locality, or a railway station that is not a museum or a heritage attraction
  - a place named with no reason to go, such as "Visit Aradale Mental Hospital" with no mention of tours or a museum
  - filler or padding: advice that is not an activity, such as visiting places "between showers", "check whether the festival is on", "stock up on food", "keep outdoor stops short", or driving to see a former rail locality
  - a detour longer than the day's main activity, or a suggestion that makes no sense for the place or the day
  - a highlight in the opening sentences that is itself one of these failures

# Rules

1. Use the descriptions in the tool results, and general knowledge of what kinds of places visitors go to, to decide whether a suggestion makes sense. A former hospital or prison that the tool results describe as a museum, or as open for tours, is a fair suggestion.
2. A single bullet saying a day is a driving day with little to see is a pass for that day.
3. Do not judge whether facts are grounded in the record, driving limits, dates, weather figures, or places to stay. Other judges check those.
4. A plan with no day sections, because a place could not be found or reached, passes.

# Explanation

Quote each suggestion that fails and say why. If all pass, say so in one sentence.
