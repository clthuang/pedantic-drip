---
description: Create architecture design for current feature
argument-hint: "[--feature=<id-slug>]"
---

Invoke the designing skill for the current feature context.

## Static Reference
## YOLO Mode Overrides

If `[YOLO_MODE]` is active:
- Step 0 research findings prompt → auto "Proceed"
- Step 0 partial recovery → auto "Resume"
- Completion prompt → skip AskUserQuestion, directly invoke `/pd:create-plan` with `[YOLO_MODE]`

## Workflow Integration

### 1-3. Validate, Branch Check, Partial Recovery, Mark Started

Follow `validateAndSetup("design")` from the **workflow-transitions** skill.

**Design-specific partial recovery:** If partial design detected, also check `phases.design.stages` to identify which stage was in progress and offer resumption from that specific stage.

### 4. Execute 5-Step Workflow

The design phase consists of 5 sequential steps:

```
Step 0: RESEARCH ("Don't Reinvent the Wheel")
    ↓
Step 1: ARCHITECTURE DESIGN
    ↓
Step 2: INTERFACE DESIGN
    ↓
Step 3: DESIGN REVIEW LOOP (design-reviewer, up to 5 iterations)
    ↓
Step 4: HANDOFF REVIEW (phase-reviewer)
```

---

#### Step 0: Research

**Purpose:** Gather prior art before designing to avoid reinventing the wheel.

a. **Mark stage started:**
   ```json
   "stages": {
     "research": { "started": "{ISO timestamp}" }
   }
   ```

b. **Dispatch parallel research agents** (2 agents, within `max_concurrent_agents` budget):
   **Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
   call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
   limit=5, brief=true.
   Include non-empty results as:

   ## Relevant Engineering Memory
   {search_memory results}

   ```
   Task tool call 1:
     description: "Explore codebase for patterns"
     subagent_type: pd:codebase-explorer
     model: sonnet
     prompt: |
       Find existing patterns related to: {feature description from spec}

       Look for:
       - Similar implementations
       - Reusable components
       - Established conventions
       - Related utilities

       Return JSON: {"findings": [...], "locations": [...]}

   **Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
   call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
   limit=5, brief=true.
   Include non-empty results as:

   ## Relevant Engineering Memory
   {search_memory results}

   Task tool call 2:
     description: "Research external solutions"
     subagent_type: pd:internet-researcher
     model: sonnet
     prompt: |
       Research existing solutions for: {feature description from spec}

       Look for:
       - Industry standard approaches
       - Library support
       - Common patterns
       - Best practices

       Return JSON: {"findings": [...], "sources": [...]}
   ```

c. **Present findings via AskUserQuestion:**
   ```
   AskUserQuestion:
     questions: [{
       "question": "Research found {n} patterns. How to proceed?",
       "header": "Research",
       "options": [
         {"label": "Review findings", "description": "See details before designing"},
         {"label": "Proceed", "description": "Continue to architecture with findings"},
         {"label": "Skip (domain expert)", "description": "Skip research, proceed directly"}
       ],
       "multiSelect": false
     }]
   ```

d. **Record results in design.md Prior Art section:**
   - If "Review findings": Display findings, then ask again (Proceed/Skip)
   - If "Proceed": Write findings to Prior Art Research section
   - If "Skip": Note "Research skipped by user" in Prior Art section

e. **Handle agent failures gracefully:**
   - If codebase-explorer fails: Note "Codebase search unavailable" in Prior Art section
   - If internet-researcher fails: Note "No external solutions found" in Prior Art section
   - If both fail: Proceed with empty Prior Art section, note "Research unavailable"

f. **Mark stage completed:**
   ```json
   "stages": {
     "research": { "started": "...", "completed": "{ISO timestamp}", "skipped": false }
   }
   ```

**Recovery from partial Step 0:**
If `stages.research.started` exists but `stages.research.completed` is null:
```
AskUserQuestion:
  questions: [{
    "question": "Detected partial research. How to proceed?",
    "header": "Recovery",
    "options": [
      {"label": "Resume", "description": "Continue from where research stopped"},
      {"label": "Restart", "description": "Run research again from beginning"},
      {"label": "Skip", "description": "Proceed without research"}
    ],
    "multiSelect": false
  }]
```

---

#### Step 1: Architecture Design

**Purpose:** Establish high-level structure, components, decisions, and risks.

a. **Mark stage started:**
   ```json
   "stages": {
     "architecture": { "started": "{ISO timestamp}" }
   }
   ```

b. **Invoke designing skill with stage=architecture:**
   - Produce: Architecture Overview, Components, Technical Decisions, Risks
   - Write to design.md

c. **Mark stage completed:**
   ```json
   "stages": {
     "architecture": { "started": "...", "completed": "{ISO timestamp}" }
   }
   ```

d. **No review at this stage** - validated holistically in Step 3.

---

#### Step 2: Interface Design

**Purpose:** Define precise contracts between components.

a. **Mark stage started:**
   ```json
   "stages": {
     "interface": { "started": "{ISO timestamp}" }
   }
   ```

b. **Invoke designing skill with stage=interface:**
   - Read existing design.md for component definitions
   - Produce: Interfaces section with detailed contracts
   - Update design.md

c. **Mark stage completed:**
   ```json
   "stages": {
     "interface": { "started": "...", "completed": "{ISO timestamp}" }
   }
   ```

d. **No review at this stage** - validated holistically in Step 3.

---

#### Step 3: Design Review Loop

**Purpose:** Challenge assumptions, find gaps, ensure robustness.

Max iterations: 5.

**Resume state initialization:**
Initialize `resume_state = {}` at the start of the review loop. This dict tracks per-role agent context for resume across iterations. Keys: `"design-reviewer"`, `"phase-reviewer"`. Each entry: `{ agent_id, iteration1_prompt_length, last_iteration, last_commit_sha }`.

a. **Mark stage started:**
   ```json
   "stages": {
     "designReview": { "started": "{ISO timestamp}", "iterations": 0, "reviewerNotes": [] }
   }
   ```

b. **Invoke design-reviewer:**

   **PRD resolution (I8):** Before dispatching, resolve the PRD reference:
   1. Check if `{feature_path}/prd.md` exists
   2. If exists → PRD line = `- PRD: {feature_path}/prd.md`
   3. If not → check `.meta.json` for `brainstorm_source`
      a. If found → PRD line = `- PRD: {brainstorm_source path}`
      b. If not → PRD line = `- PRD: No PRD — feature created without brainstorm`

   **Dispatch decision for design-reviewer:**

   **If iteration == 1 OR resume_state["design-reviewer"] is missing/empty OR resume_state["design-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

   **Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
   call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
   limit=5, brief=true, and category="anti-patterns".
   Store the returned entry names for post-dispatch influence tracking.
   Include non-empty results inside the prompt below.

   Use the Task tool to spawn design-reviewer (the skeptic):
   ```
   Task tool call:
     description: "Review design quality"
     subagent_type: pd:design-reviewer
     model: opus
     prompt: |
       Review this design for robustness and completeness.

       Your job: Find weaknesses before implementation does.
       Be the skeptic. Challenge assumptions. Find gaps.

       ## Required Artifacts
       You MUST read the following files before beginning your review.
       After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
       {resolved PRD line from I8}
       - Spec: {feature_path}/spec.md
       - Design: {feature_path}/design.md

       Return your assessment as JSON:
       {
         "approved": true/false,
         "issues": [{
           "severity": "blocker|warning|suggestion",
           "category": "completeness|consistency|feasibility|assumptions|complexity",
           "description": "...",
           "location": "...",
           "suggestion": "..."
         }],
         "summary": "..."
       }

       ## Iteration Context
       This is iteration {n} of {max}.

       ## Relevant Engineering Memory
       {search_memory results from the pre-dispatch call above}

       ## Phase Context (backward transitions only)
       If .meta.json `phases[current_phase]` has a `completed` timestamp (indicating re-entry into a completed phase):
       1. Read `backward_context` and `phase_summaries` from .meta.json
       2. Construct `## Phase Context` block per workflow-transitions SKILL.md Step 1b format
       3. Include this block here
       If no `completed` timestamp for current phase: skip injection entirely.
   ```
   After fresh dispatch: capture the `agent_id` from the Task tool result. Record the character count of the prompt above as `prompt_length`. Capture current HEAD SHA via `Bash: git rev-parse HEAD`. Store in resume_state:
   ```
   resume_state["design-reviewer"] = {
     "agent_id": {agent_id from Task result},
     "iteration1_prompt_length": {prompt_length} (only set on iteration 1; preserved on subsequent fresh dispatches),
     "last_iteration": {n},
     "last_commit_sha": {HEAD SHA}
   }
   ```
   If this is not iteration 1 (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch of this loop if available; otherwise set it from this dispatch's prompt length.

   **If iteration >= 2 AND resume_state["design-reviewer"] exists with non-null agent_id** — attempt resumed dispatch:

   First, compute the delta. Run the unified three-state git command:
   ```
   Bash: git add {feature_path}/design.md && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "pd: design review iteration {n}" && echo COMMIT_OK || echo COMMIT_FAILED)
   ```

   Handle the three outcomes:

   - **NO_CHANGES**: No revisions were committed. Issue a fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated to iteration {n}). Reset `resume_state["design-reviewer"]` so the fresh dispatch result becomes the new resume anchor. Do NOT use I3 fallback template. Do NOT reuse a prior delta.

   - **COMMIT_FAILED**: Git commit failed. Fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated to iteration {n}). Reset `resume_state["design-reviewer"]`.

   - **COMMIT_OK**: Commit succeeded. Capture new SHA: `Bash: git rev-parse HEAD` → `new_sha`. Compute delta:
     ```
     Bash: git diff {resume_state["design-reviewer"].last_commit_sha} HEAD -- {feature_path}/design.md
     ```
     Capture output as `delta_content`.

     **Delta size guard**: If `len(delta_content)` > 50% of `resume_state["design-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated to iteration {n}). Reset `resume_state["design-reviewer"]`.

     **If delta is within threshold**, attempt resumed dispatch:
     ```
     Task tool call:
       resume: {resume_state["design-reviewer"].agent_id}
       prompt: |
         You already have the upstream artifacts and the previous version of
         design.md in context from your prior review.

         The following changes were made to address your previous issues:

         ## Delta
         {delta_content from git diff}

         ## Fix Summary
         {summary of revisions made to address the reviewer's issues}

         Review the changes above. Assess whether your previous issues are resolved
         and check for new issues introduced by the fixes.

         This is iteration {n} of {max}.

         Return your assessment as JSON:
         {
           "approved": true/false,
           "issues": [{
             "severity": "blocker|warning|suggestion",
             "category": "completeness|consistency|feasibility|assumptions|complexity",
             "description": "...",
             "location": "...",
             "suggestion": "..."
           }],
           "summary": "..."
         }
     ```

     **If resume succeeds**: Update resume_state:
     ```
     resume_state["design-reviewer"].agent_id = {agent_id from resumed Task result}
     resume_state["design-reviewer"].last_iteration = {n}
     resume_state["design-reviewer"].last_commit_sha = {new_sha}
     ```

     **If resume fails** (Task tool returns an error): Fall back to fresh I1-R4 dispatch (I3 fallback — same template as iteration 1, with additional line in Iteration Context: `"(Fresh dispatch — prior review session unavailable.)"` and previous issues included). Log to `.review-history.md`: `RESUME-FALLBACK: design-reviewer iteration {n} — {error summary}`. Reset `resume_state["design-reviewer"]` with the new fresh dispatch's agent_id.

   **Context compaction detection**: Before attempting resume, if `resume_state["design-reviewer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: design-reviewer iteration {n} — agent_id lost (context compaction)`.

c. **Parse response:** Extract the `approved` field from reviewer's JSON response.
   - If response is not valid JSON, ask reviewer to retry with correct format.

   **Fallback detection (I9):** Search the agent's response for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: design-reviewer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2 template) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

   **Post-dispatch influence tracking:**
   If search_memory returned entries before this dispatch:
     call record_influence_by_content(
       subagent_output_text=<full agent output text>,
       injected_entry_names=<list of entry names from search_memory results>,
       agent_role="design-reviewer",
       feature_type_id=<current feature type_id from .meta.json>,
       threshold=0.70)
     If record_influence_by_content fails: warn "Influence tracking failed: {error}", continue
     If .meta.json missing or type_id unresolvable: skip influence recording with warning

d. **Branch on result (strict threshold):**
   - **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
   - **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"
   - If PASS → Proceed to Step 4
   - If FAIL AND iteration < max:
     - Append iteration to `.review-history.md` using format below
     - Increment iteration counter in state
     - Address all blocker AND warning issues by revising design.md
     - Return to step b
   - If FAIL AND iteration == max:
     - Store unresolved concerns in `stages.designReview.reviewerNotes`
     - Proceed to Step 4 with warning

e. **Mark stage completed:**
   ```json
   "stages": {
     "designReview": { "started": "...", "completed": "{ISO timestamp}", "iterations": {count}, "reviewerNotes": [...] }
   }
   ```

**Review History Entry Format** (append to `.review-history.md`):
```markdown
## Design Review - Iteration {n} - {ISO timestamp}

**Reviewer:** design-reviewer (skeptic)
**Decision:** {Approved / Needs Revision}

**Issues:**
- [{severity}] [{category}] {description} (at: {location})
  Challenge: {challenge}

**Changes Made:**
{Summary of revisions made to address issues}

---
```

---

#### Step 4: Handoff Review

**Purpose:** Ensure plan phase has everything it needs.

Phase-reviewer iteration budget: max 5 (independent of Step 3).

Set `phase_iteration = 1`.

a. **Mark stage started:**
   ```json
   "stages": {
     "handoffReview": { "started": "{ISO timestamp}", "iterations": 0 }
   }
   ```

b. **Invoke phase-reviewer:**

   **PRD resolution (I8):** Before dispatching, resolve the PRD reference (same logic as Step 3).

   **Dispatch decision for phase-reviewer:**

   **If phase_iteration == 1 OR resume_state["phase-reviewer"] is missing/empty OR resume_state["phase-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

   **Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
   call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
   limit=5, brief=true.
   Store the returned entry names for post-dispatch influence tracking.
   Include non-empty results inside the prompt below.

   ```
   Task tool call:
     description: "Review design for phase sufficiency"
     subagent_type: pd:phase-reviewer
     model: sonnet
     prompt: |
       Validate this design is ready for implementation planning.

       ## Required Artifacts
       You MUST read the following files before beginning your review.
       After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
       {resolved PRD line from I8}
       - Spec: {feature_path}/spec.md
       - Design: {feature_path}/design.md

       ## Next Phase Expectations
       Plan needs: Components defined, interfaces specified,
       dependencies identified, risks noted.

       Return your assessment as JSON:
       {
         "approved": true/false,
         "issues": [{"severity": "blocker|warning|suggestion", "description": "...", "location": "...", "suggestion": "..."}],
         "summary": "..."
       }

       ## Domain Reviewer Outcome
       - Reviewer: design-reviewer
       - Result: {APPROVED at iteration {n}/{max} | FAILED at iteration cap ({max}/{max})}
       - Unresolved issues: {list of remaining blocker/warning descriptions, or "none"}

       This is phase-review iteration {phase_iteration}/5.

       ## Relevant Engineering Memory
       {search_memory results from the pre-dispatch call above}

       ## Phase Context (backward transitions only)
       If .meta.json `phases[current_phase]` has a `completed` timestamp (indicating re-entry into a completed phase):
       1. Read `backward_context` and `phase_summaries` from .meta.json
       2. Construct `## Phase Context` block per workflow-transitions SKILL.md Step 1b format
       3. Include this block here
       If no `completed` timestamp for current phase: skip injection entirely.
   ```

   After fresh dispatch: capture the `agent_id` from the Task tool result. Record the character count of the prompt above as `prompt_length`. Capture current HEAD SHA via `Bash: git rev-parse HEAD`. Store in resume_state:
   ```
   resume_state["phase-reviewer"] = {
     "agent_id": {agent_id from Task result},
     "iteration1_prompt_length": {prompt_length} (only set on phase_iteration 1; preserved on subsequent fresh dispatches),
     "last_iteration": {phase_iteration},
     "last_commit_sha": {HEAD SHA}
   }
   ```
   If this is not phase_iteration 1 (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch of this stage if available; otherwise set it from this dispatch's prompt length.

   **If phase_iteration >= 2 AND resume_state["phase-reviewer"] exists with non-null agent_id** — attempt resumed dispatch:

   First, compute the delta. Run the unified three-state git command:
   ```
   Bash: git add {feature_path}/design.md && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "pd: design handoff review iteration {phase_iteration}" && echo COMMIT_OK || echo COMMIT_FAILED)
   ```

   Handle the three outcomes:

   - **NO_CHANGES**: No revisions were committed. Issue a fresh I1-R4 dispatch (same template as phase_iteration 1 above, with iteration context updated to phase_iteration {phase_iteration}). Reset `resume_state["phase-reviewer"]` so the fresh dispatch result becomes the new resume anchor. Do NOT use I3 fallback template. Do NOT reuse a prior delta.

   - **COMMIT_FAILED**: Git commit failed. Fall back to fresh I1-R4 dispatch (same template as phase_iteration 1 above, with iteration context updated to phase_iteration {phase_iteration}). Reset `resume_state["phase-reviewer"]`.

   - **COMMIT_OK**: Commit succeeded. Capture new SHA: `Bash: git rev-parse HEAD` → `new_sha`. Compute delta:
     ```
     Bash: git diff {resume_state["phase-reviewer"].last_commit_sha} HEAD -- {feature_path}/design.md
     ```
     Capture output as `delta_content`.

     **Delta size guard**: If `len(delta_content)` > 50% of `resume_state["phase-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as phase_iteration 1 above, with iteration context updated to phase_iteration {phase_iteration}). Reset `resume_state["phase-reviewer"]`.

     **If delta is within threshold**, attempt resumed dispatch:
     ```
     Task tool call:
       resume: {resume_state["phase-reviewer"].agent_id}
       prompt: |
         You already have the upstream artifacts and the previous version of
         design.md in context from your prior review.

         The following changes were made to address your previous issues:

         ## Delta
         {delta_content from git diff}

         ## Fix Summary
         {summary of revisions made to address the phase-reviewer's issues}

         Review the changes above. Assess whether your previous issues are resolved
         and check for new issues introduced by the fixes.

         This is phase-review iteration {phase_iteration}/5.

         Return your assessment as JSON:
         {
           "approved": true/false,
           "issues": [{"severity": "blocker|warning|suggestion", "description": "...", "location": "...", "suggestion": "..."}],
           "summary": "..."
         }
     ```

     **If resume succeeds**: Update resume_state:
     ```
     resume_state["phase-reviewer"].agent_id = {agent_id from resumed Task result}
     resume_state["phase-reviewer"].last_iteration = {phase_iteration}
     resume_state["phase-reviewer"].last_commit_sha = {new_sha}
     ```

     **If resume fails** (Task tool returns an error): Fall back to fresh I1-R4 dispatch (I3 fallback — same template as phase_iteration 1, with additional line after phase-review iteration line: `"(Fresh dispatch — prior review session unavailable.)"` and previous issues included). Log to `.review-history.md`: `RESUME-FALLBACK: phase-reviewer iteration {phase_iteration} — {error summary}`. Reset `resume_state["phase-reviewer"]` with the new fresh dispatch's agent_id.

   **Context compaction detection**: Before attempting resume, if `resume_state["phase-reviewer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: phase-reviewer iteration {phase_iteration} — agent_id lost (context compaction)`.

   **Fallback detection (I9):** Search the agent's response for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: phase-reviewer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2 template) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

   **Post-dispatch influence tracking:**
   If search_memory returned entries before this dispatch:
     call record_influence_by_content(
       subagent_output_text=<full agent output text>,
       injected_entry_names=<list of entry names from search_memory results>,
       agent_role="phase-reviewer",
       feature_type_id=<current feature type_id from .meta.json>,
       threshold=0.70)
     If record_influence_by_content fails: warn "Influence tracking failed: {error}", continue
     If .meta.json missing or type_id unresolvable: skip influence recording with warning

c. **Branch on result (strict threshold):**
   - **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
   - **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"
   - If PASS → Proceed to auto-commit
   - If FAIL AND phase_iteration < 5:
     - Append to `.review-history.md` with "Step 4: Handoff Review" marker
     - Increment phase_iteration
     - Address all blocker AND warning issues by revising design.md
     - Return to step b
   - If FAIL AND phase_iteration == 5:
     - Store concerns in `stages.handoffReview.reviewerNotes`
     - Proceed to auto-commit with warning

d. **Mark stage completed:**
   ```json
   "stages": {
     "handoffReview": { "started": "...", "completed": "{ISO timestamp}", "iterations": {phase_iteration}, "approved": true/false, "reviewerNotes": [...] }
   }
   ```

e. **Append to review history:**
   ```markdown
   ## Handoff Review - Iteration {n} - {ISO timestamp}

   **Reviewer:** phase-reviewer (gatekeeper)
   **Decision:** {Approved / Needs Revision}

   **Issues:**
   - [{severity}] {description} (at: {location})

   **Changes Made:**
   {Summary of revisions made to address issues}

   ---
   ```

---

### 4b. Capture Review Learnings (Automatic)

**Trigger:** Execute after any review iteration that found blocker or warning issues.

**Two-path capture:**
- **IF exactly 1 iteration with blockers found and fixed:** Store each blocker directly via `store_memory` with `confidence="low"` (single observation, not a confirmed pattern). Budget: max 2 entries.
- **IF 2+ iterations:** Use recurring-pattern grouping logic below. Budget: max 3 entries.

**Process (for 2+ iterations):**
1. Read `.review-history.md` entries for THIS phase only (design-reviewer and phase-reviewer entries)
2. Group issues by description similarity (same category, overlapping file patterns)
3. Identify issues that appeared in 2+ iterations — these are recurring patterns

**For each recurring issue, call `store_memory`:**
- `name`: derived from issue description (max 60 chars)
- `description`: issue description + the suggestion that resolved it
- `reasoning`: "Recurred across {n} review iterations in feature {id} design phase"
- `category`: infer from issue type:
  - Security issues → `anti-patterns`
  - Quality/SOLID/naming → `heuristics`
  - Missing requirements → `anti-patterns`
  - Feasibility/complexity → `heuristics`
  - Scope/assumption issues → `heuristics`
- `references`: ["feature/{id}-{slug}"]
- `confidence`: "low"

**Budget:** Max 3 entries per review cycle to avoid noise.

**Notable catches (single-iteration blockers):**
If the review loop completed in 1 iteration AND the reviewer found issues with severity "blocker":
1. For each blocker issue (max 2):
   - Store via `store_memory` MCP tool:
     - `name`: derived from issue description (max 60 chars)
     - `description`: issue description + the suggestion that resolved it
     - `reasoning`: "Single-iteration blocker catch in feature {id} design phase"
     - `category`: inferred from issue type (same mapping as recurring patterns above)
     - `confidence`: "low"
     - `references`: ["feature/{id}-{slug}"]

**Circuit breaker capture:** If review loop hit max iterations (cap reached) in either step, also capture a single entry:
- `name`: "Design review cap: {brief issue category}"
- `description`: summary of unresolved issues that prevented approval
- `category`: "anti-patterns"
- `confidence`: "low"

**Fallback:** If `store_memory` MCP tool unavailable, use `semantic_memory.writer` CLI.

**Output:** `"Review learnings: {n} patterns captured from {m}-iteration review cycle"` (inline, no prompt)

### 4c. Auto-Commit and Update State

**Construct reviewerNotes before committing:**
```
capReached = (iteration == 5 at Step 3 exit without approval) OR (phase_iteration == 5 at Step 4 exit without approval)
If phase-reviewer response lacks .issues[] or is not valid JSON: reviewerNotes = []
Else if capReached: reviewerNotes = phase-reviewer's final issues[].map(i => {severity: i.severity, description: i.description})
Else: reviewerNotes = phase-reviewer's final issues[].filter(i => i.severity in ["warning", "suggestion"]).map(i => {severity: i.severity, description: i.description})
```

Follow `commitAndComplete("design", ["design.md"], iteration + phase_iteration, capReached, reviewerNotes)` from the **workflow-transitions** skill.

Design additionally records stage-level tracking in `.meta.json` phases.design.stages (architecture, interface, designReview, handoffReview).

### 6. Completion Message

Output: "Design complete."

```
AskUserQuestion:
  questions: [{
    "question": "Design complete. Continue to next phase?",
    "header": "Next Step",
    "options": [
      {"label": "Continue to /pd:create-plan (Recommended)", "description": "Creates plan.md with dependency graphs and workflow tracking"},
      {"label": "Review design.md first", "description": "Inspect the design before continuing"},
      {"label": "Fix and rerun reviews", "description": "Apply fixes then rerun Step 3 + Step 4 review cycle"}
    ],
    "multiSelect": false
  }]
```

If "Continue to /pd:create-plan (Recommended)": Invoke `/pd:create-plan`
If "Review design.md first": Show "Design at {path}/design.md. Run /pd:create-plan when ready." → STOP
If "Fix and rerun reviews": Ask user what needs fixing (plain text via AskUserQuestion with free-text), apply the requested changes to design.md, then reset `resume_state = {}` (clear all entries — the user has made manual edits outside the review loop, so prior agent contexts are stale) and return to Step 3 (design-reviewer) with iteration counters reset to 0.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Read {pd_artifacts_root}/features/ to find active feature, then follow the workflow below.
