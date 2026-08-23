#!/usr/bin/env python3
"""PreToolUse on Bash: blocks any command that prints a secret-bearing file.

A permission deny rule on Read(**/.env*) covers the file tool. It does not cover
the shell, which is the path that actually leaks: `cat .env`, `grep KEY .env.local`,
`source .env.prod`. In the setup this was written for, a database password reached
fifteen session transcripts exactly that way, and no deny rule was violated.

Two families of file are covered:

  `.env` and its variants, but never `.env.example` / `.sample` / `.template`.
  Agent config files that hold credentials inline: `.claude.json` and `.mcp.json`
  carry an `env` block per MCP server, and that is where a token ends up when
  somebody registers a server with `--env TOKEN=...`. Found by reading one:
  a HubSpot private-app token sat in plain text in `~/.claude.json`, outside
  every deny rule, because the rules were written for `.env` and nothing else.

The lookbehind on ENVFILE is the whole trick. Without it, `process.env.TIMEOUT` in
a source file matches the pattern and every script that reads an environment
variable gets blocked, which is how a guard gets disabled within a day.

Exit 2 blocks and returns stderr to the model as a correction.
"""
import json
import re
import sys

# Utilities that print file contents.
READERS = (
    r"(cat|bat|less|more|head|tail|nl|od|xxd|strings|grep|rg|egrep|fgrep|awk|sed|cut"
    r"|sort|uniq|tee|cp|mv|base64|jq|yq|printenv|env\b)"
)
# .env, .env.local, .env.prod, but never .env.example / .sample / .template / .dist.
DOTENV = r"(?<![\w.])\.env(?![\w-]*\.?(example|sample|template|dist))(\.[A-Za-z0-9_-]+)?\b"
# Agent config that carries an inline `env` block per MCP server.
AGENTCFG = r"(?<![\w.])\.(claude|mcp)\.json\b"
ENVFILE = r"(?:" + DOTENV + r"|" + AGENTCFG + r")"
# Legitimate shapes that load a .env without printing it.
ALLOW = [
    r"vercel\s+env\s+pull",
    r"--env-file[= ]",
    r"dotenv\s+-e",
    r"DOTENV_CONFIG_PATH=",
    r"grep\s+-c\b",  # counting occurrences reveals no value
    r"grep\s+-l\b",  # listing the file reveals no value
    r"wc\s+-l",
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return 0
    if any(re.search(p, cmd) for p in ALLOW):
        return 0
    if not re.search(ENVFILE, cmd):
        return 0
    if re.search(READERS + r"[^|;&]*" + ENVFILE, cmd) or re.search(
        r"(^|[;&|]\s*)(source|\.)\s+\S*" + ENVFILE, cmd
    ):
        sys.stderr.write(
            "Blocked: the contents of a secret-bearing file do not enter context, and that\n"
            "covers .env* as well as .claude.json and .mcp.json, which hold an env block per\n"
            "MCP server. A value read into a transcript stays in that transcript, and rotating\n"
            "it later does not remove it. Read .env.example for the shape, ask the user for the\n"
            "value, or run a script that reads the variable without printing it. To list keys\n"
            "without values, grep -c, grep -l or wc -l are allowed.\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
