---
description: Create implementation plan for current feature
argument-hint: "[--feature=<id-slug>]"
---

Invoke the planning skill for the current feature context.

## Static Reference

<!-- Placeholder: static content injected here for prompt cache efficiency -->

### 1-3. Validate, Branch Check, Partial Recovery, Mark Started

Follow `validateAndSetup("create-plan")` from the **workflow-transitions** skill.

**Hard prerequisite:** Before standard validation, validate design.md exists and has substantive content (>100 bytes, has ## headers, has required sections). If validation fails:
```
BLOCKED: Valid design.md required before planning.

{Level 1}: design.md not found. Run /iflow:design first.
{Level 2}: design.md appears empty or stub. Run /iflow:design to complete it.
{Level 3}: design.md missing markdown structure. Run /iflow:design to fix.
{Level 4}: design.md missing required sections (Components or Architecture). Run /iflow:design to add them.
```
Stop execution. Do not proceed.

### 4. Execute with Two-Step Reviewer Loop

Max iterations: 5.

**Resume state initialization:**
Initialize `resume_state = {}` at the start of the review loop. This dict tracks per-role agent context for resume across iterations. Keys: `"plan-reviewer"`, `"phase-reviewer"`. Each entry: `{ agent_id, iteration1_prompt_length, last_iteration, last_commit_sha }`.

#### Step 1: Plan-Reviewer Cycle (Skeptical Review)

a. **Produce artifact:** Follow the planning skill to create/revise plan.md

b. **Invoke plan-reviewer:**

   **PRD resolution (I8):** Before dispatching, resolve the PRD reference:
   1. Check if `{feature_path}/prd.md` exists
   2. If exists → PRD line = `- PRD: {feature_path}/prd.md`
   3. If not → check `.meta.json` for `brainstorm_source`
      a. If found → PRD line = `- PRD: {brainstorm_source path}`
      b. If not → PRD line = `- PRD: No PRD — feature created without brainstorm`

   **Dispatch decision for plan-reviewer:**

   **If iteration == 1 OR resume_state["plan-reviewer"] is missing/empty OR resume_state["plan-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

   Use Task tool:
   ```
   Task tool call:
     description: "Skeptical review of plan for failure modes"
     subagent_type: iflow:plan-reviewer
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

       Return JSON: {"approved": bool, "issues": [{"severity": "blocker|warning|suggestion", "description": "...", "location": "...", "suggestion": "..."}], "summary": "..."}

       ## Plan (what you're reviewing)
       {content of plan.md}
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
   Bash: git add {feature_path}/plan.md && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "iflow: plan review iteration {n}" && echo COMMIT_OK || echo COMMIT_FAILED)
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

d. **Branch on result (strict threshold):**
   - **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
   - **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"
   - If PASS → Proceed to Step 2
   - If FAIL AND iteration < max:
     - Append to `.review-history.md` with "Step 1: Plan Review" marker
     - Address all blocker AND warning issues, return to 4b
   - If FAIL AND iteration == max:
     - Note concerns in `.meta.json` reviewerNotes
     - Proceed to Step 2 with warning

#### Step 2: Chain-Reviewer Validation (Execution Readiness)

Phase-reviewer iteration budget: max 5 (independent of Step 1).

Set `phase_iteration = 1`.

e. **Invoke phase-reviewer**:

   **PRD resolution (I8):** Before dispatching, resolve the PRD reference (same logic as Step 1).

   **Dispatch decision for phase-reviewer:**

   **If phase_iteration == 1 OR resume_state["phase-reviewer"] is missing/empty OR resume_state["phase-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

   ```
   Task tool call:
     description: "Validate plan ready for task breakdown"
     subagent_type: iflow:phase-reviewer
     model: sonnet
     prompt: |
       Validate this plan is ready for an experienced engineer
       to break into executable tasks.

       ## Required Artifacts
       You MUST read the following files before beginning your review.
       After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
       {resolved PRD line from I8}
       - Spec: {feature_path}/spec.md
       - Design: {feature_path}/design.md
       - Plan: {feature_path}/plan.md

       ## Next Phase Expectations
       Tasks needs: Ordered steps with dependencies,
       all design items covered, clear sequencing.

       Return JSON: {"approved": bool, "issues": [{"severity": "blocker|warning|suggestion", "description": "...", "location": "...", "suggestion": "..."}], "summary": "..."}

       ## Domain Reviewer Outcome
       - Reviewer: plan-reviewer
       - Result: {APPROVED at iteration {n}/{max} | FAILED at iteration cap ({max}/{max})}
       - Unresolved issues: {list of remaining blocker/warning descriptions, or "none"}

       This is phase-review iteration {phase_iteration}/5.
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
   Bash: git add {feature_path}/plan.md && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "iflow: plan chain review iteration {phase_iteration}" && echo COMMIT_OK || echo COMMIT_FAILED)
   ```

   Handle the three outcomes:

   - **NO_CHANGES**: No revisions were committed. Issue a fresh I1-R4 dispatch (same template as phase_iteration 1 above, with iteration context updated to phase_iteration {phase_iteration}). Reset `resume_state["phase-reviewer"]` so the fresh dispatch result becomes the new resume anchor. Do NOT use I3 fallback template. Do NOT reuse a prior delta.

   - **COMMIT_FAILED**: Git commit failed. Fall back to fresh I1-R4 dispatch (same template as phase_iteration 1 above, with iteration context updated to phase_iteration {phase_iteration}). Reset `resume_state["phase-reviewer"]`.

   - **COMMIT_OK**: Commit succeeded. Capture new SHA: `Bash: git rev-parse HEAD` → `new_sha`. Compute delta:
     ```
     Bash: git diff {resume_state["phase-reviewer"].last_commit_sha} HEAD -- {feature_path}/plan.md
     ```
     Capture output as `delta_content`.

     **Delta size guard**: If `len(delta_content)` > 50% of `resume_state["phase-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as phase_iteration 1 above, with iteration context updated to phase_iteration {phase_iteration}). Reset `resume_state["phase-reviewer"]`.

     **If delta is within threshold**, attempt resumed dispatch:
     ```
     Task tool call:
       resume: {resume_state["phase-reviewer"].agent_id}
       prompt: |
         You already have the upstream artifacts and the previous version of
         plan.md in context from your prior review.

         The following changes were made to address your previous issues:

         ## Delta
         {delta_content from git diff}

         ## Fix Summary
         {summary of revisions made to address the phase-reviewer's issues}

         Review the changes above. Assess whether your previous issues are resolved
         and check for new issues introduced by the fixes.

         This is phase-review iteration {phase_iteration}/5.

         Return JSON: {"approved": bool, "issues": [{"severity": "blocker|warning|suggestion", "description": "...", "location": "...", "suggestion": "..."}], "summary": "..."}
     ```

     **If resume succeeds**: Update resume_state:
     ```
     resume_state["phase-reviewer"].agent_id = {agent_id from resumed Task result}
     resume_state["phase-reviewer"].last_iteration = {phase_iteration}
     resume_state["phase-reviewer"].last_commit_sha = {new_sha}
     ```

     **If resume fails** (Task tool returns an error): Fall back to fresh I1-R4 dispatch (I3 fallback — same template as phase_iteration 1, with additional line after phase-review iteration line: `"(Fresh dispatch — prior review session unavailable.)"` and previous issues included). Log to `.review-history.md`: `RESUME-FALLBACK: phase-reviewer iteration {phase_iteration} — {error summary}`. Reset `resume_state["phase-reviewer"]` with the new fresh dispatch's agent_id.

   **Context compaction detection**: Before attempting resume, if `resume_state["phase-reviewer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: phase-reviewer iteration {phase_iteration} — agent_id lost (context compaction)`.

f. **Parse response:** Extract `approved` field.

   **Fallback detection (I9):** Search the agent's response for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: phase-reviewer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2 template) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

g. **Branch on result (strict threshold):**
   - **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
   - **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"
   - If PASS → Proceed to step 4h
   - If FAIL AND phase_iteration < 5:
     - Append to `.review-history.md` with "Step 2: Chain Review" marker
     - Increment phase_iteration
     - Address all blocker AND warning issues
     - Return to 4e
   - If FAIL AND phase_iteration == 5:
     - Note concerns in `.meta.json` phaseReview.reviewerNotes
     - Proceed to 4h with warning

h. **Complete phase:** Proceed to auto-commit, then update state.

### 4a. Capture Review Learnings (Automatic)

**Trigger:** Only execute if the review loop ran 2+ iterations (across Step 1 and/or Step 2 combined). If approved on first pass in both steps, skip — no review learnings to capture.

**Process:**
1. Read `.review-history.md` entries for THIS phase only (plan-reviewer and phase-reviewer entries)
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

**Circuit breaker capture:** If review loop hit max iterations (cap reached) in either stage, also capture a single entry:
- `name`: "Plan review cap: {brief issue category}"
- `description`: summary of unresolved issues that prevented approval
- `category`: "anti-patterns"
- `confidence`: "low"

**Fallback:** If `store_memory` MCP tool unavailable, use `semantic_memory.writer` CLI.

**Output:** `"Review learnings: {n} patterns captured from {m}-iteration review cycle"` (inline, no prompt)

### 4b. Auto-Commit and Update State

Follow `commitAndComplete("create-plan", ["plan.md"])` from the **workflow-transitions** skill.

### 6. Completion Message

Output: "Plan complete."

**YOLO Mode:** If `[YOLO_MODE]` is active, skip the AskUserQuestion and directly invoke
`/iflow:create-tasks` with `[YOLO_MODE]` in args.

```
AskUserQuestion:
  questions: [{
    "question": "Plan complete. Continue to next phase?",
    "header": "Next Step",
    "options": [
      {"label": "Continue to /iflow:create-tasks (Recommended)", "description": "Break plan into actionable tasks"},
      {"label": "Review plan.md first", "description": "Inspect the plan before continuing"},
      {"label": "Fix and rerun reviews", "description": "Apply fixes then rerun Step 1 + Step 2 review cycle"}
    ],
    "multiSelect": false
  }]
```

If "Continue to /iflow:create-tasks (Recommended)": Invoke `/iflow:create-tasks`
If "Review plan.md first": Show "Plan at {path}/plan.md. Run /iflow:create-tasks when ready." → STOP
If "Fix and rerun reviews": Ask user what needs fixing (plain text via AskUserQuestion with free-text), apply the requested changes to plan.md, then reset `resume_state = {}` (clear all entries — the user has made manual edits outside the review loop, so prior agent contexts are stale) and return to Step 4 (Step 1 plan-reviewer) with iteration counters reset to 0.

## Config Variables
Use these values from session context (injected at session start):
- `{iflow_artifacts_root}` — root directory for feature artifacts (default: `docs`)

Read {iflow_artifacts_root}/features/ to find active feature, then follow the workflow below.
