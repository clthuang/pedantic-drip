---
description: Research, analyze, and summarize any topic using parallel agents
argument-hint: <query>
---

# /pd:subagent-ras Command

Research, Analyze, Summarize — gather multi-source intelligence and produce a decision-ready summary.

## Usage

```
/pd:subagent-ras <query>
```

If no argument provided, display: `"Usage: /pd:subagent-ras <query>"`

## Execution

Invoke the `researching` skill with the query argument. The skill handles the full pipeline:
1. Parallel research (codebase + web + context)
2. Thematic synthesis
3. Structured output + save prompt
