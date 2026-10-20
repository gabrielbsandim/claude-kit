# task, stage 4 in full

Read this when the funnel reaches stage 4, before writing the review dispatches.
It is the depth behind the bullets `SKILL.md` keeps inline, and it is split out so
that a task that never reaches a review never pays for it.

### One round, then a verifier

A round is: `kit review` prints the dispatches, each block goes verbatim to its own
`task-funnel:funnel-reviewer`, and every Critical or Important finding they return
goes to **one** `task-funnel:funnel-verifier` before anything is fixed.

```
kit review                       # the lane from risk.paths, and the round it is
kit review --since <sha>         # risk lane, round 2: the fix diff only
kit lane src/billing/charge.ts   # which lane a file list would take, and why
```

The verifier exists because a reviewer is paid to find things and a round is paid
for by whatever it finds. About half of what automated review comments say is
rejected by the people who read them, and a fix for a defect that was never there is
new code nobody asked for, which the next round then reviews. So the verifier is
asked to refute, and returns one of three per finding:

| Verdict | Means | What happens |
| --- | --- | --- |
| REAL | reproduced, or traced input to wrong output in the code as committed | fixed in this session, this round |
| REFUTED | the code handles it, the input cannot reach it, or the evidence restates the claim | dropped, one row in the body's table |
| PRE-EXISTING | real, on a line this diff did not change | one line in the body, after `kit issues related` |

Its dispatch carries the worktree path, the diff files the round used, and the
findings numbered in the order they came back. Nothing else: it has its own
instructions. A finding the reviewer itself tagged `PRE-EXISTING` skips the verifier,
since it costs no round either way.

**REAL findings are fixed, all of them, in one pass**, then
`kit gate implement_fix_round` and one commit. Not deferred: a verified defect in this
change is this change's work, and a deferral is a second pull request that reloads
all of this context to do what this one could have done in a line.

### The rubric

In every dispatch, because an uncalibrated reviewer is what multiplies rounds. The
reviewer carries it in its own instructions; the dispatch does not restate it.

- **Critical**: data loss, security, money, breaks production.
- **Important**: the task is not trustworthy until fixed: incorrect or fragile
  behaviour, a missed requirement, a literal duplicated block of logic, a swallowed
  error, a test that asserts nothing.

There is no third grade. "Coverage could be broader", naming and style are not
reported at all: a Minor that is reported buys a table row and a decision sentence
for work nobody is going to do.

Each finding is also tagged by **origin**: `NEW` when the diff introduced it,
`PRE-EXISTING` when the line was already like that. A reviewer that cannot tell the
two apart sends this change back for its neighbours' defects.

### ALREADY DECIDED

From round 2 on, and on any review of a branch where the user already answered
something, the task's half of the dispatch carries an `ALREADY DECIDED` list: each
finding a previous round raised and how it was settled, fixed with the sha, refuted,
or kept as the user chose. A reviewer that re-raises one of those is told by its own
instructions to drop it. Without the list, the second round spends itself
re-litigating the first.

### The screens, in a real browser, on the risk lane

A diff lens reads what the code says. It cannot tell you that the submit button is
below the fold on a phone, that the table scrolls the page sideways, or that the save
succeeds and the screen says nothing. So when a risk-lane change touched a screen, the
review has a browser half that runs alongside the diff dispatches.

```
kit screens             # the routes, and the ones it could not resolve
kit screens --json      # the same, to paste into the dispatch
kit screens --preflight # whether the browser half can run at all, and why not
```

`kit screens` walks the import graph from each changed file up to the router entry
point that reaches it, so a component nested three levels below a page still yields a
URL. Nothing here guesses a route inside a prompt.

Run the browser half when **all four** hold, and skip it otherwise:

1. the lane is risk,
2. `browser.enabled` is true and the effort level is in `browser.efforts`,
3. `kit screens` returned at least one route under `visit`,
4. `kit screens --preflight` printed `ready`.

The preflight is there because every way this half failed before failed after the
dispatch went out: the env file `browser.start` reads was masked by the sandbox, an
auth variable it needed was not in that file, a previous browser profile still held
its lock, or the port already answered from another checkout's build. It checks each
of those and exits 3 naming the first blocker. **A blocker is a line in the report,
never something to work around inside the lens.**

Then **one** dispatch to `task-funnel:funnel-screen-lens`, answering two numbered
parts from one visit per route: part 1 is whether it works, part 2 is whether it can
be used. It gets the base URL, the `visit` list verbatim, the viewports, the spec's
acceptance criteria, and `browser.uxDocs`, which anchors part 2 to this repo's
conventions instead of to taste. One, not two: the browser is shared and two of them
corrupt each other's reads (`evidence.md` &middot; *One browser, one tab*).

- **You bring the app up, because the lens cannot.** The agent has no `Bash` on
  purpose, so `browser.start` and the `readyPath` poll are yours.
- **`kit screens` printing `blocked` is a result, not noise.** A dynamic route with
  no value in `routeParams` and a component no page imports are both screens nobody
  is going to look at. Carry them into the report.
- **Credentials by environment variable name only.** `funnel-config check` refuses a
  value in `browser.auth`, and the agent cannot read a secret the dispatch did not
  already hand it.

A finding from the lens goes through the verifier like any other. A browser is the
most nondeterministic thing in this funnel, so it never becomes a gate.

### What may actually run at once

Three lanes of work, and the rule is that each owns a resource:

| Work | Owns | How many at once |
| --- | --- | --- |
| review | nothing, it only reads diff files | up to `maxParallelAgents` |
| browser | the shared browser, the dev server, the app's data | exactly 1 |
| gates | the working tree | `gateJobs`, with `exclusive` gates alone |

Review and browser genuinely overlap. Two things that look parallel are not:

- **Two vitest runs in one working tree.** They fight over files each of them owns,
  which is what `exclusive` is for and why `gateJobs` defaults to 1.
- **The browser next to a heavy gate, on a small machine.** Overlapping it with lint
  and types is free. Overlapping it with the suite is how a gate fails for memory and
  gets read as a flake (`evidence.md` &middot; *Two things that look parallel*).

Before raising `gateJobs`, run `kit config check`: it prints, per stage, which gates
would share and which run alone. Removing work beats overlapping it, by a wide margin
(`evidence.md` &middot; *What concurrency is worth*).

### Reviewer discipline, pure token gain

The reviewer carries these in its own instructions. They are here so that a dispatch
does not contradict them:

- **It reads the diff file it was given, once,** and does not run `git`.
- It does not sweep the codebase. Outside the diff it opens only what a **named**
  risk needs, one focused check. The exception is the `consequences` lens below.
- It does not run the suite. The gates already did.
- **It does not dispatch subagents.**
- **Do not write a model into the dispatch.** The reviewer runs Sonnet from its own
  frontmatter. The one legitimate override is a `model` line `kit review` printed,
  which it prints only when `reviewModel` asks for one at this effort level
  (`evidence.md` &middot; *The model of a dispatch*).
- The final message **is** the report: verdict first, no preamble.

### Two lenses that arrive with their own reading list

**`claims`**. Every sentence this change writes **or leaves standing** is re-read
against the code as committed. What gets through the other lenses is the prose the
change **falsified**, not the prose it asserts. `kit review` hands this lens a
grep-precomputed candidate list, built from the declaration names and multi-digit
literals the diff touched, instead of whole documents to read. Candidates, not
findings: each is verified against the code.

**`consequences`**. Every other rule makes a reviewer cheap by refusing it the
codebase, and the defects that refusal hides are the ones whose cause is in the diff
and whose effect is not: a value hardcoded to `0` that silenced a warning two hundred
lines lower, a `\d+` regex against a `VARCHAR(32)` column
(`evidence.md` &middot; *Buying back the reading a slice lens is denied*). So this lens
is declared `readsOutsideDiff`, **dispatched alone**, and handed two precomputed lists
it may not leave:

- **the files the diff touched, to be read whole**, ranked by how much of each the
  change rewrote, capped at 25, with a file over 40 KB named as skipped rather than
  dropped, because a list with a silent gap in it is a list an agent goes and fills;
- **the callers outside the diff** of the declarations the diff exports, ranked by
  how many of them each file references.

Its question is: **what else already depended on what this changed, and does it still
hold?** A finding here still needs a named consumer and a concrete failure.

### The second round, on the risk lane only

The direct lane has one round: the fix ships on its gates. The risk lane runs
`kit review --since <the sha round 1 reviewed>` once, and that round is
**incremental**. Each lens receives the fix diff plus the round 1 findings it is
verifying, answers `ADDRESSED` or `NOT ADDRESSED` per finding, and reports only new
Critical or Important breakage inside the fix diff, plus one thing that is not a
severity: **prose the fix falsified**, which it reports whatever its weight, because
the fix introduced it (`evidence.md` &middot; *What a second round returns*).

**A slice the fix never touched is not dispatched.** A `--since` round prints
`skipped` for it, and that line is the whole instruction. A reviewer at an empty diff
still pays a full cold context to report nothing (`evidence.md` &middot; *An empty
slice on a fix round*).

### The cap is counted

`kit review` records each head SHA it reviewed, per branch. The same head again is
the same round; a new head past the lane's cap is refused with exit 3. The cap comes
from `lanes.<lane>.maxRounds`, falling back to `maxRounds`. Only the user buys
another round, with `kit review --reset-rounds`, and the agent does not run that on
its own: two pull requests once ran 21 and 25 rounds under a cap that was only
written down (`evidence.md` &middot; *Rounds without a counter*).

**At the cap every open finding gets a written decision** in the body's table. Silent
discard is prohibited. A round whose fix is larger than the original commit is not a
round, it is the spec having been wrong: say so and stop.

### The findings table goes in the body

One row per finding that reached the verifier, most severe first. Rows cost nothing
against `kit pr-body`'s prose budget, which is why the table replaced the separate
ledger comment: three of those measured 3734 to 4515 characters of prose each, every
one longer than the body it sat under (`evidence.md` &middot; *Why the ledger has a
budget*).

| Sev | Lens | Verifier | Finding | Decision |
| --- | --- | --- | --- | --- |
| Critical | correctness | REAL | the retry path drops the payload on timeout | fixed, `a1b2c3d` |
| Important | consequences | REFUTED | the caller already guards the empty list | dropped |
| Important | tests | PRE-EXISTING | the fixture never sets the tenant | #612 |

`Finding` is one line: what is wrong, not why you believe it. `Decision` is fixed with
the sha, dropped, or the issue that owns it. The body's last line is the lane marker,
`<!-- funnel: direct -->` or `<!-- funnel: risk -->`.

A comment answering a person's question in review still goes through `kit ledger`,
which holds it to at most 1000 characters of prose. Over budget, **cut, do not
compress**.
