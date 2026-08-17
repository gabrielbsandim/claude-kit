---
name: routing-investigate
description: A question about behaviour has to reach investigate, and must not open the delivery funnel
tags: [routing]
runs: 3
max_turns: 8
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill]
plugins: ["../.."]
---

Por que a medicao aprovada as vezes aparece com valor pago zerado? Quero
entender antes de mexer em nada.
