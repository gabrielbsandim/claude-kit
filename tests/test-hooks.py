#!/usr/bin/env python3
"""Behaviour tests for the shipped hooks.

A hook is a guard, and a guard with a false positive gets disabled within a day.
So every case below is either "must block" or, just as important, "must not
block": the second kind is what keeps the guard installed.

Run: python3 tests/test-hooks.py
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOCK, PASS = 2, 0
failures = []
checked = []


def run(hook: str, payload: dict, env: dict | None = None) -> int:
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "hooks", hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    return proc.returncode


def check(name: str, got: int, want: int) -> None:
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'}  {name}  (exit {got}, esperado {want})")
    checked.append(name)
    if not ok:
        failures.append(name)


def bash(cmd: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


def edit(path: str, old: str, new: str) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": path, "old_string": old, "new_string": new}}


def write(path: str, content: str) -> dict:
    return {"tool_name": "Write", "tool_input": {"file_path": path, "content": content}}


# ------------------------------------------------------------------ env-guard
print("== env-guard")
for cmd, want in [
    ("cat .env", BLOCK),
    ("grep SECRET .env.local", BLOCK),
    ("source .env.prod", BLOCK),
    ("cp .env /tmp/x", BLOCK),
    ("head -5 .env.wa", BLOCK),
    # Must not block: these are how a .env is used correctly, or not used at all.
    ("cat .env.example", PASS),
    ("cat .env.sample", PASS),
    ("node --env-file=.env script.js", PASS),
    ("grep -c KEY .env", PASS),
    ("vercel env pull .env.local", PASS),
    ("echo $DATABASE_URL", PASS),
    ('node -e "console.log(process.env.PORT)"', PASS),
    ("python3 -c 'import os; os.environ[\"X\"]'", PASS),
]:
    check(f"env-guard: {cmd}", run("env-guard.py", bash(cmd)), want)

# ------------------------------------------------------------- protect-tests
print("\n== protect-tests")
with tempfile.TemporaryDirectory() as tmp:
    test_file = os.path.join(tmp, "thing.test.ts")
    with open(test_file, "w") as fh:
        fh.write('it("adds", () => { expect(add(1,2)).toBe(3) })\n')
    cfg = os.path.join(tmp, "vitest.config.ts")
    with open(cfg, "w") as fh:
        fh.write("export default { test: { coverage: { thresholds: { lines: 90 } } } }\n")
    src = os.path.join(tmp, "thing.ts")

    cases = [
        ("focus marker added", edit(test_file, "it(", "it.only("), BLOCK),
        ("skip marker added", edit(test_file, "it(", "it.skip("), BLOCK),
        ("xit added", edit(test_file, "it(", "xit("), BLOCK),
        ("pytest skip added", edit(test_file, "it(", "@pytest.mark.skip\nit("), BLOCK),
        ("every assertion removed", write(test_file, 'it("adds", () => {})\n'), BLOCK),
        ("threshold lowered", write(cfg, "export default { test: { coverage: { thresholds: { lines: 70 } } } }\n"), BLOCK),
        ("no-verify in a file", write(src, "run('git push --no-verify')\n"), BLOCK),
        ("git push --no-verify", bash("git push --no-verify origin HEAD"), BLOCK),
        ("git commit -n", bash("git commit -n -m x"), BLOCK),
        ("git push --force", bash("git push --force origin feat/x"), BLOCK),
        ("git push -f", bash("git push -f"), BLOCK),
        # Must not block.
        ("threshold raised", write(cfg, "export default { test: { coverage: { thresholds: { lines: 95 } } } }\n"), PASS),
        ("assertion changed", edit(test_file, "toBe(3)", "toBe(4)"), PASS),
        ("new test added", write(os.path.join(tmp, "new.test.ts"), 'it("x", () => { expect(1).toBe(1) })\n'), PASS),
        ("only in source, not a test file", edit(src, "a", "arr.filter.only"), PASS),
        ("push with lease", bash("git push --force-with-lease origin feat/x"), PASS),
        ("ordinary push", bash("git push origin HEAD"), PASS),
        ("ordinary test run", bash("npm test"), PASS),
    ]
    for name, payload, want in cases:
        check(f"protect-tests: {name}", run("protect-tests.py", payload), want)

# ----------------------------------------------------------------- no-em-dash
print("\n== no-em-dash")
DASH = "\u2014"  # Escaped: this repo's own CI refuses the literal character
hook_src = os.path.join(ROOT, "hooks", "no-em-dash.py")
for name, payload, env, want in [
    ("em dash in a note", write("/tmp/x/nota.md", f"texto {DASH} aqui"), None, BLOCK),
    ("no em dash", write("/tmp/x/nota.md", "texto normal"), None, PASS),
    ("exempt path by default", write("/tmp/x/docs/a.md", f"a {DASH} b"), None, PASS),
    ("exemption overridden to nothing", write("/tmp/x/docs/a.md", f"a {DASH} b"), {"NO_EM_DASH_EXEMPT": "/never-matches/"}, BLOCK),
    # A hook that flags its own source is a hook nobody can maintain.
    ("its own source", write(hook_src, open(hook_src, encoding="utf8").read()), None, PASS),
]:
    check(f"no-em-dash: {name}", run("no-em-dash.py", payload, env), want)

print()
if failures:
    print(f"{len(failures)} falha(s): {', '.join(failures)}")
    sys.exit(1)
print(f"all passed ({len(checked)} cases)")
