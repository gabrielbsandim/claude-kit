# Eval suite

First recorded run, 2026-10-19 on Claude Code 2.1.304, with the no-plugin baseline
(`--ablation with-without`), US$ 1.65 in total:

| Case | With plugin | Without |
|---|---|---|
| `routing-investigate` | 1.00 | 0.50 |
| `routing-implement` | 1.00 (`task` fired 3/3) | 1.00 |
| `config-driven-gates` | 0.75 | 0.75 |

Only `routing-investigate` separates the arms. The other two are too easy: without the
plugin the model also holds off editing, and also finds `funnel.config.json` with Read,
so the Bash grader fails both arms alike.

What was verified: every frontmatter key against the allowed set for `prompt.md`,
`case.yaml` and each grader type, by `tests/check-eval-schema.py`, which runs in CI.
An unknown key is an error in the harness, so catching it offline is most of the risk.

| Case | Asks | Grades |
|---|---|---|
| `routing-implement` | a natural "add a field, with validation and a test" request in Portuguese | the `task` skill fires; no `Edit` happens first, because triage and spec come before a file changes |
| `routing-investigate` | "why does this happen, before I touch anything" | `investigate` fires **and** `task` does not, which is the failure that matters: an investigation that turns into a change skips every gate |
| `config-driven-gates` | which gate commands and base branch this repo uses | the answer names `just verify-style`, `just typecheck-strict`, `just spec --fail-fast` and `trunk`, and the run actually read the config |

`config-driven-gates` is the load-bearing one. Its scaffold builds a repo whose gate
commands exist nowhere else and whose base branch is `trunk`, so an answer naming
`npm test` or `main` can only have been guessed. The grader fails on a correct-looking
answer that names a command this repo does not have, because guessing right by luck is
the failure mode a portable funnel has to be tested against.

It needs `--scaffold`, which runs the case's bash as you. Read
`config-driven-gates/case.yaml` before passing that flag.

```sh
claude plugin eval . --scaffold --allow-tools Bash  # all three
claude plugin eval . --case 'routing-*'            # no scaffold needed
claude plugin eval . --json evals/results/run.json --threshold 0.8
```

## What is not covered

- **The review grouping.** The measured claim is that 7 lenses become 4 dispatches
  reading half the diff. Verifying it needs a repo with a real branch and a real diff,
  which a scaffold could build but has not. `kit review --dispatches` prints the
  grouping deterministically, so this one is better tested by asserting on that output
  than by grading an agent.
- **Reviewer discipline.** "Does not run git, reads the diff file once" is an agent
  instruction, and a `tool_used` grader with `min: 0, max: 0` on Bash matching `git`
  would test it. It is not here because the case needs a review to be in flight, which
  means a multi-turn scaffold.
- **The board adapters.** They mutate a real tracker, so they do not belong in an eval.
