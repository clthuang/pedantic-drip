# Tasks: pd:subagent-ras — Research, Analyze, Summarize

## Phase 1: Agent (sequential)

### Task 1.1: Create ras-synthesizer agent file
- **File:** `plugins/pd/agents/ras-synthesizer.md`
- **Action:** Create new agent file with:
  - Frontmatter: `name: ras-synthesizer`, `description: Synthesizes multi-source research findings into thematic analysis with confidence calibration`, `model: opus`, `tools: [Read]`, `color: cyan`
  - 2 example blocks (one for general research, one for codebase-specific query)
  - Agent body: role description (cross-source synthesis), input format (Original Query + Codebase Findings + External Research + Work Context sections), synthesis instructions (group by theme, flag contradictions, calibrate confidence), return JSON schema with required fields (`executive_summary`, `confidence`, `themes[]`, `contradictions[]`, `gaps[]`, `recommendations[]`, `sources[]`)
  - Confidence calibration: high = corroborating + no contradictions, medium = gaps exist, low = limited/contradictory
  - Length instruction: "Produce output that renders to approximately 30-50 lines of markdown"
- **Done when:** File exists; frontmatter has all 5 fields (name, description, model: opus, tools: [Read], color: cyan); JSON return schema block present with all 7 required fields
- **Depends on:** nothing

## Phase 2: Skill (sequential, depends on Phase 1)

### Task 2.1: Verify reused agent return schemas
- **Action:** Read `plugins/pd/agents/codebase-explorer.md` and `plugins/pd/agents/internet-researcher.md`. Confirm both return `{findings: [{finding, source, relevance}], no_findings_reason}`. Note any discrepancies.
- **Done when:** Both schemas confirmed matching expected format, or discrepancies documented
- **Depends on:** nothing (can run parallel with 1.1 but logically gates 2.2)

### Task 2.2: Create researching skill — Phase 1 (Research)
- **File:** `plugins/pd/skills/researching/SKILL.md`
- **Action:** Create skill file with frontmatter (`name: researching`, `description: Orchestrates parallel research, analysis, and synthesis into decision-ready summaries`). Write Phase 1 section:
  - Pre-dispatch memory enrichment for each agent (search_memory call + injection)
  - codebase-explorer dispatch prompt with expanded JSON return schema and `model: sonnet`
  - internet-researcher dispatch prompt with expanded JSON return schema and `model: sonnet`
  - Both dispatches in same message (parallel)
  - Inline context gathering: git branch check, .meta.json read, search_entities MCP, git log, backlog.md open items, brainstorm titles
  - Post-dispatch influence tracking (case-insensitive exact substring, record_influence with runtime feature_type_id)
  - Failure detection table: agent error/malformed JSON = failure; empty findings with no_findings_reason = success
  - MCP unavailability: treat as "no results", proceed
- **Done when:** File exists with valid frontmatter; `## Phase 1` header present; two Task dispatch blocks with `model:` fields; inline context gathering steps listed; failure detection defined
- **Depends on:** 1.1, 2.1

### Task 2.3: Add Phase 2 (Analyze) to researching skill
- **File:** `plugins/pd/skills/researching/SKILL.md`
- **Action:** Append Phase 2 section:
  - Pre-dispatch memory enrichment for ras-synthesizer
  - Dispatch `pd:ras-synthesizer` (model: opus) with original query + all Phase 1 findings
  - Schema validation: if response not valid JSON or missing required fields (executive_summary, confidence, themes) → synthesizer failure → fallback
  - Post-dispatch influence tracking
- **Done when:** `## Phase 2` header present; Task dispatch with `model: opus`; schema validation logic present
- **Depends on:** 2.2

### Task 2.4: Add Phase 3 (Summarize) to researching skill
- **File:** `plugins/pd/skills/researching/SKILL.md`
- **Action:** Append Phase 3 section:
  - JSON-to-markdown rendering: all R3 section headers in order (## Research Summary, ### Executive Summary, ### Key Findings, ### Contradictions & Gaps, ### Recommendations, ### Sources)
  - Empty sections show "None" note
  - Fallback rendering (synthesizer failure): different header set (### Codebase Findings, ### External Research, ### Work Context, ### Sources) with note "Thematic synthesis unavailable"
  - AskUserQuestion: Save / Dismiss
  - Slug derivation: (1) first 5 words, (2) lowercase, (3) strip non-[a-z0-9-], (4) join hyphens, (5) collapse consecutive hyphens, (6) max 50 chars
  - Save path: `agent_sandbox/{YYYY-MM-DD}/ras-{slug}.md`
- **Done when:** `## Phase 3` header present; both normal and fallback rendering templates present; AskUserQuestion with Save/Dismiss; slug derivation algorithm specified
- **Depends on:** 2.3

### Task 2.5: Verify skill token budget
- **Action:** Count lines in `plugins/pd/skills/researching/SKILL.md`. Must be under 500 lines per CLAUDE.md constraint. If over, trim verbose sections (reference agent file for details instead of duplicating).
- **Done when:** Skill file under 500 lines
- **Depends on:** 2.4

## Phase 3: Command (sequential, depends on Phase 2)

### Task 3.1: Create subagent-ras command file
- **File:** `plugins/pd/commands/subagent-ras.md`
- **Action:** Create thin command wrapper with:
  - Frontmatter: `description: Research, analyze, and summarize any topic using parallel agents`, `argument-hint: <query>`
  - Body: if no argument → output usage message; else invoke `researching` skill with query
- **Done when:** File exists under 30 lines; frontmatter has description + argument-hint; skill invocation present
- **Depends on:** 2.5

## Phase 4: Documentation (depends on Phase 3)

### Task 4.1: Update documentation
- **Pre-step:** Read `README.md`, `README_FOR_DEV.md`, and `plugins/pd/README.md` to confirm table formats.
- **Files:** `README.md`, `README_FOR_DEV.md`, `plugins/pd/README.md`
- **Action:**
  - `README.md`: add `subagent-ras` to command table
  - `README_FOR_DEV.md`: add `ras-synthesizer` to agent table, `researching` to skill table
  - `plugins/pd/README.md`: increment component counts (commands +1, skills +1, agents +1), add entries to tables
- **Done when:** All three files updated; `validate.sh` passes with 0 errors
- **Depends on:** 3.1

## Phase 5: Verification

### Task 5.1: Run verification checklist
- **Action:**
  1. `validate.sh` passes with 0 errors
  2. Read each new file — confirm frontmatter valid
  3. Grep for `ras-synthesizer` in skill file — confirms agent reference
  4. Grep for `researching` in command file — confirms skill reference
  5. Smoke test: run `/pd:subagent-ras what patterns exist for agent dispatch` and confirm R3 section headers appear
- **Done when:** All 5 checks pass
- **Depends on:** 4.1
