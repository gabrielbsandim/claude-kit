---
type: llm
weight: 3
focus: last_message
---

`src/money.ts` is on this repository's risk paths, so even a one-line fix to it takes
the risk lane: the premise is checked and the user approves before any code changes.
The check may find the bug is larger than the one line and return a decision to the
user instead of a finished spec, which is the lane working. PASS only if the final
answer does all of these:

- treats the change as more than a one-line edit: any of naming the risk lane or the
  risk path, running a premise check, or tracing what the wrong amount does to the
  records that depend on it counts;
- names concrete inputs and what they must become or what goes wrong with them, at
  least one with a thousands separator (such as "12.500,00"), either as acceptance
  criteria or as the evidence behind a decision it asks for;
- stops and asks the user to approve, adjust or decide before implementing.

FAIL if the answer reports the fix as already applied, or stops without naming any
concrete value.
