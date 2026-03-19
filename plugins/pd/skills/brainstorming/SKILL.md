---
name: brainstorming
description: Guides a 6-stage process producing evidence-backed PRDs. Use when the user says 'brainstorm this idea', 'explore options for', 'start ideation', or 'create a PRD'.
---

# Brainstorming Phase

Guide divergent thinking through a structured 6-stage process that produces a PRD.

## YOLO Mode Overrides

If `[YOLO_MODE]` is active in the execution context:

- **Stage 1 (CLARIFY):** Skip Q&A. Infer all 5 required items from the user's description.
  Use conventional defaults for anything not inferable. Do NOT ask any questions.
- **Step 6 (Problem Type):** Auto-select "Product/Feature"
- **Step 10 (Clarity Gate):** Skip entirely
- **Stages 2-5:** Run normally (research, drafting, and reviews still execute for quality)
- **Stage 6 (Decision):** Auto-select "Promote to Feature" regardless of variant
  (project-recommended, non-project, or blocked — always choose feature, not project)
- **Mode selection:** Auto-select "Standard"
- **Context propagation:** When invoking create-feature, include `[YOLO_MODE]` in args

These overrides take precedence over the PROHIBITED section for YOLO mode only.

## Process

The brainstorm follows 6 stages in sequence:

```
Stage 1: CLARIFY → Stage 2: RESEARCH → Stage 3: DRAFT PRD
                                                    ↓
                                        Stage 4: CRITICAL REVIEW AND CORRECTION
                                                    (prd-reviewer + auto-correct loop, max 3)
                                                    ↓
                                        Stage 5: READINESS CHECK
                                                    (brainstorm-reviewer + auto-correct loop, max 3)
                                                    ↓
                                        Stage 6: USER DECISION
```

---
### Stage 1: CLARIFY

**Goal:** Resolve ambiguities through Q&A before research begins.

**Rules:**
- Ask ONE question at a time
- Use AskUserQuestion with multiple choice options when possible
- Apply YAGNI: challenge "nice to have" features

**Required information to gather:**
1. Problem being solved
2. Target user/audience
3. Success criteria
4. Known constraints
5. Approaches already considered

**Exit condition:** User confirms understanding is correct, OR you have answers to all 5 required items.

**After exit condition is satisfied, always run Steps 6-8 before proceeding to Stage 2:**

#### Step 6: Problem Type Classification
Present problem type options via AskUserQuestion:
```
AskUserQuestion:
  questions: [{
    "question": "What type of problem is this?",
    "header": "Problem Type",
    "options": [
      {"label": "Product/Feature", "description": "User-facing product or feature design"},
      {"label": "Technical/Architecture", "description": "System design, infrastructure, or technical debt"},
      {"label": "Financial/Business", "description": "Business model, pricing, or financial analysis"},
      {"label": "Research/Scientific", "description": "Hypothesis-driven investigation or experiment"},
      {"label": "Creative/Design", "description": "Visual, UX, or creative exploration"},
      {"label": "Skip", "description": "No framework — proceed with standard brainstorm"}
    ],
    "multiSelect": false
  }]
```

(User sees 7 options: 6 above + built-in "Other" for free text.)

#### Step 7: Optional Framework Loading
**If user selected a named type (not "Skip"):**
1. Derive sibling skill path: replace `skills/brainstorming` in Base directory with `skills/structured-problem-solving`
2. Read `{derived path}/SKILL.md` via Read tool
3. If file not found: warn "Structured problem-solving skill not found, skipping framework" → skip to Step 8
4. Read reference files as directed by SKILL.md
5. Apply SCQA framing to the problem
6. Apply type-specific decomposition (or generic issue tree for "Other")
7. Generate inline Mermaid mind map from decomposition
8. Write `## Structured Analysis` section to PRD (between Research Summary and Review History)

**If user selected "Other" (free text):**
- Apply SCQA framing (universal) + generic issue tree decomposition
- Store custom type string as-is

**If "Skip":** Set type to "none", skip Step 7 body entirely.

**Loop-back behavior:** If `## Structured Analysis` already exists in the PRD (from a previous Stage 6 → Stage 1 loop), delete it entirely before re-running Steps 6-8. Do NOT duplicate.

#### Step 8: Store Problem Type
- Add `- Problem Type: {type}` to PRD Status section (or `none` if skipped)

#### Step 9: Parse Advisory Team Config

Parse advisory team configuration from skill args:

1. Look for `[ARCHETYPE: {value}]` in args
   - If found: store as `archetype`
   - If not found: set `archetype = "exploring-an-idea"`

2. Look for `[ADVISORY_TEAM: {csv}]` in args
   - If found: parse comma-separated names, store as `advisory_team` array
   - If not found: set `advisory_team = ["pre-mortem", "opportunity-cost"]`

3. Read `references/archetypes.md` via Read tool (derive path from skill base directory)
   - If not found: warn "Archetypes reference not found, using defaults" and continue
   - Store archetype definition (PRD sections, exit routes) for Stages 3 and 6

**Loop-back behavior:** If returning from Stage 6, preserve stored values (no re-prompt since no user interaction).

#### Step 10: Deliverable Clarity Gate

**Skip if:** YOLO mode active, OR archetype `uncertainty_level` is `low` (per archetypes.md).

**Applies to:** exploring-an-idea, deciding-between-options, new-product-or-business, crypto-web3-project, data-ml-project (all `high` uncertainty archetypes).

**Check two items from Stage 1:**
1. **Success criteria (item 3):** Are they measurable? Look for vague language like "works better", "is improved", "feels right" with no metric or threshold.
2. **Deliverable concreteness (item 1 + 3 combined):** Can you describe what "done" looks like in one concrete sentence? If the problem + success criteria together don't paint a clear picture of the finished deliverable, flag it.

**If either check fails:**
```
AskUserQuestion:
  questions: [{
    "question": "Your {success criteria / deliverable description} could be sharper. For example, '{quote vague part}' — what specific, measurable outcome would tell you this succeeded?",
    "header": "Clarity",
    "options": [
      {"label": "Let me clarify", "description": "Refine the answer to be more specific and measurable"},
      {"label": "Proceed as-is", "description": "Working Backwards advisor will address deliverable clarity in Stage 2"}
    ],
    "multiSelect": false
  }]
```

- **"Let me clarify":** Accept refined answer, update stored item, run ONE re-check only (no infinite loop). If still vague after re-check, proceed silently.
- **"Proceed as-is":** Continue — Working Backwards advisor handles clarity depth in Stage 2.
- **Both checks pass on first run:** Proceed silently to Stage 2 (no user interaction).

---
### Stage 2: RESEARCH AND ADVISORY ANALYSIS

**Goal:** Gather evidence and strategic analysis in parallel batches of 3.

**Build dispatch queue:**

1. **Research agents (always present):**
   - `{ type: "research", agent: "pd:internet-researcher", prompt: topic query }`
   - `{ type: "research", agent: "pd:codebase-explorer", prompt: patterns query }`
   - `{ type: "research", agent: "pd:skill-searcher", prompt: capabilities query }`

2. **Advisory agents (from Step 9):**
   For each name in `advisory_team`:
   a. Derive path: `references/advisors/{name}.advisor.md`
   b. Read file via Read tool
   c. If not found: warn "Advisor '{name}' template not found, skipping" → remove from queue
   d. If found: add `{ type: "advisor", agent: "pd:advisor", template: file_content }`

**Dispatch in batches of `max_concurrent_agents` (from session context, default 5):**

```
while queue is not empty:
  batch = take up to max_concurrent_agents items from front of queue
  For each item in batch, issue a Task call:
    If type == "research":
      Task({ subagent_type: item.agent, model: "sonnet", description: "Research: {brief}", prompt: item.prompt })
    If type == "advisor":
      Task({ subagent_type: "pd:advisor", model: "sonnet", description: "Advisory: {advisor name}", prompt: see below })
  Collect results from all batch items before next batch
```

**Advisory agent prompt construction:**
```
{full content of the .advisor.md template file}

---

## Problem Context

1. **Problem:** {from Stage 1 item 1}
2. **Target user:** {from Stage 1 item 2}
3. **Success criteria:** {from Stage 1 item 3}
4. **Constraints:** {from Stage 1 item 4}
5. **Approaches considered:** {from Stage 1 item 5}

**Archetype:** {archetype name}

Analyze this problem from your advisory perspective. Return JSON per the advisor agent output format.
```

**Collect results:**
- Research: JSON with `findings[]` and `source` refs (existing format)
- Advisory: JSON with `advisor_name`, `perspective`, `analysis`, `key_findings[]`, `risk_flags[]`, `evidence_quality`

**Fallback:** If any agent fails, warn and proceed with available results.

**Exit condition:** All batches dispatched and results collected.

---
### Stage 3: DRAFT PRD

**Goal:** Generate a complete PRD document with evidence citations.

**Action:** Write PRD to file using the PRD Output Format section below.

**Citation requirements:** Every claim must have one of:
- `— Evidence: {URL}` (from internet research)
- `— Evidence: {file:line}` (from codebase)
- `— Evidence: User input` (from Stage 1)
- `— Assumption: needs verification` (unverified)

**Strategic Analysis and archetype-aware sections:**

1. Add `- Archetype: {archetype}` to PRD Status section
2. Write `## Strategic Analysis` section:
   - For each advisory agent that returned results:
     - Extract `analysis` field from the advisor's JSON response (already contains `### {Advisor Name}` heading and structured content)
     - Append the `analysis` markdown directly under `## Strategic Analysis` (do NOT add another heading — the analysis field includes its own `###` heading)
     - Append `- **Evidence Quality:** {evidence_quality from JSON}` at the end of each advisor's subsection
   - If zero advisors returned: write `## Strategic Analysis\n\nNo advisory analysis available.`
3. Read stored archetype definition from `archetypes.md`
4. If archetype defines additional PRD sections (e.g., fixing: Symptoms, Reproduction Steps; exploring: Options Evaluated, Decision Matrix):
   - Read the section templates from the archetypes reference
   - Add those sections after Strategic Analysis, before Review History
   - Leave section content as template placeholders for the drafter to fill based on research + advisory outputs
5. Write all remaining universal sections (Review History, Open Questions, Next Steps)

**Exit condition:** PRD file written with all sections populated.

**Entity Registration:** After the PRD file is written, register the brainstorm entity. If any MCP call fails, warn `"Entity registration failed: {error}"` but do NOT block brainstorm creation. Continue to Stage 4.

1. **Extract brainstorm stem** from the PRD filename: the stem is the filename without directory and without the `.prd.md` extension (e.g., `20260227-143052-api-caching` from `{pd_artifacts_root}/brainstorms/20260227-143052-api-caching.prd.md`)

2. **Parse for backlog source** in the PRD content using pattern `\*Source: Backlog #(\d{5})\*`

3. **If backlog marker found**, register the backlog entity and initialize its workflow (idempotent):
   ```
   register_entity(
     entity_type="backlog",
     entity_id="{5-digit backlog id}",
     name="Backlog #{id}"
   )
   ```
   If duplicate error (already registered by add-to-backlog), swallow and continue.

   ```
   init_entity_workflow(
     type_id="backlog:{5-digit backlog id}",
     workflow_phase="open",
     kanban_column="backlog"
   )
   ```
   Idempotent — if `add-to-backlog` already created the workflow_phases row, returns `created: false` without error.

   ```
   transition_entity_phase(
     type_id="backlog:{5-digit backlog id}",
     target_phase="triaged"
   )
   ```
   If MCP call fails (e.g., already triaged or entity missing), warn "Backlog transition failed: {error}" but do NOT block brainstorm creation.

   Set `parent_type_id` for the brainstorm to `"backlog:{5-digit backlog id}"` in step 4.

4. **Register brainstorm entity:**
   Extract the title from the PRD first heading (e.g., `# PRD: API Caching` -> `API Caching`).
   ```
   register_entity(
     entity_type="brainstorm",
     entity_id="{stem}",
     name="{title from PRD}",
     artifact_path="{pd_artifacts_root}/brainstorms/{filename}",
     parent_type_id="{backlog parent if found, otherwise omit}"
   )
   ```

5. **Initialize brainstorm workflow state:**
   ```
   init_entity_workflow(
     type_id="brainstorm:{stem}",
     workflow_phase="draft",
     kanban_column="wip"
   )
   ```
   If MCP call fails, warn "Workflow init failed: {error}" but do NOT block brainstorm creation.

---
### Stage 4: CRITICAL REVIEW AND CORRECTION

**Goal:** Challenge PRD quality and auto-correct issues in a review-correct loop (max 3 iterations).

Set `review_iteration = 0`.

**Transition brainstorm to reviewing phase:**
```
transition_entity_phase(
  type_id="brainstorm:{stem}",
  target_phase="reviewing"
)
```
If MCP call fails, warn "Phase transition failed: {error}" but do NOT block review.

**a. Dispatch prd-reviewer** (always a NEW Task tool instance per iteration):
- Tool: `Task`
- subagent_type: `pd:prd-reviewer`
- model: `opus`
- prompt: Full PRD content + request for JSON response + "This is review iteration {review_iteration}/3"

**Expected response:**
```json
{ "approved": true/false, "issues": [...], "summary": "..." }
```

**b. Apply strict threshold:**
- **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
- **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"

**c. Branch on result:**
- If PASS → Proceed to Stage 5
- If FAIL AND review_iteration < 3:
  - Auto-correct: For each issue with severity "blocker" or "warning":
    - If has `suggested_fix`: Apply the fix to PRD content
    - Record: `Changed: {what} — Reason: {issue description}`
  - For "suggestion" severity: Consider but don't require action
  - Update PRD file with all corrections
  - Add to Review History section:
    ```markdown
    ### Review {review_iteration} ({date})
    **Findings:**
    - [{severity}] {description} (at: {location})

    **Corrections Applied:**
    - {what changed} — Reason: {reference to finding}
    ```
  - Increment review_iteration
  - Return to step a (new prd-reviewer instance verifies corrections)
- If FAIL AND review_iteration == 3:
  - Record unresolved issues in Review History
  - Proceed to Stage 5 with warning

**Fallback:** If reviewer unavailable on any iteration, show warning and proceed to Stage 5 with empty issues array.

**Exit condition:** PASS achieved or 3 iterations exhausted.

---
### Stage 5: READINESS CHECK

**Goal:** Validate brainstorm is ready for feature promotion (quality gate with auto-correction loop, max 3 iterations).

Set `readiness_iteration = 0`.

**a. Dispatch brainstorm-reviewer** (always a NEW Task tool instance per iteration):
- Tool: `Task`
- subagent_type: `pd:brainstorm-reviewer`
- model: `sonnet`
- prompt: |
    Review this brainstorm for promotion readiness.

    ## PRD Content
    {read PRD file and paste full markdown content here}

    ## Context
    Problem Type: {type from Step 8, or "none" if skipped/absent}
    Archetype: {archetype from Step 9, or "none" if absent}

    This is readiness-check iteration {readiness_iteration}/3.

    Return your assessment as JSON:
    { "approved": true/false, "issues": [...], "summary": "..." }

**Expected response:**
```json
{ "approved": true/false, "issues": [...], "summary": "..." }
```

**b. Apply strict threshold:**
- **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
- **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"

**c. Branch on result:**
- If PASS → Store `approved: true`, proceed to Stage 6
- If FAIL AND readiness_iteration < 3:
  - Auto-correct PRD to address all blocker AND warning issues
  - Record corrections in Review History
  - Increment readiness_iteration
  - Return to step a (new brainstorm-reviewer instance verifies)
- If FAIL AND readiness_iteration == 3:
  - Store unresolved issues
  - Proceed to Stage 6 with BLOCKED status (user must decide)

**Fallback:** If reviewer unavailable, show warning and proceed with `approved: unknown`.

**Exit condition:** PASS achieved, or 3 iterations exhausted (BLOCKED).

---
### Stage 6: USER DECISION

**Goal:** Present readiness status and let user decide next action.

**Step 1: Display readiness status**
- If `approved: true` with no blockers: Output "Readiness check: PASSED"
- If `approved: true` with warnings: Output "Readiness check: PASSED ({n} warnings)" + list warnings
- If `approved: false`: Output "Readiness check: BLOCKED ({n} issues)" + list all issues
- If `approved: unknown`: Output "Readiness check: SKIPPED (reviewer unavailable)"

**Step 1.5: Scale Detection (inline, before presenting options)**

Analyze the PRD content against 6 closed signals:

1. **Multiple entity types** — 3+ distinct data entities with separate CRUD lifecycles
2. **Multiple functional areas** — 3+ distinct functional capabilities
3. **Multiple API surfaces** — 2+ API types or 3+ distinct endpoint groups
4. **Cross-cutting concerns** — Capabilities spanning multiple functional areas
5. **Multiple UI sections** — 3+ distinct user-facing views/pages/screens
6. **External integrations** — 2+ external service integrations

Count matches. Store as `scale_signal_count`.
- If `scale_signal_count >= 3`: set `project_recommended = true`
- Otherwise: set `project_recommended = false`

**Step 1.7: Load Archetype Exit Routes**

Read stored archetype definition from archetypes.md. Extract the exit routes for this archetype. These replace the hardcoded option sets in Step 2.

Default exit routes (when archetype unknown or archetypes.md unavailable):
- Promote to Feature, Promote to Project (if scale detected), Refine Further, Save and Exit

**Step 2: Present archetype-aware options**

Build AskUserQuestion options from archetype exit routes:
- Map each exit route to an option label + description
- For BLOCKED status: replace promotion routes with "Address Issues" + "Promote Anyway"
- For `project_recommended`: ensure "Promote to Project" appears with "(Recommended)" suffix

**Special route handling:**
- "Route to /root-cause-analysis" → Invoke `Skill({ skill: "pd:root-cause-analysis" })`
- "Create fix task" → Invoke `Skill({ skill: "pd:create-feature", args: "--prd={path}" })` with Standard mode
- "Save as Decision Document" → Output "Decision document saved to {filepath}." and STOP
- "Promote if crystallised" → Same as "Promote to Feature" flow

If PASSED or SKIPPED — build options dynamically from archetype exit routes:
```
AskUserQuestion:
  questions: [{
    "question": "PRD complete. What would you like to do?",
    "header": "Decision",
    "options": [
      // Map archetype exit routes to options:
      // - "Promote to Project" gets "(Recommended)" suffix when project_recommended == true
      // - "Promote to Project" only included when project_recommended OR archetype explicitly lists it
      // - All other routes mapped 1:1
      // Example for building-something-new with project_recommended:
      {"label": "Promote to Project (Recommended)", "description": "Create project with AI-driven decomposition into features"},
      {"label": "Promote to Feature", "description": "Create single feature and continue workflow"},
      {"label": "Refine Further", "description": "Loop back to clarify and improve"},
      {"label": "Save and Exit", "description": "Keep PRD, end session"}
    ],
    "multiSelect": false
  }]
```

If BLOCKED (any archetype):
```
AskUserQuestion:
  questions: [{
    "question": "PRD has blockers. What would you like to do?",
    "header": "Decision",
    "options": [
      {"label": "Address Issues", "description": "Auto-correction failed after 3 attempts. Loop back to clarify and fix manually."},
      {"label": "Promote Anyway", "description": "Create feature despite blockers"},
      {"label": "Save and Exit", "description": "Keep PRD, end session"}
    ],
    "multiSelect": false
  }]
```

**Step 3: Handle response**

| Response | Action |
|----------|--------|
| Promote to Project | Transition brainstorm to promoted (see below) → Skip mode prompt → Invoke `/pd:create-project --prd={current-prd-path}` → STOP |
| Promote to Feature / Promote Anyway / Promote if crystallised | Transition brainstorm to promoted (see below) → Ask for mode → Invoke `/pd:create-feature --prd={current-prd-path}` → STOP |
| Refine Further / Address Issues | Transition brainstorm to draft (see below) → Loop back to Stage 1 with issue context |
| Save and Exit / Save as Decision Document | Output "PRD saved to {filepath}." → STOP |
| Route to /root-cause-analysis | Invoke `Skill({ skill: "pd:root-cause-analysis" })` → STOP |
| Create fix task | Invoke `Skill({ skill: "pd:create-feature", args: "--prd={current-prd-path}" })` with Standard mode → STOP |

**Workflow transitions for decision handlers:**

Before invoking create-feature or create-project for "Promote to Feature" / "Promote Anyway" / "Promote if crystallised" / "Promote to Project":
```
transition_entity_phase(
  type_id="brainstorm:{stem}",
  target_phase="promoted"
)
```
If the brainstorm references a backlog item (parsed in Stage 3), also transition the backlog:
```
transition_entity_phase(
  type_id="backlog:{5-digit backlog id}",
  target_phase="promoted"
)
```
If either MCP call fails, warn "Phase transition failed: {error}" but do NOT block feature/project creation.

Before looping back for "Refine Further" / "Address Issues":
```
transition_entity_phase(
  type_id="brainstorm:{stem}",
  target_phase="draft"
)
```
If MCP call fails, warn "Phase transition failed: {error}" but do NOT block loop-back.

**Mode prompt bypass:** "Promote to Project" skips the mode selection below. Projects have no mode — modes are per-feature, set during planned→active transition when a user starts working on a decomposed feature.

**Mode selection (only for "Promote to Feature" / "Promote Anyway"):**
```
AskUserQuestion:
  questions: [{
    "question": "Which workflow mode?",
    "header": "Mode",
    "options": [
      {"label": "Standard", "description": "All phases, optional verification"},
      {"label": "Full", "description": "All phases, required verification"}
    ],
    "multiSelect": false
  }]
```

---
## PRD Output Format

Write PRD using template from [references/prd-template.md](references/prd-template.md).

---
## Error Handling

- **WebSearch Unavailable:** Skip internet research with warning, proceed with codebase and skills research only
- **Agent Unavailable:** Show warning "{agent} unavailable, proceeding without", continue with available agents
- **All Research Fails:** Proceed with user input only, mark all claims as "Assumption: needs verification"
- **PRD Reviewer Unavailable:** Show warning, proceed to Stage 5 with empty issues array
- **Brainstorm Reviewer Unavailable:** Show warning, proceed directly to Stage 6 with `approved: unknown`

---
## PROHIBITED Actions
When executing the brainstorming skill, you MUST NOT:
- Proceed to /pd:specify, /pd:design, /pd:create-plan, or /pd:implement
- Write any implementation code
- Create feature folders directly (use /pd:create-feature)
- Continue with any action after user says "Save and Exit"
- Skip the research stage (Stage 2)
- Skip the critical review stage (Stage 4)
- Skip the readiness check stage (Stage 5)
- Skip the AskUserQuestion decision gate (Stage 6)

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

## Getting Started

### 1. Create Scratch File

- Get topic from user argument or ask: "What would you like to brainstorm?"
- Generate slug from topic:
  - Lowercase
  - Replace spaces/special chars with hyphens
  - Max 30 characters
  - Trim trailing hyphens
  - If empty, use "untitled"
- Ensure directory exists (create if needed): `mkdir -p {pd_artifacts_root}/brainstorms/`
- Create file: `{pd_artifacts_root}/brainstorms/YYYYMMDD-HHMMSS-{slug}.prd.md`
  - Example: `{pd_artifacts_root}/brainstorms/20260129-143052-api-caching.prd.md`

### 2. Run 6-Stage Process

Follow the Process above, writing content to the PRD file as you go.

---
## Completion
After Stage 6:
- If "Promote to Project": Invoke `/pd:create-project --prd={prd-file-path}` directly (no mode prompt)
- If "Promote to Feature": Ask for workflow mode (Standard/Full), then invoke `/pd:create-feature --prd={prd-file-path}`
