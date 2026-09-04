#!/usr/bin/env python3
"""PreToolUse on Bash: refuses a `gh pr create` whose body is over budget.

`kit pr-body` has existed since 0.6.0 and both skills tell you to run it before
`gh pr create`. Measured on the repository this was built against, on the 17
pull requests opened in the six days after the plugin was installed: **17 of 17
were over the budget**, median 5798 characters of prose against 2000, worst
10545. The instruction was read, agreed with, and not run.

That is the same failure the output style exists for, and it has the same fix.
Teach with the skill, enforce with the hook. The measurement is not duplicated
here: this imports `bin/pr-body` and calls its `measure`, because a second copy
of a rule is a second copy that drifts, which is exactly the defect this plugin
shipped in `no-em-dash` until 0.9.2.

Fails open on everything it cannot read with certainty: an unparseable command,
a body file that does not exist yet, a `--fill` or an interactive create with no
body at all. A guard with a false positive gets disabled within a day, and the
cost of the two mistakes is not symmetric here: a long body is a long read, and
a blocked `gh pr create` is a funnel that cannot finish.

Exit 2 blocks and returns stderr to the model as a correction.
"""

import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import sys

CREATE = re.compile(r"\bgh\s+pr\s+(create|edit)\b")
DEFAULT_MAX = int(os.environ.get("KIT_PR_BODY_MAX", 2000))
DEFAULT_SECTION_MAX = int(os.environ.get("KIT_PR_BODY_SECTION_MAX", 600))


def load_pr_body():
    """The measurement, imported from bin/pr-body rather than reimplemented."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "pr-body")
    spec = importlib.util.spec_from_loader("kit_pr_body", importlib.machinery.SourceFileLoader("kit_pr_body", path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def body_from(cmd):
    """(text, where) for the body this command would post, or (None, None).

    Returns None wherever the answer is not certain, which includes a body file
    that is not on disk: the funnel writes it before calling, so a missing path
    means this is not the shape being guarded.
    """
    try:
        tokens = shlex.split(cmd, comments=False)
    except ValueError:
        return None, None

    index = 0
    while index < len(tokens):
        token = tokens[index]
        nxt = tokens[index + 1] if index + 1 < len(tokens) else None

        for flag in ("--body-file", "-F"):
            if token == flag and nxt:
                if os.path.isfile(nxt):
                    try:
                        with open(nxt, encoding="utf-8") as handle:
                            return handle.read(), nxt
                    except OSError:
                        return None, None
                return None, None
        if token.startswith("--body-file="):
            path = token.split("=", 1)[1]
            if os.path.isfile(path):
                try:
                    with open(path, encoding="utf-8") as handle:
                        return handle.read(), path
                except OSError:
                    return None, None
            return None, None

        for flag in ("--body", "-b"):
            if token == flag and nxt is not None:
                return nxt, "--body"
        if token.startswith("--body="):
            return token.split("=", 1)[1], "--body"

        index += 1
    return None, None


def check(payload: dict) -> int:
    """The guard itself, over an already-parsed payload. See hooks/guards.py."""
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd or not CREATE.search(cmd):
        return 0

    text, where = body_from(cmd)
    if text is None:
        return 0

    try:
        pr_body = load_pr_body()
        template = pr_body.find_template(None)
        m = pr_body.measure(text, template)
    except Exception:
        return 0

    over = []
    if m["written"] > DEFAULT_MAX:
        over.append(
            f"{m['written']} characters of prose, {m['words']} words, "
            f"over the {DEFAULT_MAX} budget by {m['written'] - DEFAULT_MAX}"
        )
    if m["worst"] and m["worst"][1] > DEFAULT_SECTION_MAX:
        over.append(
            f'section "{m["worst"][0]}" is {m["worst"][1]} characters, '
            f"over the {DEFAULT_SECTION_MAX} cap by {m['worst'][1] - DEFAULT_SECTION_MAX}"
        )
    if not over:
        return 0

    lines = [f"Blocked: the pull request body is over budget ({where})."]
    lines += [f"  {line}" for line in over]
    lines.append("  by section, largest first:")
    for section, size in sorted(m["sections"], key=lambda x: -x[1])[:6]:
        mark = "  <-- over the cap" if size > DEFAULT_SECTION_MAX else ""
        lines.append(f"    {size:>6}  {section}{mark}")
    lines.append(
        "  Cut, do not compress: the audit trail belongs in a pull request comment,\n"
        "  which is one click from the diff and does not have to be read first.\n"
        "  Rewrite the file and run the command again, or `kit pr-body <file>` to check."
    )
    sys.stderr.write("\n".join(lines) + "\n")
    return 2


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    return check(payload)


if __name__ == "__main__":
    sys.exit(main())
