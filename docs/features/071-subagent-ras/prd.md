# PRD: pd:subagent-ras — Research, Analyze, Summarize

*Source: Backlog (ad-hoc)*

## Problem

When facing complex decisions — whether about feature direction, architecture choices, or understanding an unfamiliar domain — the user needs holistic situational awareness before committing. Today this requires manually dispatching individual agents (codebase-explorer, internet-researcher, investigation-agent) in separate queries, then mentally synthesizing the results. There's no single command that gathers multi-source intelligence, analyzes it, and delivers a concise decision-ready summary.

## Solution

A new `pd:subagent-ras` command that executes a three-phase pipeline:

1. **Research** — Parallel dispatch of specialized agents to gather findings from multiple sources (internal codebase, external web, current work state)
2. **Analyze** — A synthesis agent merges raw findings, identifies patterns/contradictions/gaps, and structures them thematically
3. **Summarize** — Produce a concise, decision-ready output with executive summary, key findings by theme, open questions, and actionable recommendations

## User Stories

1. "I'm about to design a new feature and want to understand what patterns already exist in the codebase and what the industry best practices are" → `/pd:subagent-ras what patterns exist for webhook retry logic`
2. "I need to understand the current state of this feature before deciding next steps" → `/pd:subagent-ras what is the current state of feature 068`
3. "I want to research a technical topic before brainstorming" → `/pd:subagent-ras compare event sourcing vs CQRS for audit logging`
4. "I want context on a bug before investigating" → `/pd:subagent-ras what do we know about the sqlite locking issues`

## Architecture

### Pipeline

```
User query
  ↓
Phase 1: RESEARCH (parallel, within max_concurrent_agents budget)
  ├─ pd:codebase-explorer  → internal patterns, related code
  ├─ pd:internet-researcher → external best practices, prior art
  └─ Context gatherer (inline) → current feature state, entity registry, git context
  ↓
Phase 2: ANALYZE (single agent — opus)
  └─ pd:ras-synthesizer → merge findings, identify themes, flag contradictions
  ↓
Phase 3: SUMMARIZE (output)
  └─ Structured markdown output to user + optional save prompt
```

### Components

**New command:** `plugins/pd/commands/subagent-ras.md`
- Accepts a free-text query as argument
- Orchestrates the 3-phase pipeline via the `researching` skill
- Outputs structured summary inline
- After output, prompts via AskUserQuestion: "Save this summary?" with options Save / Dismiss. If Save, writes to `agent_sandbox/{date}/ras-{slug}.md`

**New agent:** `plugins/pd/agents/ras-synthesizer.md`
- Model: opus (needs deep reasoning to merge contradictory findings across sources)
- Tools: [Read] (may need to read files referenced in findings)
- Role: Receives raw findings from all research agents, produces thematic analysis
- Returns structured JSON: `{executive_summary, themes[], contradictions[], gaps[], recommendations[], confidence}`

**Reused agents (no changes):**
- `pd:codebase-explorer` (sonnet) — internal code patterns
- `pd:internet-researcher` (sonnet) — external research

**New skill:** `plugins/pd/skills/researching/SKILL.md`
- Orchestration logic for the 3-phase pipeline
- Called by the command

### Query Reformulation

The skill reformulates the user's query into agent-specific prompts:
- **codebase-explorer** gets a code-pattern-focused variant: "Find existing code, patterns, and conventions related to: {query}"
- **internet-researcher** gets a best-practices-focused variant: "Research industry approaches, libraries, and best practices for: {query}"
- **ras-synthesizer** receives all raw findings plus the original query for faithful synthesis

### Pre-Dispatch Memory Enrichment

Before each research agent dispatch, call `search_memory` with query: `"{agent role} {user query}"`, limit=5, brief=true. Inject non-empty results as `## Relevant Engineering Memory` in the dispatch prompt. After each dispatch, scan output for entry name matches and call `record_influence` for matches.

### Output Format

```markdown
## Research Summary: {query}

### Executive Summary
{2-3 sentence overview}
Confidence: {high|medium|low}

### Key Findings
#### {Theme 1}
- {Finding} [source: {codebase|web|context}]
- {Finding} [source: {codebase|web|context}]

#### {Theme 2}
- ...

### Contradictions & Gaps
- {What sources disagree on or what's missing}

### Recommendations
1. {Actionable recommendation}
2. {Actionable recommendation}

### Sources
- {List of files read, URLs fetched, entities queried}
```

**Confidence calibration:**
- **High** — multiple corroborating sources, no contradictions
- **Medium** — some corroboration but gaps exist
- **Low** — limited sources, significant contradictions, or mostly assumptions

### Context Gathering (Phase 1, inline)

The third research stream runs inline (not a subagent) and always gathers:
- Current feature context from `.meta.json` (if on a feature branch)
- Entity registry state via `search_entities` MCP (query derived from user's topic)
- Recent git history: `git log --oneline -10`
- Active brainstorm titles and open backlog item descriptions

All context is passed to the synthesizer; the synthesizer filters for relevance.

### Failure Handling

| Scenario | Behavior |
|----------|----------|
| 1 of 2 research agents fails | Proceed with available findings; synthesizer notes the gap |
| Both research agents fail | Abort with: "Research failed — both agents returned errors. Try rephrasing or check network." |
| Synthesizer fails | Output raw findings without thematic grouping (fallback: bullet list per source) |
| Inline context gathering fails | Proceed without context; note "Work context unavailable" |

## Scope

### In Scope
- Command file (`subagent-ras.md`)
- Skill file (`researching/SKILL.md`)
- New agent (`ras-synthesizer.md`)
- Parallel dispatch of 2 research agents + inline context gathering
- Structured markdown output with post-output save prompt
- Graceful degradation on partial agent failures
- Documentation sync: README.md, README_FOR_DEV.md, plugins/pd/README.md component counts

### Out of Scope
- Interactive follow-up questions (one-shot query → summary)
- Custom agent selection (fixed 3-source pipeline)
- Integration with feature workflow phases (standalone utility)
- Refactoring design Step 0 to delegate to the researching skill (future improvement)

## Success Criteria

1. User can run `/pd:subagent-ras {query}` and receive a structured summary
2. Research agents dispatch in parallel (not sequentially)
3. Summary includes findings from available sources; notes which sources failed
4. Findings are grouped by theme, not by source
5. Contradictions between sources are explicitly called out
6. Output is concise: target 30-50 lines, readable in <2 minutes

## Technical Notes

- Reuses existing `pd:codebase-explorer` and `pd:internet-researcher` agents — no changes
- The `ras-synthesizer` is the only new agent; opus for cross-source reasoning
- Respects `max_concurrent_agents` budget (2 parallel agents + 1 inline = within default 5)
- No tests needed — all components are LLM-interpreted markdown templates
