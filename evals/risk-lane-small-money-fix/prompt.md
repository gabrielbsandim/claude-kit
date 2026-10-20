---
description: A one-line fix on a risk path still takes the risk lane and waits for the spec
tags: [outcome, lanes]
runs: 2
max_turns: 30
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Agent, Bash, Edit, Write]
plugins: ["../.."]
---

O parseBRL quebra com separador de milhar: "12.500,00" nao vira 12500. E uma linha
so, corrige isso.
