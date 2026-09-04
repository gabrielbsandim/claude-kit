#!/usr/bin/env python3
"""One interpreter for every guard in this plugin, dispatched by event.

Registering the guards separately is correct and was measurably expensive. Each
registration is its own process, and on the machine this was written on a bare
`python3 -c pass` costs 13 ms, so three PreToolUse guards spent 39 ms of startup
on every Bash call before any of them looked at the command. Measured over the
three guards as they were registered: 76 ms per call, of which 51 ms was startup.
Almost every call is a `npm test` or a `git status` that all three answer no to.

Two things make this cheap:

  1. One process. The payload is parsed once and the guards are functions.
  2. A substring prefilter before each import. `re.compile` at module scope is
     not free either, so a guard whose trigger is absent is never loaded.

The prefilters below are deliberately looser than the regexes they stand in
front of. Each one must match everything its guard could match, or the guard
stops firing and the prefilter has silently become the policy. That property is
what tests/test-guards.py checks, by running both paths over the same table.
"""
import importlib.machinery
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Trigger substrings, one per guard. A guard runs only when its trigger appears
# in the text the guard would read. Keep these as supersets: see the docstring.
ENV_MARKERS = (".env", ".claude.json", ".mcp.json")
# Escaped on purpose: this file must not contain the literal it looks for.
DASH = "\u2014"


def load(stem: str):
    """Import a hook module by file stem. The names carry hyphens, so the
    ordinary import statement cannot spell them."""
    path = os.path.join(HERE, stem + ".py")
    loader = importlib.machinery.SourceFileLoader(stem.replace("-", "_"), path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def pre_tool_use(payload: dict) -> int:
    tool = payload.get("tool_name") or ""
    args = payload.get("tool_input") or {}

    if tool == "Bash":
        cmd = args.get("command") or ""
        if not cmd:
            return 0
        if any(marker in cmd for marker in ENV_MARKERS):
            code = load("env-guard").check(payload)
            if code:
                return code
        if "git" in cmd:
            code = load("protect-tests").check(payload)
            if code:
                return code
        if "gh" in cmd and "pr" in cmd:
            code = load("pr-body-gate").check(payload)
            if code:
                return code
        return 0

    if tool in ("Write", "Edit", "NotebookEdit"):
        # No prefilter: this path compares against what is on disk, so the
        # decision needs the file, not a substring of the payload.
        return load("protect-tests").check(payload)

    return 0


def post_tool_use(payload: dict) -> int:
    # House style rather than a correctness property, so it stays opt-in: the
    # plugin does not impose an em dash rule on anyone who did not ask for it.
    # Set KIT_NO_EM_DASH=1 to turn it on.
    if not os.environ.get("KIT_NO_EM_DASH"):
        return 0
    tool = payload.get("tool_name") or ""
    if tool not in ("Write", "Edit", "NotebookEdit"):
        return 0
    args = payload.get("tool_input") or {}
    text = (
        args.get("content")
        or args.get("new_string")
        or "".join((e or {}).get("new_string") or "" for e in args.get("edits") or [])
        or ""
    )
    if DASH not in text:
        return 0
    return load("no-em-dash").check(payload)


EVENTS = {
    "PreToolUse": pre_tool_use,
    "PostToolUse": post_tool_use,
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    handler = EVENTS.get(payload.get("hook_event_name") or "")
    if handler is None:
        return 0
    try:
        return handler(payload)
    except Exception:
        # A guard that crashes must not block the call it was inspecting. The
        # blocking decisions are all explicit returns above.
        return 0


if __name__ == "__main__":
    sys.exit(main())
