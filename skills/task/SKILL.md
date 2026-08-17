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

## Stage 1 · Triage and spec, one read-only dispatch

One dispatch, structured return. Triage and spec used to be two, over the same
material, each paying the repo's mandatory doc load; the gate below reads the
`verdict` field before the spec is used, so nothing is lost by fusing them.

The dispatch returns:

1. **verdict**: `PROCEED`, `NEEDS_DECISION`, `BLOCKED` or `ALREADY_DONE`
2. **kind**: feature / bug / refactor / chore, and where it lives
3. **binding documents**: which of the repo's docs this change is subject to
4. **effort level**, with the reason
5. **the dispatch spec**: objective, file scope, prohibitions, acceptance
   criteria × expected evidence, test plan
6. **invariants**, per the table below

**GATE**: only `PROCEED` advances. `NEEDS_DECISION` or `BLOCKED` → stop and
present the diagnosis, AskUserQuestion when the alternatives are objective.
`ALREADY_DONE` → stop and show the evidence.

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

Dispatch the ENTIRE spec to an implementer working in the worktree.

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

On `standard` and `deep`, dispatch spec plus the list of implemented files to a
test writer that did not write the code. On `light`, the implementer's tests
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
file and the exact document list for the group. Give each dispatch its block
verbatim.

Fan-out per lens is not a neutral choice, it is the thing that was measured and
removed: two reviewer prompts fused into one that returns "Part 1 spec
conformity, Part 2 code quality" from a single read of the same diff ran twice as
fast for about half the tokens. Grouping by slice keeps independent contexts
exactly where the material differs and stops paying for the same read twice.

On the repository this was built against, a `deep` review goes from 7 dispatches
reading 4,256 diff lines and 517 KB of documents to 4 dispatches reading 2,043
lines and 117 KB. Reproduce with `kit review deep` on any branch.

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
**PLAUSIBLE** → a "points of attention" section in the pull request body, not a
blocker.

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
4. `kit board in_review --issue <issue>`, after the pull request URL exists.
5. Never `done`. The funnel does not merge, and the tracker's own automation
   owns that column.
6. `kit worktree rm <issue>`. It refuses while anything is uncommitted or
   unpushed, so running it is safe and skipping it is the thing that leaves 27
   orphans and 33 GB behind.

## Stage 6 · Report

Short prose with real numbers: what changed, gate results, findings found and
fixed, the pull request link, and what was deliberately left out. A gate that
stopped the funnel is named as such, without varnish. Never declare done
without the numbers.

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
