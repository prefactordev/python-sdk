# Criterion: trip plan locations

Decide whether the planner found the places the user asked for, and told the user when it could not. The plan is the last Assistant entry that starts with a `# ` heading. Earlier drafts and later entries are not the plan, and the run may still be in progress. The user's request is the User entry. The places the planner found are in the tool results for `geocode`, and the driving route is in the tool results for `get_route` and `find_towns_along_route`.

# Rubric

- pass: one of these is true:
  - `geocode` found a real place for both the origin and the destination, each is the place the user most likely meant, a driving route between them exists in the `get_route` result, and the plan's title and day sections start at the origin and end at the destination
  - a place was not found, `geocode` found a different place from the one the user most likely meant, or there is no driving route, and the plan has no day sections and has a "Before you go" section that tells the user this
- fail: any of these is true:
  - the plan gives a day-by-day trip although a place was not found, was the wrong place or cannot be reached by road
  - `geocode` found a different place from the one the user meant, such as a town of the same name in another country or state, and the plan does not say so
  - the plan says a place could not be found or reached when the record shows it was
  - the plan's start or end is not the place `geocode` found for the origin or destination

# Rules

1. Use general knowledge of geography to decide which place the user most likely meant. When the user gives only a city name, the best-known place of that name is the one they meant, unless other places in the request point elsewhere. For example, a trip from Melbourne to Adelaide means the Australian cities.
2. Two places that cannot be joined by road, such as places separated by sea with no car ferry in the route, have no driving route.
3. Judge only the locations. Driving limits, dates, weather, places to stay and what to see are checked by other judges.

# Explanation

Name the origin and destination the user asked for, what `geocode` found for each, whether a driving route exists, and what the plan did.
