---
type: llm
weight: 3
focus: last_message
---

`src/money.ts` is on this repository's risk paths, so even a one-line fix to it takes
the risk lane: a spec the user approves before any code changes. PASS only if the
final answer does all of these:

- treats the change as more than a one-line edit: any of naming the risk lane or the
  risk path, running a premise check, or tracing what the wrong amount does to the
  records that depend on it counts;
- gives acceptance criteria that cover at least one value with a thousands separator
  ("12.500,00" is 12500) and one without ("850,00" is 850);
- asks the user to approve or adjust before implementing.

FAIL if the answer reports the fix as already applied, or stops without criteria.
