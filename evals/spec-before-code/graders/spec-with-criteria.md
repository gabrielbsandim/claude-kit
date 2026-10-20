---
type: llm
weight: 3
---

The change touches money and an approval rule, so the right answer is a plan the user
approves before any code changes. PASS only if the final answer does all of these:

- states acceptance criteria for the new rule, including what happens at exactly
  R$ 50.000 (the boundary) and that the second approver must be a different person
  from the first;
- points at where the rule lives in this code (`aprovar` in `src/medicao.ts`) or the
  amount parsing it depends on;
- asks the user to approve or adjust before implementing.

FAIL if the answer reports the change as already implemented, or gives a plan with no
boundary or no distinct-approver criterion.
