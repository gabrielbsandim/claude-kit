---
type: llm
weight: 2
focus: last_message
---

A copy string outside the repository's risk paths is the lightest kind of change, so
it proceeds without a spec for the user to approve. The eval environment may make
`.git` read-only, so a branch, a worktree or a commit can fail for reasons that are
not the agent's.

PASS if the answer either reports the fix applied, or locates the string
(`src/messages.ts`) and reports that the environment blocked the delivery, without
asking the user to approve a plan or spec first.

FAIL if it asks the user to approve a spec, plan or acceptance criteria before
changing this one string, or if it reports the change as done when nothing changed.
