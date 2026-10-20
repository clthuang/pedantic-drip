# Design: Context and Review Hardening

## Prior Art Research

### Codebase Patterns (from codebase-explorer)

1. **No per-task dispatch loop** — implementing SKILL.md dispatches subagents by domain, not per-task. Task Selection (lines 95-103) finds first incomplete task but no explicit iteration. The skill dispatches in bulk.
2. **Full artifact loading everywhere** — implement.md loads ALL artifacts (prd, spec, design, plan, tasks) into every reviewer and fix-iteration prompt. No selective loading.
3. **Implementer report is free-text** — Report Format: "What you implemented, What you tested, Files changed, Self-review findings, Any issues or concerns". No structured JSON, no decisions/deviations fields.
4. **.review-history.md lifecycle** — append during review iterations → read during retro Step 1b → committed via commitAndComplete → deleted during finish Phase 6b. This is the model for implementation-log.md.
5. **workflow-transitions Step 5** — already loads project PRD, roadmap, dependency features at phase startup. Same sources needed for task-level injection.
6. **External tools split** — spec-reviewer and design-reviewer have WebSearch + Context7 with verification instructions. All other reviewers (security, implementation, code-quality, task, phase) only have Read/Glob/Grep.
7. **Phase-reviewer receives no domain reviewer signal** — prompt contains only artifact content and "next phase expectations". No iteration count, no approval status, no unresolved issues from domain reviewer.
8. **Knowledge bank: append-only, no validation** — retro Step 4 appends entries but never reads existing entries for validation, deduplication, or staleness checking.
9. **hooks.json: all 4 SessionStart matchers include `compact`** — `startup|resume|clear|compact` on all entries. yolo-guard uses `.*` wildcard with fast-path bash substring check.

### External Research (from internet-researcher)

1. **Anthropic context engineering** — Four strategies: Write, Select, Compress, Isolate. "Find the smallest set of high-signal tokens." Sub-agents should return condensed summaries, not raw data.
2. **Google ADK** — "On-demand artifact expansion": agents maintain artifacts as named references, sub-agents receive only their necessary slice via configurable handoff parameters.
3. **JetBrains Research** — Observation masking outperforms LLM summarization: 2.6% higher solve rates, 52% cheaper. Simpler beats sophisticated.
4. **Aider** — Tree-sitter repository map with PageRank-like ranking. Default 1k token budget, dynamically adjusted. Per-task context scoping via fresh optimized repo map.
5. **Architecture Decision Records (ADRs)** — Standard pattern: Context + Decision + Status + Consequences. MADR variant stores decisions as markdown alongside code. Directly applicable to implementation-log.md.
6. **Knowledge freshness automation** — 5-stage lifecycle: Detection → Flagging → Review → Update/Archive → Cleanup. Quarantine staging before deletion. Temporal markers + engagement metrics for staleness.
7. **Azure multi-agent patterns** — Maker-Checker loop: one agent creates, another validates against criteria, with iteration caps and fallback. Matches our review pipeline exactly.
8. **Context rot** — As token count increases, model ability to recall accurately decreases. Three failure modes: poisoning, distraction, confusion. Validates aggressive context scoping.

---

## Architecture Overview

This feature makes 7 changes across 3 areas (implementation context, review pipeline, context window) by modifying 14 existing files. No new infrastructure, no new file types beyond implementation-log.md (which follows the .review-history.md lifecycle exactly).

```
┌─────────────────────────────────────────────────────────────────┐
│                    IMPLEMENTING SKILL                            │
│  (Changes 1-3: per-task loop, selective context, project ctx)   │
│                                                                 │
│  for each task in tasks.md:                                     │
│    1. Parse Why/Source → extract design/plan refs               │
│    2. Load scoped sections (or full fallback)                   │
│    3. Load project context (if project-linked)                  │
│    4. Dispatch implementer agent with task-specific prompt      │
│    5. Collect report → append to implementation-log.md          │
│    6. Proceed to next task                                      │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Task 1 ctx  │  │  Task 2 ctx  │  │  Task N ctx  │         │
│  │  (scoped)    │→ │  (scoped)    │→ │  (scoped)    │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         ↓                  ↓                  ↓                 │
│    implementer        implementer        implementer            │
│    agent              agent              agent                  │
│         ↓                  ↓                  ↓                 │
│    impl-log.md        impl-log.md        impl-log.md           │
│    (append)           (append)           (append)              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              REVIEW PIPELINE (Changes 4-6)                       │
│                                                                 │
│  Phase commands (specify, design, create-plan, create-tasks):   │
│    Stage 1: domain reviewer → [outcome captured]                │
│    Stage 2: phase-reviewer ← [Domain Reviewer Outcome block]   │
│                                                                 │
│  Post-planning reviewers (security, implementation):            │
│    + WebSearch, Context7 tools                                  │
│    + "MUST verify at least 1 claim if present"                  │
│                                                                 │
│  Retro skill:                                                   │
│    + Read implementation-log.md (Step 1c)                       │
│    + Validate knowledge bank entries (new sub-step in Step 4)   │
│    + Flag stale entries (10+ features without re-observation)   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              CONTEXT WINDOW (Change 7)                           │
│                                                                 │
│  hooks.json SessionStart matchers:                              │
│    Before: startup|resume|clear|compact                         │
│    After:  startup|resume|clear                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### Component 1: Per-Task Dispatch Loop (implementing SKILL.md)

**Responsibility:** Replace the current bulk-dispatch approach with an explicit per-task iteration that constructs distinct Task tool calls to the implementer agent.

**Current behavior (implementing SKILL.md):**
- Phase 1: "Deploy Implementation Subagents" — dispatches by domain, not per-task
- Task Selection: finds first incomplete task, reads details
- Phases 2-4: Interface → RED-GREEN → REFACTOR (executed by subagent)

**New behavior:**
```
1. Read tasks.md, extract all task headings (### or #### Task N.N: Title)
2. For each task (in document order, top to bottom):
   a. Parse task block: title, description, Why/Source field, done criteria
   b. Prepare scoped context (Component 2)
   c. Prepare project context (Component 3, if applicable)
   d. Construct Task tool dispatch to implementer agent with:
      - Task description and done criteria
      - Scoped design/plan sections (or full fallback)
      - Full spec.md (always)
      - PRD Problem Statement + Goals (always)
      - Project context block (if project-linked)
   e. Collect implementer report
   f. Extract implementation-log entry from report (Component 4)
   g. Append entry to implementation-log.md
   h. If dispatch fails: log error, ask user retry/skip (AC-20)
   i. If report malformed: write partial log entry, proceed (AC-21)
3. After all tasks: report summary, proceed to review phase
```

**Aggregate output to implement.md Steps 5-6:**

After the per-task loop completes, the implementing skill returns to implement.md's control. The skill's aggregate output includes:
- **Files changed** (deduplicated union of all per-task filesChanged strings — since these are LLM-produced paths, deduplication is best-effort string comparison; acceptable because Steps 5-6 use the list for context, not programmatic processing)
- **Task completion summary** (N tasks completed, M skipped/blocked) — logged
- **Implementation-log.md** exists on disk — retro will read it later

implement.md Steps 5 (code simplification) and 6 (review phase) continue to work with **full artifact context** as they do today. The per-task scoping applies only to the initial task dispatch loop inside the implementing skill. Fix iterations (implement.md Step 6d) also use full artifacts, consistent with the existing pattern.

**Key design decision:** The TDD phases (Interface → RED-GREEN → REFACTOR) become the implementer agent's internal workflow per task dispatch. The implementing skill orchestrates the per-task loop; the implementer agent owns the TDD cycle within each dispatch.

**implement.md changes (minor):** implement.md Step 4 currently says "Execute the implementing skill with phased approach" and lists sub-steps (Deploy subagents, Interface Phase, RED-GREEN, REFACTOR, Return). These sub-steps are now the implementer agent's internal workflow per task — the implementing skill orchestrates the per-task loop. implement.md Step 4 should reference the updated implementing skill without duplicating its internals. The implementer agent's report format (defined in implementer.md) already covers the new decisions/deviations fields — fix-iteration dispatches (Step 6d) inherit this from the agent's system prompt, so no prompt template change is needed in implement.md's Step 6d.

**Task parsing:** Extract task blocks from tasks.md by finding lines matching `### Task N.N:` or `#### Task N.N:` (heading-based format per breaking-down-tasks template). Each block extends from its heading line through the next same-level or higher-level heading (or EOF). Within each block, look for `**Why:**` or `**Source:**` field.

**Completion tracking:** The implementing skill does not use checkbox state to determine task completion. Instead, it dispatches ALL tasks in document order. The implementer agent per-task checks whether the task's done criteria are already met (e.g., files already exist, tests already pass) and reports "already complete" if so. This matches the existing implementing SKILL.md approach (lines 95-97: "find first incomplete task" via Vibe-Kanban/TodoWrite status). For the new per-task loop, dispatching all tasks sequentially is simpler and safer than inferring completion state from external trackers.

### Component 2: Selective Context Loading (implementing SKILL.md)

**Responsibility:** Parse traceability fields and extract only referenced sections from design.md and plan.md.

**Input:** Task block's Why/Source field value (string or absent).

**Processing pipeline:**
```
1. EXTRACT field value
   - Scan task block for `**Why:**` or `**Source:**` followed by text until next `**` or line break
   - If neither found: FALLBACK (load full artifacts)

2. SPLIT references
   - Split field value on comma (`,`) to produce individual reference strings
   - Trim whitespace from each reference

3. MATCH each reference
   For each trimmed reference, apply regexes in order:
   a. Plan ref: /Plan (?:Step )?(\w+\.\w+)/i → captured group is plan identifier
   b. Design ref: /Design (?:Component )?(\w+[-\w]*)/i → captured group is design identifier
   c. Spec ref: /Spec (\w+\.\w+)/i → informational only (spec always loaded in full)
   d. No match: log warning, skip this reference

4. EXTRACT sections from artifacts
   For each plan identifier:
   a. Search all headings in plan.md for one containing the identifier as substring
   b. If no match: try prefix fallback (remove last dot-segment: "1A.1" → "1A")
   c. If still no match: log warning, load full plan.md
   d. If match found: extract from matched heading through next same-level heading (or EOF)

   For each design identifier:
   a. Search all headings in design.md for one containing the identifier as substring
   b. If no match: log warning, load full design.md
   c. If match found: extract from matched heading through next same-level heading (or EOF)

5. ASSEMBLE context
   - spec.md: always full
   - design.md: scoped sections joined, or full if any extraction failed
   - plan.md: scoped sections joined, or full if any extraction failed
   - prd.md: Problem Statement + Goals sections only (extract by heading match)
```

**Heading extraction algorithm:**
```
function extractSection(markdown, identifier):
  lines = markdown.split('\n')
  headings = []
  for i, line in enumerate(lines):
    match = line.match(/^(#{1,6})\s+(.+)/)
    if match:
      headings.append({level: match[1].length, text: match[2], lineIndex: i})

  # Find heading containing identifier as substring
  target = null
  for h in headings:
    if identifier in h.text:
      target = h
      break

  if target is null:
    return null  # caller should try prefix fallback or load full

  # Find section end: next heading at same level or higher (lower number)
  endIndex = len(lines)
  for h in headings:
    if h.lineIndex > target.lineIndex and h.level <= target.level:
      endIndex = h.lineIndex
      break

  return '\n'.join(lines[target.lineIndex:endIndex])
```

**Known non-matching formats (graceful fallback):**
- Feature 018: `Design § Component 2 § scqa-framing.md` (§ separator — regex won't match → full loading)
- Feature 020: No traceability fields at all → full loading
- Features 002-016: Pre-template, no Why/Source fields → full loading

### Component 3: Project Context Injection (implementing SKILL.md)

**Responsibility:** For project-linked features, prepend a compact strategic context block to each task dispatch.

**Trigger:** Feature `.meta.json` has `project_id` field (non-null).

**Processing:**
```
1. Check .meta.json for project_id
   - If absent/null: skip entirely (AC-10)

2. Resolve project directory
   - Glob: docs/projects/{project_id}-*/
   - If not found: log warning, skip (no project context)

3. Load project goals
   - Read project prd.md
   - Extract ## Problem Statement section (heading through next ##)
   - Extract ## Goals section (heading through next ##)
   - Summarize to 2-3 bullet points (~100 tokens)

4. Load feature dependency status
   - Read this feature's .meta.json depends_on_features list
   - For each: glob docs/features/{ref}-*/, read .meta.json status
   - Categorize: completed[], in-progress[], blocked[]
   - (~50-100 tokens per dependency)

5. Load priority signal
   - Read project roadmap.md if exists
   - Find milestone containing this feature
   - Extract milestone name and position (~50 tokens)

6. Format block (~200-500 tokens total):
   ## Project Context
   **Project:** {name} | **This feature:** {feature name}
   **Project goals:** {2-3 bullets from PRD goals}
   **Feature dependencies:** completed: X, Y | in-progress: Z
   **Priority signal:** {milestone name, or "not on roadmap"}
```

**Token budget:** ~200 base (goals + priority) + ~100 per dependency feature. Design phase decides cap at ~500 tokens for large dependency lists (per SC-7).

**Relationship to workflow-transitions Step 5:** workflow-transitions Step 5 loads project context at *phase startup* (once, into the orchestrating command's context). Component 3 loads project context at *per-task dispatch time* (once per Task tool call to the implementer agent). These are distinct injection points — Step 5's context does NOT flow into Task tool dispatches because each Task call constructs a fresh prompt. Component 3 reuses the same data sources (project prd.md, roadmap.md, dependency .meta.json files) but formats a compact ~200-500 token block specifically for the implementer agent's task-scoped context window.

**Field name verification:** Feature 021 (project-level-workflow) design.md line 94 defines: `project_id` (string/null, P-prefixed like "P001") and `depends_on_features` (array/null, `{id}-{slug}` references). These are the exact field names used above. Verified at `docs/dev_artifacts/workitems/021-project-level-workflow/design.md:482-484`.

### Component 4: Implementation Decision Log (implementer.md + implementing SKILL.md)

**Responsibility:** Record per-task implementation decisions, deviations, and concerns in a persistent file.

**Implementer agent changes (implementer.md):**
- Extend Report Format section with two new fields:
  - **Decisions:** implementation choices with rationale (or "none")
  - **Deviations:** changes from plan/design with reason (or "none")
- Agent produces these as part of its existing report step (no separate step)

**Design authority note:** The PRD and spec describe the implementer agent as appending to implementation-log.md. The design clarifies: the implementing skill (not the implementer agent) performs the file append. The implementer agent produces report fields; the skill extracts and writes to disk. This is more reliable because the implementer agent runs in a Task dispatch without guaranteed knowledge of the feature directory path.

**Implementing skill changes (implementing SKILL.md):**
- After collecting implementer report, extract the 4 fields:
  - Files changed, Decisions, Deviations, Concerns
- Append structured entry to `docs/dev_artifacts/workitems/{id}-{slug}/implementation-log.md`:
  ```markdown
  ## Task N: {task title}
  - **Files changed:** {from report}
  - **Decisions:** {from report, or "none"}
  - **Deviations:** {from report, or "none"}
  - **Concerns:** {from report, or "none"}
  ```
- If implementation-log.md doesn't exist: create it with header `# Implementation Log`
- If report missing fields: write partial entry with available fields (AC-21)

**Lifecycle (mirrors .review-history.md):**
1. **Created:** First task completion creates the file
2. **Appended:** Each subsequent task completion appends an entry
3. **Read:** Retro skill Step 1c reads full content (Component 5)
4. **Deleted:** /finish Phase 6 deletes after retro (Component 6)

### Component 5: Retro Context Enhancement (retrospecting SKILL.md)

**Responsibility:** Include implementation-log.md in retro context bundle and add knowledge bank validation.

**Step 1c addition (between Review History and Git Summary):**
```
**c. Implementation Log** — Read `implementation-log.md`:
- If file exists: capture full content
- If file doesn't exist: note "No implementation log available"
```

**Step 2 prompt update (retro-facilitator dispatch):**
Add `### Implementation Log` section to context bundle between Review History and Git Summary.

**Step 4 addition (knowledge bank validation sub-step):**

**Mechanism:** Validation is performed by the main orchestrating agent (the skill executor, not a separate agent dispatch). The retro-facilitator (Step 2) produces the AORTA analysis with new entries. After Step 4a writes new entries, the orchestrating agent performs Step 4b directly — reading knowledge bank files, comparing against feature artifacts already in context (git diff, implementation-log, review-history are all read in Step 1), and applying the validation logic below. This is LLM-judgment-based work done by the main agent, not delegated to a sub-agent.

**Cognitive load note:** By Step 4b, the retro agent has already completed the heavy analytical work (AORTA analysis in Step 2, entry writing in Step 4a). Validation is a bounded read-and-compare task over ~15 short entries against artifacts already in context. The staleness check (Step 4b.d) is purely mechanical (glob count). The confirm/challenge logic (Step 4b.c) leverages context already loaded in Step 1 — no additional file reads required. This is lighter than the AORTA analysis itself. **Escape hatch:** If the orchestrating agent's context is tight after receiving the retro-facilitator response, KB validation could be extracted to a separate agent dispatch in a future iteration. For now, the bounded nature (~15 entries) makes inline validation acceptable.

```
4b. Validate Knowledge Bank (pre-existing entries only — entries just added in Step 4a are excluded since they were derived from this feature's experience and are inherently validated)
  a. Read ALL pre-existing entries from anti-patterns.md and heuristics.md (~15 entries total; distinguish from Step 4a entries by comparing against the retro-facilitator's act.anti_patterns and act.heuristics output)
  b. For each entry, determine relevance to this feature:
     - RELEVANT if: entry's domain (file patterns, coding practices, workflow steps)
       overlaps with this feature's git diff files OR implementation-log decisions/deviations
       OR review-history issues
     - NOT RELEVANT if: entry's domain has no overlap (skip, no update)
  c. For each relevant entry, evaluate accuracy against this feature's experience:
     - CONFIRMED: This feature's experience aligns with the entry's guidance
       → Update "Last observed: Feature #{id}", increment "Observation count"
     - CONTRADICTED: This feature's experience contradicts the entry
       (e.g., entry says "X causes problems" but this feature did X successfully)
       → Append "- Challenged: Feature #{id} — {specific contradiction}"
  d. Staleness check (mechanical, not LLM-judgment):
     - For each entry, extract feature number from "Last observed: Feature #{NNN}" (always reads from "Last observed" field, not original "Source" or "Observed in" fields — "Last observed" is uniform across all entries after backfill)
     - Glob docs/features/ directories, count those with numeric ID > NNN
     - If count >= 10: flag entry with "⚠️ STALE" marker
     - Surface stale entries to user via AskUserQuestion:
       "The following entries haven't been observed in 10+ features: {list}. Keep, update, or retire?"
     - Retire: delete entry from file, note in retro.md "Retired: {name} — {reason}"
     - Keep: remove stale marker, update Last observed to current feature
     - Update: user provides new text, modify in-place, reset Observation count to 1
```

### Component 6: Implementation Log Cleanup (finish.md)

**Responsibility:** Delete implementation-log.md after retro has read it.

**Change:** Add to Phase 6b cleanup, immediately after .review-history.md deletion:
```bash
rm docs/features/{id}-{slug}/implementation-log.md 2>/dev/null || true
```

### Component 7: Domain Reviewer Outcome Block (specify.md, design.md, create-plan.md, create-tasks.md)

**Responsibility:** Signal domain reviewer results to phase-reviewer in all 4 two-stage review commands.

**Data source:** The orchestrating command already parses the domain reviewer's JSON response (`approved`, `issues[]`). It retains the iteration count. No additional reads needed.

**Block format (inserted into phase-reviewer prompt immediately before `## Next Phase Expectations`, after the last artifact section):**
```markdown
## Domain Reviewer Outcome
- Reviewer: {spec-reviewer | design-reviewer | plan-reviewer | task-reviewer}
- Result: {APPROVED at iteration {n}/{max} | FAILED at iteration cap ({max}/{max})}
- Unresolved issues: {list of remaining blocker/warning descriptions, or "none"}
```

**Full prompt template example (specify.md Stage 2):**
```
Task tool call:
  subagent_type: iflow-dev:phase-reviewer
  prompt: |
    Validate this spec is ready for an engineer to design against.

    ## PRD (original requirements)
    {content of prd.md}

    ## Spec (what you're reviewing)
    {content of spec.md}

    ## Domain Reviewer Outcome
    - Reviewer: spec-reviewer
    - Result: APPROVED at iteration 3/5
    - Unresolved issues: none

    ## Next Phase Expectations
    Design needs: All requirements listed, acceptance criteria defined,
    scope boundaries clear, no ambiguities.

    This is phase-review iteration {phase_iteration}/5.

    Return your assessment as JSON: { ... }
```

The block is inserted as a new `##` section between the last artifact section and `## Next Phase Expectations`. The same pattern applies to all 4 commands — only the reviewer name, result text, and surrounding artifact sections differ.

**Affected prompts:**
| Command | Phase-reviewer prompt location | Domain reviewer |
|---------|-------------------------------|-----------------|
| specify.md | Stage 2 (lines ~102-128) | spec-reviewer |
| design.md | Stage 4 (lines ~295-324) | design-reviewer |
| create-plan.md | Stage 2 (lines ~67-95) | plan-reviewer |
| create-tasks.md | Stage 2 (lines ~110-146) | task-reviewer |

**Edge case:** If domain reviewer was not invoked (future command without domain review), the block is omitted entirely — no empty block, no error (Resolved Design Decision #3 from spec).

### Component 8: External Verification for Post-Planning Reviewers (security-reviewer.md, implementation-reviewer.md)

**Responsibility:** Add WebSearch and Context7 tools with verification instructions to security-reviewer and implementation-reviewer.

**security-reviewer.md changes:**
1. Frontmatter `tools:` line: `[Read, Glob, Grep]` → `[Read, Glob, Grep, WebSearch, mcp__context7__resolve-library-id, mcp__context7__query-docs]`
2. Add verification section after "## What You Check":
   ```
   ## Independent Verification
   MUST verify at least 1 security-relevant claim via WebSearch or Context7 if present.
   Include verification result in output:
   - "Verified: {claim} via {source}"
   - OR "Unable to verify independently - flagged for human review"

   If code is pure internal logic with no external security claims:
   - Note "No external security claims to verify" in summary
   - Proceed without forced verification
   ```
3. Add Tool Fallback section (matching spec-reviewer pattern at lines 220-226):
   ```
   ## Tool Fallback
   If Context7 tools are unavailable:
   1. Use WebSearch as fallback for security claim verification
   2. If both unavailable, flag claims as "Unable to verify — external tools unavailable"
   3. Do NOT block approval solely due to tool unavailability — note it in summary
   4. Include tool availability status in review output
   ```

**implementation-reviewer.md changes:**
1. Frontmatter `tools:` line: `[Read, Glob, Grep]` → `[Read, Glob, Grep, WebSearch, mcp__context7__resolve-library-id, mcp__context7__query-docs]`
2. Add verification section after "## Critical Rule":
   ```
   ## Independent Verification
   MUST verify at least 1 library/API usage claim via Context7 or WebSearch if present.
   Include verification result in output:
   - "Verified: {claim} via {source}"
   - OR "Unable to verify independently - flagged for human review"

   If implementation is pure internal logic with no external library/API claims:
   - Note "No external claims to verify" in summary
   - Proceed without forced verification
   ```
3. Add Tool Fallback section (same pattern as security-reviewer).

### Component 9: Knowledge Bank Metadata (anti-patterns.md, heuristics.md)

**Responsibility:** Backfill existing entries with Last observed and Observation count metadata.

**Entry template change (retrospecting SKILL.md Step 4):**
```markdown
### {Type}: {Name}
{Text}
- Observed in: {provenance}
- Confidence: {confidence}
- Last observed: Feature #{NNN}
- Observation count: 1
```

**Backfill for existing entries:**
- Entries with `- Observed in: Feature #NNN` (anti-patterns.md: 7 of 8 entries): Extract NNN, set `Last observed: Feature #NNN`, `Observation count: 1`
- Entries with non-numeric provenance (anti-patterns.md line 25: "Observed in: Plugin cache staleness bug"): Set `Last observed: Feature #008 (approximate — original provenance was non-numeric)`, `Observation count: 1`
- Heuristics.md uses `- Source: Feature #NNN` instead of `- Observed in:`: Extract NNN from Source field. Add `Last observed` and `Observation count` alongside existing Source field (do not rename Source to Observed in — heuristics use "Source" consistently)
- Do NOT change existing fields (Observed in / Source remains as the original provenance)
- **New entry provenance field:** When the retro skill writes new entries (Step 4a), it should use `Observed in:` for anti-patterns.md and `Source:` for heuristics.md to maintain per-file consistency. This is a cosmetic consistency concern — only `Last observed` is mechanically consumed by staleness checks.

### Component 10: Compact-Safe Hook Matchers (hooks.json)

**Responsibility:** Remove `compact` from all 4 SessionStart hook matchers.

**Change (4 identical edits):**
```
Before: "matcher": "startup|resume|clear|compact"
After:  "matcher": "startup|resume|clear"
```

**Rationale:** The compacted summary already retains workflow context. Hooks don't need to re-inject it. sync-cache.sh and cleanup-locks.sh are filesystem operations that don't need to run mid-conversation. session-start.sh and inject-secretary-context.sh awareness persists through compaction.

---

## Technical Decisions

### TD-1: Per-task dispatch vs. single-session multi-task
**Decision:** Explicit per-task Task tool dispatch (new agent instance per task).
**Rationale:** Enables task-specific context scoping. Each dispatch gets a fresh context window with only the relevant design/plan sections. The alternative (single agent session with all tasks) would require the agent to manage its own context window across tasks, defeating the purpose of selective loading.
**Trade-off:** More Task tool calls (one per task instead of one for all). Offset by smaller context per call.

### TD-2: Heading extraction via substring match
**Decision:** Find headings by substring containment of the reference identifier, not exact match.
**Rationale:** Plan headings vary across features (`### Step 3.2:`, `#### 3.2:`, `### 3.2 Title`). Substring match handles all variants. Prefix fallback (1A.1 → 1A) handles features where sub-items are bold text under parent headings.
**Risk:** Could match wrong heading if identifier appears in unrelated heading text. Mitigated by using first match (headings are in document order) and falling back to full loading on ambiguity.
**Limitation:** The regex `\w+\.\w+` handles up to two-level identifiers (e.g., "1.2", "1A.1"). Three-level identifiers like "1.2.3" would capture "1.2" only, missing ".3". The prefix fallback would then extract the parent section containing all sub-items, which is acceptable behavior. No three-level references exist in current features (017-021).

### TD-3: Implementation-log.md as markdown, not JSON
**Decision:** Markdown file, appendable, following .review-history.md pattern.
**Rationale:** Consistent with existing lifecycle pattern. Readable by humans. Appendable without read-modify-write. LLM (retro-facilitator) reads markdown better than JSON. ADR research confirms markdown-alongside-code is the standard pattern.
**Alternative rejected:** JSON manifest per the original brainstorm proposal — would duplicate artifact lineage already in the pipeline.

### TD-4: Domain reviewer outcome as prompt block, not metadata
**Decision:** Include outcome as a markdown block in the phase-reviewer prompt, not stored in .meta.json.
**Rationale:** The data is already in the orchestrating command's working context (it parsed the reviewer's JSON response to decide pass/fail). No need to persist it — the phase-reviewer prompt is constructed immediately after the domain reviewer finishes. Storing in .meta.json would add unnecessary I/O.

### TD-5: Brute-force knowledge bank validation
**Decision:** Read ALL entries (~15 total across 2 files) and check each against feature artifacts.
**Rationale:** Entry count is bounded and grows slowly (~1-2 per feature). At current scale (~15 entries), a brute-force scan is faster than any indexing mechanism. The retro agent is an LLM — it can process 15 short entries easily.
**Scaling note:** If entries reach 50+, consider partitioning validation (only check entries in categories relevant to the feature's domain).

### TD-6: Feature-count staleness, not calendar time
**Decision:** Count actual feature directories via glob, not time-based expiry.
**Rationale:** Features are the natural clock for this codebase. An entry not re-observed across 10 actual features has had enough opportunity to be tested. Calendar time is misleading (development pace varies).

### TD-7: Project context cap at ~500 tokens
**Decision:** Cap project context block at ~500 tokens even for features with many dependencies.
**Rationale:** Context savings from selective loading should not be consumed by project context inflation. ~200 base (goals + priority) + ~100 per dependency, capped at ~500 total. If more dependencies exist, summarize to counts rather than listing each.

---

## Risks

### R-1: Heading extraction false positives
**Likelihood:** Low. **Impact:** Medium (wrong section loaded, but full fallback is safe).
**Mitigation:** First match in document order. Prefix fallback only attempted when exact fails. Full artifact fallback on any ambiguity. Verified against features 017-021.

### R-2: Implementer agent ignores new report fields
**Likelihood:** Medium. **Impact:** Low (partial log entry written, next task proceeds).
**Mitigation:** AC-21 specifies graceful degradation — partial entries with available fields. The implementing skill does not block on missing fields.

### R-3: Knowledge bank validation quality
**Likelihood:** Medium. **Impact:** Low (worst case: entries confirmed when they shouldn't be, or missed).
**Mitigation:** SC-13 calibration: first retro run manually reviewed. Challenge text must be specific and actionable. User has final authority on staleness decisions.

### R-4: Phase-reviewer ignores domain reviewer outcome
**Likelihood:** Low. **Impact:** Medium (rubber-stamping failed domain reviews).
**Mitigation:** Informational for now (spec Open Question #1). Monitor in first few features. Add escalation rule if data shows rubber-stamping.

### R-5: External tool unavailability during security/implementation review
**Likelihood:** Medium. **Impact:** Low (reviews proceed with "Unable to verify" notes).
**Mitigation:** Tool Fallback sections match spec-reviewer pattern. Approval not blocked by tool unavailability alone.

---

## Interfaces

### Interface 1: Task Block Parser

**Input:** Raw tasks.md content (string)
**Output:** Array of task objects

```
TaskBlock {
  number: string              // Task number (e.g., "1.1", "2.3", "3.1")
  title: string               // Task title (e.g., "Create config directory")
  body: string                // Full task block text
  headingLevel: number        // 3 for ###, 4 for ####
  traceability: {
    fieldName: "Why" | "Source" | null
    rawValue: string | null   // e.g., "Implements Plan 3.2 / Design Component Auth-Module"
    references: Reference[]   // parsed references (see below)
  }
  doneCriteria: string | null // text after "Done when:" if present
}

Reference {
  type: "plan" | "design" | "spec"
  identifier: string          // e.g., "3.2", "Auth-Module", "C4.1"
  raw: string                 // original reference text
}
```

**Parsing rules:**
- Task heading: `/^(#{3,4})\s+Task\s+(\d+(?:\.\d+)*):?\s*(.+)$/` — capture group 1 is the heading level, group 2 is the dot-separated task number (e.g., "1.1", "2.3"), group 3 is the title.
- Actual format in tasks.md (per breaking-down-tasks template): `#### Task 1.1: Verb + Object + Context`. Some older features use `### Task N.N:` (feature 015).
- Block boundary: next heading at same or higher level (e.g., next `###`/`####` Task heading, or next `##` phase heading), or EOF.
- Why field: `/\*\*Why:\*\*\s*(.+)/` within block
- Source field: `/\*\*Source:\*\*\s*(.+)/` within block
- Reference splitting: comma-separated, then per-reference regex
- **Verified against actual data:** Tested regex against tasks.md from features 004 (`#### Task 1.1:`), 015 (`### Task 1.1:`), and breaking-down-tasks template (`#### Task 1.1:`) — all match. Feature 006 uses a different format (non-heading, checkbox-based subtasks) — this is a pre-template feature and would trigger the "no tasks found" fallback.
- **Failure mode:** If no task headings found, log error and surface to user (not silent degradation).

### Interface 2: Section Extractor

**Input:** Markdown content (string), identifier (string)
**Output:** Extracted section (string | null)

```
extractSection(markdown: string, identifier: string): string | null
  - Finds first heading containing identifier as substring
  - Returns content from heading through next same-level heading (exclusive)
  - Returns null if no matching heading found

extractSectionWithFallback(markdown: string, identifier: string): string | null
  - Calls extractSection(markdown, identifier)
  - If null and identifier contains '.': try prefix (remove after last '.')
  - Returns extracted section or null
```

### Interface 3: Implementer Agent Report

**Input:** Implementer agent's text report (string)
**Output:** Structured report fields

```
ImplementerReport {
  implemented: string         // what was implemented
  tested: string              // test results
  filesChanged: string[]      // list of files
  selfReview: string | null   // self-review findings
  decisions: string           // decisions with rationale, or "none"
  deviations: string          // deviations from plan/design, or "none"
  concerns: string            // concerns for future, or "none"
}
```

The implementing skill extracts these fields from the agent's free-text report by looking for section headers in the report text. Extraction patterns (substring match, case-insensitive): `files changed`, `decisions`, `deviations`, `concerns`, `implemented`, `tested`, `self-review`. The agent's prompt instructs it to use these exact headers; if the agent produces variants (e.g., "Implementation Decisions" instead of "Decisions"), substring match handles this. Missing fields default to "none" for decisions/deviations/concerns, null for optional fields.

### Interface 4: Implementation Log Entry

**Input:** Task number (string, e.g., "1.1"), title, ImplementerReport
**Output:** Markdown entry appended to implementation-log.md

```markdown
## Task {number}: {title}
- **Files changed:** {filesChanged joined with ", "}
- **Decisions:** {decisions}
- **Deviations:** {deviations}
- **Concerns:** {concerns}
```

### Interface 5: Project Context Block

**Input:** Feature .meta.json (with project_id), project artifacts
**Output:** Markdown block (~200-500 tokens)

```markdown
## Project Context
**Project:** {project name} | **This feature:** {feature name}
**Project goals:** {2-3 bullet summary from project PRD goals}
**Feature dependencies:** completed: {names} | in-progress: {names} | blocked: {names}
**Priority signal:** {milestone name, or "not on roadmap"}
```

**Token budget enforcement:** If formatted block exceeds ~500 tokens, truncate dependency details to counts only ("3 completed, 1 in-progress") and trim goal bullets.

### Interface 6: Domain Reviewer Outcome Block

**Input:** Domain reviewer name, iteration count, max iterations, approval status, unresolved issues
**Output:** Markdown block (~100-200 tokens)

```markdown
## Domain Reviewer Outcome
- Reviewer: {reviewer name}
- Result: {APPROVED at iteration {n}/{max} | FAILED at iteration cap ({max}/{max})}
- Unresolved issues: {issue descriptions, or "none"}
```

### Interface 7: Knowledge Bank Entry (updated template)

**Input:** Entry type, name, text, provenance, confidence, feature number
**Output:** Markdown entry

```markdown
### {Type}: {Name}
{Text}
- Observed in: {provenance}
- Confidence: {confidence}
- Last observed: Feature #{NNN}
- Observation count: {N}
```

### Interface 8: Knowledge Bank Validation Result

**Input:** All knowledge bank entries, feature artifacts (git diff, impl-log, review-history)
**Output:** Per-entry action

```
ValidationAction {
  entryName: string
  action: "confirmed" | "challenged" | "stale" | "skip"
  reason: string | null       // for challenged/stale
  newLastObserved: string     // for confirmed: current feature number
}
```

---

## File Modification Summary

| File | Change Type | Component |
|------|------------|-----------|
| `plugins/iflow-dev/skills/implementing/SKILL.md` | Major rewrite (incremental: C1 first, then C2, then C3) | C1, C2, C3 |
| `plugins/iflow-dev/agents/implementer.md` | Extend report format | C4 |
| `plugins/iflow-dev/commands/implement.md` | Minor: Step 4 references updated implementing skill | C1 |
| `plugins/iflow-dev/skills/retrospecting/SKILL.md` | Add Step 1c + Step 4b | C5 |
| `plugins/iflow-dev/commands/finish.md` | Add cleanup line | C6 |
| `plugins/iflow-dev/commands/specify.md` | Add outcome block to phase-reviewer prompt | C7 |
| `plugins/iflow-dev/commands/design.md` | Add outcome block to phase-reviewer prompt | C7 |
| `plugins/iflow-dev/commands/create-plan.md` | Add outcome block to phase-reviewer prompt | C7 |
| `plugins/iflow-dev/commands/create-tasks.md` | Add outcome block to phase-reviewer prompt | C7 |
| `plugins/iflow-dev/agents/security-reviewer.md` | Add tools + verification section | C8 |
| `plugins/iflow-dev/agents/implementation-reviewer.md` | Add tools + verification section | C8 |
| `docs/dev_artifacts/knowledge-bank/anti-patterns.md` | Backfill metadata | C9 |
| `docs/dev_artifacts/knowledge-bank/heuristics.md` | Backfill metadata | C9 |
| `plugins/iflow-dev/hooks/hooks.json` | Remove compact from matchers | C10 |
