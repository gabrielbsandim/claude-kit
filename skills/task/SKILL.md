---
name: task
description: Delivery funnel for one repository task: a feature, bug fix, refactor or chore. Takes a task description or issue number and runs triage and spec, implementation, tests and a scoped adversarial review, ending in a pushed branch and a draft pull request with the board moved. Every path, gate command and board id comes from .claude/funnel.config.json, so this runs on any stack. Use when the user asks to implement, fix, build or change something in this repository, or on /task <description | issue number>.
---

# task: one task, from description to draft pull request

You are the **orchestrator**: you specify, dispatch subagents, guard the gates
and report. You do not write feature or test code yourself. Your advantage is a
clean global context for decisions, and it stays clean by letting subagents read
the code.

Input: the task description or issue number after the command. Empty → ask which
task and stop.

## The repo describes itself

Nothing in this skill knows your paths, commands or board. All of that is in
`.claude/funnel.config.json`, read through `kit`:

```
kit doctor                     # is this machine and this repo ready
kit config get .base           # the base branch
kit config gates ship          # which gates a stage runs
kit review standard            # the review dispatch plan, diffs already written
```

If `kit` is not on PATH, run `/claude-kit:setup` once. If the repo has no
config, `kit config init` writes a starting one and `kit config check`
validates it. A repo with no config still runs on detected defaults, and a
wrong default fails loudly at a gate rather than quietly reviewing the wrong
slice.

## Before stage 1: is this skill the one that shipped

```
kit version 0.9.5
```

The literal is the version this file shipped in, so the command is comparing the text
you are reading against what is installed on the machine. Measured on 2026-08-17: a
funnel run executed the 0.1.0 skill while a newer one existed upstream, so that task
ran without a browser lens, without the report cap, and without two other rules that
had already shipped, and nothing in its output said so.

The cause was the **installed** copy being old, not the session holding an old one.
A skill body is re-read at each invocation: the same unrestarted session loaded this
file from 0.1.0 at 14:11, from 0.1.1 at 19:03 and from 0.3.1 at 23:16. So a STALE KIT
is the case that actually bites here, and it is the one you can fix without stopping.

- **STALE SKILL**: the caller declares a version newer than anything installed, which
  means this file came from somewhere the machine does not have. Tell the user in one
  line and stop; running anyway spends an hour against rules whose code is absent.
- **STALE KIT**: you can fix this. Run the `kit setup` line it prints, then carry on.
- **`unknown subcommand: version`**: the `kit` on PATH is older than 0.3.0, which is
  the STALE KIT case with no way to say so. `kit setup` from the newest installed
  copy fixes it. Find that copy with
  `ls -d "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/plugins/cache/*/claude-kit/*/ | sort -V | tail -1`.
- Anything else: carry on without mentioning it.

## Rules that hold for the whole funnel

- **The repo's own pipeline document wins.** `kit config get .docs.pipeline`
  names it. This skill sequences the work; the rules of the flow live there.
  Where the two disagree, that document is right and this skill is the thing to
  fix.
- **Full spec in every dispatch.** A subagent inherits none of your context.
  Every prompt carries objective, file scope, prohibitions and acceptance
  criteria, the prohibitions always including this one: _you are one stage
  inside the task funnel; do not invoke the task or investigate skills
  yourself_. A dispatch that leans on "as discussed" produces a guess, then a
  redo, which is the most expensive token there is.
- **The writer never approves their own work.** Review runs in separate,
  clean-context agents that did not implement.
- **Never merge.** The funnel ends at the draft pull request.
- **An inherited claim is not a fact.** When a triage finding travels into the
  spec, mark it **MEASURED**, with the command that proved it, or **INFERRED**.
  Whoever writes an INFERRED claim into code or docs measures it first.
- **Concurrency comes from the config**, `maxParallelAgents`. On a small machine
  this is 3, not 7. Read-only fan-out runs in parallel; anything that writes
  runs alone.
- **Everything the funnel writes is English, whatever language the conversation
  is in.** Branch names, commit messages, the pull request body, code, comments,
  documents, and the label and description of every dispatch. Talk to the user in
  their language; write artifacts in English. The tell that this drifted is a
  dispatch list reading "Re-review de testes da 582", which is a label three
  people later read in a repository whose every other line is English.
- **A new issue is the last resort, and never an orphan.** A finding outside this
  task's scope has four homes before a new issue: the deferred ledger, a comment on
  an issue that already covers it, this task's own diff if it is smaller than
  explaining why it was left out, or the epic as a new child. Before creating
  anything, run it:

  ```
  kit issues related "<the title you were going to use>" --files a.ts,b.ts --parent <epic>
  ```

  It ranks the open board by shared source files, identifiers and words, and it
  prints the parent's existing children. Two distinctive files in common means it is
  the same work: comment there, or deliver both in one pull request. Then, if you do
  create it, **link it to a parent** with `addSubIssue`, or write in the issue why it
  stands alone. Measured on 2026-08-17 in the repository this was built against:
  eleven security issues in two days, nine of them correctly linked, and the only
  two orphans were the two created as findings mid-task. An orphan is what turns an
  epic with children into a flat list that reads as growing forever, which is what
  the backlog felt like while the count was in fact flat at 18 open.

- **Compact at a boundary, never at a percentage, and always before a pause.**
  Compacting is cheap and a prefix rewrite is not, and the rewrite is not something
  you choose. Measured across 16 sessions, 2026-08-11 to 2026-08-18, at
  API-equivalent rates: US$ 2442 spent, **US$ 393 of it, 16%, on requests that read
  almost nothing from cache and wrote a whole prefix back**, at US$ 2.62 each
  against US$ 0.20 for a normal request. So the value of compacting is not the
  cheaper reads afterwards, it is that the rewrite which happens anyway is smaller.

  ```
  kit context
  ```

  It reads this session through `CLAUDE_CODE_SESSION_ID` and prints one of four
  verdicts: **HOLD** above 60% of the window free, **AT THE NEXT BOUNDARY** from 60
  to 35, **NOW** from 35 to 15 even mid-task, and **LATE** below 15, where the
  automatic compaction picks the cut point instead of you.

  The end of a unit of work is the trigger; the percentage is only how urgent the
  next boundary is. Compacting mid-task trades a dollar for file re-reads that cost
  more and come back worse. One case ignores the percentage: **before a long pause.**
  In the session measured on Bedrock, 116 of 152 prefix rewrites followed a gap of 5
  to 60 minutes, at a median of 301,026 tokens and US$ 1.89 each, because that route
  was not getting the one-hour cache TTL. A pause with a large prefix is the only
  place one request costs five dollars.

### Effort level, declared by the spec in stage 1

| Level      | When                                                                | Review                                    |
| ---------- | ------------------------------------------------------------------- | ----------------------------------------- |
| `light`    | mechanical change, copy, one file, no new contract                  | whatever `.effort.light` lists            |
| `standard` | normal feature or fix                                               | `.effort.standard`                        |
| `deep`     | migration, auth/tenancy/billing, cross-module contract, new webhook | `.effort.deep`                            |

When in doubt go one level up: over-reviewing costs minutes, under-reviewing
ships a defect with a green report attached. The level buys **width in the first
pass**, not permission to iterate, because a round is the expensive unit.

## Stage 0 · Pre-flight, read-only

- `kit doctor`. A missing `project` scope or an invalid config is cheaper to
  find now than at stage 5.
- Issue number known → run the pre-flight the pipeline document prescribes for
  picking up an issue, and respect what it says. An existing remote branch may
  mean the issue is taken, abandoned, or already done.
- `git status` clean, including your own edits.
- No worktree yet. Triage and spec change no file, and the environment is paid
  for only after the spec gate says the task is real.
- **Which lane.** Answered here, before the triage dispatch, because triage is
  already the floor: measured on the 2026-08-17 run of one issue, the triage agent
  alone cost 9.4 minutes and about US$ 2.46 of the run's US$ 33, so a "this was
  too small" answer coming out of triage pays the floor before saying the floor
  was not worth paying.

### The two lanes, and what they share

Both lanes are funnels. The short one is the long one with the subagents removed,
not the long one with the discipline removed, and everything that has a `kit`
command behind it happens in both:

| Step | Long | Short |
| --- | --- | --- |
| Stage 0 pre-flight | yes | yes |
| Board to in progress | yes | yes |
| Branch and worktree from the config | yes | yes |
| Triage and spec dispatch | yes | no, you write the spec inline |
| Implementer, test writer, review lenses | yes | no |
| `kit gate` for the stage | yes | yes |
| Commit under the repo's convention | yes | yes |
| `kit gate ship`, push, draft pull request | yes | yes |
| Body under the `kit pr-body` budget | yes | yes |
| `kit board in_review`, `kit worktree gc --yes` | yes | yes |

So the short lane still moves the card, still runs lint, types and tests, still
opens a reviewable pull request and still tears the worktree down. What it does
not buy is four to seven clean-context agents reading a diff that has nothing for
them to read. An issue already on the board is used and moved; the short lane
never creates one, because a typo that opens an issue is the backlog growth the
funnel-wide rule above exists to stop.

### The short lane is for a change with no reviewable surface

**Not a line count.** One line in an auth guard is the most dangerous change in
the repository and thirty lines of copy are nothing, so size is the wrong axis.
The question is whether the lenses would have anything to read. Take the short
lane only when **none** of these moves:

| Surface | Examples of it moving |
| --- | --- |
| Contract | a signature, a route, a schema, a response shape, an exported type |
| Behaviour | a new branch, a new state, an order of operations, a cap or a retry |
| Data | a migration, a write path, a query's scope, a cache key |
| Money, permission, tenancy | anything a customer is charged, refused or shown |
| Published prose | a help entry, a policy, the assistant corpus, a public document |

What is left when none of them moves: a copy string, a config value, a comment, a
dependency bump with no API change, a rename inside one file, a typo.

**Announce and proceed, without waiting.** Say in one line that this is the short
lane and which of the five surfaces you checked, then run it. The user chose
announce-and-proceed on 2026-08-18, so a confirmation round here is not free
caution, it is the cost that decision rejected. Naming the criterion in the
announcement is what makes it arguable: the user can stop you before anything is
written.

**Uncertainty goes up, never down.** If the surface table is arguable at all, take
the long lane. Escalating late costs the minutes already spent; taking the short
lane wrongly ships a defect with a green report attached, which is the failure
this whole skill exists to prevent. The reversal is cheap in one direction only.

## The five agents this skill dispatches

Each stage has a named agent that ships with the plugin, and the dispatch has to name it,
because a generic "dispatch a planning subagent" resolves to a general-purpose agent and
the standing instructions in these files are lost:

| Stage | Agent | Carries |
| --- | --- | --- |
| 1 | `claude-kit:funnel-triage` | the return shape, the verdicts, the invariant table, the sizing rule |
| 2 | `claude-kit:funnel-implementer` | the prohibitions, the bug-reproduction-first rule, what to do with a red gate |
| 3 | `claude-kit:funnel-test-writer` | what to test in what order, and the two failure modes that are the writer's own |
| 4 | `claude-kit:funnel-reviewer` | the reading discipline, the grading rubric, CONFIRMED against PLAUSIBLE |
| 4 | `claude-kit:funnel-screen-lens` | report only what you observed, the three-source standard, and NOT PROVEN is not a pass |

The screen lens runs only when the change touched a screen and `browser.enabled`
is true. It is the only agent here that finds out rather than reasons, which is
also why it is the only one that can return a green report from a session that
never left the login page. It is told to refuse that outcome by name.

**Exactly one screen lens at a time, and this was measured rather than assumed.**
The behaviour half and the interface half were two agents until two of them were
run concurrently against this MCP server: one agent's `browser_evaluate` read the
*other* agent's page in three rounds out of four, and matched only after the other
stopped navigating. One server, one browser, one tab, no per-caller isolation. So
the two halves are numbered parts of one dispatch, which also means each route is
visited once instead of twice.

The task-specific half still travels in the prompt. The agent carries what is true of that
stage in every task; the dispatch carries this task.

## Stage 1 · Triage and spec, one read-only dispatch

One dispatch to `funnel-triage`, structured return. Triage and spec used to be two, over the same
material, each paying the repo's mandatory doc load; the gate below reads the
`verdict` field before the spec is used, so nothing is lost by fusing them.

The dispatch returns:

1. **verdict**: `PROCEED`, `SHORT_FUNNEL`, `NEEDS_DECISION`, `BLOCKED` or
   `ALREADY_DONE`
2. **kind**: feature / bug / refactor / chore, and where it lives
3. **binding documents**: which of the repo's docs this change is subject to
4. **effort level**, with the reason
5. **the dispatch spec**: objective, file scope, prohibitions, acceptance
   criteria × expected evidence, test plan
6. **invariants**, per the table below

**GATE**: only `PROCEED` advances into the subagent stages. `NEEDS_DECISION` or
`BLOCKED` → stop and present the diagnosis, AskUserQuestion when the alternatives
are objective. `ALREADY_DONE` → stop and show the evidence.

`SHORT_FUNNEL` → the stage 0 lane call was one level too high, which is the side it
is required to err on. Say so in one line with the surfaces triage named, then run
the short lane on the spec it returned: implement it yourself, `kit gate` for the
stage, commit, and go to **stage 5**. Stages 2, 3 and 4 do not run; every step in
the two-lane table does. Do not re-dispatch triage to get a different answer, which
is US$ 2.46 spent to disagree with the first one.

`PROCEED` with no issue yet → open one the way the pipeline document says, and
continue with its number. The funnel needs it: branch, worktree, pull request
body and board move are all named after it. Then re-run the stage 0 pre-flight
against that number.

- Bug → the first acceptance criterion is a **failing test that reproduces it**,
  written before the fix.
- User-observable change → the spec names the surfaces that must move with it,
  per the repo's entry document.

### Invariants, not only criteria

Acceptance criteria describe what the feature does, and what the feature does is
not where the rounds go. In the run this funnel was measured on, three of four
rounds went to one rule nobody had written down: the spend was never recorded,
then it still leaked when the turn threw, then the cap rounded every sub-cent row
to zero and never moved at all. One invariant, discovered three times, at 33, 44
and 70 minutes.

So the spec names them up front and the implementer answers them in code:

| Scope in the spec     | The invariant it carries                                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Money**             | every path that spends records the spend, **including the one that throws**; a cap sums an aggregate, never a rounded per-row value    |
| **External call**     | every new call has a timeout and a `catch`; the `catch` logs what was lost, because a silent `return { status: 'failed' }` is no handler |
| **Untrusted inbound** | the response code is chosen for the sender, not for us; a path that always answers 200 must not be the path that swallows a retry      |
| **Prose it touches**  | any comment, document or knowledge entry the change **falsifies** moves in the same commit, not only the ones it adds                  |

An invariant satisfied at write time costs nothing. The same invariant found in
review has cost between 30 and 70 minutes every time it was found.

**GATE**: criteria measurable, scope closed. Too big for one reviewable pull
request → present the slices and stop.

### Self-review, inline, before you show the spec

Not a subagent. A subagent loop reviewing the spec and plan doubled execution
time for an identical score across five versions and five trials; the inline
version catches three to five real problems in about thirty seconds. Ask
yourself, in writing, four questions:

1. Which acceptance criterion cannot be checked by a command or a test?
2. Which file in scope has no criterion attached, and which criterion has no
   file?
3. Which invariant above applies and is not stated?
4. What would make this "the spec was wrong" rather than "the code was wrong"?

Then show the user the spec in 5 to 10 lines and continue.

## Stage 2 · Implement

```
kit worktree add <issue> <slug> --kind <feature|bug|refactor|chore>
kit board in_progress --issue <issue>
```

The board move belongs **here**, right after the worktree exists and before the
implementer is dispatched. It is the first instant at which there is work
another cycle must not pick up. Not earlier: triage can return `BLOCKED` or
`ALREADY_DONE`, and a card stranded in progress for a task that died is the
stale claim the pipeline document warns about.

Dispatch the ENTIRE spec to `funnel-implementer`, working in the worktree.

**GATE**: `kit gate implement_first_pass`, then the work **committed** per the
repo's commit convention. The review stage diffs commits, so uncommitted work is
invisible to it. On failure, return the exact error to the same agent, at most
2 rounds; if it persists, stop and report.

A fix round arriving back here from stage 4 runs `kit gate
implement_fix_round` instead, which is the incremental form. The full suite is
paid once at stage 5, off a receipt.

**A red gate is not automatically the implementer's defect.** `kit gate` prints
a `flake` line when a failing file is on the config's quarantine list, and says
whether this branch's diff can even reach it. A gate red in a file the diff
never touched is a wasted fix round.

On a doc-only scope the worktree has no dependencies installed, so no gate
command can run. The gate is then the commit alone, and that classification
carries through the rest of the funnel.

## Stage 3 · Tests, fresh eyes, in parallel with the code review

On `standard` and `deep`, dispatch spec plus the list of implemented files to
`funnel-test-writer`, which did not write the code. On `light`, the implementer's tests
stand.

**This runs concurrently with the stage 4 dispatches whose slices exclude
tests.** The slices are disjoint by construction; `kit review --disjoint <a> <b>`
proves it for a specific pair before you rely on it. The lens that reads tests
waits for this stage; the ones that read source do not.

**GATE**: `kit gate tests`, and the new tests committed. A flaky or hanging test
is the test writer's defect, unless the config already quarantines it.

Coverage is measured across the whole run, so it has no incremental form and is
the most expensive gate there is. It runs **once, before the push**, not once
per round. The one exception: a fix round that added production code and no test
re-runs it early, because nothing downstream would catch that.

## Stage 4 · Adversarial review, grouped by slice

```
kit review <level>              # first pass
kit review <level> --since <sha reviewed last round>   # a fix round
```

That prints one dispatch per slice, each carrying every lens that reads that
slice as a **numbered part of one contract**, with the diff already written to a
file and the exact document list for the group. Give each block, verbatim, to its own
`funnel-reviewer`.

There is also `workflows/review-fanout.js`, which runs this stage as a deterministic
fan-out and adds a verifier per finding whose instruction is to refute it. Use it when the
review is the whole job and nothing needs asking; use the dispatches above when you are
inside a task and want to keep the findings in your own context.

Fan-out per lens is not a neutral choice, it is the thing that was measured and
removed: two reviewer prompts fused into one that returns "Part 1 spec
conformity, Part 2 code quality" from a single read of the same diff ran twice as
fast for about half the tokens. Grouping by slice keeps independent contexts
exactly where the material differs and stops paying for the same read twice.

On the repository this was built against, a `deep` review goes from 7 dispatches
reading 4,256 diff lines and 517 KB of documents to 4 dispatches reading 2,043
lines and 117 KB. Reproduce with `kit review deep` on any branch.

### The screens, in a real browser, in the same round

A diff lens reads what the code says. It cannot tell you that the submit button
is below the fold on a phone, that the table scrolls the page sideways, or that
the save succeeds and the screen says nothing. So when the change touched a
screen, the review has a browser half that runs alongside the diff dispatches.

```
kit screens          # the routes, and the ones it could not resolve
kit screens --json   # the same, to paste into the two dispatches
```

`kit screens` walks the import graph from each changed file up to the router
entry point that reaches it, so a component nested three levels below a page
still yields a URL. Nothing here guesses a route inside a prompt.

Run the browser half when **all three** hold, and skip it silently otherwise:

1. `browser.enabled` is true,
2. the effort level is in `browser.efforts`,
3. `kit screens` returned at least one route under `visit`.

Then **one** dispatch to `claude-kit:funnel-screen-lens`, answering two numbered
parts from one visit per route: part 1 is whether it works, part 2 is whether it
can be used. It gets the base URL, the `visit` list verbatim, the viewports, the
spec's acceptance criteria, and `browser.uxDocs`, which is what anchors part 2 to
this repo's conventions instead of to taste. One, not two, for the reason in the
agent table: the browser is shared and two of them corrupt each other's reads.

**Four things this stage owes you, and each one has bitten:**

- **You bring the app up, because the lens cannot.** The agent has no `Bash` on
  purpose, so `browser.start` and the `readyPath` poll are yours. A dispatch sent
  at a port with nothing on it returns findings about a connection error.
- **A port that answers is not proof it is your build.** `readyPath` proves
  something is listening. If a dev server from an earlier task is still up on that
  port, the lens reviews that build and reports it as this branch. Check the port
  before starting, and if something is already there, either reuse it knowingly or
  stop: two `npm run dev` on one port do not both bind it, and the second one
  silently picks another port that `baseUrl` does not name.
- **`kit screens` printing `blocked` is a result, not noise.** A dynamic route
  with no value in `routeParams` and a component no page imports are both screens
  nobody is going to look at. Carry them into the report.
- **Credentials by environment variable name only.** `funnel-config check` refuses
  a value in `browser.auth`, and the agent has no `Bash`, so it cannot read a
  secret the dispatch did not already hand it.

A finding from the lens is a finding like any other: same ledger, same rounds,
blocks nothing on its own. A browser is the most nondeterministic thing in this
funnel, so it never becomes a gate.

### What may actually run at once

The point of parallelism here is wall clock, so it is worth being exact about what
overlaps and what only looks like it does. Three lanes, and the rule is that a
lane owns a resource:

| Lane | Owns | How many at once |
| --- | --- | --- |
| review | nothing, it only reads diff files | up to `maxParallelAgents` |
| browser | the shared browser, the dev server, the app's data | exactly 1 |
| gates | the working tree | `gateJobs`, with `exclusive` gates alone |

The review lane and the browser lane genuinely overlap: different resources,
no contention. Lanes are not a licence to fan out further inside one, and
two things that look parallelizable are not:

- **Two vitest runs in one working tree.** Not a theory: in the repository this
  was built against, `src/tests/setup-dom.test.ts` writes a config file into the
  working directory under a fixed name and deletes it in `afterAll`, and any
  coverage run `rm -rf`s its own report directory at startup. Either one makes the
  other run fail for a reason that has nothing to do with the change. That is what
  `exclusive` is for, and it is why `gateJobs` defaults to 1.
- **The browser lane next to a heavy gate, on a small machine.** Measured on the
  box this was written on: 6 cores, 5.9 GB of RAM with about 3 GB free, a dev
  script that asks for an 8 GB V8 heap ceiling, vitest pinned to 4 workers, and
  Chromium on top. Overlapping the browser with lint and types is free.
  Overlapping it with the suite is how a gate fails for memory and gets read as a
  flake. Check the machine before assuming the lane is free.

Before raising `gateJobs`, run `kit config check`: it prints, per stage, exactly
which gates would share and which run alone, and it fails when one gate's command
expands to another's plus a flag, since that stage is paying for the same work
twice.

What this is worth, measured on the repository this was built against: the `ship`
stage runs in **268.7s** where the same four gates in series cost 423.5s. Note
where that came from, because it decides where to look next: 142.5s of it was a
duplicated suite run that concurrency would have hidden rather than fixed, and
only 13s was the overlap. Removing work beats overlapping it.

### Reviewer discipline, pure token gain

Put these in every review dispatch:

- **Read the diff file you were given, once.** Its context lines are the changed
  file. Do not open the file again unless a hunk is cut off, and do not run
  `git` at all.
- Do not sweep the codebase. Look outside the diff only for a **named** risk,
  one focused check, naming both the risk and the check.
- Do not run the suite. The implementer already did. A focused test only for a
  specific doubt.
- **A reviewer does not dispatch subagents.** A reviewer spawned by a reviewer
  duplicates another at full cost and its verdict carries no weight.
- The final message **is** the report: verdict first, no preamble, no closing
  summary.

### The two lenses most repos are missing

Both were the human reviewer's finding number one on the first two pull requests
this funnel delivered, and none of the code lenses had reached them.

**`failure-edges`**. Walk every new I/O call and answer, per call: is there a
`catch`, is there a timeout, does the failure leave a log, and what is lost if it
throws here. One shipped pull request had a fetch with neither `catch` nor
timeout, so a network failure became a raw 500 instead of the route's own 502
contract. Another shipped a paid call with no `catch` on a webhook that answers
200 to everything: a throw after the charge lost the cost silently, with no retry
behind it.

**`claims`**. Every sentence this change writes **or leaves standing** is
re-read against the code as committed. The other lenses verify what the pull
request body asserts, and verify it well. What gets through is the prose the
change **falsified**: a comment still calling 16 MB the ceiling after the change
introduced a 1 MB one, a runbook naming a guard at a step the code no longer runs
it at, a help entry promising an answer a new cap refuses. `kit review` hands
this lens a **grep-precomputed candidate list** instead of two 15 KB files to
read, built from the declaration names and multi-digit literals the diff touched.
Candidates, not findings: each is verified against the code.

### Rounds are the expensive unit

Rubric, in every dispatch, because an uncalibrated reviewer is what multiplies
rounds:

- **Critical**: data loss, security, money, breaks production.
- **Important**: the task is not trustworthy until fixed: incorrect or fragile
  behaviour, a missed requirement, a literal duplicated block of logic, a
  swallowed error, a test that asserts nothing.
- **Minor**: "coverage could be broader", naming, style. **Minor never enters
  the loop.** It goes to a deferred ledger, which is a file, not prose in the
  pull request.

Then: **CONFIRMED** → back to stage 2 with the finding as the spec.
**PLAUSIBLE** → one line each in the "points of attention" section of the pull
request body, capped like every other section, with the reasoning in the ledger
comment. Not a blocker.

**The ledger is posted as a comment on the pull request**, once the URL exists.
It was a file in the session scratchpad until 0.6.0, which is a temp directory no
reviewer can open, so a ledger written there was written to nobody and the body
absorbed it instead: measured on 2026-08-17, the #588 run wrote a 12146-character
ledger to the scratchpad and a 13589-character body, and the second was largely a
retelling of the first. A comment is next to the diff, collapses on its own, and
does not have to be read before deciding whether to review.

The re-review after a fix round is **incremental**, which is what `--since`
does: the lens receives the fix diff plus the list of findings it is verifying,
each answered `ADDRESSED` or `NOT ADDRESSED`, plus new breakage inside the fix
diff only. A full re-read is warranted only when the fix moved a contract, a
signature, a route, a schema, an order of operations, and then only for the
lenses that contract touches.

Cap at `maxRounds`, and **at the cap every open finding gets a written
decision**. Silent discard is prohibited. A round whose fix is larger than the
original commit is not a round, it is the spec having been wrong: say so and
stop.

## Stage 5 · Ship

1. `kit gate ship`. Gates whose receipt already covers this exact tree are
   skipped and say so, which is why the pre-push check does not re-run what
   stage 2 just proved. The tree SHA includes untracked files, so any edit at
   all invalidates the receipt.
2. Push. The repo's pre-push hook runs its own checks; the fix for a red hook is
   the failing check, never `--no-verify`.
3. Open the pull request exactly as the pipeline document says. That document,
   not this skill, owns the base branch, the draft state and the issue
   reference. Fill the repo's template honestly: a check is ticked only if it
   ran, PLAUSIBLE findings under points of attention.

   **The body has a budget, and it is checked, not estimated.** Write it to a
   file and run `kit pr-body <file>` before `gh pr create`: at most **2000
   characters of prose** and **600 per section**, counting what you added and not
   the template, the tables, the checkboxes or the fenced blocks. Over budget it
   exits 3 and prints the sections by size.

   Cut, do not compress. The body is the only thing a human reads before deciding
   whether to review the diff, and everything worth keeping already has a better
   home: the reasoning behind each finding goes in the ledger comment, a decision
   about the product goes in the issue, and why a non-obvious line exists goes in
   the code next to it. Measured on 2026-08-17: PR 590 carried 11902 characters
   of prose across 9 sections, 7 of them over the 600 cap, on a change whose
   source diff was 163 lines. Nine minutes of reading to reach a 163-line diff is
   a body that competes with the diff instead of introducing it.

   What the body owes the reader, and nothing else: what changed and why, in the
   repo template's own sections; what to check; what is knowingly left out and
   who owns it; and the link to the ledger comment.

4. `gh pr comment` the findings ledger, right after the URL exists.
5. `kit board in_review --issue <issue>`, after the pull request URL exists.
6. Never `done`. The funnel does not merge, and the tracker's own automation
   owns that column.
7. `kit worktree gc --yes`, not `rm`. The pull request is open at exactly this
   head and everything is pushed, which is the definition of finished, and `gc`
   collects what earlier tasks left in the same pass. It keeps anything it cannot
   prove finished, including a worktree sitting on the base tip with nothing of its
   own, because that is indistinguishable from one another session just created.
   `rm <issue>` was here until 0.3.0 and could never succeed: step 3 opens the pull
   request, and an open pull request used to mean KEEP, so every task leaked its
   worktree. 27 of them and 35 GB when it was found.

## Stage 6 · Report

**Six items, hard cap, and at most 600 characters of prose in total.** Anything
that does not fit one of the six does not go in the final message. It goes in the
findings ledger comment, which is where a reader who wants it will look, and
**not** in the pull request body: the body has its own budget in stage 5, and
naming it as the overflow here is what pushed PR 590 to 11902 characters of prose
while this report stayed under 600.

The budget is in characters because "one line each" does not survive contact with
a paragraph. Measured on 2026-08-17: a report that read as six items was 1655
characters and 4 source lines, and rendered as 19 lines in the user's terminal.
100 characters is about one rendered line, so six items at 600 characters is one
sentence each.

1. The pull request link, its draft state and base, and the issue it closes.
2. What changed, in one sentence naming the class of defect, not each instance.
3. Gates: the count that ran, failed and was skipped by receipt, and the tree SHA.
4. Review: findings by severity, how many rounds, where the rest is written down.
5. What was left out, and the issue that owns it. If this run created issues, the
   count and the parent each one hangs under: "opened 2, both under #571". A run
   that closes one issue and opens three says so in those words, because an
   unstated delta is how a backlog grows without anyone deciding to grow it.
6. What needs the user, or "nothing" if the answer is nothing.

Then `kit context`. A shipped task is the boundary the rule above is about: the
detail being dropped is the detail this task no longer needs, and the next task
starts against a prefix that is cheap to rewrite. Say the verdict in the report's
item 6 when it is anything but HOLD.

A gate that stopped the funnel replaces line 1 and is named without varnish. A
number with no command behind it is not a number: leave it out. Never declare
done without lines 3 and 4.

## Why the funnel has this shape

Reconstructed by timestamp on a real 5h35 task, issue to merge:

| Phase                                | Measured | Share |
| ------------------------------------ | -------- | ----- |
| human wait and merge                 | 2h44     | 49%   |
| adversarial review, 3 rounds         | 1h28     | 26%   |
| pre-flight, triage, spec, implement  | 47min    | 14%   |
| test writer and coverage gate        | 20min    | 6%    |
| ship: coverage again, pre-push, PR   | 14min    | 4%    |

Half the clock was the human, and of the part the funnel controls, **every test
and lint command together was 11%**. So nothing here trims a check: the levers
are the number of rounds, what each dispatch reads, and not running the same
gate twice. Anything in this document that trims a check is trimming the cheap
thing.

- You stay clean: subagents read code, you read conclusions. A loaded main
  session pays for its whole history on every message.
- Dispatches are self-contained, because the redo caused by a vague spec costs
  more than the spec.
- The funnel ends in a report, and the next task starts in a fresh session. One
  task per session is the cheapest shape a session has.
