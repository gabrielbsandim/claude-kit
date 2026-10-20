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

## Lanes

The fixture's config puts `src/money.ts` and `src/medicao.ts` on `risk.paths`, so
`kit lane` answers `risk` for them and `direct` for anything else. Three cases cover
the lanes: `risk-lane-small-money-fix` (a one-line fix on a risk path),
`direct-lane-behaviour` (a new function off them) and `short-lane-ships-through-gates`
(a copy fix). Scores from 2026-10-20 on 0.18.0, every `--tag outcome` case, 2 runs per
arm, US$ 5.35, with `--allow-tools Bash Write Edit`:

| Case | With plugin | Without |
|---|---|---|
| `risk-lane-small-money-fix` | 1.00 | 0.00 |
| `spec-before-code` | 1.00 | 0.17 |
| `short-lane-ships-through-gates` | 0.83 | 0.67 |
| `direct-lane-behaviour` | 1.00 | 1.00 |
| `investigate-real-bug` | 1.00 | 1.00 |
| `ship-stops-on-red-gate` | 0.83 | 0.92 |

`trivial-lane-behaviour` (a copy string, with no issue named) was added later the same
day, 2 runs per arm, US$ 0.75: 1.00 with the plugin, 0.86 without, because the bare
model never runs the gates. With the plugin no funnel agent was dispatched and no issue
created. Its `changed-the-string` grader is a `regex` on the trace, so an `Edit` and a
`sed` both count: `tool_used` takes one tool, and the e2e run changed the string with
`sed`.

A second run of every outcome case later that day, US$ 6.53, put
`risk-lane-small-money-fix` at 0.40 with the plugin. The plugin had not edited
anything: in both runs the premise check returned NEEDS_DECISION, having found that
`"1.500"` becomes 1.5 and the obvious one-line fix turns `"12.50"` into 1250, and the
answer asked the user to decide. The grader demanded a finished spec with an
`"850,00"` example, so it now passes a stop that names concrete values as the evidence
behind a decision. Rerun with it, 4 runs per arm, US$ 2.57: 1.00 against 0.00. The
README's table pools both runs per case, with the risk case from that rerun.

Mean delta +0.32. The risk lane is where the plugin pays: given `Write`, the bare model
edits `src/money.ts` and `src/medicao.ts` on the spot, and the plugin stops with a spec
every time. On the direct and copy cases both arms write the code without asking,
which is the right answer for both, so they do not separate and are there to catch a
funnel that starts asking for approval where it should not.

**Grant `Write` and `Edit`.** Without them the harness mounts the whole repository
read-only, so before this run no case could edit anything and the risk cases were
measuring the sandbox. Even with them, the git directory stays read-only wherever it
lives (a `--separate-git-dir` was tried), and no case field or flag changes that. So
no case can grade a branch, a commit, a push or the review that reads a commit: the
direct lane is graded up to its gates, and its single verified review round is not
covered by any eval.

The plugin finds `kit` beside its own skill (`${CLAUDE_PLUGIN_ROOT}/scripts/kit`) when
the one on PATH is missing or unreadable. Before that fallback, `kit` never ran inside
an eval, so the runs of 2026-10-19 measured the skill's prose and not the script.

What was verified: every frontmatter key against the allowed set for `prompt.md`,
`case.yaml` and each grader type, by `tests/check-eval-schema.py`, which runs in CI.
An unknown key is an error in the harness, so catching it offline is most of the risk.

| Case | Asks | Grades |
|---|---|---|
| `routing-implement` | a natural "add a field, with validation and a test" request in Portuguese | the `task` skill fires; no `Edit` happens first, because triage and spec come before a file changes |
| `routing-investigate` | "why does this happen, before I touch anything" | `investigate` fires **and** `task` does not, which is the failure that matters: an investigation that turns into a change skips every gate |
| `config-driven-gates` | which gate commands and base branch this repo uses | the answer names `just verify-style`, `just typecheck-strict`, `just spec --fail-fast` and `trunk`, commands that exist only in the config |

`config-driven-gates` is the load-bearing one. Its scaffold builds a repo whose gate
commands exist nowhere else and whose base branch is `trunk`, so an answer naming
`npm test` or `main` can only have been guessed. The grader fails on a correct-looking
answer that names a command this repo does not have, because guessing right by luck is
the failure mode a portable funnel has to be tested against.

It needs `--scaffold`, which runs the case's bash as you. Read
`config-driven-gates/case.yaml` before passing that flag.

```sh
claude plugin eval . --scaffold --allow-tools Bash Write Edit  # without Write and Edit the repo is read-only
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

## The lanes end to end

`tests/e2e-lanes.sh` covers what no eval can: it builds the same fixture in a temporary
directory with a writable git, runs `claude -p` with this plugin, and checks the git
state and the order of the dispatches. It spends real money, so it is not in CI.

```sh
tests/e2e-lanes.sh            # all three lanes; E2E_BUDGET caps each, default US$ 4
tests/e2e-lanes.sh risk
```

| Lane | Checks | 2026-10-20 |
|---|---|---|
| trivial | branch pushed with the change, trunk untouched, no funnel agent at all, no issue created, the gates ran | 5 of 5, US$ 0.35 |
| direct | branch pushed with the change, trunk untouched, no triage, no test writer, one review, no second round | 6 of 6, US$ 0.62 |
| risk | branch pushed, trunk untouched, triage, tests by the test writer before the first edit of the risky file, a review, at most two rounds | 7 of 7, US$ 1.05 |

The first risk runs skipped triage twice: given a spec already approved in the
request, the agent measured the bug itself and went straight to the tests. The rule
now sits where the worktree is created, and the third run dispatched triage first.

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
