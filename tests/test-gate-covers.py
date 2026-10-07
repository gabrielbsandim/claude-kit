#!/usr/bin/env python3
"""Proves `covers`: a gate that runs a superset of another leaves that one's receipt,
so the same suite never runs twice over one tree.

    python3 tests/test-gate-covers.py

Every case asserts on a log the gates append to, because a skip line in the output
is the claim and the log is the fact.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(KIT, "scripts", "gate")
CFGTOOL = os.path.join(KIT, "scripts", "funnel-config")
PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("ok    %s  (%s)" % (name, got))
    else:
        FAIL += 1
        print("FAIL  %s\n        got  %r\n        want %r" % (name, got, want))


def git(root, *args):
    subprocess.run(["git"] + list(args), cwd=root, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write_cfg(root, cfg):
    with open(os.path.join(root, ".claude/funnel.config.json"), "w") as fh:
        json.dump(cfg, fh)


def build(root, cfg):
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    with open(os.path.join(root, ".gitignore"), "w") as fh:
        fh.write("runs.log\n.claude/\n")
    git(root, "add", ".gitignore")
    git(root, "commit", "-q", "-m", "base")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    os.makedirs(os.path.join(root, ".claude"), exist_ok=True)
    write_cfg(root, cfg)


def run(tool, root, *args):
    out = subprocess.run([tool] + list(args), cwd=root, capture_output=True, text=True)
    return {"stdout": out.stdout, "stderr": out.stderr, "code": out.returncode}


def runs(root):
    path = os.path.join(root, "runs.log")
    if not os.path.exists(path):
        return []
    return open(path).read().split()


CFG = {
    "base": "main",
    "gates": {
        "test": {"cmd": "echo test >> runs.log"},
        "coverage": {"cmd": "echo coverage >> runs.log", "covers": ["test"]},
        "lint": {"cmd": "echo lint >> runs.log"},
    },
    "stages": {
        "tests": ["coverage"],
        "suite": ["test"],
        "ship": ["lint", "coverage"],
    },
    "slices": {"all": "{base}...HEAD"},
    "lenses": {},
    "effort": {},
}


def main():
    root = tempfile.mkdtemp(prefix="kit-gatecovers-")
    try:
        build(root, CFG)

        run(GATE, root, "tests")
        r = run(GATE, root, "suite")
        check("the plain suite after coverage on one tree does not run", runs(root), ["coverage"])
        check("and says it was skipped by receipt", "test           skip" in r["stdout"], True)

        r = run(GATE, root, "--verify", "suite")
        check("a pre-push --verify of the covered gate passes", r["code"], 0)

        run(GATE, root, "ship")
        check("ship reruns only what the tests stage did not prove",
              runs(root), ["coverage", "lint"])

        # The covered receipt is keyed to the tree like any other: an edit drops it.
        with open(os.path.join(root, "a.txt"), "w") as fh:
            fh.write("edit\n")
        run(GATE, root, "suite")
        check("a new tree runs the covered gate again", runs(root)[-1], "test")

        # The reverse is not implied: the plain suite never proves coverage.
        with open(os.path.join(root, "b.txt"), "w") as fh:
            fh.write("edit\n")
        run(GATE, root, "suite")
        r = run(GATE, root, "--verify", "tests")
        check("a plain suite pass does not stand in for coverage", r["code"] != 0, True)

        # A failing covering gate leaves no receipt for what it covers.
        failing = json.loads(json.dumps(CFG))
        failing["gates"]["coverage"]["cmd"] = "exit 1"
        write_cfg(root, failing)
        with open(os.path.join(root, "c.txt"), "w") as fh:
            fh.write("edit\n")
        run(GATE, root, "tests")
        r = run(GATE, root, "--verify", "suite")
        check("a failed coverage run proves nothing it covers", r["code"] != 0, True)

        bad = json.loads(json.dumps(CFG))
        bad["gates"]["coverage"]["covers"] = ["nope"]
        bad["gates"]["lint"]["covers"] = ["lint"]
        write_cfg(root, bad)
        r = run(CFGTOOL, root, "check")
        check("check refuses a covers name that is not a gate",
              'covers "nope", which is not a gate' in r["stderr"], True)
        check("check refuses a gate covering itself", "lint covers itself" in r["stderr"], True)
        check("and fails", r["code"] != 0, True)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
