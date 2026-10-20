---
description: A behaviour change on money gets a spec with criteria and waits, instead of an edit
tags: [outcome, spec]
runs: 2
max_turns: 30
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Agent, Bash, Edit, Write]
plugins: ["../.."]
---

Medicao acima de R$ 50.000 tem que passar por um segundo gestor antes de ficar
aprovada. Implementa isso.
