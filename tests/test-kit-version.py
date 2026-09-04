#!/usr/bin/env python3
"""Proves `kit version` can tell the three copies of this plugin apart.

    python3 tests/test-kit-version.py

Three copies disagree independently and every disagreement is silent:

1. the copy a running session loaded at startup, which keeps its skills and agents
   through a `claude plugin update`,
2. the copy `kit` on PATH points at, which `kit setup` pins to a versioned cache
   directory,
3. the newest copy actually installed.

Measured on 2026-08-17: a funnel run executed the 0.1.0 skill while 0.2.0 had been
installed for five minutes. Nothing in the run said so, which is why the check is a
command and not a paragraph.

The last case also pins the version literal in the task skill to the manifest, so
the check cannot rot into comparing a stale number against itself.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def plugin_copy(root, version, name="claude-kit"):
    """A minimal plugin tree: a manifest and the real scripts/, so kit runs from it."""
    os.makedirs(os.path.join(root, ".claude-plugin"), exist_ok=True)
    with open(os.path.join(root, ".claude-plugin/plugin.json"), "w") as fh:
        json.dump({"name": name, "version": version}, fh)
    shutil.copytree(os.path.join(KIT, "scripts"), os.path.join(root, "scripts"), dirs_exist_ok=True)
    return os.path.join(root, "scripts", "kit")


def installed(cfg, name, version):
    """A copy where `claude plugin install` puts one: cache/<market>/<plugin>/<version>."""
    d = os.path.join(cfg, "plugins", "cache", name, name, version, ".claude-plugin")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "plugin.json"), "w") as fh:
        json.dump({"name": name, "version": version}, fh)
    return os.path.dirname(d)


def run(kit, cfg, *args):
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = cfg
    out = subprocess.run([kit, "version"] + list(args), capture_output=True, text=True, env=env)
    return out.stdout + out.stderr, out.returncode


def main():
    root = tempfile.mkdtemp(prefix="kit-version-")
    try:
        cfg = os.path.join(root, "cfgdir")
        running = plugin_copy(os.path.join(root, "running"), "0.3.0")

        # Nothing installed: a clone is a legitimate place to run from, so this must
        # not fail. It failing is how a version check gets removed.
        out, rc = run(running, cfg)
        check("no installed copy is not an error", rc, 0)
        check("and it says where it looked", out, "no installed copy under", contains)
        check("it still names the running version", out, "0.3.0", contains)

        installed(cfg, "claude-kit", "0.2.0")
        installed(cfg, "claude-kit", "0.3.0")
        # Lexical sorting would call 0.9.0 newer than 0.10.0.
        installed(cfg, "claude-kit", "0.9.0")
        installed(cfg, "claude-kit", "0.10.0")
        # A different plugin's manifest in the same tree must not be read as ours.
        installed(cfg, "some-other-plugin", "9.9.9")

        out, rc = run(running, cfg)
        check("the newest installed is chosen by version, not by string",
              re.search(r"installed\s+0\.10\.0", out) is not None, True)
        check("another plugin's version is ignored", "9.9.9" in out, False)

        # The running copy is older than what is installed: `kit setup` pinned a
        # versioned path, so the executable on PATH went stale on its own.
        check("an older running copy is reported as STALE KIT", out, "STALE KIT", contains)
        check("and the fix it prints is a setup command", out, "scripts/kit setup", contains)
        check("stale exits non-zero so it cannot be skimmed past", rc, 3)

        # The caller declaring an older version is the session-restart case.
        newest = plugin_copy(os.path.join(root, "newest"), "0.10.0")
        out, rc = run(newest, cfg)
        check("a current running copy is up to date", out, "up to date", contains)
        check("and exits zero", rc, 0)

        out, rc = run(newest, cfg, "0.1.0")
        check("an older caller is reported as STALE SKILL", out, "STALE SKILL", contains)
        check("the caller version is echoed", out, "0.1.0", contains)
        check("the fix named is restarting the session", out, "restart the session", contains)
        check("and it exits non-zero", rc, 3)

        out, rc = run(newest, cfg, "0.10.0")
        check("a caller at the newest version is up to date", out, "up to date", contains)
        check("and exits zero", rc, 0)

        # A caller ahead of everything installed is a clone, not a stale skill.
        out, rc = run(newest, cfg, "9.0.0")
        check("a caller ahead of the installed copies is not stale", rc, 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # The literal in the skill is the whole mechanism. If it drifts from the
    # manifest, the check compares a stale number and always answers up to date.
    with open(os.path.join(KIT, ".claude-plugin/plugin.json")) as fh:
        manifest = json.load(fh)["version"]
    with open(os.path.join(KIT, "skills/task/SKILL.md")) as fh:
        skill = fh.read()
    declared = re.findall(r"kit version (\d+\.\d+\.\d+)", skill)
    check("the task skill declares exactly one version", len(declared), 1)
    check("and it is the manifest version", declared[0] if declared else None, manifest)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
