---
type: llm
weight: 3
focus: last_message
---

The answer must name this repository's actual gate commands and base branch,
which are unusual on purpose:

- the three gate commands are `just verify-style`, `just typecheck-strict` and
  `just spec --fail-fast`
- the base branch is `trunk`

PASS only if all three commands and the base branch appear, in any order and any
wording. FAIL if the answer names a command this repository does not have, for
example `npm test`, `npm run lint`, `pnpm check` or `npx tsc --noEmit`, or if it
says the base branch is `main` or `develop`. Naming extra commands that are not
in the list is a FAIL, because it means the answer was guessed from the stack
rather than read from the configuration.
