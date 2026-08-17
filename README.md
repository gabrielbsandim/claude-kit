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
claude plugin marketplace add github.com/gabrielbsandim/claude-kit
claude plugin install claude-kit@claude-kit
```

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

Six things are deterministic, because prose does not execute:

| Command | What it removes |
| --- | --- |
| `kit worktree add/rm/gc` | the teardown step that is one command, is written in two places, and gets skipped every time a run ends in a report. It left 27 orphans and 33 GB behind once. `gc` removes only what it can prove is finished, and prints why it kept the rest. |
| `kit gate <stage>` | running the same suite twice. Receipts are keyed by the tree SHA of the working directory, including untracked files, so the pre-push check skips what the implement gate just proved and says so. |
| `kit review <level>` | fan-out per lens, and the blanket document load. One dispatch per slice, every lens on that slice as a numbered part of one contract, the diff written to a file so no reviewer runs `git`. On the repo this was built against, a deep review goes from 7 dispatches reading 4,256 diff lines and 517 KB of docs to 4 dispatches reading 2,043 lines and 117 KB. |
| `kit board <status> --issue N` | the two board writes, behind one port with three adapters. |
| `kit review --disjoint a b` | guessing whether two stages can run in parallel. It answers from the file lists. |
| the `flaky` list in the config | a red gate in a file the diff never touched turning into a wasted fix round. `kit gate` says whether the failing file is quarantined **and** whether this branch can even reach it. |

Everything else stays a model dispatch, because it is judgment: the triage
verdict, whether a scope is closed or too big for one pull request, CONFIRMED
against PLAUSIBLE, and "a round whose fix is larger than the original commit is
not a round, it is the spec having been wrong".

## Boards

The funnel knows the words `in_progress` and `in_review` and nothing about any
tracker. It reads `.claude/board.json` and calls one adapter.

| Provider | Mechanism | State |
| --- | --- | --- |
| `github-projects-v2` | `gh api graphql`, `updateProjectV2ItemFieldValue`. Adds the issue to the project if it is not on it. Needs the `project` scope. | verified end to end |
| `jira` | `POST /rest/api/3/issue/{key}/transitions`, credentials from `JIRA_EMAIL` and `JIRA_API_TOKEN`. Prints the available transitions when the mapping is missing. Prefer an Atlassian MCP server where one is registered. | written from the contract, unverified |
| `azure-devops` | `az boards work-item update --id N --state`, needs the `azure-devops` extension. | written from the contract, unverified |
| `none` | no-op with a message | |

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

## Not here yet

`ship` as a standalone skill for work that already exists, a `note` skill for
writing a durable fact into a knowledge vault, and a verified Azure DevOps
adapter. The Jira and Azure adapters are marked unverified in their own source
because they were written from the API contract on a machine where neither
service exists, and that is a different claim from "it works".

## License

MIT.
