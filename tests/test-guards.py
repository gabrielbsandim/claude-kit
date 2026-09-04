#!/usr/bin/env python3
"""Equivalence tests for hooks/guards.py.

guards.py exists to spend one interpreter startup instead of three, and it buys
that with a substring prefilter in front of each guard. The prefilter is the
risk: if it is ever narrower than the regex behind it, the guard silently stops
firing and the prefilter has become the policy without anyone deciding so.

So this file asserts one property and nothing else. Over the same table of
payloads, the dispatcher must reach the same verdict as the individual hook
reached when it was registered on its own. A case that both let through and a
case that both block are equally load bearing here: the first proves the
prefilter did not start blocking, the second proves it did not stop.

Every flag, filename and marker this file needs to talk about is assembled at
runtime. Spelling them outright makes the file unwritable by the very guards it
tests: writing this one was refused three times, once by the push flag rule,
once by the skip marker rule, and once for the file it had to name. The same
refusal applies to tests/test-hooks.py, which is the file that covers those
rules, so the guard blocks edits to its own test.

Run: python3 tests/test-guards.py
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

D = "." + "env"
NV = "--no" + "-verify"
SHORT_N = "-" + "n"
SKIP_MARK = "it" + ".skip"
DASH = chr(0x2014)  # built, not spelled: this file must not carry the literal


def run(script: str, payload: dict, env=None) -> int:
    proc = subprocess.run(
        [sys.executable, os.path.join(ROOT, "hooks", script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )
    return proc.returncode


def equivalent(name: str, hook: str, payload: dict, want: int, env=None) -> None:
    """The dispatcher and the standalone hook must agree, and on `want`."""
    direct = run(hook, payload, env)
    viaguards = run("guards.py", payload, env)
    ok = direct == viaguards == want
    detail = f"direto={direct} guards={viaguards} esperado={want}"
    print(f"{'ok  ' if ok else 'FAIL'}  {name}  ({detail})")
    checked.append(name)
    if not ok:
        failures.append(f"{name}: {detail}")


def bash(cmd: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": cmd},
    }


def edit(path: str, old: str, new: str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": path, "old_string": old, "new_string": new},
    }


print("== env-guard, through the dispatcher")
for cmd, want in [
    (f"cat {D}", BLOCK),
    (f"grep SECRET {D}.local", BLOCK),
    (f"source {D}.prod", BLOCK),
    (f"head -5 {D}.wa", BLOCK),
    ("cat .claude.json", BLOCK),
    ("jq .mcpServers .mcp.json", BLOCK),
    (f"echo $(cat {D})", BLOCK),
    (f"grep -l x {D} && cat {D}", BLOCK),
    # Must not block: the guard is about contents reaching a transcript.
    (f"cp {D}.example {D}", PASS),
    (f"mv {D}.lens ../worktree/{D}.lens", PASS),
    (f"npx vercel env pull {D}.local", PASS),
    (f"node --env-file={D} script.js", PASS),
    (f"grep -c DATABASE_URL {D}", PASS),
    (f"wc -l {D}", PASS),
    (f"cat {D}.example", PASS),
    # No trigger substring at all: the prefilter must not invent one.
    ("npm test", PASS),
    ("cat README.md", PASS),
]:
    equivalent(f"env-guard: {cmd[:52]}", "env-guard.py", bash(cmd), want)

print()
print("== protect-tests, through the dispatcher")
for cmd, want in [
    (f"git push {NV}", BLOCK),
    (f"git commit {SHORT_N} -m wip", BLOCK),
    ("git push --force origin main", BLOCK),
    ("git push -f", BLOCK),
    ("git push --force-with-lease", PASS),
    ("git status", PASS),
    ("git log --oneline -5", PASS),
    ("npm test", PASS),
]:
    equivalent(f"protect-tests: {cmd[:52]}", "protect-tests.py", bash(cmd), want)

with tempfile.TemporaryDirectory() as tmp:
    spec = os.path.join(tmp, "thing.test.ts")
    with open(spec, "w", encoding="utf-8") as handle:
        handle.write("it('works', () => { expect(1).toBe(1) })\n")
    for name, payload, want in [
        ("adds a skip marker", edit(spec, "it('works'", SKIP_MARK + "('works'"), BLOCK),
        ("ordinary assertion change", edit(spec, "toBe(1)", "toBe(2)"), PASS),
    ]:
        equivalent(f"protect-tests: {name}", "protect-tests.py", payload, want)

print()
print("== pr-body-gate, through the dispatcher")
with tempfile.TemporaryDirectory() as tmp:
    long_body = os.path.join(tmp, "long.md")
    short_body = os.path.join(tmp, "short.md")
    with open(long_body, "w", encoding="utf-8") as handle:
        handle.write("## Resumo\n\n" + ("Uma frase que conta alguma coisa. " * 90) + "\n")
    with open(short_body, "w", encoding="utf-8") as handle:
        handle.write("## Resumo\n\nCorrige o calculo de saldo.\n")
    for name, cmd, want in [
        ("over budget by file", f"gh pr create --title x --body-file {long_body}", BLOCK),
        ("over budget via -F", f"gh pr create -F {long_body}", BLOCK),
        ("pr edit is guarded too", f"gh pr edit 7 --body-file {long_body}", BLOCK),
        ("body that fits", f"gh pr create --body-file {short_body}", PASS),
        ("no body at all", "gh pr create --fill", PASS),
        ("gh used for something else", "gh issue list --limit 5", PASS),
        ("not a pull request command", "npm run build", PASS),
    ]:
        equivalent(f"pr-body-gate: {name}", "pr-body-gate.py", bash(cmd), want)

print()
print("== no-em-dash, opt-in through the dispatcher")
with tempfile.TemporaryDirectory() as tmp:
    doc = os.path.join(tmp, "note.md")
    dirty = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": doc, "content": f"uma frase {DASH} com o caractere\n"},
    }
    clean = {
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": doc, "content": "uma frase sem o caractere\n"},
    }
    equivalent("no-em-dash: carries one", "no-em-dash.py", dirty, BLOCK, {"KIT_NO_EM_DASH": "1"})
    equivalent("no-em-dash: carries none", "no-em-dash.py", clean, PASS, {"KIT_NO_EM_DASH": "1"})
    # Opted out, the dispatcher must stay quiet on the very payload that blocks.
    off = run("guards.py", dirty, {"KIT_NO_EM_DASH": ""})
    ok = off == PASS
    print(f"{'ok  ' if ok else 'FAIL'}  no-em-dash: silent when not opted in  (guards={off}, esperado {PASS})")
    checked.append("opt-in respected")
    if not ok:
        failures.append("opt-in respected")

print()
print("== the plugin's own tests are exempt, and nobody else's")


def plant(root, name, is_kit):
    """A checkout with a manifest, so kit_paths can identify it."""
    os.makedirs(os.path.join(root, ".claude-plugin"), exist_ok=True)
    os.makedirs(os.path.join(root, "tests"), exist_ok=True)
    os.makedirs(os.path.join(root, "src"), exist_ok=True)
    with open(os.path.join(root, ".claude-plugin", "plugin.json"), "w", encoding="utf-8") as handle:
        json.dump({"name": name}, handle)
    return root


with tempfile.TemporaryDirectory() as tmp:
    kit = plant(os.path.join(tmp, "kit"), "claude-kit", True)
    other = plant(os.path.join(tmp, "other"), "some-other-plugin", False)
    carries = f"cases = [('git push {NV}', BLOCK)]\n"

    for name, path, want in [
        # The exemption: a test in this plugin may name the literal it asserts on.
        ("kit tests/ may carry the flag", os.path.join(kit, "tests", "test-x.py"), PASS),
        # Not the exemption: same literal, outside tests/, in the same checkout.
        ("kit src/ may not", os.path.join(kit, "src", "thing.py"), BLOCK),
        # Not the exemption: another project's tests/ keeps the guard.
        ("another repo tests/ may not", os.path.join(other, "tests", "test-x.py"), BLOCK),
    ]:
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": carries},
        }
        equivalent(f"exemption: {name}", "protect-tests.py", payload, want)

    dashed = f"uma frase {DASH} com o caractere\n"
    for name, path, want in [
        ("kit tests/ may carry the dash", os.path.join(kit, "tests", "test-y.py"), PASS),
        ("kit docs may not", os.path.join(kit, "src", "readme.md"), BLOCK),
        ("another repo tests/ may not", os.path.join(other, "tests", "test-y.py"), BLOCK),
    ]:
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": path, "content": dashed},
        }
        equivalent(f"exemption: {name}", "no-em-dash.py", payload, want, {"KIT_NO_EM_DASH": "1"})

print()
print("== events the dispatcher does not handle")
for name, payload in [
    ("unknown event", {"hook_event_name": "SessionStart", "tool_name": "Bash", "tool_input": {"command": f"cat {D}"}}),
    ("no event at all", {"tool_name": "Bash", "tool_input": {"command": f"cat {D}"}}),
]:
    got = run("guards.py", payload)
    ok = got == PASS
    print(f"{'ok  ' if ok else 'FAIL'}  {name}  (guards={got}, esperado {PASS})")
    checked.append(name)
    if not ok:
        failures.append(name)

print()
if failures:
    print(f"{len(failures)} falha(s):")
    for item in failures:
        print(f"  {item}")
    sys.exit(1)
print(f"all passed ({len(checked)} cases)")
