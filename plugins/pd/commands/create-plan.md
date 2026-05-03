---
description: Create implementation plan for current feature
argument-hint: "[--feature=<id-slug>]"
---

Invoke the planning skill and breaking-down-tasks skill for the current feature context, producing both plan.md and tasks.md.

## Static Reference

<!-- Placeholder: static content injected here for prompt cache efficiency -->

## Codex Reviewer Routing

Before any reviewer dispatch in this command (plan-reviewer, task-reviewer, phase-reviewer), follow `plugins/pd/references/codex-routing.md`. If `~/.claude/plugins/cache/openai-codex/codex/*/scripts/codex-companion.mjs` exists AND the dispatched reviewer is NOT `pd:security-reviewer`, route the dispatch through Codex's `adversarial-review` (foreground) instead of the pd reviewer Task. Reuse the reviewer's prompt body verbatim. Translate the response per the field-mapping table in the reference doc. Falls back to pd reviewer Task on detection failure or malformed codex output.

### 1-3. Validate, Branch Check, Partial Recovery, Mark Started

Follow `validateAndSetup("create-plan")` from the **workflow-transitions** skill.

**Hard prerequisite:** Before standard validation, validate design.md exists and has substantive content (>100 bytes, has ## headers, has required sections). If validation fails:
```
BLOCKED: Valid design.md required before planning.

{Level 1}: design.md not found. Run /pd:design first.
{Level 2}: design.md appears empty or stub. Run /pd:design to complete it.
{Level 3}: design.md missing markdown structure. Run /pd:design to fix.
{Level 4}: design.md missing required sections (Components or Architecture). Run /pd:design to add them.
```
Stop execution. Do not proceed.

### 4. Execute with Combined Reviewer Loop

Max iterations: 5.

**Resume state initialization:**
Initialize `resume_state = {}` at the start of the review loop. This dict tracks per-role agent context for resume across iterations. Keys: `"plan-reviewer"`, `"task-reviewer"`, `"phase-reviewer"`. Each entry: `{ agent_id, iteration1_prompt_length, last_iteration, last_commit_sha }`.

#### Combined Review Loop (max 5 total iterations)

Each iteration dispatches up to 3 reviewers sequentially. All 3 must pass for APPROVED.

a. **Produce artifacts:**
   - Follow the planning skill to create/revise plan.md
   - Follow the breaking-down-tasks skill to create/revise tasks.md from plan.md

b. **Reviewer 1 — Invoke plan-reviewer:**

   **PRD resolution (I8):** Before dispatching, resolve the PRD reference:
   1. Check if `{feature_path}/prd.md` exists
   2. If exists → PRD line = `- PRD: {feature_path}/prd.md`
   3. If not → check `.meta.json` for `brainstorm_source`
      a. If found → PRD line = `- PRD: {brainstorm_source path}`
      b. If not → PRD line = `- PRD: No PRD — feature created without brainstorm`

   **Dispatch decision for plan-reviewer:**

   **If iteration == 1 OR resume_state["plan-reviewer"] is missing/empty OR resume_state["plan-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

   **Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
   call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
   limit=5, brief=true, and category="anti-patterns".
   Store the returned entry names for post-dispatch influence tracking.
   Include non-empty results inside the prompt below.

   Use Task tool:
   ```
   Task tool call:
     description: "Skeptical review of plan for failure modes"
     subagent_type: pd:plan-reviewer
     model: opus
     prompt: |
       Review this plan for failure modes, untested assumptions,
       dependency accuracy, and TDD order compliance.

       ## Required Artifacts
       You MUST read the following files before beginning your review.
       After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
       {resolved PRD line from I8}
       - Spec: {feature_path}/spec.md
       - Design: {feature_path}/design.md
       - Plan: {feature_path}/plan.md

       Return JSON: {"approved": bool, "issues": [{"severity": "blocker|warning|suggestion", "description": "...", "location": "...", "suggestion": "..."}], "summary": "..."}

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
   resume_state["plan-reviewer"] = {
     "agent_id": {agent_id from Task result},
     "iteration1_prompt_length": {prompt_length} (only set on iteration 1; preserved on subsequent fresh dispatches),
     "last_iteration": {n},
     "last_commit_sha": {HEAD SHA}
   }
   ```
   If this is not iteration 1 (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch of this loop if available; otherwise set it from this dispatch's prompt length.

   **If iteration >= 2 AND resume_state["plan-reviewer"] exists with non-null agent_id** — attempt resumed dispatch:

   First, compute the delta. Run the unified three-state git command:
   ```
   Bash: git add {feature_path}/plan.md && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "pd: plan review iteration {n}" && echo COMMIT_OK || echo COMMIT_FAILED)
   ```

   Handle the three outcomes:

   - **NO_CHANGES**: No revisions were committed. Issue a fresh I1-R4 dispatch (same template as iteration 1 above, with plan content updated). Reset `resume_state["plan-reviewer"]` so the fresh dispatch result becomes the new resume anchor. Do NOT use I3 fallback template. Do NOT reuse a prior delta.

   - **COMMIT_FAILED**: Git commit failed. Fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with plan content updated). Reset `resume_state["plan-reviewer"]`.

   - **COMMIT_OK**: Commit succeeded. Capture new SHA: `Bash: git rev-parse HEAD` → `new_sha`. Compute delta:
     ```
     Bash: git diff {resume_state["plan-reviewer"].last_commit_sha} HEAD -- {feature_path}/plan.md
     ```
     Capture output as `delta_content`.

     **Delta size guard**: If `len(delta_content)` > 50% of `resume_state["plan-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with plan content updated). Reset `resume_state["plan-reviewer"]`.

     **If delta is within threshold**, attempt resumed dispatch:
     ```
     Task tool call:
       resume: {resume_state["plan-reviewer"].agent_id}
       prompt: |
         You already have the upstream artifacts and the previous version of
         plan.md in context from your prior review.

         The following changes were made to address your previous issues:

         ## Delta
         {delta_content from git diff}

         ## Fix Summary
         {summary of revisions made to address the reviewer's issues}

         Review the changes above. Assess whether your previous issues are resolved
         and check for new issues introduced by the fixes.

         This is iteration {n} of {max}.

         Return JSON: {"approved": bool, "issues": [{"severity": "blocker|warning|suggestion", "description": "...", "location": "...", "suggestion": "..."}], "summary": "..."}
     ```

     **If resume succeeds**: Update resume_state:
     ```
     resume_state["plan-reviewer"].agent_id = {agent_id from resumed Task result}
     resume_state["plan-reviewer"].last_iteration = {n}
     resume_state["plan-reviewer"].last_commit_sha = {new_sha}
     ```

     **If resume fails** (Task tool returns an error): Fall back to fresh I1-R4 dispatch (I3 fallback — same template as iteration 1, with additional line after plan content: `"(Fresh dispatch — prior review session unavailable.)"` and previous issues included). Log to `.review-history.md`: `RESUME-FALLBACK: plan-reviewer iteration {n} — {error summary}`. Reset `resume_state["plan-reviewer"]` with the new fresh dispatch's agent_id.

   **Context compaction detection**: Before attempting resume, if `resume_state["plan-reviewer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: plan-reviewer iteration {n} — agent_id lost (context compaction)`.

c. **Parse response:** Extract `approved` field.

   **Fallback detection (I9):** Search the agent's response for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: plan-reviewer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2 template) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

   <!-- influence-tracking-site: s5 -->
   **Influence tracking (mandatory, unconditional):**
   Call `record_influence_by_content(
     subagent_output_text=<full agent output text>,
     injected_entry_names=<list from search_memory results, or [] if none>,
     agent_role="plan-reviewer",
     feature_type_id=<current feature type_id from .meta.json>)`
   Emit one line to your output: `Influence recorded: N matches`.
   On MCP failure: warn "Influence tracking failed: {error}", continue.
   If .meta.json missing or type_id unresolvable: skip with warning.

d. **Branch on plan-reviewer result (strict threshold):**
   - **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
   - **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"
   - If PASS → Proceed to Reviewer 2 (task-reviewer)
   - If FAIL AND iteration < max:
     - Append to `.review-history.md` with "Reviewer 1: Plan Review" marker
     - Address all blocker AND warning issues in plan.md
     - Re-run breaking-down-tasks skill to regenerate tasks.md from revised plan.md
     - Return to 4b (next iteration of combined loop)
   - If FAIL AND iteration == max:
     - Note concerns in `.meta.json` reviewerNotes
     - Proceed to Reviewer 2 (task-reviewer) with warning

#### Reviewer 2: Task-Reviewer Validation (Task Breakdown Quality)

e2. **Invoke task-reviewer:**

   **PRD resolution (I8):** Before dispatching, resolve the PRD reference (same logic as Reviewer 1).

   **Dispatch decision for task-reviewer:**

   **If iteration == 1 OR resume_state["task-reviewer"] is missing/empty OR resume_state["task-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

   **Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
   call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
   limit=5, brief=true, and category="anti-patterns".
   Store the returned entry names for post-dispatch influence tracking.
   Include non-empty results inside the prompt below.

   Use Task tool:
   ```
   Task tool call:
     description: "Review task breakdown quality"
     subagent_type: pd:task-reviewer
     model: sonnet
     prompt: |
       Review the task breakdown for quality and executability.

       ## Required Artifacts
       You MUST read the following files before beginning your review.
       After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
       {resolved PRD line from I8}
       - Spec: {feature_path}/spec.md
       - Design: {feature_path}/design.md
       - Plan: {feature_path}/plan.md
       - Tasks: {feature_path}/tasks.md

       Validate:
       1. Plan fidelity - every plan item has tasks
       2. Task executability - any engineer can start immediately
       3. Task size - 5-15 min each
       4. Dependency accuracy - parallel groups correct
       5. Testability - binary done criteria

       Return your assessment as JSON:
       {
         "approved": true/false,
         "issues": [{"severity": "blocker|warning|suggestion", "task": "...", "description": "...", "suggestion": "..."}],
         "summary": "..."
       }

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
   resume_state["task-reviewer"] = {
     "agent_id": {agent_id from Task result},
     "iteration1_prompt_length": {prompt_length} (only set on iteration 1; preserved on subsequent fresh dispatches),
     "last_iteration": {n},
     "last_commit_sha": {HEAD SHA}
   }
   ```
   If this is not iteration 1 (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch of this loop if available; otherwise set it from this dispatch's prompt length.

   **If iteration >= 2 AND resume_state["task-reviewer"] exists with non-null agent_id** — attempt resumed dispatch:

   First, compute the delta. Run the unified three-state git command:
   ```
   Bash: git add {feature_path}/tasks.md && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "pd: tasks review iteration {n}" && echo COMMIT_OK || echo COMMIT_FAILED)
   ```

   Handle the three outcomes:

   - **NO_CHANGES**: No revisions were committed. Issue a fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated). Reset `resume_state["task-reviewer"]` so the fresh dispatch result becomes the new resume anchor. Do NOT use I3 fallback template. Do NOT reuse a prior delta.

   - **COMMIT_FAILED**: Git commit failed. Fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated). Reset `resume_state["task-reviewer"]`.

   - **COMMIT_OK**: Commit succeeded. Capture new SHA: `Bash: git rev-parse HEAD` → `new_sha`. Compute delta:
     ```
     Bash: git diff {resume_state["task-reviewer"].last_commit_sha} HEAD -- {feature_path}/tasks.md
     ```
     Capture output as `delta_content`.

     **Delta size guard**: If `len(delta_content)` > 50% of `resume_state["task-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated). Reset `resume_state["task-reviewer"]`.

     **If delta is within threshold**, attempt resumed dispatch:
     ```
     Task tool call:
       resume: {resume_state["task-reviewer"].agent_id}
       prompt: |
         You already have the upstream artifacts and the previous version of
         tasks.md in context from your prior review.

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
           "issues": [{"severity": "blocker|warning|suggestion", "task": "...", "description": "...", "suggestion": "..."}],
           "summary": "..."
         }
     ```

     **If resume succeeds**: Update resume_state:
     ```
     resume_state["task-reviewer"].agent_id = {agent_id from resumed Task result}
     resume_state["task-reviewer"].last_iteration = {n}
     resume_state["task-reviewer"].last_commit_sha = {new_sha}
     ```

     **If resume fails** (Task tool returns an error): Fall back to fresh I1-R4 dispatch (I3 fallback — same template as iteration 1, with additional line: `"(Fresh dispatch — prior review session unavailable.)"` and previous issues included). Log to `.review-history.md`: `RESUME-FALLBACK: task-reviewer iteration {n} — {error summary}`. Reset `resume_state["task-reviewer"]` with the new fresh dispatch's agent_id.

   **Context compaction detection**: Before attempting resume, if `resume_state["task-reviewer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: task-reviewer iteration {n} — agent_id lost (context compaction)`.

e3. **Parse task-reviewer response:** Extract `approved` field.

   **Fallback detection (I9):** Search the agent's response for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: task-reviewer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2 template) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

   <!-- influence-tracking-site: s6 -->
   **Influence tracking (mandatory, unconditional):**
   Call `record_influence_by_content(
     subagent_output_text=<full agent output text>,
     injected_entry_names=<list from search_memory results, or [] if none>,
     agent_role="task-reviewer",
     feature_type_id=<current feature type_id from .meta.json>)`
   Emit one line to your output: `Influence recorded: N matches`.
   On MCP failure: warn "Influence tracking failed: {error}", continue.
   If .meta.json missing or type_id unresolvable: skip with warning.

e4. **Branch on task-reviewer result (strict threshold):**
   - **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
   - **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"
   - If PASS → Proceed to Reviewer 3 (phase-reviewer)
   - If FAIL AND iteration < max:
     - Append to `.review-history.md` with "Reviewer 2: Task Review" marker
     - Address all blocker AND warning issues in tasks.md
     - Return to 4b (next iteration of combined loop)
   - If FAIL AND iteration == max:
     - Note concerns in `.meta.json` taskReview.concerns
     - Proceed to Reviewer 3 (phase-reviewer) with warning

#### Reviewer 3: Phase-Reviewer Validation (Execution Readiness)

e5. **Invoke phase-reviewer:**

   **PRD resolution (I8):** Before dispatching, resolve the PRD reference (same logic as Reviewer 1).

   **Dispatch decision for phase-reviewer:**

   **If iteration == 1 OR resume_state["phase-reviewer"] is missing/empty OR resume_state["phase-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

   **Pre-dispatch memory enrichment:** Before building the dispatch prompt below,
   call `search_memory` with query: "{agent role} {task context} {space-separated file list}",
   limit=5, brief=true.
   Store the returned entry names for post-dispatch influence tracking.
   Include non-empty results inside the prompt below.

   ```
   Task tool call:
     description: "Validate plan and tasks ready for implementation"
     subagent_type: pd:phase-reviewer
     model: sonnet
     prompt: |
       Validate this plan and task breakdown are ready for implementation.

       ## Required Artifacts
       You MUST read the following files before beginning your review.
       After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
       {resolved PRD line from I8}
       - Spec: {feature_path}/spec.md
       - Design: {feature_path}/design.md
       - Plan: {feature_path}/plan.md
       - Tasks: {feature_path}/tasks.md

       ## Next Phase Expectations
       Implement needs: Small actionable tasks (<15 min each),
       clear acceptance criteria per task, dependency graph for parallel execution.

       Return JSON: {"approved": bool, "issues": [{"severity": "blocker|warning|suggestion", "description": "...", "location": "...", "suggestion": "..."}], "summary": "..."}

       ## Domain Reviewer Outcomes
       - Reviewer: plan-reviewer
       - Result: {APPROVED at iteration {n}/{max} | FAILED at iteration cap ({max}/{max})}
       - Unresolved issues: {list of remaining blocker/warning descriptions, or "none"}

       - Reviewer: task-reviewer
       - Result: {APPROVED at iteration {n}/{max} | FAILED at iteration cap ({max}/{max})}
       - Unresolved issues: {list of remaining blocker/warning descriptions, or "none"}

       This is combined review iteration {iteration}/{max}.

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
     "iteration1_prompt_length": {prompt_length} (only set on iteration 1; preserved on subsequent fresh dispatches),
     "last_iteration": {iteration},
     "last_commit_sha": {HEAD SHA}
   }
   ```
   If this is not iteration 1 (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch of this stage if available; otherwise set it from this dispatch's prompt length.

   **If iteration >= 2 AND resume_state["phase-reviewer"] exists with non-null agent_id** — attempt resumed dispatch:

   First, compute the delta. Run the unified three-state git command:
   ```
   Bash: git add {feature_path}/plan.md {feature_path}/tasks.md && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "pd: chain review iteration {iteration}" && echo COMMIT_OK || echo COMMIT_FAILED)
   ```

   Handle the three outcomes:

   - **NO_CHANGES**: No revisions were committed. Issue a fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated). Reset `resume_state["phase-reviewer"]` so the fresh dispatch result becomes the new resume anchor. Do NOT use I3 fallback template. Do NOT reuse a prior delta.

   - **COMMIT_FAILED**: Git commit failed. Fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated). Reset `resume_state["phase-reviewer"]`.

   - **COMMIT_OK**: Commit succeeded. Capture new SHA: `Bash: git rev-parse HEAD` → `new_sha`. Compute delta:
     ```
     Bash: git diff {resume_state["phase-reviewer"].last_commit_sha} HEAD -- {feature_path}/plan.md {feature_path}/tasks.md
     ```
     Capture output as `delta_content`.

     **Delta size guard**: If `len(delta_content)` > 50% of `resume_state["phase-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated). Reset `resume_state["phase-reviewer"]`.

     **If delta is within threshold**, attempt resumed dispatch:
     ```
     Task tool call:
       resume: {resume_state["phase-reviewer"].agent_id}
       prompt: |
         You already have the upstream artifacts and the previous versions of
         plan.md and tasks.md in context from your prior review.

         The following changes were made to address your previous issues:

         ## Delta
         {delta_content from git diff}

         ## Fix Summary
         {summary of revisions made to address the phase-reviewer's issues}

         Review the changes above. Assess whether your previous issues are resolved
         and check for new issues introduced by the fixes.

         This is combined review iteration {iteration}/{max}.

         Return JSON: {"approved": bool, "issues": [{"severity": "blocker|warning|suggestion", "description": "...", "location": "...", "suggestion": "..."}], "summary": "..."}
     ```

     **If resume succeeds**: Update resume_state:
     ```
     resume_state["phase-reviewer"].agent_id = {agent_id from resumed Task result}
     resume_state["phase-reviewer"].last_iteration = {iteration}
     resume_state["phase-reviewer"].last_commit_sha = {new_sha}
     ```

     **If resume fails** (Task tool returns an error): Fall back to fresh I1-R4 dispatch (I3 fallback — same template as iteration 1, with additional line: `"(Fresh dispatch — prior review session unavailable.)"` and previous issues included). Log to `.review-history.md`: `RESUME-FALLBACK: phase-reviewer iteration {iteration} — {error summary}`. Reset `resume_state["phase-reviewer"]` with the new fresh dispatch's agent_id.

   **Context compaction detection**: Before attempting resume, if `resume_state["phase-reviewer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: phase-reviewer iteration {iteration} — agent_id lost (context compaction)`.

e6. **Parse phase-reviewer response:** Extract `approved` field.

   **Fallback detection (I9):** Search the agent's response for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: phase-reviewer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2 template) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

   <!-- influence-tracking-site: s7 -->
   **Influence tracking (mandatory, unconditional):**
   Call `record_influence_by_content(
     subagent_output_text=<full agent output text>,
     injected_entry_names=<list from search_memory results, or [] if none>,
     agent_role="phase-reviewer",
     feature_type_id=<current feature type_id from .meta.json>)`
   Emit one line to your output: `Influence recorded: N matches`.
   On MCP failure: warn "Influence tracking failed: {error}", continue.
   If .meta.json missing or type_id unresolvable: skip with warning.

e7. **Branch on phase-reviewer result (strict threshold):**
   - **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
   - **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"
   - If PASS → All 3 reviewers approved. Proceed to step 4h.
   - If FAIL AND iteration < max:
     - Append to `.review-history.md` with "Reviewer 3: Chain Review" marker
     - Address all blocker AND warning issues in plan.md and/or tasks.md
     - Return to 4b (next iteration of combined loop)
   - If FAIL AND iteration == max:
     - Note concerns in `.meta.json` phaseReview.reviewerNotes
     - Proceed to 4h with warning

h. **Complete phase:** Proceed to auto-commit, then update state.

### 4a. Capture Review Learnings (Automatic)

**Trigger:** Execute after any review iteration that found blocker or warning issues.

**Two-path capture:**
- **IF exactly 1 iteration with blockers found and fixed:** Store each blocker directly via `store_memory` with `confidence="low"` (single observation, not a confirmed pattern). Budget: max 2 entries.
- **IF 2+ iterations:** Use recurring-pattern grouping logic below. Budget: max 3 entries.

**Process (for 2+ iterations):**
1. Read `.review-history.md` entries for THIS phase only (plan-reviewer, task-reviewer, and phase-reviewer entries)
2. Group issues by description similarity (same category, overlapping file patterns)
3. Identify issues that appeared in 2+ iterations — these are recurring patterns

**For each recurring issue, call `store_memory`:**
- `name`: derived from issue description (max 60 chars)
- `description`: issue description + the suggestion that resolved it
- `reasoning`: "Recurred across {n} review iterations in feature {id} create-plan phase"
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
     - `reasoning`: "Single-iteration blocker catch in feature {id} create-plan phase"
     - `category`: inferred from issue type (same mapping as recurring patterns above)
     - `confidence`: "low"
     - `references`: ["feature/{id}-{slug}"]

**Circuit breaker capture:** If review loop hit max iterations (cap reached) in either stage, also capture a single entry:
- `name`: "Plan review cap: {brief issue category}"
- `description`: summary of unresolved issues that prevented approval
- `category`: "anti-patterns"
- `confidence`: "low"

**Fallback:** If `store_memory` MCP tool unavailable, use `semantic_memory.writer` CLI.

**Output:** `"Review learnings: {n} patterns captured from {m}-iteration review cycle"` (inline, no prompt)

### 4b. Auto-Commit and Update State

**Construct reviewerNotes before committing:**
```
capReached = (iteration == max at combined loop exit without all 3 reviewers approving)
If phase-reviewer response lacks .issues[] or is not valid JSON: reviewerNotes = []
Else if capReached: reviewerNotes = phase-reviewer's final issues[].map(i => {severity: i.severity, description: i.description})
Else: reviewerNotes = phase-reviewer's final issues[].filter(i => i.severity in ["warning", "suggestion"]).map(i => {severity: i.severity, description: i.description})
```

Follow `commitAndComplete("create-plan", ["plan.md", "tasks.md"], iteration, capReached, reviewerNotes)` from the **workflow-transitions** skill.

### Relevance Gate (Pre-Implementation Coherence Check)

After commitAndComplete succeeds, before auto-chaining to implement:

**Pre-dispatch memory enrichment:** call `search_memory` with query: "relevance-verifier artifact coherence spec design plan tasks", limit=5, brief=true, category="anti-patterns".

Dispatch relevance-verifier:
```
Task tool call:
  description: "Pre-implementation relevance verification"
  subagent_type: pd:relevance-verifier
  model: opus
  prompt: |
    Verify the full artifact chain is coherent before implementation.

    ## Required Artifacts
    Read these files:
    - Spec: {feature_path}/spec.md
    - Design: {feature_path}/design.md
    - Plan: {feature_path}/plan.md
    - Tasks: {feature_path}/tasks.md

    Run all 4 checks: coverage, completeness, testability, coherence.

    Return JSON with pass/fail per check, gaps, and optional backward_to.

    ## Relevant Engineering Memory
    {search_memory results}
```

**Handle result:**
- If `pass == true`: proceed to auto-chain (/pd:implement)
- If `pass == false` AND `backward_to` exists:
  - Invoke `handleReviewerResponse()` with the gate's response (triggers backward travel)
- If `pass == false` AND no `backward_to`:
  - In YOLO mode: output message containing "relevance verification failed" (safety keyword triggers halt)
  - In interactive mode: present results, user decides

### 6. Completion Message

Output: "Plan and tasks complete."

**YOLO Mode:** If `[YOLO_MODE]` is active, skip the AskUserQuestion and directly invoke
`/pd:implement` with `[YOLO_MODE]` in args.

```
AskUserQuestion:
  questions: [{
    "question": "Plan and tasks complete. Continue to next phase?",
    "header": "Next Step",
    "options": [
      {"label": "Continue to /pd:implement (Recommended)", "description": "Begin implementing the plan and tasks"},
      {"label": "Review artifacts first", "description": "Inspect plan.md and tasks.md before continuing"},
      {"label": "Fix and rerun reviews", "description": "Apply fixes then rerun the combined review cycle"}
    ],
    "multiSelect": false
  }]
```

If "Continue to /pd:implement (Recommended)": Invoke `/pd:implement`
If "Review artifacts first": Show "Plan at {path}/plan.md, tasks at {path}/tasks.md. Run /pd:implement when ready." → STOP
If "Fix and rerun reviews": Ask user what needs fixing (plain text via AskUserQuestion with free-text), apply the requested changes to plan.md and/or tasks.md, then reset `resume_state = {}` (clear all entries — the user has made manual edits outside the review loop, so prior agent contexts are stale) and return to Step 4 (combined review loop) with iteration counter reset to 0.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Read {pd_artifacts_root}/features/ to find active feature, then follow the workflow below.
