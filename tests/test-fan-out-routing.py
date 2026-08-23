#!/usr/bin/env python3
"""The stage 0 routing call, and the triage verdict that backs it up.

A rule that lives only in prose drifts the moment nothing compares its halves.
This file compares them: the skill and the agent have to agree on the verdict
name, the criterion has to be the surface table rather than a line count, and the
one decision the user made has to still be the one written down.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "task", "SKILL.md")
EVIDENCE = os.path.join(ROOT, "skills", "task", "evidence.md")
TRIAGE = os.path.join(ROOT, "agents", "funnel-triage.md")

failures = []
passes = 0


def check(name, cond, detail=""):
    global passes
    if cond:
        passes += 1
    else:
        failures.append(f"{name}: {detail}")


def flat(text):
    """Collapse whitespace, because markdown wrapping is arbitrary.

    Every check here is about whether a rule is present, never about where the
    line broke. The first version compared against the wrapped text and failed on
    a sentence that was there, split across two lines by the 80-column fill.
    """
    return re.sub(r"\s+", " ", text)


SKILL_RAW = open(SKILL, encoding="utf-8").read()
EVIDENCE_RAW = open(EVIDENCE, encoding="utf-8").read()
TRIAGE_RAW = open(TRIAGE, encoding="utf-8").read()
skill = flat(SKILL_RAW)
evidence = flat(EVIDENCE_RAW)
triage = flat(TRIAGE_RAW)

# 1. The routing question is at stage 0, ahead of the triage dispatch. Anywhere
#    later and it pays the floor it exists to avoid.
LANE_Q = "**Which lane.**"
stage0 = skill.index("## Stage 0")
stage1 = skill.index("## Stage 1")
routing = skill[stage0:stage1]
check("1 the lane question lives in stage 0", LANE_Q in routing,
      "the question is not in the stage 0 section")
# `find`, not `index`: a missing marker is a red test, not a traceback. The first
# version raised here, so a mutation that moved the section reported as a broken
# test rather than as the rule being gone.
check("1 the lane call precedes stage 1", 0 <= skill.find(LANE_Q) < stage1,
      "the lane call is at or after the triage dispatch")

# 2. The criterion is the surface table, and every one of the five rows is named.
#    Dropping a row is how "permission" quietly stops being checked.
for surface in ("Contract", "Behaviour", "Data", "Money, permission, tenancy", "Published prose"):
    check(f"2 surface row {surface!r}", surface in routing, "row missing from the table")

# 3. It says out loud that size is the wrong axis, with the example that makes it
#    concrete. Without this the table reads as a proxy for "small".
check("3 size is refused as the axis", "Not a line count" in routing, "the anti-criterion is gone")
check("3 the auth-guard example survives", "auth guard" in routing,
      "the one-line-is-dangerous example is gone")

# 4. Announce and proceed, which is what the user chose on 2026-08-18. A later
#    edit that turns this into a confirmation round is reversing a decision, and
#    reversing it silently is the failure this case pins.
check("4 announce and proceed", "Announce and proceed" in routing, "the mode changed")
check("4 the decision is dated", "2026-08-18" in routing, "the provenance of the choice is gone")
check(
    "4 confirmation is not reintroduced",
    "announce-and-confirm" not in routing.replace("over announce-and-confirm", ""),
    "a confirmation round crept back in",
)

# 5. The short lane is a funnel, so every rail the long one runs it runs too. The
#    two-lane table is where that is stated, and each row is a thing a later edit
#    can drop without looking like it dropped anything.
check("5 the two-lane table exists", "### The two lanes, and what they share" in routing,
      "the section naming what both lanes run is gone")
for rail in (
    "Stage 0 pre-flight",
    "Board to in progress",
    "Branch and worktree from the config",
    "`kit gate` for the stage",
    "Commit under the repo's convention",
    "`kit gate ship`, push, draft pull request",
    "Body under the `kit pr-body` budget",
    "`kit board in_review`, `kit worktree gc --yes`",
):
    row = re.search(re.escape("| " + rail + " |") + r"\s*(\w+)\s*\|\s*(\w+)\s*\|", routing)
    check(f"5 the table has a row for {rail!r}", row is not None, "rail missing from the table")
    check(
        f"5 both lanes run {rail!r}",
        row is not None and row.group(1) == "yes" and row.group(2) == "yes",
        f"the row says {row.groups() if row else None}, so the short lane dropped a rail",
    )
check("5 it is a funnel, not the discipline removed",
      "not the long one with the discipline removed" in routing, "the framing guard is gone")
check("5 the short lane creates no issue", "never creates one" in routing,
      "nothing stops a typo from opening an issue")

# 6. Uncertainty escalates. This is the asymmetry the whole design rests on, so
#    it is stated in the skill rather than left to judgement.
check("6 doubt goes up", "Uncertainty goes up, never down" in routing, "the bias rule is gone")

# 7. The floor is a measured number with its origin, not a vibe. 2.46 is what one
#    real triage agent cost, and it is the reason the call is at stage 0 at all.
#    The number lives in evidence.md since the skill was split, and the skill has
#    to keep pointing at it: a rule whose measurement nobody can reach is a rule
#    the next reader deletes.
check("7 the floor is quoted", "2.46" in evidence, "the measured triage cost is gone")
check("7 the floor has its unit", "9.4 minutes" in evidence, "the wall clock half is gone")
check("7 the skill still points at the floor", "The triage floor" in routing,
      "the pointer from stage 0 to evidence.md is gone")

# 8. Both files know the same verdict name. This is the pair that actually breaks
#    at runtime: triage returns a token the orchestrator has no branch for, and the
#    orchestrator falls through to its default, which is the long lane.
check("8 triage declares SHORT_FUNNEL", "SHORT_FUNNEL" in triage, "the verdict is not in the agent")
verdict_line = next(
    (l for l in TRIAGE_RAW.splitlines() if l.startswith("VERDICT:")), ""
)
check("8 the return shape has a VERDICT line", verdict_line != "", "no VERDICT line at all")
check(
    "8 the verdict is in the return shape",
    "SHORT_FUNNEL" in verdict_line,
    f"declared in prose but not in the shape the agent returns: {verdict_line!r}",
)
# The branch, not merely the token. Grepping the whole skill passed while the
# orchestrator had no branch at all, because the name still appeared in the list of
# verdicts the dispatch returns. That mutation survived, so this asserts the arrow.
check(
    "8 the orchestrator has a branch for it",
    re.search(r"`SHORT_FUNNEL` →", skill) is not None,
    "the name appears but nothing says what to do with it",
)

# 9. The branch says where the run goes next. A verdict with no destination is a
#    verdict that gets read and then ignored.
gate_at = skill.find("**GATE**")
gate = skill[gate_at:gate_at + 1400] if gate_at >= 0 else ""
check("9 the gate section exists", gate != "", "no **GATE** in the skill")
check("9 the branch names its destination", "stage 5" in gate,
      "the branch does not say where the run continues")
check("9 the branch keeps the two-lane rails", "two-lane table" in gate,
      "the branch does not tie back to what the short lane still runs")

# 10. Triage must not return the verdict for smallness either, or the backstop
#     reintroduces the axis the skill just refused.
tri_at = triage.find("- `SHORT_FUNNEL`")
tri_verdict = triage[tri_at:] if tri_at >= 0 else ""
check("10 the triage verdict is documented", tri_verdict != "", "no prose for the verdict")
check("10 triage refuses the size axis", "because the diff looks small" in tri_verdict,
      "the agent may return the verdict for smallness")
check("10 triage still returns the spec", "still return the spec" in tri_verdict,
      "without the spec the orchestrator has nothing to implement against")

# 11. And it must not re-dispatch to shop for a different answer, which is the
#     obvious way to spend the floor twice.
check("11 no second triage", "spent to disagree" in gate, "re-dispatch is not refused")

print(f"{passes} passed, {len(failures)} failed")
for line in failures:
    print(f"  FAIL {line}")
sys.exit(1 if failures else 0)
