---
description: One-time setup for claude-kit in this environment, then a per-repo config check
argument-hint: "[--repo]"
allowed-tools: Bash(*), Read, Edit, Write
---

Set up claude-kit here. Do the steps in order and stop at the first one that
fails, reporting what failed and the one command that fixes it.

1. Put `kit` on PATH:

   ```
   "${CLAUDE_PLUGIN_ROOT}/scripts/kit" setup
   ```

   If it prints an `export PATH` line, the directory is not on PATH yet. Add
   that line to the user's shell profile only after saying which file you are
   editing and why.

2. Check the environment:

   ```
   kit doctor
   ```

   `git` and `jq` are required. `gh` is required only for the GitHub Projects
   board adapter, and it needs the `project` scope: `gh auth refresh -s project`.
   `az` is only for Azure DevOps.

3. If the current directory is a git repository and has no
   `.claude/funnel.config.json`, offer to create one:

   ```
   kit config init
   kit config check
   ```

   Then walk the file with the user and fill in the four things a default cannot
   guess: the base branch, the gate commands this repo actually has, the review
   slices (which paths are source and which are tests), and the document set per
   lens. `kit config check` fails on a slice or gate that does not exist, so run
   it after every edit.

4. If the repo uses a board, discover the ids rather than asking for them:

   ```
   kit board --discover
   ```

   Paste the project id, the Status field id and the option ids for in progress
   and in review into `.claude/board.json`. Do not invent ids, and never write a
   token into that file: the adapters read credentials from the environment or
   from `gh`.

5. Report in five lines: what is on PATH, what `kit doctor` said, whether the
   repo has a config, whether the board resolved, and the single next action if
   any step is incomplete.

Do not commit anything. The config belongs in a commit, but which commit is the
user's call.
