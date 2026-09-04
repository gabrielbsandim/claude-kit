#!/usr/bin/env python3
"""Proves the Stop hook blocks an unverified edit and stays quiet otherwise.

    python3 tests/test-phase-gate.py

Every "must block" case is paired with a "must not block" one, because the cost of
the two mistakes is not symmetric: a miss loses one reminder, a false positive
makes every turn end in an argument and the hook is off by the end of the day.

The pairing is measured, not asserted: run against the 66 turns of the session this
hook was written in, the version that shipped fires on none of them, while the first
draft fired on the write-then-compile idiom that most of those turns are made of.
"""
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "hooks", "phase-gate.py")
PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("ok    %s" % name)
    else:
        FAIL += 1
        print("FAIL  %s\n        got exit %r, want %r" % (name, got, want))


def user(text="do the thing"):
    return {"type": "user", "message": {"role": "user", "content": text}}


def results():
    """The transcript's way of handing a tool result back, not a new instruction."""
    return {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}


def edit(path):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": path}}]}}


def write(path):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Write", "input": {"file_path": path}}]}}


def bash(command):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": command}}]}}


def run(entries, stop_hook_active=False, env=None):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
        path = fh.name
    try:
        payload = {"hook_event_name": "Stop", "transcript_path": path,
                   "stop_hook_active": stop_hook_active}
        out = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                             capture_output=True, text=True,
                             env=dict(os.environ, **(env or {})))
        return out.returncode
    finally:
        os.unlink(path)


BLOCK, QUIET = 2, 0

# --- must block ------------------------------------------------------------
check("edit with nothing after it",
      run([user(), edit("src/app.ts")]), BLOCK)
check("edit after a command, the command does not count backwards",
      run([user(), bash("npm test"), results(), edit("src/app.ts")]), BLOCK)
check("last of several edits is unverified",
      run([user(), edit("a.py"), bash("pytest"), results(), edit("b.py")]), BLOCK)
check("heredoc write with nothing after it",
      run([user(), bash("cat > scripts/gate <<'SH'\necho hi\nSH")]), BLOCK)
check("in place sed with nothing after it",
      run([user(), bash("sed -i 's/a/b/' scripts/run.sh")]), BLOCK)

# --- must not block --------------------------------------------------------
check("edit then a command",
      run([user(), edit("src/app.ts"), results(), bash("npm test")]), QUIET)
check("edit then a grep, a count is a verification too",
      run([user(), edit("src/app.ts"), results(), bash("grep -c foo src/app.ts")]), QUIET)
check("write and compile in one call",
      run([user(), bash("cat > hooks/x.py <<'EOF'\nimport os\nEOF\npython3 -m py_compile hooks/x.py")]),
      QUIET)
check("prose only",
      run([user(), write("docs/notes.md")]), QUIET)
check("a scratchpad script is not the deliverable",
      run([user(), write("/tmp/scratch/probe.py")]), QUIET)
check("no edit at all",
      run([user(), bash("git status")]), QUIET)
check("the edit belongs to the previous turn",
      run([user(), edit("src/app.ts"), user("now explain it")]), QUIET)
check("a subagent's edit reaches its own SubagentStop",
      run([user(), dict(edit("src/app.ts"), isSidechain=True)]), QUIET)
check("stop_hook_active, the documented way out of a loop",
      run([user(), edit("src/app.ts")], stop_hook_active=True), QUIET)
check("KIT_PHASE_GATE=off",
      run([user(), edit("src/app.ts")], env={"KIT_PHASE_GATE": "off"}), QUIET)

# --- must never break the session -----------------------------------------
def raw(stdin):
    return subprocess.run([sys.executable, HOOK], input=stdin,
                          capture_output=True, text=True).returncode


check("missing transcript",
      raw(json.dumps({"transcript_path": "/nonexistent/x.jsonl"})), QUIET)
check("stdin is not JSON", raw("not json"), QUIET)
check("empty stdin", raw(""), QUIET)

print("\n%d ok, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
