#!/usr/bin/env python3
"""PreToolUse: refuses the four ways a green suite gets faked.

A funnel that gates on a green test run is worth exactly as much as the run is
hard to fake. These are the shortcuts, in the order an agent under time pressure
reaches for them:

  1. delete or empty a test file
  2. mark it skipped, or focus one test so the rest never run
  3. lower a coverage threshold until the number passes
  4. push with the hook disabled

None of the four is ever the right fix, and all four leave a green report
attached, which is worse than a red one. Exit 2 blocks and returns stderr to the
model as a correction.

Registered for Write, Edit and Bash. Bash is where 4 lives; the other three are
edits.
"""
import json
import re
import sys

TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec)/|\.(test|spec)\.[jt]sx?$|_test\.(py|go)$|test_[^/]+\.py$")

# Focus and skip markers across the common runners.
SKIP = re.compile(
    r"\b(?:describe|it|test|context|suite|bench)\s*\.\s*(?:skip|only|todo|failing)\b"
    r"|\b(?:xit|xdescribe|fit|fdescribe)\s*\("
    r"|@(?:pytest\.mark\.)?skip\b"
    r"|\bt\.Skip\s*\("
    r"|\.skip\s*\(\s*['\"]"
)

# A threshold going down. Matches the assignment, not the word, so a doc that
# mentions "lines: 90" in prose is not the target.
THRESHOLD = re.compile(
    r"\b(lines|branches|functions|statements|coverage|threshold|minCoverage)\s*[:=]\s*(\d{1,3})\b",
    re.IGNORECASE,
)
THRESHOLD_FILE = re.compile(r"(vitest|jest|nyc|karma|pytest|codecov|coverage)[.\-]?", re.IGNORECASE)

NO_VERIFY = re.compile(r"\bgit\s+(?:push|commit)\b[^;&|]*\s(?:--no-verify|-n)\b")
# `--force-with-lease` starts with `--force`, so the lookahead has to sit right
# after the word rather than at the end of the command.
FORCE_PUSH = re.compile(r"\bgit\s+push\b[^;&|]*\s(?:--force(?!-with-lease)|-f)\b")


def block(message: str) -> int:
    sys.stderr.write(message + "\n")
    return 2


def check_edit(path: str, new_text: str, old_text: str) -> int:
    if NO_VERIFY.search(new_text):
        return block(
            "Blocked: --no-verify in a file. The pre-push hook is a gate, not an obstacle."
        )

    if TEST_PATH.search(path):
        if SKIP.search(new_text) and not SKIP.search(old_text):
            return block(
                "Blocked: this edit adds a skip or a focus marker to a test file.\n"
                "A focused test silently stops running every other test in the file, and a\n"
                "skipped test is a deleted test that still reports green. If the test is wrong,\n"
                "fix the assertion. If the code is wrong, fix the code. If the test is a known\n"
                "flake, put it in the funnel config's `flaky` list, where the runner reads it."
            )
        # An edit that removes every assertion is a deletion wearing a diff.
        assertions = re.compile(r"\b(expect|assert|assertEqual|should|require\.|t\.Error)\b")
        if old_text and assertions.search(old_text) and not assertions.search(new_text):
            return block(
                "Blocked: this edit removes every assertion from a test file.\n"
                "A test with no assertion passes unconditionally. Change what it asserts, or\n"
                "delete the file deliberately and say so in the report."
            )

    if THRESHOLD_FILE.search(path):
        old_values = {k.lower(): int(v) for k, v in THRESHOLD.findall(old_text)}
        for key, value in THRESHOLD.findall(new_text):
            previous = old_values.get(key.lower())
            if previous is not None and int(value) < previous:
                return block(
                    f"Blocked: {key} threshold lowered from {previous} to {value} in {path}.\n"
                    "Lowering the bar is a project decision with an owner, and it is not this\n"
                    "task. Write the missing test, or report the gap and stop."
                )
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool = payload.get("tool_name") or ""
    args = payload.get("tool_input") or {}

    if tool == "Bash":
        cmd = args.get("command") or ""
        if NO_VERIFY.search(cmd):
            return block(
                "Blocked: --no-verify. The pre-push hook runs the checks that keep the branch\n"
                "reviewable, and the fix for a red hook is the failing check. If the hook itself\n"
                "is broken, say so and stop."
            )
        if FORCE_PUSH.search(cmd):
            return block(
                "Blocked: force push without --force-with-lease. If the remote moved, this\n"
                "discards whatever moved it. Use --force-with-lease, which fails instead."
            )
        return 0

    if tool in ("Write", "Edit", "NotebookEdit"):
        path = args.get("file_path") or args.get("notebook_path") or ""
        new_text = args.get("content") or args.get("new_string") or args.get("new_source") or ""
        old_text = args.get("old_string") or ""
        # Write carries no before-text, so a full-file overwrite would slip past
        # every comparison below. Read what is on disk instead.
        if not old_text and path:
            try:
                with open(path, encoding="utf8", errors="replace") as handle:
                    old_text = handle.read()
            except OSError:
                old_text = ""
        return check_edit(path, new_text, old_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
