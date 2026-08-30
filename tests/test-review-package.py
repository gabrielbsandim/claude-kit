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
RP = os.path.join(KIT, "bin", "review-package")
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
    out = subprocess.run([RP] + list(args), cwd=root, capture_output=True, text=True)
    return out.stdout + out.stderr


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
finally:
    shutil.rmtree(root, ignore_errors=True)

print(f"{PASS} passed, {len(FAIL)} failed")
for line in FAIL:
    print(f"  FAIL {line}")
sys.exit(1 if FAIL else 0)
