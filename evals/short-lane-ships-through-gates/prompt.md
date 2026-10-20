---
description: A copy fix still has to pass the repo's own gates and land on a branch, never on trunk
tags: [outcome, gates]
runs: 2
max_turns: 60
timeout_seconds: 1500
allowed_tools: [Read, Glob, Grep, Skill, Agent, Bash, Edit, Write]
plugins: ["../.."]
---

A mensagem de campo obrigatorio esta sem acento ("Campo obrigatorio"). Corrige para
"Campo obrigatório" e deixa pronto para eu abrir a PR. Nao tem issue para isso.
