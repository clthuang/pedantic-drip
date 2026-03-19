---
description: Create specification for current feature
argument-hint: [--feature=<id-slug>]
---

Invoke the specifying skill for the current feature context.

## Static Reference
## YOLO Mode Overrides

If `[YOLO_MODE]` is active:
- Multiple active features → auto-select most recently created (highest ID)
- Completion prompt → skip AskUserQuestion, directly invoke `/pd:design` with `[YOLO_MODE]`

## Workflow Integration

### 1-3. Validate, Branch Check, Partial Recovery, Mark Started

Follow `validateAndSetup("specify")` from the **workflow-transitions** skill.

### 4. Execute with Two-Step Reviewer Loop

Max iterations: 5.

**Resume state initialization:**
Initialize `resume_state = {}` at the start of the review loop. This dict tracks per-role agent context for resume across iterations. Keys: `"spec-reviewer"`, `"phase-reviewer"`. Each entry: `{ agent_id, iteration1_prompt_length, last_iteration, last_commit_sha }`.

#### Step 1: Spec-Reviewer Review (Quality Gate)

a. **Produce artifact:** Follow the specifying skill to create/revise spec.md

b. **Invoke spec-reviewer:**

   **PRD resolution (I8):** Before dispatching, resolve the PRD reference:
   1. Check if `{feature_path}/prd.md` exists
   2. If exists → PRD line = `- PRD: {feature_path}/prd.md`
   3. If not → check `.meta.json` for `brainstorm_source`
      a. If found → PRD line = `- PRD: {brainstorm_source path}`
      b. If not → PRD line = `- PRD: No PRD — feature created without brainstorm`

   **Dispatch decision for spec-reviewer:**

   **If iteration == 1 OR resume_state["spec-reviewer"] is missing/empty OR resume_state["spec-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

   Use the Task tool to spawn spec-reviewer (the skeptic):
   ```
   Task tool call:
     description: "Skeptical review of spec quality"
     subagent_type: pd:spec-reviewer
     model: opus
     prompt: |
       Skeptically review spec.md for testability, assumptions, and scope discipline.

       Your job: Find weaknesses before design does.
       Be the skeptic. Challenge assumptions. Find gaps.

       ## Required Artifacts
       You MUST read the following files before beginning your review.
       After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
       {resolved PRD line from I8}

       Return your assessment as JSON:
       {
         "approved": true/false,
         "issues": [{"severity": "blocker|warning|suggestion", "category": "...", "description": "...", "location": "...", "suggestion": "..."}],
         "summary": "..."
       }

       ## Spec (what you're reviewing)
       {content of spec.md}

       ## Iteration Context
       This is iteration {n} of {max}.
   ```
   After fresh dispatch: capture the `agent_id` from the Task tool result. Record the character count of the prompt above as `prompt_length`. Capture current HEAD SHA via `Bash: git rev-parse HEAD`. Store in resume_state:
   ```
   resume_state["spec-reviewer"] = {
     "agent_id": {agent_id from Task result},
     "iteration1_prompt_length": {prompt_length} (only set on iteration 1; preserved on subsequent fresh dispatches),
     "last_iteration": {n},
     "last_commit_sha": {HEAD SHA}
   }
   ```
   If this is not iteration 1 (fresh dispatch due to fallback/reset), preserve the original `iteration1_prompt_length` from the first fresh dispatch of this loop if available; otherwise set it from this dispatch's prompt length.

   **If iteration >= 2 AND resume_state["spec-reviewer"] exists with non-null agent_id** — attempt resumed dispatch:

   First, compute the delta. Run the unified three-state git command:
   ```
   Bash: git add {feature_path}/spec.md && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "pd: specify review iteration {n}" && echo COMMIT_OK || echo COMMIT_FAILED)
   ```

   Handle the three outcomes:

   - **NO_CHANGES**: No revisions were committed. Issue a fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated to iteration {n}). Reset `resume_state["spec-reviewer"]` so the fresh dispatch result becomes the new resume anchor. Do NOT use I3 fallback template. Do NOT reuse a prior delta.

   - **COMMIT_FAILED**: Git commit failed. Fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated to iteration {n}). Reset `resume_state["spec-reviewer"]`.

   - **COMMIT_OK**: Commit succeeded. Capture new SHA: `Bash: git rev-parse HEAD` → `new_sha`. Compute delta:
     ```
     Bash: git diff {resume_state["spec-reviewer"].last_commit_sha} HEAD -- {feature_path}/spec.md
     ```
     Capture output as `delta_content`.

     **Delta size guard**: If `len(delta_content)` > 50% of `resume_state["spec-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as iteration 1 above, with iteration context updated to iteration {n}). Reset `resume_state["spec-reviewer"]`.

     **If delta is within threshold**, attempt resumed dispatch:
     ```
     Task tool call:
       resume: {resume_state["spec-reviewer"].agent_id}
       prompt: |
         You already have the upstream artifacts and the previous version of
         spec.md in context from your prior review.

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
           "issues": [{"severity": "blocker|warning|suggestion", "category": "...", "description": "...", "location": "...", "suggestion": "..."}],
           "summary": "..."
         }
     ```

     **If resume succeeds**: Update resume_state:
     ```
     resume_state["spec-reviewer"].agent_id = {agent_id from resumed Task result}
     resume_state["spec-reviewer"].last_iteration = {n}
     resume_state["spec-reviewer"].last_commit_sha = {new_sha}
     ```

     **If resume fails** (Task tool returns an error): Fall back to fresh I1-R4 dispatch (I3 fallback — same template as iteration 1, with additional line in Iteration Context: `"(Fresh dispatch — prior review session unavailable.)"` and previous issues included). Log to `.review-history.md`: `RESUME-FALLBACK: spec-reviewer iteration {n} — {error summary}`. Reset `resume_state["spec-reviewer"]` with the new fresh dispatch's agent_id.

   **Context compaction detection**: Before attempting resume, if `resume_state["spec-reviewer"]` was previously populated but `agent_id` is now null or missing (due to context compaction), treat as fresh I1-R4 dispatch. Log: `RESUME-FALLBACK: spec-reviewer iteration {n} — agent_id lost (context compaction)`.

c. **Parse response:** Extract the `approved` field from reviewer's JSON response.
   - If response is not valid JSON, ask reviewer to retry with correct format.

   **Fallback detection (I9):** Search the agent's response for "Files read:" pattern. If not found, log `LAZY-LOAD-WARNING: spec-reviewer did not confirm artifact reads` to `.review-history.md`. Proceed regardless. Note: Resumed dispatches (I2 template) do not include Required Artifacts, so "Files read:" may not appear — only apply I9 detection to fresh dispatches.

d. **Branch on result (strict threshold):**
   - **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
   - **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"
   - If PASS → Proceed to Step 2
   - If FAIL AND iteration < max:
     - Append iteration to `.review-history.md` with "Step 1: Spec-Reviewer Review" marker
     - Increment iteration counter
     - Address all blocker AND warning issues by revising spec.md
     - Return to step 4b
   - If FAIL AND iteration == max:
     - Note concerns in `.meta.json` reviewerNotes
     - Proceed to Step 2 with warning

#### Step 2: Phase-Reviewer Validation (Handoff Gate)

Phase-reviewer iteration budget: max 5 (independent of Step 1).

Set `phase_iteration = 1`.

e. **Invoke phase-reviewer:**

   **PRD resolution (I8):** Before dispatching, resolve the PRD reference (same logic as Step 1).

   **Dispatch decision for phase-reviewer:**

   **If phase_iteration == 1 OR resume_state["phase-reviewer"] is missing/empty OR resume_state["phase-reviewer"].agent_id is null** — use fresh I1-R4 dispatch:

   ```
   Task tool call:
     description: "Validate spec ready for design"
     subagent_type: pd:phase-reviewer
     model: sonnet
     prompt: |
       Validate this spec is ready for an engineer to design against.

       ## Required Artifacts
       You MUST read the following files before beginning your review.
       After reading, confirm: "Files read: {name} ({N} lines), ..." in a single line.
       {resolved PRD line from I8}
       - Spec: {feature_path}/spec.md

       ## Next Phase Expectations
       Design needs: All requirements listed, acceptance criteria defined,
       scope boundaries clear, no ambiguities.

       Return your assessment as JSON:
       {
         "approved": true/false,
         "issues": [{"severity": "blocker|warning|suggestion", "description": "...", "location": "...", "suggestion": "..."}],
         "summary": "..."
       }

       ## Domain Reviewer Outcome
       - Reviewer: spec-reviewer
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
   Bash: git add {feature_path}/spec.md && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "pd: specify phase-review iteration {phase_iteration}" && echo COMMIT_OK || echo COMMIT_FAILED)
   ```

   Handle the three outcomes:

   - **NO_CHANGES**: No revisions were committed. Issue a fresh I1-R4 dispatch (same template as phase_iteration 1 above, with iteration context updated to phase_iteration {phase_iteration}). Reset `resume_state["phase-reviewer"]` so the fresh dispatch result becomes the new resume anchor. Do NOT use I3 fallback template. Do NOT reuse a prior delta.

   - **COMMIT_FAILED**: Git commit failed. Fall back to fresh I1-R4 dispatch (same template as phase_iteration 1 above, with iteration context updated to phase_iteration {phase_iteration}). Reset `resume_state["phase-reviewer"]`.

   - **COMMIT_OK**: Commit succeeded. Capture new SHA: `Bash: git rev-parse HEAD` → `new_sha`. Compute delta:
     ```
     Bash: git diff {resume_state["phase-reviewer"].last_commit_sha} HEAD -- {feature_path}/spec.md
     ```
     Capture output as `delta_content`.

     **Delta size guard**: If `len(delta_content)` > 50% of `resume_state["phase-reviewer"].iteration1_prompt_length`, the delta is too large — fall back to fresh I1-R4 dispatch (same template as phase_iteration 1 above, with iteration context updated to phase_iteration {phase_iteration}). Reset `resume_state["phase-reviewer"]`.

     **If delta is within threshold**, attempt resumed dispatch:
     ```
     Task tool call:
       resume: {resume_state["phase-reviewer"].agent_id}
       prompt: |
         You already have the upstream artifacts and the previous version of
         spec.md in context from your prior review.

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

f. **Branch on result (strict threshold):**
   - **PASS:** `approved: true` AND zero issues with severity "blocker" or "warning"
   - **FAIL:** `approved: false` OR any issue has severity "blocker" or "warning"
   - If PASS → Proceed to auto-commit
   - If FAIL AND phase_iteration < 5:
     - Append to `.review-history.md` with "Step 2: Phase Review" marker
     - Increment phase_iteration
     - Address all blocker AND warning issues
     - Return to step e
   - If FAIL AND phase_iteration == 5:
     - Store concerns in `.meta.json` phaseReview.reviewerNotes
     - Proceed to auto-commit with warning

g. **Complete phase:** Proceed to auto-commit, then update state.

### 4a. Capture Review Learnings (Automatic)

**Trigger:** Only execute if the review loop ran 2+ iterations (across Step 1 and/or Step 2 combined). If approved on first pass in both stages, skip — no review learnings to capture.

**Process:**
1. Read `.review-history.md` entries for THIS phase only (spec-reviewer and phase-reviewer entries)
2. Group issues by description similarity (same category, overlapping file patterns)
3. Identify issues that appeared in 2+ iterations — these are recurring patterns

**For each recurring issue, call `store_memory`:**
- `name`: derived from issue description (max 60 chars)
- `description`: issue description + the suggestion that resolved it
- `reasoning`: "Recurred across {n} review iterations in feature {id} specify phase"
- `category`: infer from issue type:
  - Security issues → `anti-patterns`
  - Quality/SOLID/naming → `heuristics`
  - Missing requirements → `anti-patterns`
  - Feasibility/complexity → `heuristics`
  - Scope/assumption issues → `heuristics`
- `references`: ["feature/{id}-{slug}"]
- `confidence`: "low"

**Budget:** Max 3 entries per review cycle to avoid noise.

**Circuit breaker capture:** If review loop hit max iterations (cap reached) in either step, also capture a single entry:
- `name`: "Specify review cap: {brief issue category}"
- `description`: summary of unresolved issues that prevented approval
- `category`: "anti-patterns"
- `confidence`: "low"

**Fallback:** If `store_memory` MCP tool unavailable, use `semantic_memory.writer` CLI.

**Output:** `"Review learnings: {n} patterns captured from {m}-iteration review cycle"` (inline, no prompt)

### 4b. Auto-Commit and Update State

Follow `commitAndComplete("specify", ["spec.md"])` from the **workflow-transitions** skill.

**Review History Entry Format** (append to `.review-history.md`):
```markdown
## {Step 1: Spec-Reviewer Review | Step 2: Phase Review} - Iteration {n} - {ISO timestamp}

**Reviewer:** {spec-reviewer (skeptic) | phase-reviewer (gatekeeper)}
**Decision:** {Approved / Needs Revision}

**Issues:**
- [{severity}] [{category}] {description} (at: {location})
  Suggestion: {suggestion}

**Changes Made:**
{Summary of revisions made to address issues}

---
```

### 6. Completion Message

Output: "Specification complete."

```
AskUserQuestion:
  questions: [{
    "question": "Specification complete. Continue to next phase?",
    "header": "Next Step",
    "options": [
      {"label": "Continue to /pd:design (Recommended)", "description": "Create architecture design"},
      {"label": "Review spec.md first", "description": "Inspect the spec before continuing"},
      {"label": "Fix and rerun reviews", "description": "Apply fixes then rerun Step 1 + Step 2 review cycle"}
    ],
    "multiSelect": false
  }]
```

If "Continue to /pd:design (Recommended)": Invoke `/pd:design`
If "Review spec.md first": Show "Spec at {path}/spec.md. Run /pd:design when ready." → STOP
If "Fix and rerun reviews": Ask user what needs fixing (plain text via AskUserQuestion with free-text), apply the requested changes to spec.md, then reset `resume_state = {}` (clear all entries — the user has made manual edits outside the review loop, so prior agent contexts are stale) and return to Step 4 (Step 1 spec-reviewer) with iteration counters reset to 0.

## Config Variables
Use these values from session context (injected at session start):
- `{pd_artifacts_root}` — root directory for feature artifacts (default: `docs`)

## Determine Target Feature

**If `--feature` argument provided:**
- Use `{pd_artifacts_root}/features/{feature}/` directly
- If folder doesn't exist: Error "Feature {feature} not found"
- If `.meta.json` missing: Error "Feature {feature} has no metadata"

**If no argument:**
1. Scan `{pd_artifacts_root}/features/` for folders with `.meta.json` where `status="active"`
2. If none found: "No active feature found. Would you like to /pd:brainstorm to explore ideas first?"
3. If one found: Use that feature
4. If multiple found:
   ```
   AskUserQuestion:
     questions: [{
       "question": "Multiple active features found. Which one?",
       "header": "Feature",
       "options": [dynamically list each active feature as {id}-{slug}],
       "multiSelect": false
     }]
   ```

Once target feature is determined, read feature context and follow the workflow below.
