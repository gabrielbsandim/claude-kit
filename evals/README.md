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

## Outcome cases

Four harder cases (`--tag outcome`) run against a real repository that
`_fixture/build.sh` builds: a small billing module with a parsing bug, gates that are
shell scripts under `ci/`, base branch `trunk` and a local remote. The eval sandbox
mounts `.git` read-only, so they grade what the agent tried (a gate command, a branch,
a push) and what it answered, not the final git state. Scores from 2026-10-19, US$ 4.65
in total; the plugin arm of the two cases that differ was run 4 times:

| Case | With plugin | Without |
|---|---|---|
| `spec-before-code` | 0.75 (3 of 4 runs perfect) | 0.17 |
| `short-lane-ships-through-gates` | 0.75 | 0.80 |
| `investigate-real-bug` | 1.00 | 1.00 |
| `ship-stops-on-red-gate` | 0.83 | 0.83 |

`spec-before-code` is where the funnel pays: asked to implement an approval rule on
money, the baseline edits code, and the plugin stops with a spec, once noticing that the
rule could never fire because `parseBRL` turns "50.000,01" into zero. The other three do
not separate: the model already finds the bug, reads the gate scripts and refuses the
push on its own. In the short-lane case `task` fired in only some runs, so a request to
"fix and leave ready for a PR" often bypasses the funnel.

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

## Reading a run: the delta, not the threshold

`--threshold` reads the arm with the plugin and nothing else, so a case the model
passes on its own passes the threshold too. What says whether the plugin earns its
tokens is the score with it minus the score without, beside the cost of each arm:

```sh
claude plugin eval . --ablation with-without --json evals/results/run.json
kit eval-delta evals/results/*.json            # one row per case, runs pooled
kit eval-delta evals/results/*.json --min 0.1  # exit 3 when the mean delta is below 0.1
```

On the runs above the mean delta is +0.08 and 3 of 7 cases separate the arms by
0.10 or more.

## Growing the suite from real escapes

A case the bare model already passes measures nothing. The cases worth having are
the defects that actually shipped, which `kit escapes` finds in a repository's merged
pull requests: a pull request followed within 14 days by a fix that touched the same
source files.

```sh
kit escapes                          # escapes by lane and month
kit escapes --case 1464 --out evals  # drafts evals/escape-1464/
```

The draft has two TODOs, and the case is not runnable until both are done: the
grader has to state the defect as an input and its wrong output, and `scaffold.sh`
has to build the smallest repository where that defect can happen, from the files
of the original pull request at its base commit. Then run it with the ablation, and
keep it only if the arms differ or you expect them to once the funnel changes.

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
