# Design: pd:subagent-ras — Research, Analyze, Summarize

## Prior Art Research

### Codebase Patterns
- **design.md Step 0**: Dispatches 2 parallel agents (codebase-explorer + internet-researcher), aggregates results, presents via AskUserQuestion. Identical dispatch pattern to reuse.
- **Agent return schemas**: Both codebase-explorer and internet-researcher return `{findings: [{finding, source, relevance}], no_findings_reason}` — consistent schema enables unified result merging.
- **Command frontmatter**: `description` + optional `argument-hint` between `---` delimiters.
- **Skill frontmatter**: `name` + `description` between `---` delimiters.
- **Agent frontmatter**: `name`, `description`, `model`, `tools` (array), `color` between `---` delimiters.

### External Patterns
- **Deep research agents**: Universal 4-stage pipeline (Plan → Execute parallel → Synthesize → Report)
- **Decision-support output**: Findings grouped by theme not source, contradictions explicit, recommendations separated from findings
- **Multi-pass synthesis**: Self-critique pass after initial synthesis to catch gaps

## Architecture Overview

### Component Structure

Three new files, no Python code:

1. **Command:** `plugins/pd/commands/subagent-ras.md` — entry point, delegates to skill
2. **Skill:** `plugins/pd/skills/researching/SKILL.md` — 3-phase pipeline orchestration
3. **Agent:** `plugins/pd/agents/ras-synthesizer.md` — thematic synthesis from multi-source findings

### Data Flow

```
/pd:subagent-ras {query}
  → Command validates argument, delegates to researching skill
  → Skill Phase 1: RESEARCH (parallel)
      ├─ Task: pd:codebase-explorer (sonnet) → {findings[], no_findings_reason}
      ├─ Task: pd:internet-researcher (sonnet) → {findings[], no_findings_reason}
      └─ Inline: context gathering → {context_text}
  → Skill Phase 2: ANALYZE
      └─ Task: pd:ras-synthesizer (opus) → {executive_summary, confidence, themes[], contradictions[], gaps[], recommendations[], sources[]}
  → Skill Phase 3: SUMMARIZE
      └─ Render JSON → markdown output
      └─ AskUserQuestion: Save / Dismiss
```

### Technical Decisions

**TD-1: Skill separation from command**

Decision: The `researching` skill contains all pipeline logic. The command is a thin wrapper (argument validation + skill invocation).

Rationale: Keeps the command file small. The skill is reusable if other commands need research capabilities in the future.

**TD-2: Synthesizer at opus tier**

Decision: `ras-synthesizer` uses opus.

Rationale: The synthesis task requires cross-source reasoning — identifying which findings from different agents corroborate or contradict each other, grouping by theme, and producing calibrated confidence. This is the highest-reasoning-demand step. The research agents (sonnet) do retrieval; the synthesizer does analysis.

**TD-3: JSON-to-markdown rendering in skill, not agent**

Decision: The skill converts the synthesizer's JSON to the output markdown format.

Rationale: The synthesizer returns structured JSON for reliability. Rendering is deterministic formatting logic that belongs in the orchestrator, not the agent. If the synthesizer also rendered markdown, errors in formatting would be mixed with errors in analysis.

**TD-4: Inline context gathering, not a third agent**

Decision: Context gathering (feature state, entity registry, git log, backlog/brainstorms) runs inline in the skill.

Rationale: These are lightweight MCP calls and filesystem reads — no web search, no deep analysis. Spawning an agent for this would add latency and token cost for trivial data gathering. The synthesizer receives all context and filters for relevance.

## Interfaces

### Command File

```yaml
---
description: Research, analyze, and summarize any topic using parallel agents
argument-hint: <query>
---
```

Body: Validate argument present. If missing, output usage. Otherwise invoke `researching` skill with query.

### Skill Interface

The `researching` skill accepts a single argument: the user's query string.

It orchestrates three phases and returns the rendered markdown summary to the command for output.

### ras-synthesizer Agent

```yaml
---
name: ras-synthesizer
description: Synthesizes multi-source research findings into thematic analysis with confidence calibration. Use when merging codebase patterns, external research, and work context into a decision-ready summary.
model: opus
tools: [Read]
color: cyan
---
```

**Input prompt structure:**
```
Synthesize these research findings into a thematic analysis.

## Original Query
{user's raw query}

## Codebase Findings
{codebase-explorer JSON output or "Agent unavailable — no codebase findings"}

## External Research
{internet-researcher JSON output or "Agent unavailable — no external findings"}

## Work Context
{inline context text or "Work context unavailable"}

## Instructions
- Group findings by THEME (not by source)
- Identify contradictions between sources
- Note gaps where information is missing
- Produce actionable recommendations
- Calibrate confidence: high (corroborating, no contradictions), medium (gaps exist), low (limited/contradictory)
- Target: output that renders to 30-50 lines of markdown

Return JSON:
{
  "executive_summary": "2-3 sentences",
  "confidence": "high|medium|low",
  "themes": [{"name": "Theme Name", "findings": [{"text": "...", "source": "codebase|web|context"}]}],
  "contradictions": ["..."],
  "gaps": ["..."],
  "recommendations": ["..."],
  "sources": ["file paths, URLs, entity queries"]
}
```

**Return schema validation:** If the response is not valid JSON or missing required fields (executive_summary, confidence, themes), treat as synthesizer failure → activate R5 fallback.

### Memory Enrichment Pattern

Applied to every Task dispatch (codebase-explorer, internet-researcher, ras-synthesizer):

1. **Pre-dispatch:** Call `search_memory(query="{agent role} {user query}", limit=5, brief=true)`. Store returned entry names. If results non-empty, append `## Relevant Engineering Memory\n{results}` to the dispatch prompt.
2. **Post-dispatch:** For each stored entry name, if it appears as a case-insensitive exact substring in the agent's output, call `record_influence(entry_name=<name>, agent_role="{agent-name}", feature_type_id=<from .meta.json if on feature branch, else skip>)`.

### Failure Detection

| Condition | Classification |
|-----------|---------------|
| Task tool returns error/exception | Agent failure |
| Output is not parseable as expected JSON schema | Agent failure |
| Valid JSON with empty `findings[]` and non-null `no_findings_reason` | Successful result (no findings) — NOT a failure |
| Synthesizer returns JSON missing required fields (executive_summary, confidence, themes) | Synthesizer failure → fallback |

### Phase 1 Dispatch Prompts

Both Task dispatches are issued in the same message (parallel). The skill waits for both results before proceeding to Phase 2. Inline context gathering runs in the same message and is available immediately.

Note: The return format instructions in dispatch prompts reinforce the agents' built-in schemas. If agents change their return format, the skill's parsing would need updating.

**codebase-explorer:**
```
Find existing code, patterns, and conventions related to: {query}

Look for:
- Similar implementations
- Reusable components
- Established conventions
- Related utilities

Return JSON: {"findings": [{"finding": "...", "source": "file/path:line", "relevance": "high|medium|low"}], "no_findings_reason": null}

## Relevant Engineering Memory
{search_memory results, if non-empty}
```

**internet-researcher:**
```
Research industry approaches, libraries, and best practices for: {query}

Look for:
- Industry standard approaches
- Library support
- Common patterns
- Best practices

Return JSON: {"findings": [{"finding": "...", "source": "URL", "relevance": "high|medium|low"}], "no_findings_reason": null}

## Relevant Engineering Memory
{search_memory results, if non-empty}
```

### Inline Context Gathering

Executed inline in the skill (not a subagent):

```
1. Git branch check: `git branch --show-current`
   - If on feature/* branch: read .meta.json for feature context
2. Entity search: search_entities(query="{keywords from user query}")
   - Extract top 3 results as context
3. Git history: `git log --oneline -10`
4. Backlog: read docs/backlog.md, extract open items (not marked closed/promoted)
5. Brainstorms: Glob docs/brainstorms/*.prd.md, extract first heading from each

Assemble into a text block:
"Current branch: {branch}
Feature context: {.meta.json summary or 'not on feature branch'}
Related entities: {entity search results or 'none found'}
Recent commits: {git log}
Open backlog: {item descriptions}
Active brainstorms: {titles}"
```

### Output Rendering (Phase 3)

The skill converts synthesizer JSON to markdown:

1. `## Research Summary: {query}` header
2. `### Executive Summary` with executive_summary text + `Confidence: {confidence}`
3. `### Key Findings` with one `#### {theme.name}` subsection per theme, each finding as a bullet with `[source: {source}]`
4. `### Contradictions & Gaps` — contradictions + gaps merged as bullets. If both empty: "No contradictions or gaps identified."
5. `### Recommendations` — numbered list
6. `### Sources` — deduplicated list from sources[]

All section headers always present (per spec R3). Empty sections show a "None" note.

### Fallback Rendering (Synthesizer Failure)

If synthesizer fails or returns invalid JSON, the spec's mandatory section headers (R3) are exempted — fallback is degraded by definition. Render raw findings grouped by source:

```markdown
## Research Summary: {query}

Note: Thematic synthesis unavailable. Raw findings shown by source.

### Codebase Findings
- {bullet per finding from codebase-explorer, or "No codebase findings available"}

### External Research
- {bullet per finding from internet-researcher, or "No external findings available"}

### Work Context
{inline context text, or "Work context unavailable"}

### Sources
- {deduplicated source list}
```

### Slug Derivation (for save path)

When saving: `agent_sandbox/{YYYY-MM-DD}/ras-{slug}.md`

Algorithm: (1) take first 5 words of query (split on whitespace), (2) lowercase, (3) strip characters not in a-z, 0-9, or hyphen, (4) join with hyphens, (5) collapse consecutive hyphens, (6) truncate to 50 characters.

### Documentation Updates

When implemented, update:
- `README.md` — add subagent-ras to command table
- `README_FOR_DEV.md` — add ras-synthesizer to agent table, researching to skill table
- `plugins/pd/README.md` — increment component counts (commands +1, skills +1, agents +1)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Synthesizer returns malformed JSON | Low | Medium | Fallback rendering from raw findings |
| Both research agents fail | Low | High | Abort with clear error message |
| Query too vague for useful results | Medium | Low | Synthesizer notes low confidence; user can rephrase |
| Output exceeds 50-line target | Medium | Low | Synthesizer prompt includes length constraint; worst case is verbose but correct |

## Dependencies

- No external dependencies
- No new Python code, MCP tools, or hooks
- Reuses existing agents: pd:codebase-explorer, pd:internet-researcher
- Reuses existing MCP tools: search_entities, search_memory, record_influence
