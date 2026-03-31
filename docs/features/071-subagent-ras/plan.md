# Plan: pd:subagent-ras — Research, Analyze, Summarize

## Overview

3 new markdown files (command, skill, agent) + documentation sync. No Python code, no tests. All changes are LLM-interpreted procedural templates.

## Execution Order

```
Task 1: Create ras-synthesizer agent
  ↓
Task 2: Create researching skill (depends on agent existing)
  ↓
Task 3: Create subagent-ras command (depends on skill existing)
  ↓
Task 4: Documentation sync (README.md, README_FOR_DEV.md, plugins/pd/README.md)
```

Sequential — each component references the previous.

## Tasks

### Task 1: Create ras-synthesizer agent

**File:** `plugins/pd/agents/ras-synthesizer.md`

**Content:**
- Frontmatter: name (ras-synthesizer), description, model (opus), tools ([Read]), color (cyan)
- 2 example blocks showing typical usage
- Agent body: role description, input format (Original Query + Codebase Findings + External Research + Work Context), synthesis instructions (group by theme, flag contradictions, calibrate confidence), return JSON schema with required fields (executive_summary, confidence, themes[], contradictions[], gaps[], recommendations[], sources[])
- Confidence calibration guidance: high/medium/low definitions
- Length constraint: "Produce output that renders to approximately 30-50 lines of markdown"

**Done when:** File exists with valid frontmatter (name, description, model: opus, tools: [Read], color: cyan) and JSON return schema block.

### Task 2: Create researching skill

**File:** `plugins/pd/skills/researching/SKILL.md`

**Content:**
- Frontmatter: name (researching), description
- Three-phase pipeline orchestration:

**Phase 1: RESEARCH**
- Memory enrichment: call search_memory before each dispatch
- Dispatch pd:codebase-explorer (model: sonnet) with code-pattern-focused query reformulation. Include expanded JSON return schema in prompt.
- Dispatch pd:internet-researcher (model: sonnet) with best-practices-focused query reformulation. Include expanded JSON return schema in prompt.
- Both dispatches in same message (parallel)
- Inline context gathering: git branch check, .meta.json read, search_entities MCP, git log, backlog.md open items, brainstorm titles
- Post-dispatch influence tracking: scan for memory entry names, call record_influence if matched (feature_type_id from .meta.json if on feature branch, else skip)
- Failure detection: agent error/malformed JSON = failure; empty findings with no_findings_reason = success (not failure)

**Phase 2: ANALYZE**
- Memory enrichment for synthesizer dispatch
- Dispatch pd:ras-synthesizer (model: opus) with original query + all Phase 1 findings
- Schema validation: if response missing executive_summary/confidence/themes → synthesizer failure → fallback
- Post-dispatch influence tracking

**Phase 3: SUMMARIZE**
- JSON-to-markdown rendering: all R3 section headers in order (on successful synthesis)
- Fallback rendering if synthesizer failed: raw bullets by source with different headers
- Empty sections show "None" note
- AskUserQuestion: Save / Dismiss
  - Save: derive slug (first 5 words, lowercase, strip non-[a-z0-9-], join hyphens, collapse doubles, max 50 chars), write to agent_sandbox/{YYYY-MM-DD}/ras-{slug}.md

**Failure handling table:** 1-of-2 agents fail → proceed with note; both fail → abort; synthesizer fail → fallback; context fail → proceed without

**Token budget:** Must stay under 500 lines per CLAUDE.md constraint. Use concise prose, reference agent files for details rather than duplicating.

**Pre-implementation check:** Read codebase-explorer.md and internet-researcher.md to confirm return JSON schema matches `{findings[], no_findings_reason}` before writing dispatch prompts.

**MCP tool unavailability:** Treat search_memory, record_influence, and search_entities unavailability the same as "no results" — proceed without memory enrichment or entity context. Consistent with R5 inline-context-failure handling.

**Internal checkpoints:** (1) Write Phase 1: dispatch prompts + context gathering, (2) Write Phase 2: synthesizer dispatch + schema validation, (3) Write Phase 3: rendering + fallback + save prompt.

**Done when:** File under 500 lines. Contains `## Phase 1`, `## Phase 2`, `## Phase 3` headers. Each Task dispatch includes `model:` field. Failure handling table has 4 rows matching R5. Fallback rendering section present. AskUserQuestion prompt with Save/Dismiss options present.

### Task 3: Create subagent-ras command

**File:** `plugins/pd/commands/subagent-ras.md`

**Content:**
- Frontmatter: description ("Research, analyze, and summarize any topic using parallel agents"), argument-hint ("<query>")
- Body: validate argument present (if missing → usage message), invoke researching skill with the query argument
- Thin wrapper — all logic in the skill

**Done when:** File exists with valid frontmatter and skill invocation. Under 30 lines.

### Task 4: Documentation sync

**Files:**
- `README.md` — add subagent-ras to command table
- `README_FOR_DEV.md` — add ras-synthesizer to agent table, researching to skill table
- `plugins/pd/README.md` — increment component counts (commands +1, skills +1, agents +1)

**Done when:** All three files updated with correct entries and counts. `validate.sh` passes.

## Verification

After all tasks:
1. `validate.sh` passes with 0 errors
2. Read each new file and confirm frontmatter is valid
3. Grep for `ras-synthesizer` in skill file — confirms agent reference
4. Grep for `researching` in command file — confirms skill reference
5. Run `/pd:subagent-ras what patterns exist for agent dispatch` and confirm all R3 section headers appear in output (per spec verification checklist)
