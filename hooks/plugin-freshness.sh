#!/bin/sh
# Stable entry point for the freshness hook. Copy this one file to a path that does
# not move, and register that path:
#
#   cp hooks/plugin-freshness.sh ~/.claude/hooks/
#   # then in settings.json:
#   "SessionStart": [{ "matcher": "startup|resume", "hooks": [
#     { "type": "command", "timeout": 90,
#       "command": "sh ~/.claude/hooks/plugin-freshness.sh" }]}]
#
# The Python half lives in the plugin, under a directory named after the version, so
# registering it directly would pin the hook to one release and make this hook the
# next thing that silently goes stale. That is the problem it exists to fix, so it
# resolves the newest installed copy at run time instead.
#
# Exits 0 with no output when there is nothing installed, because a session start is
# never the place to fail.
h=$(ls -d "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/plugins/cache/*/claude-kit/*/hooks/plugin-freshness.py 2>/dev/null |
  sort -V | tail -1)
[ -n "$h" ] || exit 0
exec python3 "$h"
