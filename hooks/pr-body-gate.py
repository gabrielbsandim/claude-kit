#!/usr/bin/env python3
"""PreToolUse: refuses a pull request body, or a comment, that is over budget.

`kit pr-body` has existed since 0.6.0 and both skills tell you to run it before
`gh pr create`. Measured on the repository this was built against, on the 17
pull requests opened in the six days after the plugin was installed: **17 of 17
were over the budget**, median 5798 characters of prose against 2000, worst
10545. The instruction was read, agreed with, and not run.

That is the same failure the output style exists for, and it has the same fix.
Teach with the skill, enforce with the hook. The measurement is not duplicated
here: this imports `scripts/pr-body` and calls its `measure`, because a second copy
of a rule is a second copy that drifts, which is exactly the defect this plugin
shipped in `no-em-dash` until 0.9.2.

Fails open on everything it cannot read with certainty: an unparseable command,
a body file that does not exist yet, a `--fill` or an interactive create with no
body at all. A guard with a false positive gets disabled within a day, and the
cost of the two mistakes is not symmetric here: a long body is a long read, and
a blocked `gh pr create` is a funnel that cannot finish.

Since 0.15.0 it also covers the other ways the same prose gets out. A body set with
`gh api .../pulls/N -X PATCH` is a body. A `gh pr comment`, a comment POSTed through
`gh api`, and a Jira comment written through an Atlassian MCP tool are comments, on
the tighter budget a comment gets. And in a repo whose config sets `ledger` to false,
a top-level pull request comment is refused outright unless the command carries
`KIT_REPLY=1`, which says it answers a person: in such a repo the body is the only
text, and a comment is where the overflow went the moment the body was measured.
Budgets come from the repo config's `prBody`, and the environment still wins.

Exit 2 blocks and returns stderr to the model as a correction.
"""

import importlib.machinery
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys

CREATE = re.compile(r"\bgh\s+pr\s+(create|edit)\b")
COMMENT = re.compile(r"\bgh\s+pr\s+comment\b")
API = re.compile(r"\bgh\s+api\b")
PR_ENDPOINT = re.compile(r"(^|/)pulls/[\w{}]+/?$")
COMMENT_ENDPOINT = re.compile(
    r"(^|/)(issues/[\w{}]+/comments|pulls/[\w{}]+/(comments|reviews)|pulls/comments/\d+/replies)/?$")
TOP_LEVEL = re.compile(r"(^|/)issues/[\w{}]+/comments/?$")
JIRA_COMMENT = "addCommentToJiraIssue"
REPLY_MARK = "KIT_REPLY=1"
SEPARATORS = {"|", "||", "&&", ";", "&"}
# gh api flags that take a value, so the value is not read as the endpoint.
VALUED = {"-H", "--header", "-q", "--jq", "-t", "--template", "-p", "--preview",
          "--hostname", "--cache"}
DEFAULTS = {"max": 2000, "sectionMax": 600, "commentMax": 1000}


def load_pr_body():
    """The measurement, imported from scripts/pr-body rather than reimplemented."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "pr-body")
    spec = importlib.util.spec_from_loader("kit_pr_body", importlib.machinery.SourceFileLoader("kit_pr_body", path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    if not path or path == "-" or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def body_from(cmd):
    """(text, where) for the body a `gh pr` command would post, or (None, None).

    Returns None wherever the answer is not certain, which includes a body file
    that is not on disk: the funnel writes it before calling, so a missing path
    means this is not the shape being guarded.
    """
    try:
        tokens = shlex.split(cmd, comments=False)
    except ValueError:
        return None, None
    for index, token in enumerate(tokens):
        nxt = tokens[index + 1] if index + 1 < len(tokens) else None
        if token in ("--body-file", "-F") and nxt:
            text = read(nxt)
            return (text, nxt) if text is not None else (None, None)
        if token.startswith("--body-file="):
            path = token.split("=", 1)[1]
            text = read(path)
            return (text, path) if text is not None else (None, None)
        if token in ("--body", "-b") and nxt is not None:
            return nxt, "--body"
        if token.startswith("--body="):
            return token.split("=", 1)[1], "--body"
    return None, None


def api_request(cmd):
    """(endpoint, method, body) for a `gh api` call, body None when it cannot be read."""
    try:
        tokens = shlex.split(cmd, comments=False)
    except ValueError:
        return None, None, None
    start = next((i for i, t in enumerate(tokens[:-1]) if t == "gh" and tokens[i + 1] == "api"), None)
    if start is None:
        return None, None, None
    endpoint, method, fields, source = None, None, {}, None
    index = start + 2
    while index < len(tokens) and tokens[index] not in SEPARATORS:
        token = tokens[index]
        nxt = tokens[index + 1] if index + 1 < len(tokens) else ""
        index += 1
        if token in ("-X", "--method"):
            method, index = nxt.upper(), index + 1
            continue
        if token.startswith("--method="):
            method = token.split("=", 1)[1].upper()
            continue
        if token in ("-f", "--raw-field", "-F", "--field") and "=" in nxt:
            key, value = nxt.split("=", 1)
            fields[key] = read(value[1:]) if token in ("-F", "--field") and value.startswith("@") else value
            index += 1
            continue
        if token == "--input":
            source, index = nxt, index + 1
            continue
        if token in VALUED:
            index += 1
            continue
        if not token.startswith("-") and endpoint is None:
            endpoint = token
    body = fields.get("body")
    if body is None and source:
        body = json_body(source)
    return endpoint, method or ("POST" if fields or source else "GET"), body


def json_body(path):
    text = read(path)
    if text is None:
        return None
    try:
        value = json.loads(text).get("body")
    except (ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def classify(payload):
    """(kind, text, where, top_level) for what this call would publish, or None.

    kind is "body" or "comment". top_level marks a comment that stands on its own
    on the pull request, as opposed to a reply inside a review thread.
    """
    tool = payload.get("tool_name") or ""
    args = payload.get("tool_input") or {}
    if tool.endswith(JIRA_COMMENT):
        text = args.get("commentBody")
        return ("comment", text, "Jira comment", False) if isinstance(text, str) else None
    cmd = args.get("command") or ""
    if CREATE.search(cmd):
        text, where = body_from(cmd)
        return ("body", text, where, False) if text is not None else None
    if COMMENT.search(cmd):
        text, where = body_from(cmd)
        return ("comment", text, where or "gh pr comment", True)
    if not API.search(cmd):
        return None
    endpoint, method, text = api_request(cmd)
    if not endpoint:
        return None
    if method == "PATCH" and PR_ENDPOINT.search(endpoint):
        return ("body", text, endpoint, False) if text is not None else None
    if method == "POST" and COMMENT_ENDPOINT.search(endpoint):
        return ("comment", text, endpoint, bool(TOP_LEVEL.search(endpoint)))
    return None


def settings(cwd):
    """The repo config, merged, or {} when it cannot be read. Read only once a call
    has already matched, so the ordinary Bash call never pays for it."""
    tool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "funnel-config")
    try:
        out = subprocess.run([tool, "print"], cwd=cwd or None, capture_output=True, text=True, timeout=10)
        return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}


def budget(config, kind):
    """(total, per section): the environment, then the repo config, then the default."""
    repo = config.get("prBody") or {}

    def pick(env, key):
        return int(os.environ.get(env) or repo.get(key) or DEFAULTS[key])

    # One cap for a comment, since a comment rarely has headings and a section cap
    # over a single section is the total cap, only smaller.
    if kind == "comment":
        total = pick("KIT_COMMENT_MAX", "commentMax")
        return total, total
    return pick("KIT_PR_BODY_MAX", "max"), pick("KIT_PR_BODY_SECTION_MAX", "sectionMax")


def check(payload: dict) -> int:
    """The guard itself, over an already-parsed payload. See hooks/guards.py."""
    found = classify(payload)
    if found is None:
        return 0
    kind, text, where, top_level = found
    config = settings(payload.get("cwd"))
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if top_level and config.get("ledger") is False and REPLY_MARK not in cmd:
        sys.stderr.write(
            "Blocked: this repo sets ledger to false, so the pull request body is the only\n"
            "text the funnel writes on a pull request. Cut what does not fit the body; do not\n"
            "move it into a comment. If this comment answers a question a person asked,\n"
            f"prefix the command with {REPLY_MARK} and run it again.\n")
        return 2
    if text is None:
        return 0
    try:
        pr_body = load_pr_body()
        m = pr_body.measure(text, pr_body.find_template(None) if kind == "body" else None)
    except Exception:
        return 0
    total, section = budget(config, kind)
    over = []
    if m["written"] > total:
        over.append(
            f"{m['written']} characters of prose, {m['words']} words, "
            f"over the {total} budget by {m['written'] - total}"
        )
    if m["worst"] and m["worst"][1] > section:
        over.append(
            f'section "{m["worst"][0]}" is {m["worst"][1]} characters, '
            f"over the {section} cap by {m['worst'][1] - section}"
        )
    if not over:
        return 0
    noun = "pull request body" if kind == "body" else "comment"
    lines = [f"Blocked: the {noun} is over budget ({where})."]
    lines += [f"  {line}" for line in over]
    lines.append("  by section, largest first:")
    for name, size in sorted(m["sections"], key=lambda x: -x[1])[:6]:
        mark = "  <-- over the cap" if size > section else ""
        lines.append(f"    {size:>6}  {name}{mark}")
    lines.append(
        "  Cut, do not move: what does not fit is left out, not posted somewhere else.\n"
        "  Rewrite it and run the command again, or `kit pr-body <file>` to check."
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
