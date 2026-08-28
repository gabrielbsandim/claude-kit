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
    ("head -5 .env.wa", BLOCK),
    # Agent config holds an env block per MCP server, so it leaks the same way.
    ("cat ~/.claude.json", BLOCK),
    ("jq .mcpServers ~/.claude.json", BLOCK),
    ("grep TOKEN .mcp.json", BLOCK),
    ("cat /home/x/.claude.json", BLOCK),
    # Must not block: these are how a .env is used correctly, or not used at all.
    ("cat .env.example", PASS),
    ("cat .env.sample", PASS),
    ("node --env-file=.env script.js", PASS),
    ("grep -c KEY .env", PASS),
    ("vercel env pull .env.local", PASS),
    # Moving a file prints nothing, so it never was this guard's business. The case
    # that paid for it: an untracked .env.lens has to reach a fresh worktree before
    # the browser lens can start the app.
    ("cp .env /tmp/x", PASS),
    ("cp /home/x/repo/.env.lens /home/x/repo-858/", PASS),
    ("mv .env.local .env.bak", PASS),
    # But a copy in one clause does not license a read in the next.
    ("cp .env /tmp/x && cat .env", BLOCK),
    ("cp .env /tmp/x; grep KEY .env", BLOCK),
    ("echo $DATABASE_URL", PASS),
    ('node -e "console.log(process.env.PORT)"', PASS),
    ("python3 -c 'import os; os.environ[\"X\"]'", PASS),
    # Counting or listing reveals no value, and the settings file is not the config file.
    ("grep -c mcpServers ~/.claude.json", PASS),
    ("cat ~/.claude/settings.json", PASS),
    ("cat package.json", PASS),
    ("ls ~/.claude.json", PASS),
    # A reader name buried inside an ordinary word is not a reader. Without the
    # boundaries: "modo" carries od, "only" carries nl, "shortcut" carries cut.
    ("echo modo 600 ~/.claude.json", PASS),
    ("echo only ~/.claude.json is affected", PASS),
    ("echo shortcut to .env.example", PASS),
    ("stat ~/.claude.json", PASS),
    ("wc -c ~/.claude.json", PASS),
    # And the boundaries must not let a real reader through.
    ("head ~/.claude.json", BLOCK),
    ("od -c .env", BLOCK),
    # Combined short flags. `grep -rl` is how a list of files actually gets asked for,
    # and the allowance was written `grep\s+-l\b`, which does not match it: the shape
    # was documented as permitted and blocked anyway.
    ("grep -rl mcpServers ~/.claude.json", PASS),
    ("grep -lr TOKEN .env", PASS),
    ("rg -l TOKEN .env", PASS),
    ("grep --files-with-matches TOKEN .env", PASS),
    ("grep -L TOKEN .env", PASS),
    # -C is context and prints the matched line, so the cluster must not admit it.
    ("grep -C3 TOKEN .env", BLOCK),
    ("grep -rn TOKEN .env", BLOCK),
    ("grep -o TOKEN .env", BLOCK),
    # An allowance is per shell segment. Tested against the whole command, one allowed
    # clause used to carry a second clause that read the file.
    ("grep -l foo && cat .env", BLOCK),
    ("grep -c KEY .env; cat .env", BLOCK),
    ("wc -l x && head .env", BLOCK),
    ("echo hi; grep -c KEY .env", PASS),
    # A substitution runs its own command, so the outer allowance does not cover it.
    ("grep $(cat .env) -l x", BLOCK),
    ("grep -l `cat .env` x", BLOCK),
    ("diff <(cat .env) x", BLOCK),
    # The long flags belong to grep, not to whatever else is on the line.
    ("cat .env --count", BLOCK),
    ("cat .env --files-with-matches", BLOCK),
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
    # No exemption by default: an English technical document is still covered.
    ("docs path not exempt by default", write("/tmp/x/docs/a.md", f"a {DASH} b"), None, BLOCK),
    ("exemption is opt-in and matches", write("/tmp/x/docs/a.md", f"a {DASH} b"), {"NO_EM_DASH_EXEMPT": "/docs/"}, PASS),
    ("exemption is opt-in and misses", write("/tmp/x/docs/a.md", f"a {DASH} b"), {"NO_EM_DASH_EXEMPT": "/never-matches/"}, BLOCK),
    # A hook that flags its own source is a hook nobody can maintain.
    ("its own source", write(hook_src, open(hook_src, encoding="utf8").read()), None, PASS),
]:
    check(f"no-em-dash: {name}", run("no-em-dash.py", payload, env), want)

# --------------------------------------------------------------- pr-body-gate
# Paired hard: this hook stands between the funnel and its own last step, so a
# false positive is a task that cannot finish. Everything uncertain must pass.
print("\n== pr-body-gate")
with tempfile.TemporaryDirectory() as tmp:
    long_body = os.path.join(tmp, "long.md")
    with open(long_body, "w", encoding="utf8") as fh:
        fh.write("## What\n\n" + ("Uma frase inteira que conta algo sobre a mudanca. " * 60) + "\n")
    short_body = os.path.join(tmp, "short.md")
    with open(short_body, "w", encoding="utf8") as fh:
        fh.write("Fecha #1.\n\n## O que muda\n\nO botao passa a dizer Salvar.\n")
    fenced = os.path.join(tmp, "fenced.md")
    with open(fenced, "w", encoding="utf8") as fh:
        fh.write("## Evidence\n\n```\n" + ("x" * 4000) + "\n```\n\nUma linha de prosa.\n")

    for name, cmd, want in [
        ("over budget by file", f"gh pr create --title x --body-file {long_body}", BLOCK),
        ("over budget with =", f"gh pr create --body-file={long_body}", BLOCK),
        ("over budget via -F", f"gh pr create -F {long_body}", BLOCK),
        ("over budget inline", "gh pr create --body '" + ("Uma frase que conta algo. " * 90) + "'", BLOCK),
        ("pr edit is guarded too", f"gh pr edit 7 --body-file {long_body}", BLOCK),
        # Must not block. Each of these is a shape the gate cannot judge, or a
        # body that fits, and blocking any of them strands the funnel.
        ("body that fits", f"gh pr create --body-file {short_body}", PASS),
        ("a fenced block is evidence, not prose", f"gh pr create --body-file {fenced}", PASS),
        ("no body at all", "gh pr create --fill", PASS),
        ("body file not written yet", "gh pr create --body-file /nonexistent/body.md", PASS),
        ("not a pull request command", "npm test", PASS),
        ("gh used for something else", "gh issue list --limit 5", PASS),
        ("unparseable quoting fails open", 'gh pr create --body-file "unclosed', PASS),
        ("budget raised by env", f"gh pr create --body-file {long_body}", PASS),
    ]:
        env = {"KIT_PR_BODY_MAX": "99999", "KIT_PR_BODY_SECTION_MAX": "99999"} if name == "budget raised by env" else None
        check(f"pr-body-gate: {name}", run("pr-body-gate.py", bash(cmd), env), want)

print()
if failures:
    print(f"{len(failures)} falha(s): {', '.join(failures)}")
    sys.exit(1)
print(f"all passed ({len(checked)} cases)")
