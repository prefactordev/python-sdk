# Criterion: trip plan accommodation

Decide whether the places to stay in the latest trip plan are correct and sensible. The plan is the last Assistant entry that starts with a `# ` heading. Earlier drafts and later entries are not the plan, and the run may still be in progress. The places to stay near each stop are in the tool results for `find_accommodation`. Each call's arguments give the stop's latitude and longitude; match them to the stops in the `find_towns_along_route` and `geocode` tool results, or to the stops listed in the System entry of the plan's model call. The driving distance to each stop is its `km_from_start`.

# Rubric

- pass: the plan meets all of these:
  - every day except the last has a "Where to stay" section, because the traveller spends that night away
  - every place named in a "Where to stay" section, or in the "Stay" part of the "At a glance" list, appears in the `find_accommodation` result for that day's end stop
  - each named place's type, town and distance match that result, allowing distances rounded to whole kilometres
  - every website link in the plan is the `website` that `find_accommodation` gave for that place, and its `website_check` is `ok`; a link whose check is `dead` or `unverified`, or that has no check, is a failure because the traveller may not be able to open it
  - when `find_accommodation` returned nothing for a day's end stop, that day's "Where to stay" section says no accommodation was found and names no place
  - no day ends at a stop where `find_accommodation` found nothing if a different stop with accommodation would have kept that day and the next day within 400 km of driving
- fail: the plan breaks any of these rules.

# Rules

1. The last day ends at the destination and the trip ends there, so it does not need a "Where to stay" section. One on the last day is not a failure.
2. A place listed for a different stop does not count as a match, even if it is real.
3. You cannot open links yourself. Use `website_check` in the tool result as the only evidence of whether a link works.
4. Do not judge the quality, price or reviews of a place. Judge only whether the plan matches the tool results and whether the overnight stops are sensible.
5. Driving limits, dates and weather are checked by other judges. Use driving distances only for the last rule in the rubric.
6. A plan with no day sections, because a place could not be found or reached, passes. Another judge checks that case.

# Explanation

List each night with its end stop, the places named and any links with their `website_check`, and say which rule, if any, it breaks.
