---
name: ship
description: Takes work that is already implemented and committed on a branch and ships it: runs the repo's ship gates off receipts, pushes, opens a draft pull request, moves the board to in review, and removes the worktree. Use when the code exists and the task is to get it reviewable, or on /ship, and not when anything still needs writing.
---

# ship: committed work to a draft pull request

The tail of the funnel, on its own. Use it when the work already exists: you implemented
by hand, or a task run stopped after the gate, or a branch has been sitting for a day.

If anything still needs writing, this is the wrong skill. Use the task funnel, which has
triage, a spec and a review in front of this.

Input: nothing, or an issue number. Empty means the current branch.

## Stage 0 · Is this shippable

```
kit doctor
git status --short
git log --oneline <base>..HEAD
```

Stop and report, without shipping, on any of:

- **Uncommitted changes.** The review diffs commits, so uncommitted work is invisible.
  Commit it or say why it is excluded.
- **No commits ahead of the base.** There is nothing to ship.
- **A commit that does not follow the repo's convention.** `kit config get .docs.commits`
  names the document. Fix the message before the pull request quotes it.
- **No review has happened.** Ask before shipping unreviewed work; `kit review <level>`
  is minutes and a defect found here costs a round instead of a revert. If the user says
  ship anyway, say in the pull request body that it went out unreviewed.

## Stage 1 · Gates, off receipts

```
kit gate ship
```

Gates whose receipt already covers this exact tree are skipped and say so. The tree SHA
includes untracked files, so any edit at all invalidates it. That is the difference
between skipping a check and proving it was already paid.

A red gate stops here. `kit gate` prints a `flake` line when the failing file is on the
repo's quarantine list and whether this branch's diff can even reach it; a red gate in a
file the diff never touched is not a reason to stop, and it is not a reason to change code
either. Re-run that file alone.

## Stage 2 · Push

The repo's pre-push hook runs its own checks. The fix for a red hook is the failing check,
never `--no-verify`, and the plugin's `protect-tests` hook refuses it anyway.

## Stage 3 · The pull request

Open it exactly as the repo's pipeline document says. That document, not this skill, owns
the base branch, the draft state and the issue reference.

Fill the repo's template honestly, which means three specific things:

1. **A check is ticked only if it ran.** An unticked box is information; a ticked box that
   did not run is a lie with a green mark next to it.
2. **Answer the surfaces question in prose**, even when the answer is nothing. A sentence
   beats a box, because the box is what gets ticked without being read.
3. **PLAUSIBLE findings go under points of attention.** A finding you could not prove is
   not a blocker and not nothing.

## Stage 4 · Board and teardown

```
kit board in_review --issue <issue>
kit worktree gc --yes
```

The board move goes after the pull request URL exists. Never `done`: this does not merge,
and the tracker's own automation owns that column.

`gc` removes only what it can prove is finished, which now includes an open pull request
sitting at exactly this head, since everything is then on the remote and the branch
survives removal. It keeps the rest and prints why, including a worktree with nothing of
its own on it, which cannot be told apart from one another session just created. `rm
<issue>` was the step here until 0.3.0 and could not succeed once the pull request existed.
`gc --dry-run` first if you want to see the verdicts without acting.

## Stage 5 · Report

Three to six lines: what shipped, the gate result including what was skipped by receipt,
the pull request link, and what was left out. Never declare done without the numbers, and
name a gate that stopped you as such.
