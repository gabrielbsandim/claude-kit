---
name: routing-implement
description: A natural "change this repo" request has to reach the task funnel, not a bare edit
tags: [routing]
runs: 3
max_turns: 8
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill]
plugins: ["../.."]
---

Preciso adicionar um campo de observacao na tela de medicao, com validacao de
tamanho maximo e teste. Pode comecar?
