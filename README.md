# claude-kit

**You give Claude Code one task. You get a pull request to review.**

Not a chat log to read and not a pile of edits in your working tree: a branch, in
its own worktree, with tests, with your repo's lint and test commands actually
run, reviewed by several independent reviewers whose job is to find what is wrong
with it, and a draft pull request with your board card moved.

```
/claude-kit:task 575
```

What that does, in order:

1. **Reads the task and decides if it is real.** Ambiguous or too big for one pull
   request, it says so and stops instead of guessing. It writes a spec with
   acceptance criteria and shows it to you before spending anything.
2. **Makes a worktree** so your current work stays untouched, and implements
   against that spec.
3. **Runs your gates**, the lint, types and test commands you already have. Not
   its own idea of a check.
4. **Writes tests with fresh eyes**, from the spec, by an agent that did not write
   the code.
5. **Reviews the diff adversarially**, several reviewers at once, each reading only
   the slice and documents it needs. If the change touched a screen, one of them
   opens it in a real browser.
6. **Opens the draft pull request**, moves the board to in review, and removes the
   worktree.

A real run, the one this paragraph was written from: issue #575, 4 commits, 44
files, 13 places where an API treated a company-wide permission as if it were
per-project permission. Seven review passes found 6 Important defects, all fixed
before the pull request existed. 838 test files and 11,419 tests green. One hour
45 minutes, unattended.

## Install

```sh
claude plugin marketplace add gabrielbsandim/claude-kit
claude plugin install claude-kit@claude-kit
/claude-kit:setup
```

`owner/repo` shorthand, or a full `https://.../repo.git` clone URL for a non-GitHub
host. `github.com/owner/repo` is rejected, being neither. `setup` runs once per
machine: it puts `kit` on your PATH, checks `git`, `jq` and `gh`, and offers to
write a starting config for the current repo.

## The five entry points

| Command | For |
| --- | --- |
| `/claude-kit:task` | one task, description or issue number, to a draft pull request |
| `/claude-kit:investigate` | a question about the system. Read-only, ends in an answer, never in a change |
| `/claude-kit:ship` | work already committed on a branch, to a reviewable pull request |
| `/claude-kit:backlog` | the open board: what is the same work, what is an orphan, what ships together |
| `/claude-kit:note` | one durable fact into a markdown vault, with provenance |

## Configure a repo

The funnel knows nothing about your stack. Everything it runs comes from one file.

```sh
kit config init      # writes .claude/funnel.config.json
kit config check     # validates it against this repo
kit board --discover # prints the board ids to paste into .claude/board.json
```

Four keys are worth your attention; the rest have workable defaults.

| Key | What it decides |
| --- | --- |
| `base` | the branch every diff and every worktree starts from |
| `gates` | your real commands, and `stages` groups them per funnel stage |
| `slices` | which paths are source and which are tests, which is what makes a scoped review possible |
| `lenses` | which document each reviewer reads, which is the largest cost lever here |

`kit config check` is worth running after any edit. It fails on a gate, slice or
lens that does not exist, a base branch with no remote, a document the config
names but the repo lacks, and a stage that runs the same work twice.

## What is scripted, and what is left to judgment

Ten things are commands rather than instructions, because prose does not execute:

| Command | What it removes |
| --- | --- |
| `kit worktree add/rm/gc` | the teardown nobody does. `gc` removes only what it can prove is finished and says why it kept the rest, and the funnel runs it at ship. While the teardown step was `rm`, which could not succeed once the pull request existed, it left 27 orphans and 35 GB behind. |
| `kit version <declared>` | a session silently running an old copy of this plugin. It compares the version the skill declares, the version of the `kit` on PATH and the newest installed, and names which of the two fixes applies. |
| `kit reload` | the three-step dance after a release. It updates, relinks, and separates what is already live (`bin/`, and a skill body, which is re-read at every invocation) from what actually waits on a restart (the output style, hooks, the listing). Until 0.7.1 it claimed skills were stuck until a restart, which was false and cost a restart nobody needed. |
| `kit issues related/orphans/tree` | a second issue for work already on the board, and an issue with no parent. Ranking is rarity-weighted, so the file every issue names counts for almost nothing and the file two issues name decides. |
| the context nudge | the same rule without having to remember it. A `UserPromptSubmit` hook that says, once per band and never again until the band changes, that it is time to compact. HOLD is silent, which is most prompts. Register `hooks/context-nudge.sh`, never the versioned Python path. It writes one line to `/dev/tty` as well as into the model's context: only the user can run `/compact`, so a nudge that stops at the model still needs somebody to choose to relay it. |
| `kit context` | a boundary passed without compacting, and a long pause taken with a large prefix. It reads this session through `CLAUDE_CODE_SESSION_ID` and answers HOLD, AT THE NEXT BOUNDARY, NOW or LATE off how full the window is, with what one prefix rewrite would cost right now. Measured across 16 sessions: 16% of an API-equivalent US$ 2442 went to requests that read almost nothing from cache and wrote a whole prefix back, US$ 2.62 each against US$ 0.20 for a normal one. |
| `kit pr-body <file>` | a pull request body that competes with the diff instead of introducing it. It measures the prose you added, not the template, its tables or a fenced block, and refuses over 2000 characters or 600 in one section. The chat report had a budget and the body did not, so the overflow went there: one measured body ran to 11902 characters of prose in front of a 163-line source diff. |
| `kit gate <stage>` | paying twice for the same check. Receipts are keyed by the working tree's SHA, so the pre-push check skips what the implement gate just proved. `gateJobs` runs a stage's independent gates at once; `exclusive` keeps one alone. |
| `kit review <level>` | one dispatch per reviewer and a blanket document load. One dispatch per slice instead, with the diff written to a file so no reviewer runs `git`. |
| `kit screens` | guessing which URL renders a component the diff changed. It walks the import graph to the router entry point that reaches it. |
| `kit board <status>` | two board writes, behind one port with three adapters. |
| `kit review --disjoint a b` | guessing whether two stages can run in parallel. It answers from the file lists. |
| the `flaky` list | a red gate in a file the diff never touched becoming a wasted fix round. |

What stays a model decision is the judgment: the triage verdict, whether a scope is
too big for one pull request, whether a finding is confirmed or merely plausible,
and "a round whose fix is larger than the original commit is not a round, it is the
spec having been wrong".

## Screens, in a real browser

Every other reviewer reads a diff and reasons about it, which is why a change can
pass lint, types, the whole suite and a seven-reviewer review and still ship a form
whose submit button is off screen on a phone.

So when a change touches a screen, one more reviewer opens it. `funnel-screen-lens`
answers two things from one visit per route:

- **Does it work.** Render, console errors, failed requests, and each acceptance
  criterion either exercised or explicitly reported as not exercised.
- **Can it be used.** Overflow and reach at every viewport, the states a screen has
  beyond the one it loads in, feedback after an action, keyboard, contrast, and
  consistency with the screens the change did not touch.

Off unless `browser.enabled` is true and `kit screens` found a route. It never
becomes a gate: a browser is the most nondeterministic thing here, so it produces
findings and blocks nothing on its own.

```jsonc
"browser": {
  "enabled": true,
  "baseUrl": "http://localhost:3000",
  "start": "npm run dev",           // the funnel brings the app up and polls it
  "appDir": "src/app",              // how an entry file becomes a URL
  "routeParams": { "id": "sup-1" }, // a real value per dynamic segment
  "viewports": [{ "name": "mobile", "width": 390, "height": 844 }],
  "auth": { "userEnv": "APP_E2E_USER", "passEnv": "APP_E2E_PASS" },
  "uxDocs": ["docs/frontend.md"]    // what an interface finding has to cite
}
```

Three of those are not preferences:

**An interface finding must cite something**: your frontend documents, a sibling
screen the change did not touch, or something a person cannot do. Grounded in none
of the three it is an opinion, and the agent is told not to report opinions. That is
what stops a browser reviewer from proposing a redesign in the middle of a bug fix.

**Credentials are environment variable names, never values.** `kit config check`
fails on a value there, and the agent has no shell, so it cannot read a secret its
dispatch did not already hold.

**One browser reviewer at a time.** Measured, not assumed: two agents driving this
MCP server concurrently share one browser and one tab, and in a four-round test one
agent's read returned the *other* agent's page three times out of four.

## Boards

The funnel knows the words `in_progress` and `in_review` and nothing about any
tracker. It reads `.claude/board.json` and calls one adapter.

| Provider | State |
| --- | --- |
| `github-projects-v2` | verified end to end. Needs the `project` scope |
| `jira` | written from the API contract, unverified |
| `azure-devops` | written from the API contract, unverified |
| `none` | no-op with a message |

In progress is written when the worktree exists and before any code, the first
instant at which another cycle must not pick the task up, and it **assigns** the
issue if it has no assignee, because a card in progress with no owner is the same
stale claim the column exists to prevent. In review is written once the pull
request URL exists. Never done: the funnel does not merge.

## Hooks

Three are registered, each protecting a property the funnel depends on:

- **`env-guard`** blocks any shell command that would print a secret-bearing file
  into the transcript. A permission rule on file reads does not cover `cat`,
  `grep` or `source`, and that is the path a real leak took. It covers `.env*`
  and, since 0.9.2, `.claude.json` and `.mcp.json`: both hold an `env` block per
  MCP server, which is where a token lands when a server is registered with
  `--env TOKEN=...`, and a real HubSpot private-app token was found sitting in
  plain text in one of them, outside every deny rule. `grep -c`, `grep -l` and
  `wc -l` still pass, because a count reveals no value.
- **`protect-tests`** refuses the four ways a green suite gets faked: deleting or
  emptying a test, adding a skip or focus marker, lowering a coverage threshold,
  and `--no-verify`. A gate on a green suite is worth exactly what that suite is
  hard to fake. It also blocks `git push --force` without `--force-with-lease`.
- **`pr-body-gate`** refuses a `gh pr create` or `gh pr edit` whose body is over
  the `kit pr-body` budget. Both skills already said to run that check before
  opening the pull request, and on the repository this was built against **17 of
  the 17 pull requests opened in the six days after install were over budget**,
  median 5798 characters of prose against 2000, worst 10545. An instruction that
  is read and agreed with is not a gate. It imports `bin/pr-body` rather than
  reimplementing the measurement, and fails open on everything it cannot judge:
  a body file not written yet, `--fill`, an unparseable command. Raise the
  budget for one repository with `KIT_PR_BODY_MAX`.

Two more ship unregistered, because one is house style and the other updates
software without being asked:

- **`no-em-dash`** enforces house style rather than correctness. It exempts
  nothing by default: the earlier version exempted `docs/**` and the root
  markdown files, which contradicted the rule it exists to enforce and left 820
  files carrying the character on the repository it was written against. Export
  `NO_EM_DASH_EXEMPT`, a colon-separated list of regexes, to loosen it.
- **`plugin-freshness`** is a `SessionStart` hook that updates this plugin, relinks
  the `kit` on PATH, and says in the session's own context when the skills it loaded
  are the previous version. It cannot make a running session current, because
  `claude plugin update` prints "restart required to apply" and means it. What it can
  do is stop the staleness from being silent, and fix the PATH half, which is live
  immediately. It is silent when nothing changed, runs the update at most once every
  six hours, holds a lock so two sessions cannot both write the cache, and exits zero
  on every failure path including offline. Registering it makes `main` your release
  channel, which is only sane because the three `validate` jobs gate `main`.

Register the **shim**, never the Python file. The Python half lives under a directory
named after the version, so registering it directly would pin the hook to one release
and make the hook itself the next thing that goes silently stale.

```sh
cp hooks/plugin-freshness.sh ~/.claude/hooks/
```

```jsonc
"SessionStart": [
  { "matcher": "startup|resume", "hooks": [
      { "type": "command", "timeout": 90,
        "command": "sh ~/.claude/hooks/plugin-freshness.sh" } ] }
]
```

The manual half is one command, and it prints the one line a session cannot run for
itself:

```sh
kit reload      # update, relink kit, then `exec claude -c` in your terminal
```

## Output style

`kit-terse` is the brevity mechanism: set `"outputStyle": "kit-terse"` in settings.
A brevity rule in a memory file gets read, agreed with, and lost by the end of the
turn. An output style is appended to the system prompt and reapplied every turn,
which is the difference that makes it hold.

## Why this shape

Reconstructed by timestamp from one well-reviewed task that took 5h35 instead of
the 45 minutes it looked like:

| Phase | Measured | Share |
| --- | --- | --- |
| human wait and merge | 2h44 | 49% |
| adversarial review, 3 rounds | 1h28 | 26% |
| pre-flight, triage, spec, implement | 47min | 14% |
| test writer and coverage gate | 20min | 6% |
| ship: coverage again, pre-push, PR | 14min | 4% |

Every lint and test command together was 11% of the part the funnel controls. So
nothing here trims a check. The levers are the number of review rounds, what each
reviewer reads, and never running the same gate twice.

**Removing work beats overlapping it.** On the repository this was built against,
the ship stage went from 423.5s to 268.7s. Only 13s of that came from running gates
concurrently; 142.5s came from noticing that `vitest run` and `vitest run --coverage`
prove the same 11,419 tests, so the stage was paying for the suite twice.
`kit config check` now finds that by itself.

**The funnel is a skill and only the review is a workflow.**
`workflows/review-fanout.js` runs the review as deterministic fan-out and sends every
finding to a verifier told to refute it. The rest is deliberately not a workflow,
because a workflow cannot stop and ask, and four of the funnel's gates are questions
a human owns: triage returning NEEDS_DECISION, "too big for one pull request", the
spec shown before the worktree is paid for, and the written adjudication at the round
cap. Answering those on your behalf is what turns a 45-minute task into a five-hour
one.

## Releasing

The version in `.claude-plugin/plugin.json` is the trigger. Bump it, merge to main,
and `release.yml` tags `v<version>` and cuts a release with generated notes once
`validate` has passed on that commit. A push that does not bump the version produces
nothing, which is the point: the tag says what shipped, not how many times main
moved.

`main` is protected: the three `validate` jobs are required and must be up to date,
force pushes and deletions refused, conversations resolved before a merge. Admin
enforcement is off, so the owner can still push directly. Nothing in CI commits to
main, so no bot exception is needed.

## Tests

```sh
python3 tests/test-hooks.py            # 36 cases, half of them "must not block"
python3 tests/test-screen-routes.py    # 10 cases: route groups, dynamic segments, the import walk
python3 tests/test-gate-jobs.py        # 14 cases: that concurrency happens, and that exclusive means alone
python3 tests/test-worktree-state.py   # 23 cases: what teardown will and will not delete
python3 tests/test-kit-version.py      # 19 cases: the three copies of this plugin, and the skill literal
python3 tests/test-issues.py           # 17 cases: what counts as the same work, and what a false no costs
python3 tests/test-plugin-freshness.py # 27 cases, most of them "must stay silent and must not fail"
python3 tests/check-eval-schema.py     # eval frontmatter against the harness's allowed keys
claude plugin validate . --strict      # manifests, skills, agents, commands
```

CI runs all of those, plus a syntax check per script dispatched on the shebang,
`shellcheck`, and a check that no shipped text contains an em dash.

Three of those suites are shaped by a specific failure. The hook tests pair every
"must block" case with a "must not block" one, because a guard with a false positive
gets disabled within a day. The gate tests assert on the order of start and end
markers rather than on wall clock, because three gates that pass are three gates
that pass whether they ran together or not, and because `sleep 2` on the machine
this was written on returns in 1.06 seconds about one run in six. The teardown tests
pair every "would remove" case with a "must keep" one, since the cost of the two
mistakes is not symmetric: a worktree kept too long is disk, and one removed too
early is somebody's unpushed work.

## Status of each piece

| Piece | State |
| --- | --- |
| skills, agents, commands, hooks, output style, `bin/*` | verified by running them |
| GitHub Projects v2 board adapter | verified end to end: discover, read, write |
| review grouping and doc-load numbers | measured on a real branch, reproducible with `kit review deep` |
| `kit screens` route mapping | 10 cases in CI, and resolved a real component three levels below its page in 0.29s |
| gate concurrency | 14 cases in CI, and the 423.5s to 268.7s measurement above |
| worktree teardown | 23 cases in CI. The first `gc --yes` after the verdict was fixed removed 24 of 27 worktrees and took that tree from 35 GB to 4.2 GB, measured with `du -shc` on both sides |
| `kit version` | 19 cases in CI. Found by a real run: a task executed the 0.1.0 skill while 0.2.0 had been installed for five minutes |
| `kit issues` and `/claude-kit:backlog` | 17 cases in CI, and the scorer was calibrated against a real 17-issue board: it reproduces the two orphans and refuses to call two issues the same work for sharing a document. The GitHub path is verified; other trackers exit non-zero rather than answer |
| the context nudge | 39 cases in CI, most of them proving silence, and 13 mutations. Writing them found two real defects: the state never came back down, so a session that compacted and refilled was never warned again, and the blanket `except Exception` made a crash indistinguishable from correct silence |
| `kit context` | 49 cases in CI, and 11 mutations to the bands and the lookup each turn it red. Three survived the first suite: the env-var window, a transcript with no requests, and the rewrite price being a constant |
| `kit reload` | 21 cases in CI, and 6 mutations to the message each turn it red. Writing them found two bugs in one subcommand: `die` was called and never defined, and `set -euo pipefail` killed the script on the first `ls` when no copy was installed, so its only error exited 2 with no message |
| the two lanes | 45 cases in CI, and 19 mutations to the rules each turn it red. Two of them survived the first version of the suite: a verdict removed from the agent's return shape, and the short lane silently dropping the board move |
| `kit pr-body` | 34 cases in CI, and 8 mutations to the guards each turn it red. Calibrated on three real bodies: 3123, 9999 and 11902 characters of prose against a 2000 budget |
| the browser lens | plumbing proven: server started, polled, navigated, resized, and the layout probe named the overflowing element and the below-fold button. **Never run against a real authenticated app**, so the auth path and the dispatch prompt are unproven |
| Jira and Azure DevOps adapters | written from the API contract, **never run**, marked so in their own source |
| `evals/` | schema validated offline, **never run**: `claude plugin eval` is early access and was not enabled on the account this was built from |

## License

MIT.
