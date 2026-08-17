#!/usr/bin/env python3
"""Proves what `worktree` will and will not delete.

    python3 tests/test-worktree-state.py

Every case here is a state a real worktree was found in. Two of them are the
reason this file exists:

- An **open** pull request at exactly the local head used to mean KEEP, which made
  the funnel's own teardown step impossible: stage 5 opens the pull request and
  then asks for the worktree back. Every task leaked one, 27 worktrees and 35 GB
  on the machine where it was measured.
- A worktree sitting **exactly** on the base tip with nothing of its own is what a
  worktree created seconds ago looks like. `gc` runs at ship now, so calling that
  FINISHED would delete the worktree another session is still setting up. A head
  that is merely an *ancestor* of the base is a different thing and stays
  removable.

`gh` is stubbed, because the states worth testing are the tracker's answers and a
real one would need a real pull request.
"""
import os
import shutil
import subprocess
import sys
import tempfile

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKTREE = os.path.join(KIT, "bin", "worktree")
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


def git(root, *args, **kw):
    return subprocess.run(["git"] + list(args), cwd=root, check=kw.get("check", True),
                          capture_output=True, text=True).stdout


def fake_gh(bindir, table):
    """A `gh` that answers `pr list --head <branch>` from a table, and nothing else.

    The real command is asked for state, number and headRefOid as one string, so
    that is exactly what this prints.
    """
    os.makedirs(bindir, exist_ok=True)
    path = os.path.join(bindir, "gh")
    lines = ["#!/bin/sh", 'head=""', 'for a in "$@"; do',
             '  [ "$prev" = "--head" ] && head="$a"; prev="$a"', 'done', "case \"$head\" in"]
    for branch, answer in table.items():
        lines.append('  %s) printf \'%s\\n\' ;;' % (branch, answer))
    lines += ["  *) : ;;", "esac", "exit 0"]
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    os.chmod(path, 0o755)
    return path


def build(root):
    """A repository with a real origin, so ancestry questions have real answers."""
    remote = os.path.join(root, "remote.git")
    work = os.path.join(root, "work")
    git(root, "init", "-q", "--bare", "-b", "main", remote)
    git(root, "clone", "-q", remote, work)
    git(work, "config", "user.email", "t@t")
    git(work, "config", "user.name", "t")
    os.makedirs(os.path.join(work, ".claude"), exist_ok=True)
    with open(os.path.join(work, ".claude/funnel.config.json"), "w") as fh:
        fh.write('{"base": "main", "gates": {}, "stages": {}, "slices": {}, "lenses": {}, "effort": {}}')
    with open(os.path.join(work, "a.txt"), "w") as fh:
        fh.write("one\n")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "base one")
    old_main = git(work, "rev-parse", "HEAD").strip()
    with open(os.path.join(work, "a.txt"), "w") as fh:
        fh.write("two\n")
    git(work, "commit", "-qam", "base two")
    git(work, "push", "-q", "origin", "main")
    return work, old_main


def add_worktree(work, root, name, start):
    path = os.path.join(root, name)
    git(work, "worktree", "add", "-q", "-b", name, path, start)
    return path


def commit_in(path, text):
    with open(os.path.join(path, "b.txt"), "w") as fh:
        fh.write(text)
    git(path, "add", "-A")
    git(path, "commit", "-qm", "work " + text)
    return git(path, "rev-parse", "HEAD").strip()


def run(work, env, *args):
    e = dict(os.environ)
    e.update(env)
    e["FUNNEL_FAST"] = "1"
    out = subprocess.run([WORKTREE] + list(args), cwd=work, capture_output=True, text=True, env=e)
    return out.stdout + out.stderr, out.returncode


def state_line(output, name):
    for line in output.splitlines():
        if (" " + name + " ") in (" " + line.replace("\t", " ") + " ") or line.split()[1:2] == [name]:
            return line
    for line in output.splitlines():
        if name in line:
            return line
    return ""


def main():
    root = tempfile.mkdtemp(prefix="kit-wtstate-")
    try:
        work, old_main = build(root)
        bindir = os.path.join(root, "bin")

        # fresh: created at the base tip, nothing of its own. Must survive gc.
        fresh = add_worktree(work, root, "fresh", "origin/main")
        # behind: an older base tip, so nobody is starting from it.
        behind = add_worktree(work, root, "behind", old_main)
        # open-at-head: a pull request showing exactly what is here.
        at_head = add_worktree(work, root, "open-at-head", "origin/main")
        oid_at_head = commit_in(at_head, "pushed\n")
        # open-ahead: local commits the pull request has not seen.
        ahead = add_worktree(work, root, "open-ahead", "origin/main")
        oid_seen = commit_in(ahead, "seen\n")
        commit_in(ahead, "unseen\n")
        # open-unfetched: the pull request head is a commit this repo does not have.
        unfetched = add_worktree(work, root, "open-unfetched", "origin/main")
        commit_in(unfetched, "local only\n")
        # merged-at-head: the case that already worked, kept as a regression.
        merged = add_worktree(work, root, "merged-at-head", "origin/main")
        oid_merged = commit_in(merged, "merged\n")
        # dirty: an edit nobody committed.
        dirty = add_worktree(work, root, "dirty", "origin/main")
        with open(os.path.join(dirty, "c.txt"), "w") as fh:
            fh.write("uncommitted\n")

        fake_gh(bindir, {
            "open-at-head": "OPEN 11 " + oid_at_head,
            "open-ahead": "OPEN 12 " + oid_seen,
            "open-unfetched": "OPEN 13 " + ("d" * 40),
            "merged-at-head": "MERGED 14 " + oid_merged,
        })
        env = {"PATH": bindir + os.pathsep + os.environ["PATH"]}

        out, rc = run(work, env, "gc", "--dry-run")
        if rc != 0:
            out2, _ = run(work, env, "list")
            out = out + "\n--- list ---\n" + out2
        check("gc lists every worktree", out.count("fresh"), 1, lambda a, b: a >= b)

        check("a worktree at the exact base tip is kept",
              state_line(out, "fresh"), "KEEP nothing of its own yet", contains)
        check("a worktree at an older base tip is finished",
              state_line(out, "behind"), "FINISHED head is in main", contains)
        check("an open pull request at this exact head is finished",
              state_line(out, "open-at-head"),
              "FINISHED pr #11 open at this exact head", contains)
        check("commits the open pull request has not seen are kept",
              state_line(out, "open-ahead"), "KEEP 1 commit(s) past the head pr #12", contains)
        check("an unfetched open head is kept, and says why",
              state_line(out, "open-unfetched"), "never fetched", contains)
        check("a merged pull request at this exact head is still finished",
              state_line(out, "merged-at-head"),
              "FINISHED pr #14 merged at this exact head", contains)
        check("an uncommitted edit is still kept",
              state_line(out, "dirty"), "KEEP uncommitted changes", contains)

        # The whole point: gc would remove the shipped one and leave the fresh one.
        would = [ln for ln in out.splitlines() if ln.startswith("would rm")]
        kept = [ln for ln in out.splitlines() if ln.startswith("keep")]
        check("gc would remove the shipped worktree",
              any("open-at-head" in ln for ln in would), True)
        check("gc would not remove the fresh one",
              any("fresh" in ln for ln in kept), True)
        check("gc would not remove the dirty one",
              any("dirty" in ln for ln in kept), True)
        check("gc removes nothing without --yes", "nothing removed" in out, True)

        # rm follows the same verdict: no --force needed for a shipped worktree,
        # and still refused for anything with work in it.
        out, rc = run(work, env, "rm", at_head, "--dry-run")
        check("rm accepts the shipped worktree without --force", rc, 0)
        check("rm prints how to recreate it", "recreate with: git worktree add" in out, True)

        out, rc = run(work, env, "rm", fresh)
        check("rm refuses a worktree at the exact base tip", rc != 0, True)
        check("and names the reason", "nothing of its own yet" in out, True)
        check("the refused worktree is still there", os.path.isdir(fresh), True)

        out, rc = run(work, env, "rm", dirty)
        check("rm still refuses uncommitted changes", rc != 0, True)

        # And --yes actually removes, which is the half a dry run cannot prove.
        out, rc = run(work, env, "gc", "--yes")
        check("gc --yes removes the shipped worktree", os.path.isdir(at_head), False)
        check("gc --yes keeps the fresh one", os.path.isdir(fresh), True)
        check("gc --yes keeps the dirty one", os.path.isdir(dirty), True)
        check("gc --yes keeps the unfetched one", os.path.isdir(unfetched), True)
        check("gc --yes reports what it removed", "removed" in out, True)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
