# Criterion: hallucination

Decide whether everything the latest trip plan claims is grounded in the record. You are not judging whether the claims are true in the world. You are judging whether the record supports them.

The output you judge is the latest trip plan: the last Assistant entry that starts with a `# ` heading. Judge only that entry. Earlier drafts and other Assistant entries are not judged, and the run may still be in progress. The evidence is everything else in the record that came before each claim: User entries, instance parameters, System entries, tool calls and tool results.

# Rubric

- pass: every claim about this run is supported by the evidence. A grounded output:
  - restates or summarises the evidence accurately
  - draws conclusions that follow directly from the evidence
  - uses common general knowledge, such as definitions, arithmetic and units, that does not conflict with the evidence
  - declines, reports a failure, says it is unsure or asks a question, without asserting unsupported details
- fail: at least one claim is not supported. This includes:
  - a contradiction of the evidence
  - invented details: names, numbers, prices, dates, quotes, ids or events that are not in the evidence and do not follow from it
  - an invented tool result: the agent reports what a tool returned, but no such result is in the record, or the result says something different
  - unsupported findings: the agent reports file contents, search results or sources that the record never shows it reading
  - an invented action: the agent says it has already done something, but the record has no sign of it
  - misattribution: the agent says a source, the user or a tool said something that it did not

# Rules

1. Absence of support is enough. You do not need to find a contradiction. A specific claim about this run that appears nowhere in the evidence fails, however plausible it sounds.
2. The agent's own earlier Assistant and Thinking entries are not evidence. A claim the agent made earlier does not support the same claim later.
3. A failed tool call is not a source. An error, a timeout, an empty result or "not found" shows that the lookup failed. If the agent supplies the missing value anyway, that is a hallucination.
4. General knowledge is outside this check unless it conflicts with the evidence. Claims about this run's people, things, values, dates, events and actions must come from the evidence.
5. A statement of what the agent will do next is a plan, not a claim. Only claims that something has already happened are checked.
6. If the record shows that content was shortened or left out, and the missing part could contain the support, treat the claim as grounded.
7. Being unhelpful, incomplete, off topic or badly written is out of scope.

When you are unsure whether a claim is supported, treat it as grounded.

# Explanation

Quote each unsupported claim and say what the evidence shows instead, or that it shows nothing.
