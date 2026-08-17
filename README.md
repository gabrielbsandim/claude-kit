# claude-kit

A delivery funnel for one repository task, plus the scripts that keep it honest.

Triage and spec, implement, tests, a scoped adversarial review, a draft pull
request, and the board moved. Every path, gate command, review slice and board id
comes from one file in your repo, so the same funnel runs on any stack.

It exists because a well-reviewed task took 5h35 instead of 45 minutes, and the
reconstruction of where that time went says the problem is not rigor:

| Phase                                | Measured | Share |
| ------------------------------------ | -------- | ----- |
| human wait and merge                 | 2h44     | 49%   |
| adversarial review, 3 rounds         | 1h28     | 26%   |
| pre-flight, triage, spec, implement  | 47min    | 14%   |
| test writer and coverage gate        | 20min    | 6%    |
| ship: coverage again, pre-push, PR   | 14min    | 4%    |

Every lint and test command together was 11% of the part the funnel controls. So
nothing here trims a check. The levers are the number of review rounds, what each
dispatch reads, and not running the same gate twice.

## Install

```sh
claude plugin marketplace add gabrielbsandim/claude-kit
claude plugin install claude-kit@claude-kit
```

The first argument is `owner/repo` shorthand. `github.com/owner/repo` is rejected: it is
neither the shorthand nor a clone URL. A full `https://github.com/owner/repo.git` also
works, and is what you need on a host other than GitHub.

Then, once per machine:

```
/claude-kit:setup
```

That puts `kit` on your PATH, checks `git`, `jq` and `gh`, and offers to write a
starting config for the current repo. To hack on the plugin without reinstalling:
`claude --plugin-dir ./claude-kit`.

## Configure a repo

```sh
kit config init      # writes .claude/funnel.config.json
kit config check     # validates it against this repo
kit board --discover # prints the board ids to paste into .claude/board.json
```

`kit config check` fails on a gate, slice or lens that does not exist, on a base
branch with no remote, and on a document the config names but the repo does not
have. A repo with no config runs on detected defaults; a wrong default fails
loudly at a gate rather than quietly reviewing the wrong slice.

The four things a default cannot guess:

| Key      | What it decides |
| -------- | --------------- |
| `base`   | the branch every diff and every worktree starts from |
| `gates`  | the commands that actually gate this repo, and `stages` groups them per funnel stage |
| `slices` | which paths are source and which are tests, which is what makes a scoped review possible |
| `lenses` | which document each review lens reads, which is the largest single cost lever here |

## What is scripted, and what stays a judgment call

Seven things are deterministic, because prose does not execute:

| Command | What it removes |
| --- | --- |
| `kit worktree add/rm/gc` | the teardown step that is one command, is written in two places, and gets skipped every time a run ends in a report. It left 27 orphans and 33 GB behind once. `gc` removes only what it can prove is finished, and prints why it kept the rest. |
| `kit gate <stage>` | running the same suite twice. Receipts are keyed by the tree SHA of the working directory, including untracked files, so the pre-push check skips what the implement gate just proved and says so. With `gateJobs` above 1 the stage's independent gates also run at once, and a gate marked `exclusive` still runs alone. |
| `kit review <level>` | fan-out per lens, and the blanket document load. One dispatch per slice, every lens on that slice as a numbered part of one contract, the diff written to a file so no reviewer runs `git`. On the repo this was built against, a deep review goes from 7 dispatches reading 4,256 diff lines and 517 KB of docs to 4 dispatches reading 2,043 lines and 117 KB. |
| `kit board <status> --issue N` | the two board writes, behind one port with three adapters. |
| `kit review --disjoint a b` | guessing whether two stages can run in parallel. It answers from the file lists. |
| `kit screens` | guessing, inside a prompt, which URL renders a component the diff changed. It walks the import graph from each changed file to the router entry point that reaches it, and reports the ones it cannot resolve instead of inventing them. |
| the `flaky` list in the config | a red gate in a file the diff never touched turning into a wasted fix round. `kit gate` says whether the failing file is quarantined **and** whether this branch can even reach it. |

Everything else stays a model dispatch, because it is judgment: the triage
verdict, whether a scope is closed or too big for one pull request, CONFIRMED
against PLAUSIBLE, and "a round whose fix is larger than the original commit is
not a round, it is the spec having been wrong".

## Screens, in a real browser

Every other lens in the review reads a diff and reasons about it. That is why a
change can pass lint, types, the whole suite and a seven-lens review and still
ship a form whose submit button is off screen on a phone. So when a change touches
a screen, the review gains a browser half over Playwright MCP: `funnel-screen-lens`,
one agent answering two numbered parts from one visit per route.

| Part | Asks | Reports |
| --- | --- | --- |
| 1 | does it work | render, console errors, failed requests, each acceptance criterion exercised or explicitly not |
| 2 | can it be used | overflow and reach at every viewport, the states a screen has beyond the one it loads in, feedback after an action, keyboard and contrast, and consistency with the screens the change did not touch |

It is off unless `browser.enabled` is true, the effort level is in
`browser.efforts`, and `kit screens` found a route. A browser is the most
nondeterministic thing in this toolkit, so it is never a gate: it produces
findings, which go into the same ledger and block nothing on their own.

**One agent, and that is measured rather than preferred.** The two parts were two
agents first. Two of them run concurrently against this MCP server, four rounds
each: one agent's `browser_evaluate` read the *other* agent's page in three rounds
out of four, and matched only once the other stopped navigating. The server is
launched as `npx @playwright/mcp@latest` with no `--isolated`, so every caller in a
session shares one browser, one profile and one tab. Merging the parts also halves
the navigation, since both questions are answerable from one visit.

```jsonc
"browser": {
  "enabled": true,
  "baseUrl": "http://localhost:3000",
  "start": "npm run dev",          // the lens brings the app up, and polls readyPath
  "readyPath": "/login",
  "artifactsDir": ".playwright-mcp",
  "appDir": "src/app",             // how an entry file becomes a URL
  "routeParams": { "id": "sup-1" },// a real value per dynamic segment
  "viewports": [{ "name": "mobile", "width": 390, "height": 844 }],
  "auth": { "userEnv": "APP_E2E_USER", "passEnv": "APP_E2E_PASS" },
  "uxDocs": ["docs/frontend.md"]   // what the critic cites, so a finding is not a preference
}
```

Three decisions in there that are not preferences:

**A UX finding has to cite something.** The critic answers to this repo's own
frontend documents, to a sibling screen the change did not touch, or to something
a person cannot do. Anything grounded in none of the three is an opinion and the
agent is told not to report it. That is what keeps a browser lens from turning
into a redesign proposal in the middle of a bug fix.

**Credentials are environment variable names, never values.** `funnel-config
check` fails on a value in `browser.auth`, and neither agent is given `Bash`, so
neither can read a secret its dispatch did not already hold.

**`artifactsDir` must be ignored by git.** Playwright MCP writes a snapshot and a
console log per navigation, and `kit gate` keys its receipts on a working-tree SHA
computed with `git add -A`, which sees untracked files. Measured on a scratch
repo: with the directory ignored the SHA is identical before and after a
navigation writes into it, and with the ignore line removed it changes. Unignored,
every gate after the first navigation re-runs from scratch and it reads as
slowness rather than as a misconfiguration, so `funnel-config check` refuses it.

## Boards

The funnel knows the words `in_progress` and `in_review` and nothing about any
tracker. It reads `.claude/board.json` and calls one adapter.

| Provider | Mechanism | State |
| --- | --- | --- |
| `github-projects-v2` | `gh api graphql`, `updateProjectV2ItemFieldValue`. Adds the issue to the project if it is not on it. Needs the `project` scope. | verified end to end |
| `jira` | `POST /rest/api/3/issue/{key}/transitions`, credentials from `JIRA_EMAIL` and `JIRA_API_TOKEN`. Prints the available transitions when the mapping is missing. Prefer an Atlassian MCP server where one is registered. | written from the contract, unverified |
| `azure-devops` | `az boards work-item update --id N --state`, needs the `azure-devops` extension. | written from the contract, unverified |
| `none` | no-op with a message | |

The in-progress move also **assigns** the issue, to `assignee` from `board.json` or to
whoever `gh` is authenticated as, and only if it has no assignee yet. An issue in progress
with no owner is the same stale claim the column exists to prevent: the next cycle can see
that something is being worked on and not by whom. Turn it off with
`"assignOnProgress": false`. The review move never touches the assignee.

In progress is written at the top of the implement stage, right after the
worktree exists and before the implementer runs, which is the first instant at
which there is work another cycle must not pick up. Not earlier: triage can
return `BLOCKED`, and a card stranded in progress for a task that died is a stale
claim. In review is written after the pull request URL exists. Never done: the
funnel does not merge, and the tracker's own automation owns that column.

## Hooks

Two are registered, because both protect a property the funnel depends on:

- **`env-guard`** blocks any shell command that would print a `.env` file into
  the transcript. A permission rule on `Read` does not cover `cat`, `grep` or
  `source`, and that is the path a real leak took.
- **`protect-tests`** refuses the four ways a green suite gets faked: deleting or
  emptying a test, adding a skip or focus marker, lowering a coverage threshold,
  and `--no-verify`. A gate on a green suite is worth what the suite is hard to
  fake. It also blocks `git push --force` without `--force-with-lease`.

**`no-em-dash`** ships but is not registered, because it enforces a house style
rather than a correctness property. Register it yourself if you want it; the
exempt path list is configurable through `NO_EM_DASH_EXEMPT`.

## Output style

`kit-terse` is the brevity mechanism. Activate it with `"outputStyle":
"kit-terse"` in settings. A brevity rule in a memory file gets read, agreed with,
and lost by the end of the turn; an output style is appended to the system prompt
and reapplied every turn, which is the difference that makes it hold.

## Why the funnel is a skill and only the review is a workflow

`workflows/review-fanout.js` runs the review stage as deterministic fan-out: read the
grouped plan, review each slice as one multi-part contract, then send every finding to a
verifier whose instruction is to **refute** it. Findings that survive go back to the
implementer; the rest are recorded, including the refuted ones.

The rest of the funnel is deliberately not a workflow. A workflow has no way to stop and
ask, and four of the funnel's gates are questions a human owns: triage returning
NEEDS_DECISION, "this is too big for one pull request", showing the spec before the
worktree is paid for, and the written adjudication at the round cap. Scripting those means
answering them on the user's behalf, which is what turns a 45-minute task into a five-hour
one. The review stage is the opposite: the work is already committed, the plan is computed
by `kit review --dispatches`, the dispatches are read-only and disjoint by construction,
and nothing in it needs a human until the findings come back.

## Releasing

The version in `.claude-plugin/plugin.json` is the release trigger. Bump it, merge to main,
and `release.yml` tags `v<version>` and cuts a GitHub release with generated notes once
`validate` has passed on that commit. A push that does not bump the version produces
nothing, which is the point: the tag says what shipped, not how many times main moved.

Nothing in CI commits to main, so branch protection needs no bot exception.

`main` is protected: the three `validate` jobs are required and have to be up to date with
main, force pushes and deletions are refused, and conversations have to be resolved before
a merge. Admin enforcement is off, so the owner can still push directly.

## Tests

```sh
python3 tests/test-hooks.py           # 36 cases, half of them "must not block"
python3 tests/test-screen-routes.py   # 10 cases: route groups, dynamic segments, the import walk
python3 tests/test-gate-jobs.py       # 13 cases: that concurrency happens, and that exclusive still means alone
python3 tests/check-eval-schema.py    # eval frontmatter against the harness's allowed keys
claude plugin validate . --strict     # manifests, skills, agents, commands
```

CI runs all of those plus a syntax check on every script, `shellcheck`, and a check that
no shipped text contains an em dash, since the plugin ships a hook that forbids it. The
syntax step dispatches on the shebang, because `bin/` holds both bash and Python and
`bash -n` on a Python file is a syntax error about the wrong language.

`test-screen-routes.py` builds a throwaway repo per case and resets it to base between
them. Without that reset each case inherits the previous case's diff, and the suite
passes or fails for a reason no assertion states, which is how it failed 7 of 10 on the
first run.

`test-gate-jobs.py` asserts on wall clock and on ordering, never only on the verdict:
three gates that pass are three gates that pass whether they ran together or not. Three
two-second gates finish in 2.5s at `gateJobs: 3` and 6.5s at 1, and the exclusive case is
proven from a file each gate appends to at start and at end, not from timing.

The hook tests exist in that shape on purpose: a guard with a false positive gets
disabled within a day, so every "must block" case is paired with a "must not block" one.
`node --env-file=.env` and `process.env.PORT` have to pass, or `env-guard` is unusable.

## Status of each piece

| Piece | State |
|---|---|
| skills, agents, commands, hooks, output style, `bin/*` | verified by running them |
| GitHub Projects v2 board adapter | verified end to end: discover, read, write |
| review grouping and doc-load numbers | measured on a real branch, reproducible with `kit review deep` |
| `kit screens` route mapping | 10 cases in CI, plus resolved a real component three levels below its page to `/procurement` in 0.29s |
| the browser lens | the plumbing is proven: a local server started, polled, navigated, resized, and the layout probe named the overflowing element and the below-fold button. The shared-browser constraint is proven by a two-agent collision test. **Not yet run against a real authenticated app**, so the auth path and the dispatch prompt are unproven |
| gate concurrency | 13 cases in CI, and measured on the real repo: the `ship` stage runs in **268.7s** against 423.5s for the same four gates in series. 142.5s of that came from dropping a duplicated suite run (`vitest run` and `vitest run --coverage` prove the same 11,419 tests) and 13s from overlapping lint with types |
| Jira and Azure DevOps adapters | written from the API contract, **never run**, marked so in their own source |
| `evals/` | schema validated offline, **never run**: `claude plugin eval` is early access and was not enabled on the account this was built from |

## The four skills

| Skill | For |
| --- | --- |
| `task` | one repository task, description to draft pull request |
| `investigate` | a question about the system, read-only, ends in an answer and never in a change |
| `ship` | work that is already committed, to a draft pull request with the board moved |
| `note` | one durable fact into a markdown vault, with the provenance that keeps it checkable |

## Not here yet

A verified Azure DevOps adapter, a run of the eval suite, and one run of the browser
lenses against a real authenticated app.

## License

MIT.
