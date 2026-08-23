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

# Utilities that print file contents. The word boundaries are not decoration:
# without them `od` matches inside "modo", `nl` inside "only" and `cut` inside
# "shortcut", so any sentence near a covered filename blocks. That stayed
# invisible while only `.env` was covered, because prose rarely sits beside it,
# and surfaced the hour `.claude.json` joined the list.
READERS = (
    r"(?<![\w.-])(cat|bat|less|more|head|tail|nl|od|xxd|strings|grep|rg|egrep|fgrep|awk|sed|cut"
    r"|sort|uniq|tee|cp|mv|base64|jq|yq|printenv|env)(?![\w-])"
)
# .env, .env.local, .env.prod, but never .env.example / .sample / .template / .dist.
DOTENV = r"(?<![\w.])\.env(?![\w-]*\.?(example|sample|template|dist))(\.[A-Za-z0-9_-]+)?\b"
# Agent config that carries an inline `env` block per MCP server.
AGENTCFG = r"(?<![\w.])\.(claude|mcp)\.json\b"
ENVFILE = r"(?:" + DOTENV + r"|" + AGENTCFG + r")"
GREP = r"(grep|egrep|fgrep|rg)"
# Legitimate shapes that load a .env without printing it.
ALLOW = [
    r"vercel\s+env\s+pull",
    r"--env-file[= ]",
    r"dotenv\s+-e",
    r"DOTENV_CONFIG_PATH=",
    # -c, -l and -L all suppress the matched line, so they reveal no value. The flag is
    # matched anywhere in a short cluster because `grep -rl` is how the list actually gets
    # asked for, and `grep\s+-l\b` did not match it: the allowance existed and the command
    # blocked anyway. Uppercase -C is context and is deliberately not in the class.
    #
    # Only other flags may sit between the tool and the flag. An earlier version wrote the
    # gap as `[^|;&]*?`, which let `grep $(cat .env) -l x` satisfy the allowance and read
    # the file through the substitution the allowance was never about.
    r"\b" + GREP + r"\b(\s+-[A-Za-z-]+)*\s+-[A-Za-z]*[clL][A-Za-z]*\b",
    r"\b" + GREP + r"\b(\s+-[A-Za-z-]+)*\s+--(count|files-with-matches|files-without-match)\b",
    r"\bwc\s+(-[A-Za-z]+\s+)*-[A-Za-z]*l\b",
]
# A substitution runs its own command with its own output, so an allowance granted to the
# outer command says nothing about it.
SUBSTITUTION = r"\$\(|`|<\("


def segments(cmd: str) -> list:
    """The shell's own boundaries.

    ALLOW used to be tested against the whole command, so `grep -l x && cat .env`
    presented one allowed clause and carried a second that read the file. The blocking
    side already refused to cross `|;&`; only the allowing side did.
    """
    return re.split(r"[|;&\n]+", cmd)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    if not cmd:
        return 0
    if not re.search(ENVFILE, cmd):
        return 0
    risky = [
        s
        for s in segments(cmd)
        if re.search(ENVFILE, s)
        and not (not re.search(SUBSTITUTION, s) and any(re.search(p, s) for p in ALLOW))
    ]
    if not risky:
        return 0
    if any(
        re.search(READERS + r"[^|;&]*" + ENVFILE, s)
        or re.search(r"^\s*(source|\.)\s+\S*" + ENVFILE, s)
        for s in risky
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
