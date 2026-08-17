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
  2. Exempt the paths where an em dash is normal English typesetting. The
     default list is docs/ plus the root markdown files; override it with
     NO_EM_DASH_EXEMPT, a colon-separated list of regexes.

Exit 2 returns stderr to the model as a correction. The edit already landed, so
the right response is to rewrite the passage.
"""
import json
import os
import re
import sys

DASH = "\u2014"  # escaped on purpose: this file must not contain the literal
DEFAULT_EXEMPT = [
    r"/docs/",
    r"/AGENTS\.md$",
    r"/CONTRIBUTING\.md$",
    r"/README\.md$",
    r"/CHANGELOG\.md$",
]
EXEMPT = [p for p in (os.environ.get("NO_EM_DASH_EXEMPT") or "").split(":") if p] or DEFAULT_EXEMPT


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


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path or any(re.search(p, path) for p in EXEMPT):
        return 0
    text = new_text(tool_input)
    count = text.count(DASH)
    if not count:
        return 0
    sample = next((line.strip() for line in text.splitlines() if DASH in line), "")[:120]
    sys.stderr.write(
        f"Em dash in the text you just wrote to {path} ({count}x).\n"
        f"  line: {sample}\n"
        "Rewrite with a comma, a colon or parentheses. Exempt paths: "
        + ", ".join(EXEMPT)
        + "\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
