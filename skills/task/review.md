# task, stage 4 in full

Read this when the funnel reaches stage 4, before writing the review dispatches.
It is the depth behind the five bullets `SKILL.md` keeps inline, and it is split out
so that a task that never reaches a review never pays for it.

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

- **Two vitest runs in one working tree.** Two suites in one tree fight over files
  each of them owns, which is what `exclusive` is for and why `gateJobs` defaults to 1.
- **The browser lane next to a heavy gate, on a small machine.** Overlapping the
  browser with lint and types is free. Overlapping it with the suite is how a gate
  fails for memory and gets read as a flake. Check the machine before assuming the
  lane is free (`evidence.md` &middot; *Two things that look parallel*).

Before raising `gateJobs`, run `kit config check`: it prints, per stage, exactly
which gates would share and which run alone, and it fails when one gate's command
expands to another's plus a flag, since that stage is paying for the same work
twice.

Removing work beats overlapping it, and the numbers say so by a wide margin
(`evidence.md` &middot; *What concurrency is worth*).

### Reviewer discipline, pure token gain

Put these in every review dispatch:

- **Read the diff file you were given, once.** Its context lines are the changed
  file. Do not open the file again unless a hunk is cut off, and do not run
  `git` at all.
- Do not sweep the codebase. Look outside the diff only for a **named** risk,
  one focused check, naming both the risk and the check. The one exception is a
  dispatch whose plan line says *reads outside the diff*, which arrives with the
  list of files it may open and may open no others.
- Do not run the suite. The implementer already did. A focused test only for a
  specific doubt.
- **A reviewer does not dispatch subagents.** A reviewer spawned by a reviewer
  duplicates another at full cost and its verdict carries no weight.
- **Do not write a model into the dispatch.** The reviewer runs Sonnet from its own
  frontmatter, because its input is already scoped for it: a diff file that is
  already written, plus an exact document list. The one legitimate override is a
  `model` line `kit review` printed, which it prints only when this repo's
  `reviewModel` asks for an escalation at this effort level. No line, no model
  (`evidence.md` &middot; *The model of a dispatch*).
- The final message **is** the report: verdict first, no preamble, no closing
  summary.

### The two lenses most repos are missing

Both were the human reviewer's finding number one on the first two pull requests
this funnel delivered, and none of the code lenses had reached them
(`evidence.md` &middot; *The two lenses*).

**`failure-edges`**. Walk every new I/O call and answer, per call: is there a
`catch`, is there a timeout, does the failure leave a log, and what is lost if it
throws here.

**`claims`**. Every sentence this change writes **or leaves standing** is re-read
against the code as committed. What gets through the other lenses is the prose the
change **falsified**, not the prose it asserts. `kit review` hands this lens a
**grep-precomputed candidate list** instead of two 15 KB files to read, built from
the declaration names and multi-digit literals the diff touched. Candidates, not
findings: each is verified against the code.

### The lens that is allowed to read outside the diff

Every rule above makes a reviewer cheap by refusing it the codebase, and that
refusal has a cost of its own: the defects it cannot see are the ones whose cause
is in the diff and whose effect is not. Measured on pull requests 879 and 880, an
outside reviewer reading whole files returned **four findings each**, eight of
eight of that shape, and no slice lens had reached any of them: a value hardcoded
to `0` that silenced a warning rendered two hundred lines lower in the same file,
a `save` action validating a field the function it routes to ignores, a `\d+`
regex against a `VARCHAR(32)` column, an interval anchored to the newest tag so a
failed release is skipped forever.

So one lens buys the permission back, `consequences`, and pays for it with grep
rather than with a sweep. It is declared `readsOutsideDiff` and **dispatched
alone**: an agent given one prompt that says "read only the diff" and another that
says "open these files" follows the looser one. `kit review` hands it two lists,
both precomputed, and it may open nothing else:

- **the files the diff touched, to be read whole and not as hunks.** Ranked by how
  much of each the change rewrote, capped at 25, and a file over 40 KB is named as
  skipped rather than dropped, because a list with a silent gap in it is a list an
  agent goes and fills. `git diff -U8` is eight lines of context, and the
  consequence of a change is routinely further away than that *inside the same
  file*.
- **the callers outside the diff**, from the declarations the diff exports,
  ranked by how many of them each file references. Exported only: the unfiltered
  form on 880 yielded `result`, `hours` and `rate`, which rank the schema first
  and spend the whole budget on files that merely contain the word.

Its question is not "is this line correct". It is: **what else already depended on
what this changed, and does it still hold?** Signature, ordering, a default now
written where a caller reads it, a column narrower than the value, a branch made
unreachable, a warning silenced. A finding here still needs a named consumer and a
concrete failure, and it grades on the same rubric as any other lens.

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

**The ledger is posted as a comment on the pull request**, once the URL exists. A
comment is next to the diff, collapses on its own, and does not have to be read
before deciding whether to review. The scratchpad file it replaced was written to
nobody, and the body absorbed it (`evidence.md` &middot; *Why the ledger is a comment*).

### The ledger is a table, and it has a budget

A comment nobody finishes reading is a comment nobody read. Measured on 2026-08-29,
the ledgers on pull requests 874, 877 and 880 carried **4515, 4432 and 3734
characters of prose**, each more than twice the 2000 the body itself is allowed,
and the body is the part written to be read first.

So the ledger is **a table plus a few sentences**, and the split is not a style
preference: `kit ledger` counts prose and ignores table rows, exactly as
`kit pr-body` does, so a finding moved into a row costs nothing and a finding
explained in a paragraph costs its full length.

One row per finding, in this order, most severe first:

| Sev | Lens | Verdict | Finding | Decision |
| --- | --- | --- | --- | --- |
| Critical | failure-edges | CONFIRMED | the retry path never logs what was lost | fixed, `a1b2c3d` |
| Important | conventions | PLAUSIBLE | the hook could be a selector | deferred, #612 |

`Finding` is one line: what is wrong, not why you believe it. `Decision` is one of
fixed with the sha, deferred with the issue, or dismissed with four words of
reason. The reasoning behind a finding belongs in the row's own thread if anybody
asks for it, and until somebody asks, it is not owed.

Prose is then for what a table cannot hold: what the rounds converged on, and what
the reviewer of this pull request should look at with their own eyes.

```
kit ledger <file>          # at most 1000 characters of prose, 350 per section
gh pr comment <n> --body-file <file>
```

Over budget it exits 3 and prints the sections by size. **Cut, do not compress**,
and the same rule the body has applies here: everything worth keeping has a better
home. A follow-up comment answering a review is a ledger too, and runs the same
command: measured on the same day, the "Resposta ao review" comment on 880 was
3419 characters against a body of 1876 (`evidence.md` &middot; *Why the ledger has a
budget*).

The re-review after a fix round is **incremental**, which is what `--since`
does: the lens receives the fix diff plus the list of findings it is verifying,
each answered `ADDRESSED` or `NOT ADDRESSED`, plus new breakage inside the fix
diff only. A full re-read is warranted only when the fix moved a contract, a
signature, a route, a schema, an order of operations, and then only for the
lenses that contract touches.

**A slice the fix never touched is not dispatched at all.** A `--since` round
prints `skipped` for it and names the slice, and that line is the whole
instruction: do not send it, do not send it with an apology in the prompt. A
reviewer at an empty diff still pays a full cold context to report that there is
nothing to report, and a fix that touched only `src` was re-dispatching the tests
and surfaces slices every round. The first round never skips, because there an
empty slice is a fact worth having stated (`evidence.md` &middot; *An empty slice on
a fix round*).

**A new Minor on a fix round is not reported.** What the round owes is `ADDRESSED`
or `NOT ADDRESSED` per finding it was sent, plus anything new it grades Critical or
Important, plus one thing that is not a severity at all: **prose the fix
falsified**, a comment, a document or a knowledge entry the fix itself made untrue.
That one is reported whatever its severity, because the fix introduced it. Anything
else new and Minor is dropped, not deferred: a deferred Minor buys a ledger row and
a decision sentence for work nobody is going to do. Measured across two second
rounds, 13 findings, none above Minor, and the only four that changed a line were
prose (`evidence.md` &middot; *What a second round returns*).

Cap at `maxRounds`, and **at the cap every open finding gets a written
decision**. Silent discard is prohibited. A round whose fix is larger than the
original commit is not a round, it is the spec having been wrong: say so and
stop.
