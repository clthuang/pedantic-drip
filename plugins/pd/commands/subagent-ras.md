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

1. **Research in parallel,** each dispatch following the `researching` skill's contract (one narrow question, pointers back):
   - `pd:codebase-explorer` (model: sonnet) for the codebase;
   - `pd:internet-researcher` (model: sonnet) for external sources.
2. **Synthesize:** dispatch `pd:ras-synthesizer` (model: opus) with the query, both findings (or their unavailability notes) and the work context.
3. **Report** its summary to the user.
