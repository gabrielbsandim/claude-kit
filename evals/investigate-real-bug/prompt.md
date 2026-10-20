---
description: A why-question gets the real root cause with evidence and no edits
tags: [outcome, investigate]
runs: 2
max_turns: 30
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Agent, Bash, Edit, Write]
plugins: ["../.."]
---

Por que medicao aprovada as vezes aparece com valor pago zerado? Quero entender
antes de mexer em qualquer coisa.
