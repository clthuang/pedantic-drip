---
name: researching
description: Orchestrates parallel research, analysis, and synthesis into decision-ready summaries. Use when the user says 'research this', 'summarize what we know', 'gather context', or runs /pd:subagent-ras.
---

# Researching Skill

Three-phase pipeline: Research (parallel) → Analyze (synthesis) → Summarize (output).

## Input

A single argument: the user's query string.

## Phase 1: RESEARCH

Dispatch two research agents in parallel + gather context inline.

### Pre-Dispatch Memory Enrichment

Before each Task dispatch:
1. Call `search_memory(query="{agent role} {user query}", limit=5, brief=true)`
2. If results non-empty, append `## Relevant Engineering Memory\n{results}` to the dispatch prompt
3. Store returned entry names for post-dispatch influence tracking

### Parallel Agent Dispatch

Issue both Task dispatches in the same message:

**Task 1: Codebase Research**
```
Task tool call:
  description: "Find codebase patterns for: {query}"
  subagent_type: pd:codebase-explorer
  model: sonnet
  prompt: |
    Find existing code, patterns, and conventions related to: {query}

    Look for:
    - Similar implementations
    - Reusable components
    - Established conventions
    - Related utilities

    Return JSON:
    {
      "findings": [{"finding": "...", "source": "file/path:line", "relevance": "high|medium|low"}],
      "no_findings_reason": null
    }

    ## Relevant Engineering Memory
    {search_memory results if non-empty}
```

**Task 2: External Research**
```
Task tool call:
  description: "Research external solutions for: {query}"
  subagent_type: pd:internet-researcher
  model: sonnet
  prompt: |
    Research industry approaches, libraries, and best practices for: {query}

    Look for:
    - Industry standard approaches
    - Library support
    - Common patterns
    - Best practices

    Return JSON:
    {
      "findings": [{"finding": "...", "source": "URL", "relevance": "high|medium|low"}],
      "no_findings_reason": null
    }

    ## Relevant Engineering Memory
    {search_memory results if non-empty}
```

### Post-Dispatch Influence Tracking

For each agent response: scan output for stored memory entry names (case-insensitive exact substring). For matches, call `record_influence(entry_name, agent_role, feature_type_id)` where feature_type_id is from `.meta.json` if on a feature branch, otherwise skip.

### Inline Context Gathering

Run concurrently with agent dispatches:

1. `git branch --show-current` — if on `feature/*`, read `.meta.json` for feature context
2. `search_entities(query="{keywords from query}")` MCP — extract top 3 results. If MCP unavailable, skip.
3. `git log --oneline -10` — recent commits
4. Read `{pd_artifacts_root}/backlog.md` — extract open items (not marked closed/promoted)
5. Glob `{pd_artifacts_root}/brainstorms/*.prd.md` — extract first heading from each

Assemble into a text block for the synthesizer.

### Failure Detection

| Condition | Classification |
|-----------|---------------|
| Task tool returns error/exception | Agent failure |
| Output not parseable as expected JSON | Agent failure |
| Valid JSON, empty findings[], non-null no_findings_reason | Success (no findings) |
| search_memory / search_entities / record_influence unavailable | Skip gracefully, proceed |

### Failure Handling

| Scenario | Action |
|----------|--------|
| 1 of 2 research agents fails | Proceed; pass failure note to synthesizer |
| Both research agents fail | Abort: "Research failed — both agents returned errors. Try rephrasing or check network." |

---

## Phase 2: ANALYZE

After Phase 1 completes (both Task results received + inline context assembled):

### Pre-Dispatch Memory Enrichment

Call `search_memory(query="ras-synthesizer {user query}", limit=5, brief=true)`. Inject if non-empty.

### Synthesizer Dispatch

```
Task tool call:
  description: "Synthesize research findings for: {query}"
  subagent_type: pd:ras-synthesizer
  model: opus
  prompt: |
    Synthesize these research findings into a thematic analysis.

    ## Original Query
    {user's raw query}

    ## Codebase Findings
    {codebase-explorer JSON output, or "Agent unavailable — no codebase findings"}

    ## External Research
    {internet-researcher JSON output, or "Agent unavailable — no external findings"}

    ## Work Context
    {inline context text, or "Work context unavailable"}

    Return JSON per your agent schema.

    ## Relevant Engineering Memory
    {search_memory results if non-empty}
```

### Schema Validation

If synthesizer response is not valid JSON, or missing required fields (`executive_summary`, `confidence`, `themes`): treat as synthesizer failure → Phase 3 fallback.

### Post-Dispatch Influence Tracking

Same pattern as Phase 1.

---

## Phase 3: SUMMARIZE

### Normal Rendering (successful synthesis)

Convert synthesizer JSON to markdown. All section headers must be present:

```
Output:
## Research Summary: {query}

### Executive Summary
{executive_summary}
Confidence: {confidence}

### Key Findings
#### {theme.name}    (for each theme)
- {finding.text} [source: {finding.source}]

### Contradictions & Gaps
- {each contradiction}
- {each gap}
(or "No contradictions or gaps identified." if both empty)

### Recommendations
1. {each recommendation}

### Sources
- {each source, deduplicated}
```

### Fallback Rendering (synthesizer failure)

Spec R3 headers are exempted in fallback — degraded output:

```
Output:
## Research Summary: {query}

Note: Thematic synthesis unavailable. Raw findings shown by source.

### Codebase Findings
- {bullet per finding, or "No codebase findings available"}

### External Research
- {bullet per finding, or "No external findings available"}

### Work Context
{context text, or "Work context unavailable"}

### Sources
- {deduplicated source list}
```

### Save Prompt

After rendering output:

```
AskUserQuestion:
  questions: [{
    "question": "Save this research summary?",
    "header": "Save",
    "options": [
      {"label": "Save", "description": "Write to agent_sandbox/{date}/ras-{slug}.md"},
      {"label": "Dismiss", "description": "Summary shown only — not persisted"}
    ],
    "multiSelect": false
  }]
```

**Slug derivation:** (1) first 5 words of query (split on whitespace), (2) lowercase, (3) strip chars not in a-z, 0-9, or hyphen, (4) join with hyphens, (5) collapse consecutive hyphens, (6) truncate to 50 chars.

If Save: write rendered markdown to `agent_sandbox/{YYYY-MM-DD}/ras-{slug}.md`. Create directory if needed.
If Dismiss: no action.
