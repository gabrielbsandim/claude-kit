#!/usr/bin/env python3
"""Proves gate concurrency: that it happens, that exclusive still means alone, and
that a failure survives being run next to a passing gate.

    python3 tests/test-gate-jobs.py

Concurrency is the one feature here that can look correct while being wrong. Three
gates that pass are three gates that pass whether they ran together or not, so
every case below asserts on wall clock or on ordering, never only on the verdict.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(KIT, "bin", "gate")
PASS, FAIL = 0, 0


def check(name, got, want, compare=lambda a, b: a == b):
    global PASS, FAIL
    if compare(got, want):
        PASS += 1
        print("ok    %s  (%s)" % (name, got))
    else:
        FAIL += 1
        print("FAIL  %s\n        got  %r\n        want %r" % (name, got, want))


def git(root, *args):
    subprocess.run(["git"] + list(args), cwd=root, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build(root, cfg):
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    git(root, "commit", "-q", "--allow-empty", "-m", "base")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    os.makedirs(os.path.join(root, ".claude"), exist_ok=True)
    with open(os.path.join(root, ".claude/funnel.config.json"), "w") as fh:
        json.dump(cfg, fh)


def run(root, *args):
    started = time.time()
    out = subprocess.run([GATE] + list(args), cwd=root, capture_output=True, text=True)
    return {"seconds": time.time() - started,
            "stdout": out.stdout, "stderr": out.stderr, "code": out.returncode}


SLEEP = 2

CFG = {
    "base": "main",
    "gates": {
        "a": {"cmd": "sleep %d" % SLEEP},
        "b": {"cmd": "sleep %d" % SLEEP},
        "c": {"cmd": "sleep %d" % SLEEP},
        # Writes the moment it starts and again when it ends, so an overlap with
        # another gate is provable from the file rather than from the clock alone.
        "solo": {"cmd": "echo solo-start >> order.log; sleep %d; echo solo-end >> order.log" % SLEEP,
                 "exclusive": True},
        "noisy": {"cmd": "echo other-start >> order.log; sleep %d; echo other-end >> order.log" % SLEEP},
        "boom": {"cmd": "echo o-motivo-real >&2; exit 1"},
    },
    "stages": {
        "three": ["a", "b", "c"],
        "barrier": ["noisy", "solo"],
        "mixed": ["a", "boom"],
    },
    "slices": {"all": "{base}...HEAD"},
    "lenses": {},
    "effort": {},
}


def main():
    root = tempfile.mkdtemp(prefix="kit-gatejobs-")
    try:
        build(root, dict(CFG, gateJobs=3))

        r = run(root, "three")
        check("three 2s gates at jobs=3 finish in about one gate's time",
              round(r["seconds"], 1), SLEEP + 1.5, lambda got, lim: got < lim)
        check("all three still pass", r["stdout"].count("pass"), 3)
        check("the parallel line names them", "3 gates at once" in r["stdout"], True)

        # Same gates, serial, and the receipts from the run above have to be ignored
        # or this measures nothing.
        r = run(root, "--force", "--jobs", "1", "three")
        check("the same gates at jobs=1 take the sum",
              round(r["seconds"], 1), SLEEP * 3, lambda got, low: got >= low)

        # Output integrity: a pass line must never be spliced by another gate's.
        r = run(root, "--force", "three")
        bad = [ln for ln in r["stdout"].splitlines()
               if ln.strip() and not re.match(r"^(\w[\w-]*\s+(pass|run|skip|FAIL)|parallel|\d+ ran|$)", ln)]
        check("no line is spliced by a concurrent gate", bad, [])

        # An exclusive gate is a barrier: its neighbour must be finished before it
        # starts. Proven from the order file, not from the wall clock.
        open(os.path.join(root, "order.log"), "w").close()
        r = run(root, "--force", "barrier")
        order = open(os.path.join(root, "order.log")).read().split()
        check("exclusive gate does not overlap its neighbour",
              order, ["other-start", "other-end", "solo-start", "solo-end"])

        # A failure next to a pass still reports its own reason and its own log.
        r = run(root, "--force", "mixed")
        check("the failing gate is named FAIL", "boom" in r["stderr"] and "FAIL" in r["stderr"], True)
        check("the failure reason survives concurrency", "o-motivo-real" in r["stderr"], True)
        check("a log path is printed", "log      " in r["stderr"], True)
        check("the passing neighbour still passes", "a              pass" in r["stdout"], True)
        check("exit code is non-zero", r["code"] != 0, True)
        check("the summary counts one failure", "1 failed" in r["stdout"], True)

        # A bad jobs value is refused rather than silently treated as 1.
        r = run(root, "--jobs", "banana", "three")
        check("a non-numeric jobs value is refused", r["code"] != 0, True)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
