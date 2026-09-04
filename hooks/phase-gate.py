#!/usr/bin/env python3
"""Stop hook: refuses to end a turn that edited code and then ran nothing.

The rule it mechanizes is already written down, in this repository and in the
user's own instructions: a phase reported done without the command that verifies
it is the phase that comes back. Written rules get followed until the turn is long,
which is exactly when they matter, so this is the hook half of the pair that the
skills are the teaching half of.

What it blocks: a Stop where the last edit to a source file has no Bash call after
it. Nothing else. It does not judge which command was run, because the useful
verification in practice ranges from a full test suite to a `grep -c` that proves
a count, and a hook that ranks those would be wrong often enough to be turned off.

What it deliberately ignores, each because a false positive here costs more than
the miss:

  * prose, config and data files. A markdown note has no command that proves it.
  * anything under /tmp or a scratchpad directory, which is where throwaway
    scripts live.
  * subagent transcripts, which reach their own SubagentStop.
  * a turn with no edit at all, which is most of them.

Set KIT_PHASE_GATE=off to disable it for a session.

Exit 2 blocks the stop and returns stderr to the model.
"""
import json
import os
import re
import sys

# Extensions where "did you run it" is a question with an answer.
CODE = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".sh", ".bash",
    ".go", ".rs", ".rb", ".sql", ".yml", ".yaml",
}
EDITORS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
# A Bash call that writes a file: a redirect, an in-place sed, a tee, a patch.
BASH_WRITE = re.compile(
    r"(?:^|[;&|]|\s)(?:cat|tee|printf|echo)\b[^|;&]*>\s*(\S+)"
    r"|(?:^|[;&|]|\s)sed\s+(?:-[^\s-]*\s+)*-i\b[^|;&]*?(\S+)\s*$"
    r"|(?:^|[;&|]|\s)patch\b[^|;&]*?(\S+)\s*$",
    re.M,
)
# A heredoc body is data, not commands. Stripping it first is what makes it safe to
# ask whether anything runs after the write, since a body is full of semicolons.
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?\n.*?\n\1\s*$", re.S | re.M)
# How much of the transcript tail to read. A turn longer than this fails open.
TAIL = 4 * 1024 * 1024


def is_code(path):
    if not path:
        return False
    path = str(path)
    if path.startswith("/tmp/") or "/scratchpad/" in path or "/.git/" in path:
        return False
    if os.path.splitext(path)[1].lower() in CODE:
        return True
    # An extensionless file under scripts/ is an executable, which this repository is
    # mostly made of. Anywhere else, no extension means no way to tell.
    parts = path.split("/")
    return "scripts" in parts[:-1] and "." not in parts[-1]


def bash_writes(command):
    """(source files this command writes, whether another command runs after them).

    The second half is what keeps the common idiom out of the false positive pile:
    a heredoc that writes a file and then compiles it is one Bash call, and the
    compile is the verification. Measured over the 66 turns of the session this was
    written in, that idiom was the only thing the first version flagged.
    """
    text = HEREDOC.sub("", command or "")
    hits, end = [], 0
    for match in BASH_WRITE.finditer(text):
        for group in match.groups():
            if group and is_code(group.strip("\"'")):
                hits.append(group.strip("\"'"))
                end = match.end()
    if not hits:
        return [], False
    rest = re.sub(r"^[\s;&|]+", "", text[end:])
    return hits, bool(rest)


def turn_entries(path):
    """Entries since the last real user message, oldest first.

    A user entry carrying only tool_result blocks is the transcript's way of
    handing a tool's output back, not a new instruction, so it does not open a turn.
    """
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        if size > TAIL:
            fh.seek(size - TAIL)
            fh.readline()
        raw = fh.read().decode("utf8", "replace").splitlines()

    entries = []
    for line in reversed(raw):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("isSidechain"):
            continue
        kind = entry.get("type")
        if kind not in ("user", "assistant"):
            continue
        entries.append(entry)
        if kind == "user":
            content = (entry.get("message") or {}).get("content")
            blocks = content if isinstance(content, list) else []
            only_results = blocks and all(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in blocks
            )
            if not only_results:
                break
    return list(reversed(entries))


def verdict(entries):
    """The file left unverified, or None."""
    pending = None
    for entry in entries:
        if entry.get("type") != "assistant":
            continue
        for block in (entry.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name, args = block.get("name"), block.get("input") or {}
            if name in EDITORS:
                path = args.get("file_path") or args.get("notebook_path")
                if is_code(path):
                    pending = path
            elif name == "Bash":
                written, verified_here = bash_writes(args.get("command"))
                # A writing call clears the slate unless it is itself the last thing
                # to touch a source file with nothing running after it.
                pending = None if (not written or verified_here) else written[-1]
    return pending


def main():
    if os.environ.get("KIT_PHASE_GATE", "").lower() in ("off", "0", "false"):
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
    pending = verdict(turn_entries(path))
    if not pending:
        return 0
    sys.stderr.write(
        "%s was the last source file this turn changed, and no command ran after it.\n"
        "Run the thing that proves the change: the repo's gate, the test file, or the\n"
        "grep whose count you are about to quote. Then report the number with it.\n"
        "If the change genuinely has no verifying command, say which one you skipped\n"
        "and why, and stop again.\n" % pending
    )
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # A guard that breaks the session it guards is worse than no guard.
        sys.exit(0)
