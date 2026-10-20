#!/usr/bin/env python3
"""Proves that a fix round dispatches the slices the fix touched, and only those.

    python3 tests/test-review-package.py

A reviewer sent at an empty diff still pays a full cold context to report that
there is nothing to report, and until 0.10.0 every `--since` round re-dispatched
every slice regardless. On the repository this funnel was built against, the
reviewer ran 310 times over thirteen days at US$ 2.16 each, which is the fan-out
this file exists to bound.

The first round never skips: an empty slice there is a fact worth having stated,
and the reviewer's silence is not the same statement as the reviewer's absence.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RP = os.path.join(KIT, "scripts", "review-package")
PASS, FAIL = 0, []

CFG = {
    "base": "main",
    "slices": {
        "src": "origin/main...HEAD -- src ':(exclude)src/tests'",
        "tests": "origin/main...HEAD -- src/tests",
        "all": "origin/main...HEAD",
    },
    "lenses": {
        "correctness": {"slice": "src", "docs": []},
        "tests": {"slice": "tests", "docs": []},
        "claims": {"slice": "all", "docs": [], "grepTargets": ["docs"]},
    },
    "effort": {"standard": ["correctness", "tests", "claims"]},
    "maxParallelAgents": 3,
}


def check(name, ok, detail=""):
    global PASS
    if ok:
        PASS += 1
    else:
        FAIL.append(f"{name}: {detail}")


def git(root, *args):
    subprocess.run(["git"] + list(args), cwd=root, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write(root, path, text):
    full = os.path.join(root, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as fh:
        fh.write(text)


def run(root, *args):
    """A plan with the round count cleared first: the cases below are about slices,
    and section 11 is the one about the cap."""
    extra = ["--reset-rounds"] if "--dispatches" in args else []
    out = subprocess.run([RP] + list(args) + extra, cwd=root, capture_output=True, text=True)
    return out.stdout + out.stderr


def raw(root, *args):
    return subprocess.run([RP] + list(args), cwd=root, capture_output=True, text=True)


def dispatched(text):
    """The slices a plan would actually send an agent at."""
    return re.findall(r"^dispatch \d+   parts:(.*)$", text, re.M)


def skipped(text):
    return re.findall(r'^  the fix since \S+ touched nothing in slice "(\w+)"$', text, re.M)


root = tempfile.mkdtemp(prefix="kit-review-")
try:
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    write(root, ".claude/funnel.config.json", json.dumps(CFG))
    write(root, "docs/readme.md", "the number is 41\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")

    # The first pass: source and tests both move, so all three slices carry something.
    write(root, "src/thing.ts", "export const answer = 42\n")
    write(root, "src/tests/thing.test.ts", "test('answer', () => {})\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "first pass")
    first = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                           capture_output=True, text=True).stdout.strip()

    out = run(root, "--dispatches", "standard")
    check("1 the first pass dispatches every slice", len(dispatched(out)) == 3, out)
    check("1 and skips nothing", skipped(out) == [], out)
    check("1 the count line agrees", "3 dispatch(es)" in out, out)

    # The fix round: only source moves. The tests slice has nothing in it, and a
    # reviewer sent at it would read an empty diff at full price.
    write(root, "src/thing.ts", "export const answer = 43\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fix round")

    out = run(root, "--dispatches", "standard", "--since", first)
    check("2 the untouched slice is skipped", skipped(out) == ["tests"], out)
    check("2 the touched slices still dispatch",
          len(dispatched(out)) == 2, out)
    check("2 the count line counts what was sent", "2 dispatch(es)" in out, out)
    # The skip has to name the slice, because the line is the whole instruction the
    # orchestrator gets: "skipped" with no name is a line nobody can act on.
    check("2 the skip names the slice", 'slice "tests"' in out, out)

    # A fix that touched nothing at all sends nobody, rather than sending three
    # agents to confirm it.
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, text=True).stdout.strip()
    out = run(root, "--dispatches", "standard", "--since", head)
    check("3 an empty fix round dispatches nobody", dispatched(out) == [], out)
    check("3 and says so", "0 dispatch(es)" in out, out)

    # 3b. A claims lens whose grep candidates match nothing still prints a complete
    #     plan. Found by this file: under `set -o pipefail` the grep's exit 1 became
    #     the pipeline's status and `set -e` killed the plan after the dispatch lines
    #     were already on stdout, so the caller read a plan with the count line
    #     missing and had nothing to tell it apart from a plan.
    out = run(root, "--dispatches", "standard")
    check("3b no candidate matched is not a failure", "none matched" in out, out)
    check("3b and the plan still ends with its count", "dispatch(es), max" in out, out)

    # 3c. The reviewer's model is its frontmatter, and a dispatch that writes one
    #     itself silently overrides it. With no `reviewModel` entry the plan says
    #     nothing about a model, which is the instruction to pass none.
    out = run(root, "--dispatches", "standard")
    check("3c no reviewModel prints no model line", "  model " not in out, out)
    # An escalation the repo asked for by effort level is printed instead of
    # remembered, so the one legitimate override has a source the dispatch can cite.
    write(root, ".claude/funnel.config.json",
          json.dumps({**CFG, "reviewModel": {"deep": "opus"}}))
    out = run(root, "--dispatches", "standard")
    check("3c an entry for another level does not leak", "  model " not in out, out)
    write(root, ".claude/funnel.config.json",
          json.dumps({**CFG, "reviewModel": {"standard": "opus"}}))
    out = run(root, "--dispatches", "standard")
    check("3c the level's own entry prints", out.count("  model opus") == 3, out)
    check("3c and names where it came from", "config reviewModel.standard" in out, out)
    write(root, ".claude/funnel.config.json", json.dumps(CFG))

    # 5. The lens that reads outside the diff. It shares the "src" slice with
    #    correctness, and it must still get a dispatch of its own: an agent handed
    #    one prompt saying "read only the diff" and another saying "open these
    #    files" follows the looser one.
    OUTSIDE = {**CFG,
               "lenses": {**CFG["lenses"],
                          "consequences": {"slice": "src", "docs": [],
                                           "readsOutsideDiff": True,
                                           "codeTargets": ["src"]}},
               "effort": {"standard": ["correctness", "tests", "claims", "consequences"]}}
    write(root, "src/caller.ts", "import { answer } from './thing'\nexport const use = answer\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "a caller")
    write(root, ".claude/funnel.config.json", json.dumps(OUTSIDE))
    out = run(root, "--dispatches", "standard")
    groups = dispatched(out)
    check("5 it is not grouped into its slice",
          not any("correctness" in g and "consequences" in g for g in groups), out)
    check("5 it gets a dispatch of its own",
          any(g.strip().startswith("consequences") for g in groups), out)
    check("5 and the plan says why it is alone",
          "alone: reads outside the diff" in out, out)
    check("5 it is told to read the touched files whole",
          "to be read whole and not as hunks" in out, out)
    check("5 and the file the diff touched is on that list",
          "src/thing.ts" in out, out)

    # 5b. A file large enough to be prose is named as skipped rather than dropped:
    #     a list with a silent gap in it is a list an agent goes and fills.
    write(root, "src/thing.ts", "export const answer = 44\n")
    write(root, "src/huge.ts", "// x\n" * 12000)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "a large file")
    out = run(root, "--dispatches", "standard")
    check("5b the oversized file is named, not dropped",
          re.search(r"src/huge\.ts\s+SKIPPED at \d+ bytes", out) is not None, out)
    check("5b and the small ones are still listed with their size",
          re.search(r"src/thing\.ts\s+\(\d+ bytes\)", out) is not None, out)

    # 5c. A fix round skips it too when its slice did not move, on the same rule
    #     every other lens follows.
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                          capture_output=True, text=True).stdout.strip()
    out = run(root, "--dispatches", "standard", "--since", head)
    check("5c an untouched fix round does not dispatch it",
          not any("consequences" in g for g in dispatched(out)), out)
    check("5c and says so by name",
          "parts: consequences" in out and "touched nothing this lens reads" in out, out)
    write(root, ".claude/funnel.config.json", json.dumps(CFG))

    # The first pass is the case that must not have learned this. Same tree, no
    # --since, and every slice goes out even though one of them is empty.
    write(root, ".claude/funnel.config.json",
          json.dumps({**CFG, "slices": {**CFG["slices"],
                                        "tests": "origin/main...HEAD -- src/nothing"}}))
    out = run(root, "--dispatches", "standard")
    check("4 a first pass never skips an empty slice",
          len(dispatched(out)) == 3 and skipped(out) == [], out)

    # 6. A path buys a lens the level does not. Size is the wrong axis for risk, so
    #    the escalation is keyed on which file moved, never on how much of it.
    RISKY = {**OUTSIDE,
             "effort": {"standard": ["correctness", "tests", "claims"]},
             "risk": {"paths": ["*/retry-logic.ts"], "lenses": ["consequences"]}}
    write(root, ".claude/funnel.config.json", json.dumps(RISKY))
    out = run(root, "--dispatches", "standard")
    check("6 no risky path touched, no extra lens",
          not any("consequences" in g for g in dispatched(out)) and "risk " not in out, out)
    write(root, "src/jobs/retry-logic.ts", "export const retries = 3\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "a risky file")
    out = run(root, "--dispatches", "standard")
    check("6 a risky path adds its lens",
          any(g.strip().startswith("consequences") for g in dispatched(out)), out)
    check("6 and names the file and the pattern that matched",
          "src/jobs/retry-logic.ts matches */retry-logic.ts" in out, out)

    # 7. At maxRounds 1 there is no fix round, so reviewing one is refused out loud
    #    rather than quietly paid for.
    write(root, ".claude/funnel.config.json", json.dumps({**CFG, "maxRounds": 1}))
    out = subprocess.run([RP, "--dispatches", "standard", "--since", first], cwd=root,
                         capture_output=True, text=True)
    check("7 a fix round at maxRounds 1 is refused", out.returncode != 0, out.stdout)
    check("7 and says what to do instead", "one decision per finding" in out.stderr, out.stderr)
    out = run(root, "--dispatches", "standard")
    check("7 the first round still runs", len(dispatched(out)) == 3, out)

    # 8. The lite lane defaults to one round and no ledger, and a repo that names a
    #    value still wins over the profile.
    CFGTOOL = os.path.join(KIT, "scripts", "funnel-config")

    def get(key):
        return subprocess.run([CFGTOOL, "get", key], cwd=root, capture_output=True,
                              text=True).stdout.strip()

    write(root, ".claude/funnel.config.json", json.dumps({**CFG, "lane": "lite"}))
    check("8 lite defaults to one round", get(".maxRounds") == "1", get(".maxRounds"))
    check("8 lite defaults to no ledger", get(".ledger") == "false", get(".ledger"))
    out = run(root, "--dispatches", "standard")
    check("8 the plan says it is the lite lane", "lane   lite" in out, out)
    write(root, ".claude/funnel.config.json",
          json.dumps({**CFG, "lane": "lite", "maxRounds": 2}))
    check("8 a value the repo names wins over the profile", get(".maxRounds") == "2",
          get(".maxRounds"))
    write(root, ".claude/funnel.config.json", json.dumps(CFG))
    check("8 the full lane keeps two rounds", get(".maxRounds") == "2", get(".maxRounds"))

    # 9. One reviewer is the lite lane's whole price, so `check` refuses a level whose
    #    lenses sit on two slices, which would dispatch two.
    write(root, ".claude/funnel.config.json", json.dumps({**CFG, "lane": "lite"}))
    out = subprocess.run([CFGTOOL, "check"], cwd=root, capture_output=True, text=True)
    check("9 a lite level over three slices fails check",
          "spreads its lenses over 3 slices" in out.stderr, out.stderr)
    LITE = {**CFG, "lane": "lite",
            "lenses": {"correctness": {"slice": "src"}, "failure-edges": {"slice": "src"}},
            "effort": {"standard": ["correctness", "failure-edges"]}}
    write(root, ".claude/funnel.config.json", json.dumps(LITE))
    out = subprocess.run([CFGTOOL, "check"], cwd=root, capture_output=True, text=True)
    check("9 a lite level on one slice passes that check", "spreads" not in out.stderr,
          out.stderr)
    out = run(root, "--dispatches", "standard")
    check("9 and dispatches exactly one reviewer", len(dispatched(out)) == 1, out)
    write(root, ".claude/funnel.config.json", json.dumps(CFG))

    # 10. A config and its lens document can both be local, untracked, and then they
    #     exist only in the main checkout. From a worktree the document still resolves,
    #     and prints absolute, because the reviewer has no cwd that is sure to be either.
    LOCAL = {**CFG, "lenses": {**CFG["lenses"],
                                "correctness": {"slice": "src", "docs": [".claude/rubric.md"]}},
             "slices": {**CFG["slices"], "src": "origin/main...HEAD -- . ':(exclude)**/*.test.ts'"}}
    write(root, ".claude/funnel.config.json", json.dumps(LOCAL))
    write(root, ".claude/rubric.md", "no if inside if\n")
    git(root, "rm", "-q", "--cached", ".claude/funnel.config.json")
    git(root, "commit", "-q", "-m", "config goes local")
    tree = root + "-wt"
    git(root, "worktree", "add", "-q", "--detach", tree, "HEAD")
    out = run(tree, "--dispatches", "standard")
    check("10 a local lens document resolves from a worktree",
          os.path.join(root, ".claude", "rubric.md") in out, out)

    # 11. The cap is counted, not remembered. A round is one review of one head, so
    #     printing the same plan twice is still one round, and the lane decides how
    #     many heads a branch gets.
    write(root, ".claude/funnel.config.json",
          json.dumps({**CFG, "risk": {"paths": ["src/money/*"]}, "reviewGuide": "docs/readme.md",
                      "effort": {**CFG["effort"], "light": ["correctness"],
                                 "deep": ["correctness", "tests", "claims"]}}))
    git(root, "switch", "-q", "-c", "feat/cap")
    write(root, "src/plain.ts", "export const plain = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "plain")
    lane = raw(root, "--lane").stdout
    check("11 a plain diff is the direct lane", lane.startswith("direct"), lane)
    lane = raw(root, "--lane", "src/money/fee.ts").stdout
    check("11 a named risky file is the risk lane before any code exists",
          lane.startswith("risk") and "src/money/fee.ts matches src/money/*" in lane, lane)
    out = raw(root, "--dispatches", "auto")
    check("11 auto on a plain diff runs the direct lane, round 1 of 1",
          "lane   direct, round 1 of 1" in out.stdout and len(dispatched(out.stdout)) == 1, out.stdout + out.stderr)
    check("11 the review guide is in every dispatch", "docs/readme.md" in out.stdout, out.stdout)
    again = raw(root, "--dispatches", "auto")
    check("11 the same head is the same round", again.returncode == 0 and "round 1 of 1" in again.stdout,
          again.stdout + again.stderr)
    first_cap = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                               text=True).stdout.strip()
    write(root, "src/plain.ts", "export const plain = 2\n")
    git(root, "commit", "-q", "-am", "fix")
    out = raw(root, "--dispatches", "auto")
    check("11 a second head in the direct lane is refused", out.returncode != 0
          and "allows 1" in out.stderr, out.stdout + out.stderr)
    out = raw(root, "--dispatches", "risk", "--since", first_cap)
    check("11 the risk lane allows a second round", out.returncode == 0
          and "lane   risk, round 2 of 2" in out.stdout, out.stdout + out.stderr)
    write(root, "src/plain.ts", "export const plain = 3\n")
    git(root, "commit", "-q", "-am", "fix again")
    out = raw(root, "--dispatches", "risk", "--since", first_cap)
    check("11 and refuses a third", out.returncode != 0 and "allows 2" in out.stderr,
          out.stdout + out.stderr)
    check("11 naming who can buy another", "--reset-rounds" in out.stderr, out.stderr)
    out = raw(root, "--dispatches", "risk", "--reset-rounds")
    check("11 the user's reset starts over", out.returncode == 0 and "round 1 of 2" in out.stdout,
          out.stdout + out.stderr)
    write(root, "src/money/fee.ts", "export const fee = 1\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "money")
    out = raw(root, "--dispatches", "auto", "--reset-rounds")
    check("11 auto on a risky diff runs the risk lane at its effort",
          "lane   risk" in out.stdout and "effort deep" in out.stdout, out.stdout + out.stderr)
    out = subprocess.run([CFGTOOL, "check"], cwd=tree, capture_output=True, text=True)
    check("10 a wildcard in a slice is a pattern, not a missing path",
          "**/*.test.ts" not in out.stderr, out.stderr)
    git(root, "worktree", "remove", "--force", tree)
finally:
    shutil.rmtree(root, ignore_errors=True)

print(f"{PASS} passed, {len(FAIL)} failed")
for line in FAIL:
    print(f"  FAIL {line}")
sys.exit(1 if FAIL else 0)
