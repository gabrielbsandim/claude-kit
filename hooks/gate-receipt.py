#!/usr/bin/env python3
"""Stop: refuses to end a turn that changed code in a funnel repository and ran no gate.

`phase-gate` asks whether anything ran after the last edit, and accepts a `grep`.
That is the right bar for a session that has no gates. A repository with a funnel
config has them, so the bar there is the repository's own: `kit gate`, after the
last edit to a source file in that checkout. Verification inside the loop is the
one practice whose payoff is measured everywhere it was looked for, and the funnel
used to delegate it to an implementer agent whose report the session then trusted.
With the main session writing the code, this is what keeps the gate in the loop.

A red gate is not refused. The turn ran the gate and can report what failed.

Ignored: any checkout without `.claude/funnel.config.json`, a branch that is the
config's base, prose and data files, subagent transcripts, and a turn with no edit.
Set KIT_GATE_RECEIPT=off to disable it for a session.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = re.compile(r"\bkit\s+gate\b|/scripts/gate\b")


def phase_gate():
    loader = importlib.machinery.SourceFileLoader("phase_gate", os.path.join(HERE, "phase-gate.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def checkout_of(path):
    """(the checkout holding path, the checkout that owns its config) or None."""
    here = os.path.dirname(os.path.abspath(path))
    while True:
        dotgit = os.path.join(here, ".git")
        if os.path.isdir(dotgit):
            return here, here
        if os.path.isfile(dotgit):
            try:
                gitdir = open(dotgit).read().split("gitdir:", 1)[1].strip()
            except (OSError, IndexError):
                return here, here
            return here, os.path.dirname(os.path.normpath(os.path.join(gitdir, "..", "..")))
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def branch(checkout):
    head = os.path.join(checkout, ".git")
    try:
        if os.path.isfile(head):
            head = open(head).read().split("gitdir:", 1)[1].strip()
        ref = open(os.path.join(head, "HEAD")).read().strip()
    except (OSError, IndexError):
        return ""
    return ref.rsplit("refs/heads/", 1)[-1] if ref.startswith("ref:") else ""


def funnel_base(owner):
    try:
        with open(os.path.join(owner, ".claude", "funnel.config.json")) as fh:
            return json.load(fh).get("base") or ""
    except FileNotFoundError:
        return None
    except (OSError, ValueError, AttributeError):
        return ""


def pending(entries, is_code):
    """The checkout and file of each code edit with no gate run after it."""
    last = {}
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        for block in (entry.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name, args = block.get("name"), block.get("input") or {}
            if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
                path = args.get("file_path") or args.get("notebook_path")
                found = checkout_of(path) if is_code(path) else None
                if found:
                    last[found] = path
            elif name == "Bash" and GATE.search(args.get("command") or ""):
                last.clear()
    return last


def main():
    if os.environ.get("KIT_GATE_RECEIPT", "").lower() in ("off", "0", "false"):
        return 0
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if payload.get("stop_hook_active"):
        return 0
    path = payload.get("transcript_path")
    if not path or not os.path.exists(path):
        return 0
    gate = phase_gate()
    for (checkout, owner), changed in pending(gate.turn_entries(path), gate.is_code).items():
        base = funnel_base(owner)
        if base is None or branch(checkout) in ("", base):
            continue
        sys.stderr.write(
            "%s changed in %s, a funnel checkout, and no `kit gate` ran after it.\n"
            "Run the stage's gate there and report its summary line:\n"
            "  kit gate implement_first_pass     (or implement_fix_round after a review)\n"
            "A red gate is a fine thing to stop on; an unrun one is not.\n" % (changed, checkout)
        )
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
