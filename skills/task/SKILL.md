---
name: task
description: "Delivery funnel for one repository task: a feature, bug fix, refactor or chore. Takes a task description or issue number and runs triage and spec, implementation, tests and a scoped adversarial review, ending in a pushed branch and a draft pull request with the board moved. Every path, gate command and board id comes from .claude/funnel.config.json, so this runs on any stack. Use when the user asks to implement, fix, build or change something in this repository, or on /task <description | issue number>."
---

# task: one task, from description to draft pull request

You are the **orchestrator**: you specify, dispatch subagents, guard the gates
and report. You do not write feature or test code yourself. Your advantage is a
clean global context for decisions, and it stays clean by letting subagents read
the code.

Input: the task description or issue number after the command. Empty → ask which
task and stop.

Two files sit next to this one and are **not** loaded with it. `review.md` is stage 4
in full, and stage 4 says to read it before dispatching. `evidence.md` is the
measurement behind every rule here that reads as arbitrary; open it when you are about
to disagree with a rule or adapt the funnel to a repository it was not written
against, never to run a task.

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
kit version 0.13.0
```

The literal is the version this file shipped in, so the command compares the text you
are reading against what is installed. STALE KIT is the case that actually bites, and
it is the one you can fix without stopping (`evidence.md` &middot; *Stale kit*).

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
- **Never write a `model` field into a dispatch.** Every agent declares its model
  in its own frontmatter and a `model` in the Agent input silently overrides it:
  measured over thirteen days, **101 of 625 dispatches carried one** the
  orchestrator wrote itself, at up to 3.6 times the cost per execution. The only
  exception is a `model:` line `kit review` printed, which it prints only when the
  config asks for an escalation (`evidence.md` &middot; *The model of a dispatch*).
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
  stands alone (`evidence.md` &middot; *Orphan issues*).

- **Compact at a boundary, at a prefix size and not at a share of the window, and
  always before a pause.** Compacting is cheap and a prefix rewrite is not, and the
  rewrite is not something you choose (`evidence.md` &middot; *Prefix rewrite*, and
  *Why the bands are token counts* for the floors).

  ```
  kit context
  ```

  It reads this session through `CLAUDE_CODE_SESSION_ID` and prints one of four
  verdicts: **HOLD** below 120k tokens in context, **AT THE NEXT BOUNDARY** from
  120k to 300k, **NOW** above 300k, and **LATE** below 15% of the window free,
  where the automatic compaction picks the cut point instead of you. Since 0.10.0
  the first three are token counts, not percentages, and they have arithmetic
  behind them: compacting at 250k repays itself in about **3 turns** of cheaper
  reads, and `kit context` prints that number for the size you are at.

  The end of a unit of work is still the trigger. NOW means the next boundary you
  reach and not this line of the diff, because compacting mid-task still trades a
  dollar for file re-reads that come back worse. One case ignores the band
  entirely: **before a long pause**, where a large prefix is the only place one
  request costs five dollars (`evidence.md` &middot; *A pause is the expensive
  moment*).

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
  already the floor: a "this was too small" verdict coming out of triage has already
  paid the floor before saying the floor was not worth paying (`evidence.md`
  &middot; *The triage floor*).

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
opens a reviewable pull request and still tears the worktree down. What it does not
buy is clean-context agents reading a diff that has nothing for them to read.

An issue already on the board is used and moved; the short lane never creates one,
because a typo that opens an issue is the backlog growth the funnel-wide rule above
exists to stop.

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

| Stage | Agent | Model | Carries |
| --- | --- | --- | --- |
| 1 | `claude-kit:funnel-triage` | inherit | the return shape, the verdicts, the invariant table, the sizing rule |
| 2 | `claude-kit:funnel-implementer` | inherit | the prohibitions, the bug-reproduction-first rule, what to do with a red gate |
| 3 | `claude-kit:funnel-test-writer` | sonnet | what to test in what order, and the two failure modes that are the writer's own |
| 4 | `claude-kit:funnel-reviewer` | sonnet | the reading discipline, the grading rubric, CONFIRMED against PLAUSIBLE |
| 4 | `claude-kit:funnel-screen-lens` | inherit | report only what you observed, the three-source standard, and NOT PROVEN is not a pass |

The Model column is the frontmatter, printed so a dispatch never guesses it and
never states it (`evidence.md` &middot; *The model of a dispatch*).

The screen lens runs only when the change touched a screen and `browser.enabled`
is true. It is the only agent here that finds out rather than reasons, which is
also why it is the only one that can return a green report from a session that
never left the login page. It is told to refuse that outcome by name.

**Exactly one screen lens at a time, and this was measured rather than assumed.**
One server, one browser, one tab, no per-caller isolation, so the behaviour half and
the interface half are numbered parts of one dispatch, which also means each route is
visited once instead of twice (`evidence.md` &middot; *One browser, one tab*).

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

`NEEDS_DECISION` answered by an investigation → **stage 1 does not run again.**
The ordinary shape of that answer is: triage stops, `/investigate` measures what
the decision turned on, the finding is written to the issue, and one slice of it
becomes a child issue. That child arrives with a file scope, acceptance criteria
and evidence that were **measured** rather than reasoned, which is more than
triage returns, so re-dispatching triage against it buys a second opinion about a
question already settled with numbers. Write the spec from the investigation
comment and go to stage 2. Measured on issue 910: the second triage cost 6.1
minutes of agent time and changed one number in the issue body, which a `grep`
would have caught (`evidence.md` &middot; *Paying triage twice*).

The exception is the pre-flight, not the spec: run stage 0 against the child's
number, because a branch or a pull request may exist for it.

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
not where the rounds go: on the run this funnel was measured on, three of four
rounds went to one rule nobody had written down (`evidence.md` &middot; *One
invariant, found three times*). So the spec names them up front and the
implementer answers them in code:

| Scope in the spec     | The invariant it carries                                                                                                              |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Money**             | every path that spends records the spend, **including the one that throws**; a cap sums an aggregate, never a rounded per-row value    |
| **External call**     | every new call has a timeout and a `catch`; the `catch` logs what was lost, because a silent `return { status: 'failed' }` is no handler |
| **Untrusted inbound** | the response code is chosen for the sender, not for us; a path that always answers 200 must not be the path that swallows a retry      |
| **Prose it touches**  | any comment, document or knowledge entry the change **falsifies** moves in the same commit, not only the ones it adds                  |

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

**One implementer per round, carrying every CONFIRMED finding of that round.** Not
one per finding: a second implementer on the same branch pays a second cold read of
the same repository for no independence in return, and over thirteen days this
stage ran **101 times for about 40 tasks** (`evidence.md` &middot; *An empty slice on
a fix round*).

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

`workflows/review-fanout.js` is a deterministic fan-out that adds a verifier per
finding, instructed to refute it: use it when the review is the whole job, and the
dispatches above when you are inside a task. Fan-out per lens was measured and
removed, because grouping by slice stops paying for the same read twice
(`evidence.md` &middot; *Why the dispatch is grouped by slice*).

### What stage 4 owes you before the dispatches go out

Read `review.md` in this skill's directory now, before writing a single dispatch. It
carries the browser half, what may actually run at once, the reviewer discipline, the
lenses most repos are missing, and the grading rubric. What follows is only what
a skipped read must not lose:

- **The browser half runs when `browser.enabled` is true, the effort level is in
  `browser.efforts`, and `kit screens` returned a route**, and is skipped silently
  otherwise. **Exactly one screen lens at a time**, and you bring the app up,
  because the lens has no `Bash`.
- **The rubric does not travel in the dispatch, because the agent already carries
  it.** `agents/funnel-reviewer.md` holds the reading discipline, the
  Critical/Important/Minor rubric, CONFIRMED against PLAUSIBLE and the return
  shape, and `funnel-screen-lens.md` holds its own. What the dispatch adds is this
  task's half and nothing else: what the change is for, the acceptance criteria,
  and what was deliberately left out. `kit review` prints that instruction above
  the blocks, because the mistake is made while writing the prompt and this output
  is the only thing read at that moment (`evidence.md` &middot; *A dispatch that
  restates the agent*).
- **A fix round dispatches only the slices the fix touched.** `--since` prints
  `skipped` for the others and names them; that line is the whole instruction
  (`evidence.md` &middot; *An empty slice on a fix round*).
- **A dispatch marked `alone: reads outside the diff` goes alone, both of its
  file lists verbatim.** All eight findings an outside reviewer returned on 879
  and 880 needed that permission (`review.md` &middot; *The lens that is allowed
  to read outside the diff*).
- **CONFIRMED** goes back to stage 2 as the spec, all of that round's findings in
  **one** implementer dispatch. **PLAUSIBLE** is one line in the pull request
  body's points of attention, and blocks nothing.
- **Cap at `maxRounds`, and at the cap every open finding gets a written decision.**
  Silent discard is prohibited.

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

   Cut, do not compress. Everything worth keeping has a better home: the reasoning
   behind a finding goes in the ledger comment, a product decision goes in the issue,
   and why a non-obvious line exists goes in the code next to it (`evidence.md`
   &middot; *A body that competes with the diff*).

   What the body owes the reader, and nothing else: what changed and why, in the
   repo template's own sections; what to check; what is knowingly left out and
   who owns it; and the link to the ledger comment.

4. The findings ledger, right after the URL exists. It has its own budget and it
   is checked: run `kit ledger` on the file, then post it with
   `gh pr comment --body-file`. **1000 characters of prose, 350 per section**, and
   one row per finding in a table, which costs no prose at all. `review.md` has
   the columns; a follow-up answering a review is a ledger too.
5. `kit board in_review --issue <issue>`, after the pull request URL exists.
6. Never `done`. The funnel does not merge, and the tracker's own automation
   owns that column.
7. `kit worktree gc --yes`, not `rm`. The pull request is open at exactly this
   head and everything is pushed, which is the definition of finished, and `gc`
   collects what earlier tasks left in the same pass. It keeps anything it cannot
   prove finished, including a worktree sitting on the base tip with nothing of its
   own, because that is indistinguishable from one another session just created.
   `rm <issue>` was here until 0.3.0 and could never succeed against an open pull
   request, so every task leaked its worktree (`evidence.md` &middot; *The worktree leak*).

## Stage 6 · Report

**Six items, hard cap, and at most 600 characters of prose in total.** Anything
that does not fit one of the six does not go in the final message. It goes in the
findings ledger comment, which is where a reader who wants it will look, and
**not** in the pull request body: the body has its own budget in stage 5, and
naming it as the overflow here is what pushed PR 590 to 11902 characters of prose
while this report stayed under 600.

The budget is in characters because "one line each" does not survive contact with a
paragraph: 100 characters is about one rendered line, so six items at 600 characters
is one sentence each (`evidence.md` &middot; *Why the budget is in characters*).

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

Reconstructed by timestamp on a real 5h35 task, half the clock was the human, and of
the part the funnel controls **every test and lint command together was 11%**. So
nothing here trims a check: the levers are the number of rounds, what each dispatch
reads, and not running the same gate twice (`evidence.md` &middot; *Where the 5h35
went*).
