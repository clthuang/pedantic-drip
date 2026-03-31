# Spec: pd:subagent-ras — Research, Analyze, Summarize

## Problem

No single command gathers multi-source intelligence (internal codebase + external web + current work state), analyzes it thematically, and delivers a concise decision-ready summary. Users must manually dispatch individual agents and mentally synthesize results.

## Requirements

### R1: Command Interface

The command `pd:subagent-ras` accepts a free-text query as its argument:
```
/pd:subagent-ras {query}
```

If no argument provided, display usage: `"Usage: /pd:subagent-ras <query>"`

The command delegates to the `researching` skill for pipeline orchestration.

### R2: Three-Phase Pipeline

The `researching` skill executes three sequential phases:

**Phase 1: RESEARCH** (parallel)
- Dispatch `pd:codebase-explorer` (model: sonnet) with a code-pattern-focused reformulation of the query
- Dispatch `pd:internet-researcher` (model: sonnet) with a best-practices-focused reformulation of the query
- Inline context gathering (not a subagent): current feature `.meta.json` (if on feature branch), entity registry via `search_entities` MCP (query derived from user topic), `git log --oneline -10`, backlog items from `docs/backlog.md` (items not marked closed/promoted), brainstorm titles from `docs/brainstorms/*.prd.md` first headings

Both agent Task dispatches are issued in the same message (parallel). Each dispatch MUST include `model:` matching agent frontmatter. Inline context gathering runs concurrently.

**Pre-dispatch memory enrichment:** Before each agent dispatch, call `search_memory` with `"{agent role} {user query}"`, limit=5, brief=true. Inject non-empty results as `## Relevant Engineering Memory` in the dispatch prompt. Post-dispatch: for each entry name returned, if it appears as a case-insensitive exact substring in the agent's output, call `record_influence(entry_name=<name>, agent_role="{agent-name}", feature_type_id=<current feature type_id from .meta.json if on a feature branch, otherwise skip record_influence>)`.

**Phase 2: ANALYZE** (sequential, after Phase 1 completes)
- Dispatch `pd:ras-synthesizer` (model: opus) with:
  - Original user query
  - All raw findings from Phase 1 (codebase, web, context)
  - Instruction to merge thematically, flag contradictions, identify gaps, produce recommendations
  - Length constraint: "Produce output that renders to approximately 30-50 lines of markdown"
  - Confidence calibration: high = multiple corroborating sources with no contradictions; medium = some corroboration but gaps; low = limited sources, significant contradictions, or mostly assumptions
- The synthesizer returns structured JSON:
  ```json
  {
    "executive_summary": "string",
    "confidence": "high|medium|low",
    "themes": [{"name": "string", "findings": [{"text": "string", "source": "codebase|web|context"}]}],
    "contradictions": ["string"],
    "gaps": ["string"],
    "recommendations": ["string"],
    "sources": ["string"]
  }
  ```
- If the synthesizer returns malformed or schema-invalid JSON: treat as synthesizer failure and activate fallback (R5).

**Phase 3: SUMMARIZE** (sequential, after Phase 2 completes)
- The skill renders the synthesizer's JSON into the output format (see R3)
- Outputs the rendered summary inline to the user
- Prompts via AskUserQuestion: "Save this summary?" with options Save / Dismiss
  - Save: writes to `agent_sandbox/{YYYY-MM-DD}/ras-{slug}.md`
  - Dismiss: no persistence

**Slug derivation:** (1) Take first 5 words (split on whitespace), (2) lowercase, (3) strip characters that are not a-z, 0-9, or hyphen, (4) join words with hyphens, (5) truncate to 50 characters. Example: "compare event sourcing vs CQRS" → `compare-event-sourcing-vs-cqrs`.

### R3: Output Format

```markdown
## Research Summary: {query}

### Executive Summary
{2-3 sentences}
Confidence: {high|medium|low}

### Key Findings
#### {Theme name}
- {Finding} [source: {codebase|web|context}]

### Contradictions & Gaps
- {Description}

### Recommendations
1. {Actionable recommendation}

### Sources
- {file paths, URLs, entity queries}
```

All section headers (## Research Summary, ### Executive Summary, ### Key Findings, ### Contradictions & Gaps, ### Recommendations, ### Sources) must be present in order on successful synthesis. Sections may be empty if no relevant content (e.g., "No contradictions found."). In fallback mode (synthesizer failure), a different header set applies — see R5.

### R4: Query Reformulation

The skill reformulates the user's raw query into agent-specific prompts:
- **codebase-explorer**: `"Find existing code, patterns, and conventions related to: {query}"`
- **internet-researcher**: `"Research industry approaches, libraries, and best practices for: {query}"`
- **ras-synthesizer**: receives the original query verbatim plus all raw findings

### R5: Failure Handling

| Scenario | Behavior |
|----------|----------|
| 1 of 2 research agents fails | Proceed; Contradictions & Gaps section includes: "[source: {failed_agent}] — agent unavailable, findings from this source are missing." |
| Both research agents fail | Abort: "Research failed — both agents returned errors. Try rephrasing or check network." |
| Synthesizer fails or returns malformed JSON | Fallback: output raw findings as bullet list per source (no thematic grouping) |
| Inline context gathering fails | Proceed without context; note "Work context unavailable" in output |

### R6: New Components

**Command:** `plugins/pd/commands/subagent-ras.md`
- Frontmatter: description, argument-hint
- Delegates to `researching` skill
- Handles save prompt after output

**Skill:** `plugins/pd/skills/researching/SKILL.md`
- Orchestrates the 3-phase pipeline
- Query reformulation, parallel dispatch, result aggregation, JSON-to-markdown rendering
- Token budget: <500 lines per CLAUDE.md constraint

**Agent:** `plugins/pd/agents/ras-synthesizer.md`
- Model: opus
- Tools: [Read]
- Returns structured JSON (schema in R2)
- Prompt includes confidence calibration guidance and 30-50 line output target

## Acceptance Criteria

- **AC-1**: Given a query, when the command completes, then the output contains all section headers (## Research Summary, ### Executive Summary, ### Key Findings, ### Contradictions & Gaps, ### Recommendations, ### Sources) in order
- **AC-2**: Given a query, when Phase 1 executes, then both Task tool calls are issued in the same message (parallel dispatch)
- **AC-3**: Findings in Key Findings are grouped by theme name, not by source type
- **AC-4**: Contradictions between sources appear in the Contradictions & Gaps section
- **AC-5**: Given one research agent fails, then the summary renders with available findings and Contradictions & Gaps includes a note about the missing source
- **AC-6**: Given both research agents fail, then the command outputs the abort error message and stops
- **AC-7**: Given the synthesizer fails or returns malformed JSON, then raw findings render as a bullet list per source
- **AC-8**: After output, a save AskUserQuestion prompt appears; selecting Save writes to `agent_sandbox/{date}/ras-{slug}.md`
- **AC-9**: Three new files created: `plugins/pd/commands/subagent-ras.md`, `plugins/pd/skills/researching/SKILL.md`, `plugins/pd/agents/ras-synthesizer.md`
- **AC-10**: Documentation updated: README.md, README_FOR_DEV.md, plugins/pd/README.md component counts

**Verification checklist (manual):**
1. Run with a general query — verify all output section headers present
2. Run with a codebase-specific query — verify codebase findings appear under themes
3. Verify save prompt appears and saving creates the file at the expected path
4. Run with no argument — verify usage message displayed
