#!/usr/bin/env python3
"""Proves `kit escapes` counts a later fix on the same source file, and nothing looser.

    python3 tests/test-escapes.py

The raw count lies in two measured ways, and each has a case: a file most pull
requests touch shares itself with everything, and tests and documents move with
every fix by design.
"""
import json
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "escapes")
PASS, FAIL = 0, []


def check(name, ok, detail=""):
    global PASS
    if ok:
        PASS += 1
    else:
        FAIL.append(f"{name}: {detail}")


def pr(n, day, title, files, body="", branch="feat/x"):
    return {"number": n, "title": title, "mergedAt": f"2026-10-{day:02d}T12:00:00Z", "headRefName": branch,
            "body": body, "url": f"https://example.test/pull/{n}", "files": [{"path": f} for f in files]}


hot = [pr(100 + i, 1, "feat: copy", ["src/help.ts"]) for i in range(3)]
prs = hot + [
    pr(1, 2, "feat: fee rule", ["src/fee.ts", "src/fee.test.ts"], "<!-- funnel: risk -->"),
    pr(2, 5, "fix: fee rounds wrong", ["src/fee.ts"], branch="fix/2"),
    pr(3, 2, "feat: menu", ["src/menu.tsx", "src/help.ts"], "<!-- funnel: direct -->"),
    pr(4, 6, "fix: help typo", ["src/help.ts"]),
    pr(5, 2, "feat: report", ["src/report.ts", "docs/report.md"]),
    pr(6, 7, "fix: report docs", ["docs/report.md"]),
    pr(7, 2, "feat: export", ["src/export.ts"]),
    pr(8, 25, "fix: export", ["src/export.ts"]),
    pr(9, 3, "feat: banner", ["src/banner.ts"]),
    pr(10, 4, 'Revert "feat: banner" (#9)', ["src/banner.ts"]),
]
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
    json.dump(prs, fh)
    source = fh.name
try:
    out = subprocess.run([SCRIPT, "--from", source, "--hot", "3", "--json"], capture_output=True, text=True)
    data = json.loads(out.stdout or "{}")
    found = {e["from"]: e for e in data.get("escapes", [])}
    check("a later fix on the same source file is an escape", 1 in found and found[1]["fixedBy"] == 2, out.stdout)
    check("and it carries the lane from the body marker", found.get(1, {}).get("lane") == "risk", found)
    check("a hot file is not shared", 3 not in found, found.get(3))
    check("and the hot file is named", "src/help.ts" in data.get("hotFiles", []), data.get("hotFiles"))
    check("a fix that only moves documents is not an escape", 5 not in found, found.get(5))
    check("a fix outside the window is not an escape", 7 not in found, found.get(7))
    check("a revert is an escape", found.get(9, {}).get("shared") == ["reverted"], found.get(9))
    check("the lane table counts every pull request",
          data["lanes"]["risk"] == {"prs": 1, "escaped": 1} and data["lanes"]["direct"]["escaped"] == 0, data["lanes"])
    text = subprocess.run([SCRIPT, "--from", source, "--hot", "3"], capture_output=True, text=True).stdout
    check("the table prints a rate per lane", "risk" in text and "100%" in text, text)
    with tempfile.TemporaryDirectory() as out_dir:
        made = subprocess.run([SCRIPT, "--from", source, "--hot", "3", "--case", "1", "--out", out_dir],
                              capture_output=True, text=True)
        case = os.path.join(out_dir, "escape-1")
        check("an escape becomes an eval case skeleton",
              all(os.path.exists(os.path.join(case, p)) for p in
                  ("case.yaml", "prompt.md", "graders/escape-not-repeated.md", "scaffold.sh")), made.stdout + made.stderr)
        grader = open(os.path.join(case, "graders/escape-not-repeated.md")).read() if os.path.isdir(case) else ""
        check("and the grader names the fix and the file", "fix: fee rounds wrong" in grader and "src/fee.ts" in grader, grader)
    none = subprocess.run([SCRIPT, "--from", source, "--case", "7"], capture_output=True, text=True)
    check("a pull request with no escape has no case", none.returncode != 0, none.stdout)
finally:
    os.unlink(source)

print(f"{PASS} passed, {len(FAIL)} failed")
for line in FAIL:
    print(f"  FAIL {line}")
sys.exit(1 if FAIL else 0)
