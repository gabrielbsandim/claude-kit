#!/usr/bin/env python3
"""Proves gate concurrency: that it happens, that exclusive still means alone, and
that a failure survives being run next to a passing gate.

    python3 tests/test-gate-jobs.py

Concurrency is the one feature here that can look correct while being wrong. Three
gates that pass are three gates that pass whether they ran together or not, so
every case asserts on the interleaving of start and end markers each gate appends
to a file.

**Not on wall clock**, which is the version of this file that existed first and
failed one run in three. On the machine this was written on, `sleep 2` returns
after 1.06 seconds of wall clock with exit status 0, roughly one run in six: the
host steps its realtime clock while the sleep measures its own deadline against
it. So a wall-clock assertion tests the host's timekeeping, and the marker order
tests what the feature actually claims.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

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
    out = subprocess.run([GATE] + list(args), cwd=root, capture_output=True, text=True)
    return {"stdout": out.stdout, "stderr": out.stderr, "code": out.returncode}


SLEEP = 2


def marked(name, exclusive=False):
    """A gate that appends its own start and end, so overlap is a fact in a file."""
    gate = {"cmd": "echo %s-start >> order.log; sleep %d; echo %s-end >> order.log"
                   % (name, SLEEP, name)}
    if exclusive:
        gate["exclusive"] = True
    return gate


CFG = {
    "base": "main",
    "gates": {
        "a": marked("a"),
        "b": marked("b"),
        "c": marked("c"),
        "solo": marked("solo", exclusive=True),
        "noisy": marked("noisy"),
        "boom": {"cmd": "echo the-real-reason >&2; exit 1"},
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


def order(root):
    path = os.path.join(root, "order.log")
    if not os.path.exists(path):
        return []
    return open(path).read().split()


def reset_order(root):
    open(os.path.join(root, "order.log"), "w").close()


def overlaps(marks):
    """Names whose run overlapped another's, read off the marker sequence."""
    open_now, overlapping = set(), set()
    for m in marks:
        name, edge = m.rsplit("-", 1)
        if edge == "start":
            if open_now:
                overlapping.update(open_now | {name})
            open_now.add(name)
        else:
            open_now.discard(name)
    return sorted(overlapping)


def main():
    root = tempfile.mkdtemp(prefix="kit-gatejobs-")
    try:
        build(root, dict(CFG, gateJobs=3))

        reset_order(root)
        r = run(root, "three")
        check("three gates at jobs=3 all overlap", overlaps(order(root)), ["a", "b", "c"])
        check("all three still pass", r["stdout"].count("pass"), 3)
        check("the parallel line names them", "3 gates at once" in r["stdout"], True)

        # Same gates, serial, and the receipts from the run above have to be ignored
        # or this proves nothing.
        reset_order(root)
        r = run(root, "--force", "--jobs", "1", "three")
        check("the same gates at jobs=1 never overlap", overlaps(order(root)), [])
        check("and they all still ran", len(order(root)), 6)

        # Output integrity: a pass line must never be spliced by another gate's.
        reset_order(root)
        r = run(root, "--force", "three")
        bad = [ln for ln in r["stdout"].splitlines()
               if ln.strip() and not re.match(r"^(\w[\w-]*\s+(pass|run|skip|FAIL)|parallel|\d+ ran|$)", ln)]
        check("no line is spliced by a concurrent gate", bad, [])

        # An exclusive gate is a barrier: its neighbour must be finished before it
        # starts.
        reset_order(root)
        r = run(root, "--force", "barrier")
        check("exclusive gate does not overlap its neighbour",
              order(root), ["noisy-start", "noisy-end", "solo-start", "solo-end"])

        # A failure next to a pass still reports its own reason and its own log.
        r = run(root, "--force", "mixed")
        check("the failing gate is named FAIL", "boom" in r["stderr"] and "FAIL" in r["stderr"], True)
        check("the failure reason survives concurrency", "the-real-reason" in r["stderr"], True)
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
