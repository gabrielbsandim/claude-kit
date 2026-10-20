---
description: A behaviour change off the risk paths takes the direct lane, writes the code and runs the gates without waiting on a spec
tags: [outcome, lanes]
runs: 2
max_turns: 80
timeout_seconds: 1800
allowed_tools: [Read, Glob, Grep, Skill, Agent, Bash, Edit, Write]
plugins: ["../.."]
---

A observacao da medicao precisa ser cortada em 500 caracteres, com "..." no fim quando
cortar. Cria uma funcao para isso em src/texto.ts e deixa pronto para eu abrir a PR.
