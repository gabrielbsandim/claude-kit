#!/usr/bin/env python3
"""Proves the funnel Stop hook asks for `kit gate` where a funnel lives, and nowhere else.

    python3 tests/test-gate-receipt.py

Paired like test-phase-gate.py: each case that must block has one beside it that
must not, because a Stop hook with false positives is off by the end of the day.
"""
import json
import os
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "hooks", "gate-receipt.py")
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


def edit(path):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": path}}]}}


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
        return subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                              capture_output=True, text=True,
                              env=dict(os.environ, **(env or {}))).returncode
    finally:
        os.unlink(path)


def git(cwd, *args):
    subprocess.run(["git", "-C", cwd, "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


# Not under /tmp: the hook ignores it, on purpose, as the home of throwaway scripts.
SCRATCH = os.path.join(os.path.expanduser("~"), ".cache")
os.makedirs(SCRATCH, exist_ok=True)
with tempfile.TemporaryDirectory(dir=SCRATCH) as tmp:
    main = os.path.join(tmp, "app")
    os.makedirs(os.path.join(main, ".claude"))
    git(tmp, "init", "-q", "-b", "trunk", main)
    with open(os.path.join(main, ".claude", "funnel.config.json"), "w") as fh:
        json.dump({"base": "trunk"}, fh)
    git(main, "commit", "-q", "--allow-empty", "-m", "base")
    task = os.path.join(tmp, "app-12")
    git(main, "worktree", "add", "-q", "-b", "feat/12-x", task)
    plain = os.path.join(tmp, "plain")
    git(tmp, "init", "-q", "-b", "main", plain)
    git(plain, "commit", "-q", "--allow-empty", "-m", "base")
    git(plain, "switch", "-q", "-c", "feat/x")

    src = os.path.join(task, "src", "fee.ts")
    check("code edited in a funnel worktree, no gate", run([user(), edit(src)]), 2)
    check("the gate ran after the edit", run([user(), edit(src), bash("env -C %s kit gate implement_first_pass" % task)]), 0)
    check("a gate before the edit does not count", run([user(), bash("kit gate implement_first_pass"), edit(src)]), 2)
    check("a grep is not the repository's gate", run([user(), edit(src), bash("grep -c fee %s" % src)]), 2)
    check("a prose edit asks for nothing", run([user(), edit(os.path.join(task, "docs", "a.md"))]), 0)
    check("the base branch is not a task", run([user(), edit(os.path.join(main, "src", "fee.ts"))]), 0)
    check("a repository without a funnel config", run([user(), edit(os.path.join(plain, "src", "a.ts"))]), 0)
    check("an edit in an earlier turn is that turn's business",
          run([user(), edit(src), user("next question")]), 0)
    check("a blocked stop does not loop", run([user(), edit(src)], stop_hook_active=True), 0)
    check("the switch turns it off", run([user(), edit(src)], env={"KIT_GATE_RECEIPT": "off"}), 0)

print("%d ok, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
