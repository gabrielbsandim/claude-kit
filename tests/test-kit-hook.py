#!/usr/bin/env python3
"""Proves the shim resolves the newest installed copy and never breaks a tool call.

    python3 tests/test-kit-hook.py

The shim exists so that no hook of this plugin is ever registered by copying its
Python file. A copy is correct exactly until the next release and silent about it
afterwards, which is how `~/.claude/hooks/` ended up three versions behind on
2026-08-23 while the tests covering those same hooks were green.
"""
import os
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIM = os.path.join(KIT, "hooks", "kit-hook.sh")
PASS, FAIL = 0, 0


def check(name, got, want):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print("ok    %s" % name)
    else:
        FAIL += 1
        print("FAIL  %s\n        got  %r\n        want %r" % (name, got, want))


def install(cfg, version, name, body):
    root = os.path.join(cfg, "plugins", "cache", "claude-kit", "claude-kit", version, "hooks")
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, name)
    with open(path, "w") as fh:
        fh.write(body)
    return path


def run(cfg, *args, stdin=""):
    out = subprocess.run(
        ["sh", SHIM, *args], input=stdin, capture_output=True, text=True,
        env=dict(os.environ, CLAUDE_CONFIG_DIR=cfg))
    return out.stdout.strip(), out.returncode


def main():
    root = tempfile.mkdtemp(prefix="kit-hook-")
    try:
        empty = os.path.join(root, "empty")
        os.makedirs(empty)

        # Nothing registered can be allowed to fail: this runs before a tool call.
        check("no argument exits zero", run(empty, ), ("", 0))
        check("nothing installed exits zero", run(empty, "no-em-dash.py"), ("", 0))

        cfg = os.path.join(root, "cfg")
        install(cfg, "0.9.1", "demo.py", "import sys; print('old'); sys.exit(0)\n")
        install(cfg, "0.9.10", "demo.py", "import sys; print('new'); sys.exit(2)\n")
        install(cfg, "0.9.2", "demo.py", "import sys; print('middle'); sys.exit(0)\n")

        # Version order is numeric, not lexical. 0.9.10 is newer than 0.9.2, and a
        # plain sort would disagree the day the tenth patch ships.
        check("resolves the newest version", run(cfg, "demo.py"), ("new", 2))

        # The exit code is the hook's whole contract: 2 blocks, 0 allows. A shim that
        # swallowed it would turn every guard in the plugin into a no-op.
        install(cfg, "0.9.11", "demo.py", "import sys; sys.exit(0)\n")
        check("passes the exit code through", run(cfg, "demo.py"), ("", 0))

        # The payload arrives on stdin, so the shim has to be transparent to it.
        install(cfg, "0.9.12", "echo.py", "import sys; sys.stdout.write(sys.stdin.read())\n")
        check("passes stdin through", run(cfg, "echo.py", stdin="payload"), ("payload", 0))

        # The argument names a hook. Nothing here composes a path, so anything that
        # looks like one is refused rather than resolved.
        check("refuses a path", run(cfg, "../../../bin/kit"), ("", 0))
        check("refuses a bare parent", run(cfg, ".."), ("", 0))
        check("a missing hook name exits zero", run(cfg, "not-a-hook.py"), ("", 0))
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
