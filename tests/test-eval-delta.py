#!/usr/bin/env python3
"""Proves `kit eval-delta` reads both arms and pools runs of one case across files.

    python3 tests/test-eval-delta.py
"""
import json
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "eval-delta")
PASS, FAIL = 0, []


def check(name, ok, detail=""):
    global PASS
    if ok:
        PASS += 1
    else:
        FAIL.append(f"{name}: {detail}")


def run_file(cases):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump({"cases": [{"name": n, "arms": {
        "with": [{"score": s, "costUsd": 0.2, "error": None} for s in w],
        "without": [{"score": s, "costUsd": 0.1, "error": None} for s in wo]}} for n, w, wo in cases]}, fh)
    fh.close()
    return fh.name


a = run_file([("spec", [1, 0.5], [0, 0]), ("same", [1], [1])])
b = run_file([("spec", [1], [0.5])])
c = run_file([("spec", [1], [])])
try:
    out = subprocess.run([SCRIPT, a, b], capture_output=True, text=True)
    row = next((l for l in out.stdout.splitlines() if l.startswith("spec")), "")
    check("runs of one case pool across files", "0.83" in row and "+0.67" in row and "3/3" in row, out.stdout)
    check("a case the model passes alone shows zero", any(l.startswith("same") and "+0.00" in l
                                                          for l in out.stdout.splitlines()), out.stdout)
    check("the summary counts the cases that separate", "1 of 2 case(s)" in out.stdout, out.stdout)
    low = subprocess.run([SCRIPT, a, b, "--min", "0.5"], capture_output=True, text=True)
    check("a mean delta under --min exits 3", low.returncode == 3, low.stdout)
    none = subprocess.run([SCRIPT, c], capture_output=True, text=True)
    check("a run with no without arm is refused by name", none.returncode != 0 and "ablation" in none.stderr,
          none.stderr)
finally:
    for path in (a, b, c):
        os.unlink(path)

print(f"{PASS} passed, {len(FAIL)} failed")
for line in FAIL:
    print(f"  FAIL {line}")
sys.exit(1 if FAIL else 0)
