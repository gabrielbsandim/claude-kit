#!/usr/bin/env python3
"""PostToolUse on Write and Edit: flags em dashes in the text just written.

Not registered by default, because it enforces a house style rather than a
correctness property. Register it in your own settings if you want it:

  "PostToolUse": [{ "matcher": "Write|Edit|NotebookEdit", "hooks": [
    { "type": "command", "command": "python3 <plugin>/hooks/no-em-dash.py" } ]}]

Two design rules, both learned by getting them wrong first:

  1. Check only the new text (`new_string` on Edit, `content` on Write), never
     the whole file. Billing whoever edited one line for the file's legacy
     content produces a guaranteed false positive and trains everyone to ignore
     the hook.
  2. No exemption by default, decided 2026-08-17. The earlier version exempted
     English technical documents (`docs/**`, AGENTS.md, CONTRIBUTING.md,
     README.md), and that contradicted the rule this hook exists to enforce,
     which is "never, in anything". Measured on the repository it was written
     against: the exemption was letting 820 files keep the character while the
     rule said none should. To loosen it without editing code, export
     NO_EM_DASH_EXEMPT, a colon-separated list of regexes.

Exit 2 returns stderr to the model as a correction. The edit already landed, so
the right response is to rewrite the passage.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_paths  # noqa: E402  (needs the path above; the hook runs as a script)

DASH = "\u2014"  # escaped on purpose: this file must not contain the literal
# Empty by default: the rule is absolute. NO_EM_DASH_EXEMPT loosens it per machine.
EXEMPT = [p for p in (os.environ.get("NO_EM_DASH_EXEMPT") or "").split(":") if p]


def new_text(tool_input: dict) -> str:
    if "content" in tool_input:  # Write
        return tool_input.get("content") or ""
    if "new_string" in tool_input:  # Edit
        return tool_input.get("new_string") or ""
    if "edits" in tool_input:  # batched Edit
        return "\n".join(
            (e or {}).get("new_string") or "" for e in tool_input.get("edits") or []
        )
    return ""


def check(payload: dict) -> int:
    """The check itself, over an already-parsed payload. See hooks/guards.py."""
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path or any(re.search(p, path) for p in EXEMPT):
        return 0
    # A test that asserts on the character has to contain it. See kit_paths.py.
    if kit_paths.is_own_test(path):
        return 0
    text = new_text(tool_input)
    count = text.count(DASH)
    if not count:
        return 0
    sample = next((line.strip() for line in text.splitlines() if DASH in line), "")[:120]
    sys.stderr.write(
        f"Em dash in the text you just wrote to {path} ({count}x).\n"
        f"  line: {sample}\n"
        "Rewrite with a comma, a colon or parentheses. The rule is absolute; "
        + ("exempt here: " + ", ".join(EXEMPT) if EXEMPT else "to loosen it, export NO_EM_DASH_EXEMPT")
        + "\n"
    )
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    return check(payload)


if __name__ == "__main__":
    sys.exit(main())
