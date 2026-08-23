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
  one focused check, naming both the risk and the check.
- Do not run the suite. The implementer already did. A focused test only for a
  specific doubt.
- **A reviewer does not dispatch subagents.** A reviewer spawned by a reviewer
  duplicates another at full cost and its verdict carries no weight.
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
