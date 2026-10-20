#!/usr/bin/env python3
"""PreToolUse on Bash: refuses a gate's tool run without the environment the gate gives it.

A repository that needs `NODE_OPTIONS=--max-old-space-size=6144` for its type check
writes it into the gate's `cmd`, and `kit gate` runs it that way. An agent checking
its own work runs the bare tool instead, `npx tsc --noEmit`, which dies for memory
after a minute and reads as a defect in the change. Measured in the repository the
funnel was built on, 2026-10-08 to 2026-10-19: no `kit gate` run ran out of memory
after the gate got its heap, and 18 bare `tsc` runs did.

So for every gate whose `cmd` starts with variable assignments, a command that runs
the same tool without them is refused, naming the gate to run instead. A gate with no
assignments constrains nothing, and nothing else is read.
"""
import json
import os
import re
import sys

ASSIGN = re.compile(r"^\s*((?:[A-Z_][A-Z0-9_]*=\S+\s+)+)(.*)$")
RUNNERS = {"npx", "pnpm", "yarn", "bunx", "exec", "--no-install", "--yes", "-y", "dlx"}


def checkouts(cwd: str) -> list:
    path = os.path.abspath(cwd)
    while True:
        dotgit = os.path.join(path, ".git")
        if os.path.isdir(dotgit):
            return [path]
        if os.path.isfile(dotgit):
            try:
                gitdir = open(dotgit).read().split("gitdir:", 1)[1].strip()
            except (OSError, IndexError):
                return [path]
            return [path, os.path.dirname(os.path.normpath(os.path.join(gitdir, "..", "..")))]
        parent = os.path.dirname(path)
        if parent == path:
            return []
        path = parent


def gates(cwd: str) -> dict:
    for root in checkouts(cwd):
        try:
            with open(os.path.join(root, ".claude", "funnel.config.json")) as fh:
                return json.load(fh).get("gates") or {}
        except (OSError, ValueError, AttributeError):
            continue
    return {}


def constrained(gate_cmd: str):
    """(the assignments, the tool they are for), or None."""
    match = ASSIGN.match(gate_cmd or "")
    if not match:
        return None
    words = [w for w in match.group(2).split() if w not in RUNNERS]
    if not words:
        return None
    return match.group(1).split(), os.path.basename(words[0])


def check(payload: dict) -> int:
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd or re.search(r"\bkit\s+gate\b", cmd):
        return 0
    for name, gate in gates(payload.get("cwd") or os.getcwd()).items():
        found = constrained((gate or {}).get("cmd"))
        if not found:
            continue
        assigns, tool = found
        runs_tool = re.search(r"(?:^|[\s;&|(/])" + re.escape(tool) + r"(?:\s|$)", cmd)
        if not runs_tool or all(a in cmd for a in assigns):
            continue
        sys.stderr.write(
            f"Blocked: this repository's `{name}` gate runs {tool} with {' '.join(assigns)},\n"
            f"and without it {tool} fails here for reasons that are not the change. Run the\n"
            f"gate instead, which also leaves a receipt: kit gate --gates {name}\n"
        )
        return 2
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    return check(payload)


if __name__ == "__main__":
    sys.exit(main())
