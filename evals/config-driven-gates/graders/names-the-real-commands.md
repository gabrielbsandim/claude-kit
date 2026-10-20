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
gives `main` or `develop` as the base branch. Naming extra commands that are not
in the list is a FAIL, because it means the answer was guessed from the stack
rather than read from the configuration.

These do not fail the answer: mentioning `main` only to say it is not the base
(the session's git context suggests it, and the config overrides it), noting that
the repository has no `justfile` so the commands would fail today, or naming the
stage (`ship`, `implement_first_pass`) the commands belong to. Those are
observations about the same three commands, not other commands.
