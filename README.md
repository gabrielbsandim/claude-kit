# task-funnel

**Give Claude Code a task. Get back a pull request you can trust.**

A Claude Code plugin that turns "fix this" into a branch in its own worktree, with your
own lint, type and test commands run, a review whose every finding is checked before it
costs a fix, and a draft pull request with your board card moved. A change that can
hurt (money, permissions, data) stops for your approval before any code is written.

```
/task-funnel:task 575
```

## Not every task takes the same path

The funnel picks a lane by what a change can break, not by its size, and your
`risk.paths` decide. A simple change goes straight through; only a risky one pays for
the extra checks.

| Lane | For | What runs |
| --- | --- | --- |
| trivial | a typo, a copy string, a config value | the change, your checks, the pull request |
| direct | most work | a short spec, the code, your checks, one review round |
| risk | money, permissions, tenancy, data, a shared contract | premise check, a spec you approve, tests first, the code, a five-lens review, up to two rounds |

## Why use it

Same model, same prompts, same repository, with the plugin and without it, measured
per lane: two tasks per lane, two runs each, on 2026-10-20 with
`claude plugin eval --ablation with-without`.

| | Claude Code alone | With task-funnel |
| --- | --- | --- |
| **Simple task** (a new helper, a copy fix): direct lane | right in most runs, 0.83 | right, 0.92, and asks nothing extra |
| cost, time | US$ 0.17, 46 s | US$ 0.29, 64 s |
| **Risky task** (a fix or a rule on money): risk lane | edits the money code before anyone checked it, 4 of 4 runs, 0.08 | checks first and stops for your approval, 4 of 4 runs, 1.00 |
| cost, time | US$ 0.18, 42 s | US$ 0.42, 82 s, up to the spec |

The whole task, issue to pushed branch and reviewed draft pull request, run end to end
by `tests/e2e-lanes.sh` on a small repository: **95 s and US$ 0.62** on the direct
lane, **194 s and US$ 1.05** on the risk lane. The trivial lane has no eval yet.

### Reliability

Asked to fix a one-line bug in `src/money.ts`, Claude Code alone opens the file and
edits it, every time. With the plugin, the file matches your `risk.paths`, so an agent
first checks the bug is real, a spec states what must hold, and it waits for you. Tests
are written by a separate agent before the code, and the code only ships once they pass.

Where a change cannot hurt, the direct lane writes the code without stopping to ask,
like the bare model does, and scores at least as well. That is measured too, so a
funnel that starts asking where it should not shows up as a regression.

On a real task, issue #575 (44 files, 13 places where an API checked a company-wide
permission instead of a per-project one), seven review passes found 6 Important
defects, all fixed before the pull request existed, with 11,419 tests green.

### Cost

You pay for checks where they matter: about US$ 0.12 more than the bare model on a
simple task, US$ 0.24 more on a risky one. At 20 tasks a week, 3 of them risky, that
is roughly US$ 2.80 a week (an estimate from the averages above). What it saves,
measured on the repository it was built against:

- **Review rounds are counted and capped.** Before the cap, two pull requests ran 21 and
  25 rounds, 14% of five weeks of spend.
- **A check never runs twice on the same code.** 359 s saved on every push.
- **The ship stage went from 423.5 s to 268.7 s** by noticing the test suite ran twice.

`kit usage --by-branch` gives you the cost of each pull request in your own repository.

### Productivity

Issue #575 ran 1 h 45 unattended. The funnel stops only where the decision is yours: the
spec of a risky change, a task too big for one pull request, and the pull request itself.
That matters because, in a 5 h 35 task reconstructed by timestamp, 49% of the time was
waiting for a person.

Method, every case and every run: [`evals/README.md`](evals/README.md).

## Install

```sh
claude plugin marketplace add gabrielbsandim/task-funnel
claude plugin install task-funnel@task-funnel
/task-funnel:setup
```

Needs `git`, `jq` and `python3` on Linux or macOS, and `gh` for GitHub issues, pull
requests and Projects. Claude Code only: claude.ai chat cannot run the scripts and hooks
the funnel is made of. Coming from `claude-kit`? See
[Upgrading](docs/reference.md#upgrading-from-claude-kit).

## What every lane keeps

Every lane works in its own worktree, so your checkout is never touched, and runs your
real checks: a hook refuses to end a turn that changed code without running one. Every
review finding goes to a second agent told to refute it, and only a defect that
reproduces gets fixed. The pull request carries the findings table.

## Commands

| Command | For |
| --- | --- |
| `/task-funnel:task` | one task, description or issue number, to a draft pull request |
| `/task-funnel:investigate` | a question about the system. Read-only, ends in an answer, never a change |
| `/task-funnel:ship` | work already committed on a branch, to a reviewable pull request |
| `/task-funnel:backlog` | the open board: what is the same work, what is an orphan, what ships together |
| `/task-funnel:note` | one durable fact into a markdown vault, with provenance |

## Configure a repo

The funnel knows nothing about your stack. Everything it runs comes from one file,
`.claude/funnel.config.json`:

```sh
kit config init      # writes a starting config to edit
kit config check     # fails on a command, path or branch that does not exist
```

The keys, the lite lane for tight budgets, the browser review and the boards (GitHub
Projects, Jira, Azure DevOps) are in the [reference](docs/reference.md).

## Your data

No telemetry, and nothing is sent to the author. Branches go to your remote and pull
requests to GitHub with your own `gh` login. The full list of what it runs, writes and
sends is [here](docs/reference.md#what-it-runs-writes-and-sends).

## More

- [Reference](docs/reference.md): every `kit` command, the hooks, the browser lens,
  boards, the model per stage, tests, and the status of each piece.
- [Evals](evals/README.md): how the numbers above were measured, and how to rerun them.
- `investigate` and `note` also ship as standalone skills for any agent:
  [investigate.zip](https://github.com/gabrielbsandim/task-funnel/releases/latest/download/investigate.zip),
  [note.zip](https://github.com/gabrielbsandim/task-funnel/releases/latest/download/note.zip).

## License

MIT.
