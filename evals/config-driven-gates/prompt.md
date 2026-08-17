---
name: config-driven-gates
description: The funnel has to read this repo's own gate commands instead of assuming a stack
tags: [config]
runs: 2
max_turns: 10
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Bash]
plugins: ["../.."]
---

Antes de eu te dar uma tarefa: quais comandos exatos este repositorio roda como
gate antes de um push, e qual e o branch base? Responda so isso, sem mexer em
nada.
