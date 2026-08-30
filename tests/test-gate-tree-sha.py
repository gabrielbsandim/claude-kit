#!/usr/bin/env python3
"""Proves a gate receipt is keyed to the working tree even when `git add -A` fails.

    python3 tests/test-gate-tree-sha.py

`kit gate` keys a receipt to the tree sha of the working directory: read HEAD into
a throwaway index, `git add -A`, `git write-tree`. `git add -A` refuses any path
that is not a regular file, a symlink or a git directory, and one such path aborts
the whole add. `write-tree` then returns the tree already in the index, HEAD's, and
says nothing about it. Every receipt written after that verifies clean against any
uncommitted change at all, which is the one thing a receipt exists to refuse.

Found in obranova on 2026-08-30: three character devices in the repository root,
bind mounts over /dev/null created by an agent sandbox to deny reads on dotfiles.
A device node cannot be created without root, and a fifo does not reproduce it
(git ignores those silently), so the failure is injected here with a `git` stub
that delegates everything else to the real one.
"""
import os
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = os.path.join(KIT, "bin", "gate")
REAL_GIT = shutil.which("git")
PASS, FAIL = 0, []

# Refuses the first `refusals` paths named in .refuse on any `add -A`, one per
# call and aborting there, which is what git itself does. Everything else is git.
STUB = """#!/bin/sh
if [ "$1" = add ]; then
  i=0
  while IFS= read -r p; do
    i=$((i + 1))
    case " $* " in *" :(exclude)$p "*) continue ;; esac
    echo "error: $p: can only add regular files, symbolic links or git-directories" >&2
    echo "fatal: adding files failed" >&2
    exit 128
  done < "$REFUSE"
fi
exec %s "$@"
""" % REAL_GIT


def check(name, ok, detail=""):
    global PASS
    if ok:
        PASS += 1
    else:
        FAIL.append("%s: %s" % (name, detail))


def git(root, *args):
    subprocess.run([REAL_GIT] + list(args), cwd=root, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def receipts_tree(root, bindir, refuse):
    """The tree sha `kit gate` would key a receipt to, or None when it refuses."""
    env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"],
               REFUSE=refuse)
    out = subprocess.run([GATE, "--receipts"], cwd=root, env=env,
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        if line.startswith("tree "):
            return line.split()[1]
    return None


# The fixtures live outside the repository under test: a stub binary or a refusal
# list inside it is an untracked file, and this file's whole subject is a tree sha
# that must react to untracked files.
work = tempfile.mkdtemp(prefix="kit-gate-tree-")
root = os.path.join(work, "repo")
bindir = os.path.join(work, "stub-bin")
try:
    os.makedirs(bindir)
    os.makedirs(root)
    with open(os.path.join(bindir, "git"), "w") as fh:
        fh.write(STUB)
    os.chmod(os.path.join(bindir, "git"), 0o755)

    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    os.makedirs(os.path.join(root, ".claude"))
    with open(os.path.join(root, ".claude/funnel.config.json"), "w") as fh:
        fh.write('{"base":"main","stages":{"ship":{"gates":["lint"]}},'
                 '"gates":{"lint":{"command":"true"}}}')
    with open(os.path.join(root, "code.ts"), "w") as fh:
        fh.write("export const answer = 42\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")

    none = os.path.join(work, "refuse-none")
    open(none, "w").close()
    three = os.path.join(work, "refuse-three")
    with open(three, "w") as fh:
        fh.write(".bash_profile\n.bashrc\n.gitconfig\n")

    head_tree = subprocess.run([REAL_GIT, "rev-parse", "HEAD^{tree}"], cwd=root,
                               capture_output=True, text=True).stdout.strip()

    clean = receipts_tree(root, bindir, none)
    check("1 a clean tree with nothing refused is HEAD's tree",
          clean == head_tree, "%s vs %s" % (clean, head_tree))

    # The whole point. Three refused paths, and the answer is still the tree the
    # working directory has, not the one the index happened to be holding.
    check("2 three refused paths do not change the answer",
          receipts_tree(root, bindir, three) == clean, "the exclusions moved the tree")

    # And the invariant that failed in production: an uncommitted edit has to move
    # the sha even while the add is failing, or the receipt survives the edit.
    with open(os.path.join(root, "code.ts"), "w") as fh:
        fh.write("export const answer = 43\n")
    dirty = receipts_tree(root, bindir, three)
    check("3 an uncommitted edit moves the sha anyway",
          dirty is not None and dirty != clean, "the receipt would survive the edit")
    check("3 and it is not HEAD's tree, which is the bug's signature",
          dirty != head_tree, dirty)

    with open(os.path.join(root, "code.ts"), "w") as fh:
        fh.write("export const answer = 42\n")
    check("4 reverting the edit returns the original sha",
          receipts_tree(root, bindir, three) == clean, "not content-addressed")

    # 6. Excluding an untracked path is safe: it was never in the tree. Excluding a
    #    tracked one is not, because the index still holds HEAD's copy, so a change
    #    to that file would not move the sha and the receipt would survive it.
    tracked = os.path.join(work, "refuse-tracked")
    with open(tracked, "w") as fh:
        fh.write("code.ts\n")
    env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"],
               REFUSE=tracked)
    out = subprocess.run([GATE, "--receipts"], cwd=root, env=env,
                         capture_output=True, text=True)
    check("6 a tracked unstageable path stops the run", out.returncode != 0,
          out.stdout + out.stderr)
    check("6 and says the receipt would hide a change to it",
          "which is\ntracked" in out.stderr, out.stderr)

    # A failure this does not understand is not silently excluded into a wrong
    # answer: there is nothing to exclude, so it stops.
    other = os.path.join(work, "refuse-other")
    with open(other, "w") as fh:
        fh.write("x\n")
    env = dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"],
               REFUSE=other)
    with open(os.path.join(bindir, "git"), "w") as fh:
        fh.write(STUB.replace("can only add regular files, symbolic links or"
                              " git-directories", "some other failure"))
    os.chmod(os.path.join(bindir, "git"), 0o755)
    out = subprocess.run([GATE, "--receipts"], cwd=root, env=env,
                         capture_output=True, text=True)
    check("5 an unrecognised add failure stops instead of guessing",
          out.returncode != 0, out.stdout + out.stderr)
    check("5 and says why", "cannot compute the work tree sha" in out.stderr,
          out.stderr)
finally:
    shutil.rmtree(work, ignore_errors=True)

print("%d passed, %d failed" % (PASS, len(FAIL)))
for line in FAIL:
    print("  FAIL %s" % line)
sys.exit(1 if FAIL else 0)
