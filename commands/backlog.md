---
description: Groom the open backlog: what is the same work, what is an orphan, and what can ship in one pull request
argument-hint: "[epic-number | label]"
allowed-tools: Bash(*), Read
---

Groom the backlog with the `claude-kit:backlog` skill. Scope is `$ARGUMENTS`, or the
whole open board when that is empty.

Read-only until the user approves each group. Do not close, edit or adopt anything on
your own initiative, and do not close an issue without naming the commit or pull
request that already did the work.

Report the four counts at the end: open before, open after if every proposal is
accepted, orphans before and after.
