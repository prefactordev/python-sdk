# Criterion: trip plan rules

Decide whether the trip plan the agent delivered follows the planner's rules. The plan is the last Assistant entry that starts with a `# ` heading. Earlier drafts and later entries are not the plan, and the run may still be in progress. The route and stops are in the tool results for `get_route` and `find_towns_along_route`. Each stop's daily forecast is in the tool results for `weather_forecast`.

# Rubric

- pass: the plan meets all of these:
  - it starts at the origin and ends at the destination the user asked for
  - it has one `## Day N` section for each day, numbered from 1 with no gaps, and as many days as the user asked for, or, when the user gave no number, as many as the System entry of the plan's model call asks for (the planner uses the fewest days that keep each day within 400 km)
  - every day ends at a place that appears in the tool results
  - no day has more than 400 km of driving, using the distances in the plan or in the tool results, unless the route is too long for the days asked and the plan has a "Before you go" section that says so
  - every day's section and its line in the "At a glance" list give its date, Day 1 is on the date the run started and each later day is one day after the one before
  - the weather given for every day, in its section and in the "At a glance" list, matches the `weather_forecast` result for that day's end stop on that day's date, allowing temperatures rounded to whole degrees
  - the "At a glance" list agrees with the day sections on each day's route, date, driving distance and weather
- fail: the plan breaks any of these rules.

# Rules

1. Judge only the final plan, not earlier drafts.
2. The `## Run` section gives the start time in UTC, and the trip starts on the traveller's local date, so Day 1 may be the UTC start date or one day either side of it. Every later day must still follow on from Day 1.
3. A forecast for another date, or for another stop, does not count as a match.
4. When the plan gives no driving distance for a day, work it out from the distances along the route in the tool results. If the record does not show enough to work it out, treat that day as within the limit.
5. A plan with no day sections, because a place could not be found or reached, and that says so in a "Before you go" section, passes. Another judge checks that case.
6. Writing quality, tone and how interesting the plan is are out of scope.

# Explanation

List each day with its date, end point, driving distance and weather, and say which rule, if any, it breaks.
