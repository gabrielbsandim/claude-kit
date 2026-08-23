#!/bin/sh
# Stable entry point for any hook in this plugin that you register yourself. Copy
# this one file to a path that does not move, and register that path with the hook
# you want as its argument:
#
#   cp hooks/kit-hook.sh ~/.claude/hooks/
#   # then in settings.json:
#   "PostToolUse": [{ "matcher": "Write|Edit|NotebookEdit", "hooks": [
#     { "type": "command", "timeout": 15,
#       "command": "sh ~/.claude/hooks/kit-hook.sh no-em-dash.py" }]}]
#
# Copying the Python file instead is the thing this exists to prevent. That copy
# stops being the plugin's copy the moment the plugin updates, and nothing says so.
# Measured 2026-08-23 on the machine this was written on: `~/.claude/hooks/` held an
# env-guard and a no-em-dash from three releases back, so the covered file list and
# the exemption list in force were both the old ones, while the tests that proved
# them green were running against the new ones.
#
# `plugin-freshness.sh` predates this and stays as its own file, because it is named
# in installation instructions that are already followed on other machines. This is
# the shim for everything after it.
#
# Exits 0 with no output when the plugin is not installed. A hook that fails when the
# thing it wraps is missing is a hook that breaks every tool call on a fresh machine.
[ -n "$1" ] || exit 0
case "$1" in
  */*|..*) exit 0 ;;  # a hook name, not a path: nothing here composes a path
esac
h=$(ls -d "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/plugins/cache/*/claude-kit/*/hooks/"$1" 2>/dev/null |
  sort -V | tail -1)
[ -n "$h" ] || exit 0
exec python3 "$h"
