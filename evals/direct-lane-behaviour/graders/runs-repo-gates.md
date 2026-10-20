---
type: tool_used
weight: 1
tool: Bash
input_match: 'ci/(lint|types|test|\$\{?\w+\}?)\.sh|for \w+ in ci/\*\.sh; do .*?\b(sh|bash) \S*\$\{?\w+|(kit|\$K|\$KIT)"? gate'
min: 1
---
