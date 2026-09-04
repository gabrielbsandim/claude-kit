#!/usr/bin/env python3
"""Proves the SessionStart hook is safe to leave registered forever.

    python3 tests/test-plugin-freshness.py

A hook that runs before every session has one hard requirement: it must be
impossible for it to make a session worse. So the cases here are mostly about
silence and about not failing, and only then about the message.

The update command is injected, so nothing here touches the network or the real
plugin cache.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(KIT, "hooks", "plugin-freshness.py")
PASS, FAIL = 0, 0


def check(name, got, want, compare=lambda a, b: a == b):
    global PASS, FAIL
    if compare(got, want):
        PASS += 1
        print("ok    %s" % name)
    else:
        FAIL += 1
        print("FAIL  %s\n        got  %r\n        want %r" % (name, got, want))


def contains(got, want):
    return want in got


def install(cfg, version, market="claude-kit", name="claude-kit"):
    """A copy where `claude plugin install` puts one, with a runnable scripts/kit."""
    root = os.path.join(cfg, "plugins", "cache", market, name, version)
    os.makedirs(os.path.join(root, ".claude-plugin"), exist_ok=True)
    with open(os.path.join(root, ".claude-plugin", "plugin.json"), "w") as fh:
        json.dump({"name": name, "version": version}, fh)
    os.makedirs(os.path.join(root, "scripts"), exist_ok=True)
    kit = os.path.join(root, "scripts", "kit")
    # A stand-in for `kit setup`: link this copy's kit into the target directory,
    # which is all the hook uses it for.
    with open(kit, "w") as fh:
        fh.write('#!/bin/sh\n[ "$1" = setup ] || exit 0\nmkdir -p "$2"\n'
                 'ln -sf "$0" "$2/kit"\n')
    os.chmod(kit, 0o755)
    return root


def run(cfg, bin_dir, update_cmd=None, source="startup", interval="0", extra=None):
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = cfg
    env["KIT_FRESHNESS_BIN_DIR"] = bin_dir
    env["KIT_FRESHNESS_INTERVAL"] = interval
    env["KIT_FRESHNESS_UPDATE_CMD"] = update_cmd if update_cmd is not None else "true"
    if extra:
        env.update(extra)
    out = subprocess.run([sys.executable, HOOK], input=json.dumps(
        {"hook_event_name": "SessionStart", "source": source}),
        capture_output=True, text=True, env=env)
    return out.stdout, out.stderr, out.returncode


def context(stdout):
    if not stdout.strip():
        return ""
    return json.loads(stdout)["hookSpecificOutput"]["additionalContext"]


def main():
    root = tempfile.mkdtemp(prefix="kit-fresh-")
    try:
        # Nothing installed at all: a machine mid-install must not get an error at
        # session start.
        cfg = os.path.join(root, "empty")
        os.makedirs(cfg)
        out, err, rc = run(cfg, os.path.join(root, "bin1"))
        check("no installed copy exits zero", rc, 0)
        check("and says nothing", out.strip(), "")

        # Already current: the normal case, every session, so it must be silent.
        cfg = os.path.join(root, "current")
        install(cfg, "0.4.0")
        bin_dir = os.path.join(root, "bin2")
        os.makedirs(bin_dir)
        os.symlink(os.path.join(cfg, "plugins/cache/claude-kit/claude-kit/0.4.0/scripts/kit"),
                   os.path.join(bin_dir, "kit"))
        out, err, rc = run(cfg, bin_dir)
        check("nothing to do is silent", out.strip(), "")
        check("and exits zero", rc, 0)

        # The version moves: the session that just started holds the old one, and
        # that sentence is the whole reason this hook exists.
        cfg = os.path.join(root, "moves")
        install(cfg, "0.4.0")
        bin_dir = os.path.join(root, "bin3")
        os.makedirs(bin_dir)
        os.symlink(os.path.join(cfg, "plugins/cache/claude-kit/claude-kit/0.4.0/scripts/kit"),
                   os.path.join(bin_dir, "kit"))
        newer = os.path.join(root, "newer.sh")
        with open(newer, "w") as fh:
            fh.write("#!/bin/sh\nmkdir -p '%s/plugins/cache/claude-kit/claude-kit/0.5.0/.claude-plugin'\n"
                     "printf '{\"name\":\"claude-kit\",\"version\":\"0.5.0\"}' > "
                     "'%s/plugins/cache/claude-kit/claude-kit/0.5.0/.claude-plugin/plugin.json'\n"
                     "mkdir -p '%s/plugins/cache/claude-kit/claude-kit/0.5.0/scripts'\n"
                     "printf '#!/bin/sh\\n[ \"$1\" = setup ] || exit 0\\nmkdir -p \"$2\"\\n"
                     "ln -sf \"$0\" \"$2/kit\"\\n' > "
                     "'%s/plugins/cache/claude-kit/claude-kit/0.5.0/scripts/kit'\n"
                     "chmod +x '%s/plugins/cache/claude-kit/claude-kit/0.5.0/scripts/kit'\n"
                     % (cfg, cfg, cfg, cfg, cfg))
        os.chmod(newer, 0o755)
        out, err, rc = run(cfg, bin_dir, update_cmd="sh " + newer)
        ctx = context(out)
        check("an update produces context", bool(ctx), True)
        check("it names both versions", ctx, "0.4.0 to 0.5.0", contains)
        check("it says this session holds the old one", ctx, "older copy", contains)
        check("it names the command that fixes it", ctx, "claude -c", contains)
        check("and it relinks kit, which does take effect now", ctx, "now points at 0.5.0", contains)
        check("the symlink really moved",
              "0.5.0" in os.path.realpath(os.path.join(bin_dir, "kit")), True)
        check("still exits zero", rc, 0)

        # A stale symlink with no version change: the one thing the hook can fix
        # outright, and it must report only that.
        cfg = os.path.join(root, "stalelink")
        install(cfg, "0.4.0")
        install(cfg, "0.5.0")
        bin_dir = os.path.join(root, "bin4")
        os.makedirs(bin_dir)
        os.symlink(os.path.join(cfg, "plugins/cache/claude-kit/claude-kit/0.4.0/scripts/kit"),
                   os.path.join(bin_dir, "kit"))
        out, err, rc = run(cfg, bin_dir)
        ctx = context(out)
        check("a stale link is reported", ctx, "now points at 0.5.0", contains)
        check("and no restart is demanded, because nothing was updated",
              "claude -c" in ctx, False)

        # An update command that fails, or does not exist, must be indistinguishable
        # from a quiet success. This is the offline case.
        cfg = os.path.join(root, "offline")
        install(cfg, "0.4.0")
        bin_dir = os.path.join(root, "bin5")
        os.makedirs(bin_dir)
        os.symlink(os.path.join(cfg, "plugins/cache/claude-kit/claude-kit/0.4.0/scripts/kit"),
                   os.path.join(bin_dir, "kit"))
        out, err, rc = run(cfg, bin_dir, update_cmd="false")
        check("a failing update exits zero", rc, 0)
        check("and says nothing", out.strip(), "")
        out, err, rc = run(cfg, bin_dir, update_cmd="this-command-does-not-exist")
        check("a missing update command exits zero", rc, 0)
        check("and says nothing", out.strip(), "")

        # Version ordering must be numeric. 0.10.0 is newer than 0.9.0, and a string
        # comparison says the opposite.
        cfg = os.path.join(root, "ordering")
        install(cfg, "0.9.0")
        install(cfg, "0.10.0")
        bin_dir = os.path.join(root, "bin6")
        os.makedirs(bin_dir)
        os.symlink(os.path.join(cfg, "plugins/cache/claude-kit/claude-kit/0.9.0/scripts/kit"),
                   os.path.join(bin_dir, "kit"))
        out, err, rc = run(cfg, bin_dir)
        check("0.10.0 is newer than 0.9.0", context(out), "now points at 0.10.0", contains)

        # Throttling: a second start inside the window must not run the update.
        cfg = os.path.join(root, "throttle")
        install(cfg, "0.4.0")
        bin_dir = os.path.join(root, "bin7")
        os.makedirs(bin_dir)
        os.symlink(os.path.join(cfg, "plugins/cache/claude-kit/claude-kit/0.4.0/scripts/kit"),
                   os.path.join(bin_dir, "kit"))
        marker = os.path.join(root, "ran.log")
        counter = os.path.join(root, "count.sh")
        with open(counter, "w") as fh:
            fh.write("#!/bin/sh\necho ran >> '%s'\n" % marker)
        os.chmod(counter, 0o755)
        run(cfg, bin_dir, update_cmd="sh " + counter, interval="3600")
        run(cfg, bin_dir, update_cmd="sh " + counter, interval="3600")
        run(cfg, bin_dir, update_cmd="sh " + counter, interval="3600")
        ran = len(open(marker).read().split()) if os.path.exists(marker) else 0
        check("three starts inside the window run the update once", ran, 1)
        # And the window expiring lets it run again.
        os.utime(os.path.join(cfg, "claude-kit", "freshness-checked-at"),
                 (time.time() - 7200, time.time() - 7200))
        run(cfg, bin_dir, update_cmd="sh " + counter, interval="3600")
        check("an expired window runs it again", len(open(marker).read().split()), 2)

        # A held lock means another session is already writing the plugin cache.
        os.utime(os.path.join(cfg, "claude-kit", "freshness-checked-at"),
                 (time.time() - 7200, time.time() - 7200))
        os.mkdir(os.path.join(cfg, "claude-kit", "freshness.lock"))
        run(cfg, bin_dir, update_cmd="sh " + counter, interval="3600")
        check("a held lock skips the update", len(open(marker).read().split()), 2)
        check("and leaves the other session's lock alone",
              os.path.isdir(os.path.join(cfg, "claude-kit", "freshness.lock")), True)

        # clear and compact do not restart the process, so there is nothing to check.
        os.utime(os.path.join(cfg, "claude-kit", "freshness-checked-at"),
                 (time.time() - 7200, time.time() - 7200))
        shutil.rmtree(os.path.join(cfg, "claude-kit", "freshness.lock"))
        out, err, rc = run(cfg, bin_dir, update_cmd="sh " + counter,
                           interval="3600", source="compact")
        check("compact does not trigger an update", len(open(marker).read().split()), 2)
        check("and says nothing", out.strip(), "")

        # Garbage on stdin must not crash it either, and the exit code is the half
        # that matters: a non-zero here is a hook that breaks every session start.
        bad = subprocess.run(
            [sys.executable, HOOK], input="not json at all", capture_output=True,
            text=True, env=dict(os.environ, CLAUDE_CONFIG_DIR=os.path.join(root, "empty"),
                                KIT_FRESHNESS_INTERVAL="0",
                                KIT_FRESHNESS_UPDATE_CMD="true"))
        check("malformed stdin exits zero", bad.returncode, 0)
        check("and prints nothing", bad.stdout.strip(), "")
        # Empty stdin is what a client that sends no payload looks like.
        empty = subprocess.run(
            [sys.executable, HOOK], input="", capture_output=True, text=True,
            env=dict(os.environ, CLAUDE_CONFIG_DIR=os.path.join(root, "empty"),
                     KIT_FRESHNESS_INTERVAL="0", KIT_FRESHNESS_UPDATE_CMD="true"))
        check("empty stdin exits zero", empty.returncode, 0)

        # With no override, the hook must refresh the marketplace before updating.
        # `claude plugin update` reads the cached index, so without the refresh a
        # version pushed since the last one is invisible and the update is a no-op
        # that reports success. That is how 0.9.1 stayed installed against a 0.9.4
        # remote while this hook ran every six hours.
        fake_dir = tempfile.mkdtemp(prefix="kit-fake-bin-", dir=root)
        log = os.path.join(fake_dir, "calls.log")
        fake = os.path.join(fake_dir, "claude")
        with open(fake, "w") as fh:
            fh.write('#!/bin/sh\necho "$@" >> "%s"\n' % log)
        os.chmod(fake, 0o755)
        cfg8 = os.path.join(root, "market")
        install(cfg8, "1.0.0")
        run(cfg8, os.path.join(root, "bin8"), update_cmd="",
            extra={"PATH": fake_dir + os.pathsep + os.environ["PATH"]})
        calls = open(log).read() if os.path.exists(log) else ""
        check("refreshes the marketplace index", calls, "marketplace update claude-kit",
              contains)
        check("and then updates the plugin", calls, "plugin update claude-kit@claude-kit",
              contains)
        # An explicit override owns the whole update path and gets no extra call.
        log2 = os.path.join(fake_dir, "calls2.log")
        with open(fake, "w") as fh:
            fh.write('#!/bin/sh\necho "$@" >> "%s"\n' % log2)
        os.chmod(fake, 0o755)
        cfg9 = os.path.join(root, "market-override")
        install(cfg9, "1.0.0")
        run(cfg9, os.path.join(root, "bin9"), update_cmd="true",
            extra={"PATH": fake_dir + os.pathsep + os.environ["PATH"]})
        check("an override suppresses both", os.path.exists(log2), False)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
