# Criterion: trip worth taking

Decide whether the road trip, as the user asked for it, is worth taking, and whether the plan warns the user when it is not. The plan is the last Assistant entry that starts with a `# ` heading. Earlier drafts and later entries are not the plan, and the run may still be in progress. The trip's length in days is what the user asked for. When the user gave no number, the planner chose it, and the System entry of the plan's model call gives it; a length the planner chose is never a poor idea for having too many or too few days. The route distance and driving time are in the `get_route` tool result. The weather is in the `weather_forecast` tool results, and what there is to do at each stop is in the `nearby_attractions` and `wikipedia_summary` tool results.

A trip is a poor idea as asked when any of these is true:
- the days are too few to keep every day within 400 km of driving (route distance divided by days is more than 400 km)
- the days are more than the drive needs: the route distance divided by the days is under 250 km. For example, Melbourne to Adelaide is about 730 km, a one or two day drive, so four days is too many
- rain is 70% likely or more on most days of the trip, or the forecast shows extreme heat (40°C or more) or cold (0°C or less on the daily maximum)
- the route has few places to stop: `find_towns_along_route` returned fewer than two towns, or `find_accommodation` found nothing for most overnight stops

# Rubric

- pass: one of these is true:
  - the trip is a poor idea as asked, and the plan has a "Before you go" section that says so, gives the reason and suggests what would work better, such as more or fewer days
  - the trip is not a poor idea, and the plan has no "Before you go" section, or one whose reasons are supported by the tool results
  - the plan has no day sections because a place could not be found or reached, and says so (another judge checks this case)
- fail: one of these is true:
  - the trip is a poor idea as asked, and the plan has no "Before you go" section or does not give the reason
  - the "Before you go" section gives a reason that the tool results do not support, such as rain that the forecast does not show

# Rules

1. Work out the numbers from the tool results, not from the plan's own claims.
2. Judge only whether the trip is worth taking and whether the plan warns the user. The plan's other content is checked by other judges.

# Explanation

Give the route distance, the days, the distance per day, the weather across the trip and the number of stops with places to stay, say whether the trip is a poor idea as asked, and say whether the plan's "Before you go" section matches that.
