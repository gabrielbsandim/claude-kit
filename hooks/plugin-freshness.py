#!/usr/bin/env python3
"""SessionStart hook: keep the plugin current, and say when this session is not.

Registered by hand, not by the plugin, because it updates software without being
asked and that has to be a choice:

    "hooks": {
      "SessionStart": [
        { "matcher": "startup|resume", "hooks": [
            { "type": "command", "timeout": 90,
              "command": "python3 ~/.claude/plugins/.../hooks/plugin-freshness.py" } ] }
      ]
    }

Three copies of a plugin disagree independently and every disagreement is silent.
`claude plugin update` says so itself: "restart required to apply". So this hook
cannot make the running session current, and does not pretend to. It does the two
things that are actually possible:

1. **Fixes the copy `kit` on PATH points at**, which takes effect immediately,
   because a shell script is read at exec time. `kit setup` links a version-pinned
   cache path, so that symlink goes stale on its own with every update.
2. **Says, in the session's context, that the skills in this session are the
   previous version**, which is provable rather than guessed: if the update moved
   the version, then what this session loaded is the version before it.

Measured on 2026-08-17: a two-hour funnel run executed the 0.1.0 skill while 0.2.0
had been installed for five minutes, and nothing anywhere said so. The whole point
of this file is that the sentence exists.

Silence is the normal outcome. It emits nothing when nothing changed, throttles to
one network call every `KIT_FRESHNESS_INTERVAL` seconds (6 hours by default), holds
a lock so two sessions starting together cannot both write the plugin cache, and
exits 0 on every failure path. A hook that can break a session start is a hook that
gets deleted.

Environment, all optional and all present so the tests need no network:
  KIT_FRESHNESS_UPDATE_CMD   the update command (default: claude plugin update ...)
  KIT_FRESHNESS_INTERVAL     seconds between checks (default 21600, 0 disables)
  KIT_FRESHNESS_BIN_DIR      where `kit` is linked (default ~/.local/bin)
  KIT_FRESHNESS_PLUGIN       plugin id (default claude-kit@claude-kit)
  CLAUDE_CONFIG_DIR          where plugins/cache lives (default ~/.claude)
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

PLUGIN = os.environ.get("KIT_FRESHNESS_PLUGIN", "claude-kit@claude-kit")
NAME = PLUGIN.split("@")[0]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def quiet(msg=None):
    """Every exit is a success. A session start is not the place to fail."""
    if msg:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": msg}}))
    sys.exit(0)


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def state_dir():
    d = os.path.join(config_dir(), NAME)
    os.makedirs(d, exist_ok=True)
    return d


def key(v):
    return tuple(int(p) for p in v.split("."))


def newest_installed():
    """The highest version under plugins/cache, and its root. Directory names are
    the version, so this needs no manifest read and no network."""
    base = os.path.join(config_dir(), "plugins", "cache")
    best, root = None, None
    if not os.path.isdir(base):
        return None, None
    for market in sorted(os.listdir(base)):
        pdir = os.path.join(base, market, NAME)
        if not os.path.isdir(pdir):
            continue
        for v in sorted(os.listdir(pdir)):
            if not SEMVER.match(v):
                continue
            if not os.path.isfile(os.path.join(pdir, v, ".claude-plugin", "plugin.json")):
                continue
            if best is None or key(v) > key(best):
                best, root = v, os.path.join(pdir, v)
    return best, root


def linked_version(bin_dir):
    """The version the `kit` on PATH resolves to, or None if it is not a link into
    the cache."""
    link = os.path.join(bin_dir, "kit")
    if not os.path.exists(link):
        return None
    target = os.path.realpath(link)
    for part in target.split(os.sep):
        if SEMVER.match(part):
            return part
    return None


def throttled(interval):
    stamp = os.path.join(state_dir(), "freshness-checked-at")
    now = time.time()
    if interval > 0 and os.path.exists(stamp):
        try:
            if now - os.path.getmtime(stamp) < interval:
                return True
        except OSError:
            pass
    try:
        with open(stamp, "w") as fh:
            fh.write(str(int(now)))
    except OSError:
        pass
    return False


def take_lock():
    """mkdir is atomic on every filesystem this runs on, which is the point. A lock
    older than five minutes belonged to a process that died."""
    lock = os.path.join(state_dir(), "freshness.lock")
    try:
        os.mkdir(lock)
        return lock
    except FileExistsError:
        try:
            if time.time() - os.path.getmtime(lock) > 300:
                shutil.rmtree(lock, ignore_errors=True)
                os.mkdir(lock)
                return lock
        except OSError:
            pass
        return None


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    # clear and compact do not restart the process, so nothing it loaded can have
    # changed and there is nothing to report.
    if payload.get("source") not in (None, "startup", "resume"):
        quiet()

    interval = int(os.environ.get("KIT_FRESHNESS_INTERVAL", "21600") or 0)
    bin_dir = os.environ.get("KIT_FRESHNESS_BIN_DIR") or os.path.join(
        os.path.expanduser("~"), ".local", "bin")

    before, _ = newest_installed()
    was_linked = linked_version(bin_dir)

    if not throttled(interval):
        lock = take_lock()
        if lock:
            try:
                cmd = os.environ.get("KIT_FRESHNESS_UPDATE_CMD") or \
                    "claude plugin update %s -y" % PLUGIN
                # Split rather than shell=True: the string is a command, not a shell
                # program, and there is nothing here a shell would add except an
                # injection surface through the environment.
                subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=90)
            except (subprocess.SubprocessError, OSError):
                pass
            finally:
                shutil.rmtree(lock, ignore_errors=True)

    after, root = newest_installed()
    if after is None:
        quiet()

    # Relink first, because this half does take effect in the running session and a
    # message about it is only true once it is done.
    relinked = False
    if was_linked != after and root:
        try:
            subprocess.run([os.path.join(root, "bin", "kit"), "setup", bin_dir],
                           capture_output=True, text=True, timeout=30)
            relinked = linked_version(bin_dir) == after
        except (subprocess.SubprocessError, OSError):
            pass

    lines = []
    if before and after and key(after) > key(before):
        lines.append(
            "claude-kit was updated on disk, %s to %s. This session loaded %s, so its "
            "skills, agents and commands are the older copy for as long as it lives: "
            "`claude plugin update` cannot reach a running session. Tell the user, in "
            "one line, that restarting with `claude -c` picks up %s and keeps this "
            "conversation." % (before, after, before, after))
    if relinked:
        lines.append(
            "The `kit` on PATH pointed at %s and now points at %s. That half is live "
            "already, because a script is read when it runs." % (was_linked or "nothing", after))
    quiet("\n".join(lines) if lines else None)


if __name__ == "__main__":
    main()
