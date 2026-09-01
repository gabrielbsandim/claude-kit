# task, the measurements behind the rules

Every rule in `SKILL.md` that reads as arbitrary was a defect first. This file holds
the measurement, so the rule can stay one sentence where the funnel is running and
still be arguable when someone wants to change it. Section names match the pointers
in `SKILL.md` and `review.md` exactly.

Read it when you are about to disagree with a rule, when you are adapting the funnel
to a repository it was not written against, or when a number in a report needs its
source. Do not read it to run a task.

## Stale kit

The literal is the version this file shipped in, so the command is comparing the text
you are reading against what is installed on the machine. Measured on 2026-08-17: a
funnel run executed the 0.1.0 skill while a newer one existed upstream, so that task
ran without a browser lens, without the report cap, and without two other rules that
had already shipped, and nothing in its output said so.

The cause was the **installed** copy being old, not the session holding an old one.
A skill body is re-read at each invocation: the same unrestarted session loaded this
file from 0.1.0 at 14:11, from 0.1.1 at 19:03 and from 0.3.1 at 23:16. So a STALE KIT
is the case that actually bites here, and it is the one you can fix without stopping.

## Orphan issues

It ranks the open board by shared source files, identifiers and words, and it
  prints the parent's existing children. Two distinctive files in common means it is
  the same work: comment there, or deliver both in one pull request. Then, if you do
  create it, **link it to a parent** with `addSubIssue`, or write in the issue why it
  stands alone. Measured on 2026-08-17 in the repository this was built against:
  eleven security issues in two days, nine of them correctly linked, and the only
  two orphans were the two created as findings mid-task. An orphan is what turns an
  epic with children into a flat list that reads as growing forever, which is what
  the backlog felt like while the count was in fact flat at 18 open.

## Prefix rewrite

Compacting is cheap and a prefix rewrite is not, and the rewrite is not something
  you choose. Measured across 16 sessions, 2026-08-11 to 2026-08-18, at
  API-equivalent rates: US$ 2442 spent, **US$ 393 of it, 16%, on requests that read
  almost nothing from cache and wrote a whole prefix back**, at US$ 2.62 each
  against US$ 0.20 for a normal request. So the value of compacting is not the
  cheaper reads afterwards, it is that the rewrite which happens anyway is smaller.

## Why the bands are token counts

Until 0.10.0 the four bands were percentages of the context window. Measured
2026-08-29 over 988 transcripts and 87,306 messages, the median session peaked at
**260,253 tokens** of context, the p90 at 506,574 and the largest at 654,359.
Against a 1M window those are 74%, 49% and 35% free, so a rule whose first floor
was "above 60% free, hold" answered HOLD or AT THE NEXT BOUNDARY for essentially
every session ever run, and HOLD is the one verdict nobody can act on.

The unit was the defect, not the floors. A 300k prefix costs the same to re-read on
a 200k window as on a 1M one, so what makes a threshold arguable is payback, not
proportion. A turn re-reads its prefix at US$ 0.50 per million. One compaction was
measured at **US$ 0.4389 for the turn that follows it against US$ 0.1346 for a
normal one**, across 35,583 main-loop turns, so about US$ 0.30 extra, and it resets
the prefix to roughly 40k. Compacting at P therefore repays itself in
`0.30 / ((P - 40_000) x 0.5e-6)` turns: about 8 at 120k, about 3 at 250k, under 2 at
400k. Sessions run into the hundreds of turns.

So the floors moved to 120k and 300k, `kit context` prints the payback for the size
you are actually at, and LATE stayed a percentage because what LATE describes is the
automatic compaction, which fires against the window rather than against a prefix.

What did not change is the trigger. The whole measured cost of compaction is
US$ 63.03 across 141 of them, about 1% of the period's bill, so compacting is not
what a quota goes on. A redo is. NOW means the next boundary you reach.

## A pause is the expensive moment

The end of a unit of work is the trigger; the percentage is only how urgent the
  next boundary is. Compacting mid-task trades a dollar for file re-reads that cost
  more and come back worse. One case ignores the percentage: **before a long pause.**
  In the session measured on Bedrock, 116 of 152 prefix rewrites followed a gap of 5
  to 60 minutes, at a median of 301,026 tokens and US$ 1.89 each, because that route
  was not getting the one-hour cache TTL. A pause with a large prefix is the only
  place one request costs five dollars.

## The triage floor

- **Which lane.** Answered here, before the triage dispatch, because triage is
  already the floor: measured on the 2026-08-17 run of one issue, the triage agent
  alone cost 9.4 minutes and about US$ 2.46 of the run's US$ 33, so a "this was
  too small" answer coming out of triage pays the floor before saying the floor
  was not worth paying.

## One browser, one tab

**Exactly one screen lens at a time, and this was measured rather than assumed.**
The behaviour half and the interface half were two agents until two of them were
run concurrently against this MCP server: one agent's `browser_evaluate` read the
*other* agent's page in three rounds out of four, and matched only after the other
stopped navigating. One server, one browser, one tab, no per-caller isolation. So
the two halves are numbered parts of one dispatch, which also means each route is
visited once instead of twice.

## Two things that look parallel

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

## What concurrency is worth

What this is worth, measured on the repository this was built against: the `ship`
stage runs in **268.7s** where the same four gates in series cost 423.5s. Note
where that came from, because it decides where to look next: 142.5s of it was a
duplicated suite run that concurrency would have hidden rather than fixed, and
only 13s was the overlap. Removing work beats overlapping it.

## The two lenses

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

## Why the ledger is a comment

**The ledger is posted as a comment on the pull request**, once the URL exists.
It was a file in the session scratchpad until 0.6.0, which is a temp directory no
reviewer can open, so a ledger written there was written to nobody and the body
absorbed it instead: measured on 2026-08-17, the #588 run wrote a 12146-character
ledger to the scratchpad and a 13589-character body, and the second was largely a
retelling of the first. A comment is next to the diff, collapses on its own, and
does not have to be read before deciding whether to review.

## Why the ledger has a budget

Then the body had a budget and the ledger did not, so the overflow moved into the
ledger the same way it had moved into the body. Measured 2026-08-29 with
`kit pr-body --max 999999`, the first ledger comment on pull requests 874, 877 and
880 carried **4515, 4432 and 3734 characters of prose**, in front of bodies of 1876
to 2837 characters that the 2000 budget had already disciplined. The follow-up
comment answering the review on 880 was another 3419.

So `kit ledger` is `kit pr-body` at 1000 and 350, half the body's, because the
ledger is the second thing read and only by somebody who has already decided to
review. The budget is reachable rather than merely small because a table row costs
no prose at all under the same counting rules: twelve findings in rows measure 55
characters, and the same twelve as paragraphs measure past 3000. That is what makes
the shape a table with a few sentences under it, rather than a shorter essay.

## One invariant, found three times

Acceptance criteria describe what the feature does, and what the feature does is not
where the rounds go. In the run this funnel was measured on, three of four rounds
went to one rule nobody had written down: the spend was never recorded, then it
still leaked when the turn threw, then the cap rounded every sub-cent row to zero
and never moved at all. One invariant, discovered three times, at 33, 44 and 70
minutes.

An invariant satisfied at write time costs nothing. The same invariant found in
review has cost between 30 and 70 minutes every time it was found.

## Why the dispatch is grouped by slice

Fan-out per lens was the shape this stage started in, and it was measured and
removed: two reviewer prompts fused into one that returns "Part 1 spec conformity,
Part 2 code quality" from a single read of the same diff ran twice as fast for
about half the tokens. So the parts share one read, and independent contexts are
kept where the material actually differs, which is the slice.

On the repository this was built against, a `deep` review goes from 7 dispatches
reading 4,256 diff lines and 517 KB of documents to 4 dispatches reading 2,043
lines and 117 KB. Reproduce with `kit review deep` on any branch.

## An empty slice on a fix round

A reviewer sent at a diff with nothing in it still pays a full cold context to
report that there is nothing to report. Until 0.10.0 a `--since` round wrote every
slice for the fix range and printed a dispatch for each one regardless of whether
the fix had touched it, so a fix confined to `src` re-sent the
tests and surfaces lenses every round.

The scale it operates at is the fan-out itself: over thirteen days the reviewer ran
**310 times for about 40 tasks**, roughly 8 per task against a plan that prints 3 on
`standard` and 4 on `deep`, so most of the excess is fix rounds. `--since` now prints
`skipped` and names the slice, and that line is the whole instruction.

The first round never skips. There an empty slice is a fact worth having stated, and
a reviewer's silence is not the same statement as a reviewer's absence.

The same round has one other rule with the same shape: **one implementer per round,
carrying every CONFIRMED finding of that round**, not one per finding. The
implementer ran 101 times for about 40 tasks on a funnel whose `maxRounds` is 2. A
second implementer on the same branch reads the same repository from an empty
context to fix a second line in a file the first one already had open, and the fix
is not a judgement anybody wanted a fresh opinion on.

## What a second round returns

Two tasks, both `standard`, both at `maxRounds` 2, both with a real fix between the
rounds, so the second round had something to verify and a fresh diff to read. It
returned **13 findings, 0 Critical, 0 Important**, and four of them changed a line:

| Task | Round 2 findings | Changed a line | What those were |
| --- | --- | --- | --- |
| 908 | 6 | 2 | a documented rule the fix falsified, a test comment naming the gate it had replaced |
| 909 | 7 | 2 | a comment the fix left overstated, a round 1 number the round itself falsified |

Not one of the four was a code defect. Every code finding a second round raised was
deferred, which is the outcome a Minor on a fix round reliably has: the first round
already read that code cold at the width the effort level bought, so what is left
for the second is the prose the fix moved and whether the fix worked.

Hence the severity floor, and hence the exception carved into it. Dropping every
new Minor would have dropped all four of the findings that were worth having, since
none of them was graded above Minor; dropping every new Minor **except prose the
fix falsified** keeps all four and drops the nine that were deferred on sight.

The floor removes a report, not a dispatch. On 909 the second round sent four
lenses for 1,606 seconds of agent time and added 517 seconds of wall clock, the
longest of the four, and that arithmetic does not move. What moves is what each
lens spends its context hunting for once breadth stops being the thing that makes
a report look complete, and the ledger rows and decision sentences downstream of
it.

## The model of a dispatch

An agent declares its model in its own frontmatter, and a `model` field in the Agent
input silently overrides it, with nothing in the transcript marking that it did.
Measured over the first thirteen days of funnel use, **101 of 625 funnel dispatches
carried `model: "opus"` written by the orchestrator**: 57 reviewers, 23
implementers, 10 test writers, 8 triages and 3 screen lenses.

The test writer is the one where the override is visible in the bill, because its
frontmatter has said `sonnet` since 0.9.0: its Opus executions cost **US$ 10.87
each against US$ 3.03** on Sonnet, 3.6 times, for the stage with the narrowest input
in the funnel. So the rule is that the model is never written into a dispatch, and
`tests/check-frontmatter.py` holds the table in `SKILL.md` to what the frontmatter
actually says, because two places holding one value is the drift that produced this.

Which stages sit where is the same argument in the other direction. Over the same
thirteen days the reviewer ran **310 times at US$ 2.16 each**, the test writer 81
times, the implementer 101 and the triage 59. The two stages on Sonnet are the two
whose input is already scoped for them: the reviewer is handed a diff file that is
already written plus an exact document list, and the test writer is handed the spec
and the list of files that changed. The two left on `inherit` are the two that read
an open codebase in order to decide something.

## Where the 5h35 went

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

## A body that competes with the diff

Cut, do not compress. The body is the only thing a human reads before deciding
   whether to review the diff, and everything worth keeping already has a better
   home: the reasoning behind each finding goes in the ledger comment, a decision
   about the product goes in the issue, and why a non-obvious line exists goes in
   the code next to it. Measured on 2026-08-17: PR 590 carried 11902 characters
   of prose across 9 sections, 7 of them over the 600 cap, on a change whose
   source diff was 163 lines. Nine minutes of reading to reach a 163-line diff is
   a body that competes with the diff instead of introducing it.

## The worktree leak

`rm <issue>` was here until 0.3.0 and could never succeed: step 3 opens the pull
   request, and an open pull request used to mean KEEP, so every task leaked its
   worktree. 27 of them and 35 GB when it was found.

## Why the budget is in characters

The budget is in characters because "one line each" does not survive contact with
a paragraph. Measured on 2026-08-17: a report that read as six items was 1655
characters and 4 source lines, and rendered as 19 lines in the user's terminal.
100 characters is about one rendered line, so six items at 600 characters is one
sentence each.

## A receipt keyed to the wrong tree

`kit gate` keys a receipt to the tree sha of the working directory, computed in a
throwaway index as `git read-tree HEAD` then `git add -A` then `git write-tree`.
`git add -A` refuses any path that is not a regular file, a symlink or a git
directory, and one such path fails the whole add. `write-tree` then returns the
tree already in the index, HEAD's, and nothing says so.

Every receipt written after that verifies clean against **any** uncommitted change,
which is the one thing a receipt exists to refuse. Found in obranova on 2026-08-30:
three character devices in the repository root, `.bash_profile`, `.bashrc` and
`.gitconfig`, each a bind mount over `/dev/null` created by the agent sandbox to
deny reads, none of which exist outside it. The gate had been reporting
`3 skipped by receipt` against `tree 41ef1b66`, which is `git rev-parse HEAD^{tree}`.

```bash
# The failure, if it ever returns HEAD's tree, is this equality.
kit gate --receipts | head -1        # tree <working directory>
git rev-parse HEAD^{tree}            # must differ whenever anything is uncommitted
```

The fix excludes exactly the paths git named, one per attempt because `git add -A`
reports the first and aborts, and dies if the add fails for any other reason. A
silent wrong answer here is worse than a stopped run, because the receipt is what
a pre-push hook trusts when it decides not to run the suite.

## Buying back the reading a slice lens is denied

The reviewer discipline is what makes a slice lens cost about two dollars: it reads
one already-written diff file and a named document list, and nothing else. The
defects that survive it are the ones whose cause is in the diff and whose effect is
not.

Measured on pull requests 879 and 880, an outside reviewer reading whole files
returned four findings each, eight of eight of that shape, none reached by any
slice lens: a value hardcoded to `0` silencing a warning rendered two hundred lines
lower in the same file, a `save` action validating a field the function it routes to
ignores, a `\d+` regex against a `VARCHAR(32)` column, a release interval anchored
to the newest tag so a failed release is skipped forever. That reviewer's own
opening line was that it had read 84 files, including files the diff does not touch.

So the permission is bought back for one lens and paid for with grep. On the merge
of 880 the full-read list came to eight files and 126 KB after the two prose files
over 40 KB were named as skipped, against the 340 KB reading them whole would have
cost, and the caller list is ranked by how many of the exported names each file
references. Unfiltered, that same diff yielded `result`, `hours`, `rate` and
`order`, which rank `prisma/schema.prisma` first; exported only, it yields twelve
names, one of them the `pickCostSnapshot` that was finding number two.

## The push that runs the gates a second time

A repository whose pre-push hook runs its own lint, types and suite runs them again
on a tree `kit gate ship` has already proved. Measured in obranova on 2026-08-30
against a clean `develop`: lint 101s, types 72s, suite 186s, so **359 seconds per
push**, and a fix round pushes again. The hook's guard is one line, and it fails
open, which is what makes it safe to add:

```sh
kit gate --verify ship >/dev/null 2>&1 && exit 0
```

No receipt, a tree that moved since one was written, or no `kit` on the path all
exit non-zero, and the checks run exactly as before. A push by hand with no funnel
behind it is that case.
