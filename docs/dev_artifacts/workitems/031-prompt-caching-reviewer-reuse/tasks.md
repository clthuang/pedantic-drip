# Tasks: Prompt Caching & Reviewer Reuse

## Task 1: Execute R1.0 validation gate (V1-V4)

- **Phase:** 1 — Validation Gate
- **File(s):** None modified (interactive). `.meta.json` updated only if tests fail.
- **Dependencies:** None
- **Description:** Execute 3 total Task tool calls: (1) V1 fresh dispatch — `Task({ subagent_type: "iflow:spec-reviewer", prompt: "Review spec.md at docs/features/031-prompt-caching-reviewer-reuse/spec.md. Read the file, list any obvious issues you notice, and report the first line of the file verbatim." })` — triggers Read tool use (V1) and produces a countable issue list for V4. Capture `agentId` from the Task tool result. (2) V2+V3 combined resume — `Task({ resume: agentId, prompt: "Confirm you can still respond. Also repeat verbatim the first line of the file you read." })` — V2 is pass-by-absence-of-error (if the resume call returns a response without throwing, V2 passes; a 400 error or timeout means V2 fails), V3 is pass-by-content (if the response contains the correct first line of spec.md, V3 passes). (3) V4 separate resume — `Task({ resume: agentId, prompt: "How many issues did you find?" })` — verify prior output accessible (V4 passes if the response references a specific count from the V1 review, including 0 if no issues were found). Per design I10, use simplified prompts — this validates the resume mechanism, not full template behavior.
  - **Pass path:** If all V1-V4 pass, no file is modified. Gate decision is recorded as a session note: "R1 APPROVED — all V1-V4 passed." No `.meta.json` update needed.
  - **Fail path:** If any test fails, write `r1_deferred_reason` to `docs/dev_artifacts/workitems/031-prompt-caching-reviewer-reuse/.meta.json` with the failing test ID and reason.
- **Acceptance criteria:**
  - V2/V3 disambiguation: if the combined call returns without API error but contains the wrong first line, record V2=PASS and V3=FAIL separately. The gate fails due to V3.
  - V1-V4 each has binary pass/fail recorded in the session
  - Gate decision documented: "R1 APPROVED" or "R1 DEFERRED: {test_id}: {reason}"
  - If deferred: `docs/dev_artifacts/workitems/031-prompt-caching-reviewer-reuse/.meta.json` contains `r1_deferred_reason` field
  - If approved: no file changes, session note only

## Task 2: R4 reorder specify.md dispatch prompts

- **Phase:** 2 — R4 Prompt Reordering
- **File(s):** `plugins/iflow/commands/specify.md`
- **Dependencies:** None
- **Description:** Reorder both dispatch prompts (spec-reviewer Stage 1, phase-reviewer Stage 2) to place static content before dynamic content per I1-R4 canonical skeleton. For spec-reviewer: move rubric coda ("Your job: Find weaknesses...") into section 1, move JSON schema above spec content and iteration context. PRD is the only Required Artifact. For phase-reviewer: move Next Phase Expectations to stable prefix (above domain outcome), move JSON schema above domain outcome and iteration context. Do NOT change JSON schema content, field names, or approval/rejection logic.
- **Acceptance criteria:**
  - spec-reviewer prompt: rubric → rubric coda → Required Artifacts → JSON schema → spec content → iteration context
  - phase-reviewer prompt: rubric → Required Artifacts → Next Phase Expectations → JSON schema → domain outcome → iteration context
  - No change to JSON schema field names or structure
  - No change to approval/rejection branching logic
  - spec-reviewer Required Artifacts section contains only PRD path (spec.md is inline as artifact-under-review, not listed as Required Artifact)
  - PRD resolution conditional preserved: when no brainstorm artifact exists, Required Artifacts emits `- PRD: No PRD — feature created without brainstorm` (I8 resolve_prd logic unchanged by reorder)

## Task 3: R4 reorder design.md dispatch prompts

- **Phase:** 2 — R4 Prompt Reordering
- **File(s):** `plugins/iflow/commands/design.md`
- **Dependencies:** None (parallel with Tasks 2, 4, 5)
- **Description:** Reorder design-reviewer (Stage 3) and phase-reviewer (Stage 4) dispatch prompts. For design-reviewer: move rubric coda into section 1, move JSON schema above design content and iteration context. Preserve `"suggestion"` field name (not `"challenge"`). For phase-reviewer: move Next Phase Expectations to stable prefix, move JSON schema above domain outcome and iteration context.
- **Acceptance criteria:**
  - design-reviewer prompt: rubric → rubric coda → Required Artifacts → JSON schema → design content → iteration context
  - phase-reviewer prompt: rubric → Required Artifacts → Next Phase Expectations → JSON schema → domain outcome → iteration context
  - `"suggestion"` field name preserved in design-reviewer schema
  - No change to approval/rejection logic

## Task 4: R4 reorder create-plan.md dispatch prompts

- **Phase:** 2 — R4 Prompt Reordering
- **File(s):** `plugins/iflow/commands/create-plan.md`
- **Dependencies:** None (parallel with Tasks 2, 3, 5)
- **Description:** Reorder plan-reviewer (Stage 1) and phase-reviewer (Stage 2) dispatch prompts. For plan-reviewer: move compact JSON schema above plan content. No rubric coda, no iteration context for plan-reviewer. For phase-reviewer: same pattern as other commands.
- **Acceptance criteria:**
  - plan-reviewer prompt: rubric → Required Artifacts → JSON schema → plan content
  - phase-reviewer prompt: rubric → Required Artifacts → Next Phase Expectations → JSON schema → domain outcome → iteration context
  - No change to compact JSON format for plan-reviewer

## Task 5: R4 reorder create-tasks.md dispatch prompts

- **Phase:** 2 — R4 Prompt Reordering
- **File(s):** `plugins/iflow/commands/create-tasks.md`
- **Dependencies:** None (parallel with Tasks 2, 3, 4)
- **Description:** Reorder task-reviewer (Stage 1) and phase-reviewer (Stage 2) dispatch prompts. For task-reviewer: move validate checklist (plan fidelity, executability, size, dependencies, testability) and JSON schema above tasks content. Validate checklist is static — part of stable prefix. For phase-reviewer: same pattern.
- **Acceptance criteria:**
  - task-reviewer prompt: rubric → Required Artifacts → validate checklist → JSON schema → tasks content
  - phase-reviewer prompt: rubric → Required Artifacts → Next Phase Expectations → JSON schema → domain outcome → iteration context
  - `"task"` field preserved in task-reviewer schema (not `"location"`)

## Task 6: R4 reorder implement.md dispatch prompts

- **Phase:** 2 — R4 Prompt Reordering
- **File(s):** `plugins/iflow/commands/implement.md`
- **Dependencies:** None (parallel with Tasks 2-5, but recommended last in Phase 2)
- **Description:**
  - **Pre-step 1 (baseline):** Run `grep -c "reviewer_status" plugins/iflow/commands/implement.md` and record the output as `BASELINE_COUNT`.
  - **Pre-step 2 (verification only):** Read `plugins/iflow/agents/implementation-reviewer.md` (flat file, not subdirectory) to confirm the agent's actual output schema. The full schema includes: `{"approved": true/false, "levels": {"tasks": {"passed": bool, "issues_count": N}, "spec": {...}, "design": {...}, "prd": {...}}, "issues": [{"severity": "blocker|warning|suggestion", "level": "tasks|spec|design|prd", "category": "missing|extra|misunderstood|incomplete", "description": "...", "location": "...", "suggestion": "..."}], "evidence": {"verified": [], "missing": []}, "summary": "..."}`. Use this full schema in the explicit JSON schema block.
  - Reorder 4 dispatch prompts: implementation-reviewer (7a), code-quality-reviewer (7b), security-reviewer (7c), implementer fix (7e). For implementation-reviewer: add explicit JSON schema block with the schema above, replacing prose instruction ("Return JSON with approval status..."), move validate levels above file list. For code-quality-reviewer and security-reviewer: move check lists above file lists, move JSON schema above file lists. Preserve selective re-dispatch logic and `reviewer_status` tracking.
  - **Post-edit verification:** Run `grep -c "reviewer_status" plugins/iflow/commands/implement.md` and confirm the count equals `BASELINE_COUNT`. Also verify 7a/7b/7c dispatch blocks still reference `reviewer_status` values.
- **Acceptance criteria:**
  - implementation-reviewer (7a): rubric → Required Artifacts → validate levels → explicit JSON schema with `"approved":` field → file list
  - code-quality-reviewer (7b): rubric → Required Artifacts → check list → JSON schema → file list
  - security-reviewer (7c): rubric → Required Artifacts → check list → JSON schema → file list
  - `grep '"approved"'` within the 7a dispatch block returns a match (old prose did not contain this literal)
  - `grep '"levels"'` within the 7a dispatch block returns a match (confirms full schema, not truncated)
  - Selective re-dispatch logic and `reviewer_status` tracking unchanged

## Task 7: R4 Checkpoint verification

- **Phase:** 2 — R4 Prompt Reordering (verification gate)
- **File(s):** None modified
- **Dependencies:** Tasks 2, 3, 4, 5, 6 (all R4 items complete)
- **Description:** Verify both schema presence and section ordering across all 5 command files. Step 0a (header discovery): Run `grep -n "^## " plugins/iflow/commands/specify.md` (and each other command file) to collect the actual section header text used for artifact content sections. Record the discovered headers — e.g., if specify.md uses `## Spec (what you're reviewing)`, record that exact text. Step 0b (baseline): For each command file, substitute its discovered header into a grep pattern, escaping special regex characters with `\` (parentheses → `\(`, brackets → `\[`, etc.). For example, if Step 0a reveals specify.md uses `## Spec (what you're reviewing)`, run: `grep -En '"approved"|## Spec \(what' plugins/iflow/commands/specify.md`. Repeat for each of the 5 command files by substituting the file-specific header discovered in Step 0a. Confirm at least one match per pattern per file — zero matches means the pattern needs adjusting, not that the test passed. **If actual headers differ from expected patterns**: update the grep pattern to match reality before proceeding. Do NOT skip the checkpoint. Step 1: `grep -n '"approved"' plugins/iflow/commands/*.md` — confirm JSON schema blocks exist in all dispatch prompts. Expect at least 1 match per command file (5 files). Step 2: For each command file, verify the `"approved"` line number is LESS THAN the corresponding artifact content section line number within the same dispatch block.
- **Acceptance criteria:**
  - Step 0 confirms patterns match actual file content (non-vacuous)
  - All 5 command files have JSON schema blocks containing `"approved"` (Step 1 returns >= 5 matches)
  - In each dispatch block, JSON schema line number < artifact content section line number
  - No regressions in file structure

## Task 8: R1 resume logic in specify.md

- **Phase:** 3 — R1 Resume Logic (conditional on Task 1 pass)
- **File(s):** `plugins/iflow/commands/specify.md`
- **Dependencies:** Task 1 (R1.0 must pass), Task 2 (R4 reorder specify.md)
- **Skip condition:** If Task 1 resulted in "R1 DEFERRED", skip this task and Tasks 9-12.
- **Description:** Add resume_state tracking and resume dispatch logic for both spec-reviewer (Stage 1) and phase-reviewer (Stage 2) review loops. This establishes the pattern for all other command files. Implement: (a) resume_state dict initialized after iteration 1, (b) unified three-state git command after revisions: `git add {feature_path}/spec.md && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "iflow: specify review iteration {n}" && echo COMMIT_OK || echo COMMIT_FAILED)` where `{n}` is the iteration number and `{feature_path}` is the active feature's artifact directory, (c) git diff delta computation on COMMIT_OK: `git diff {last_commit_sha} HEAD -- {feature_path}/spec.md`, (d) delta size guard (50% of iteration1_prompt_length), (e) I2 resumed prompt template for iteration 2+, (f) I3 fallback on resume error with RESUME-FALLBACK logging to `.review-history.md` — also triggered if context compaction loses agent_id, (g) resume_state reset on "Fix and rerun reviews", (h) COMMIT_FAILED → fresh dispatch per TD2 fallback.
- **Acceptance criteria:**
  - Iteration 1 dispatches fresh with I1-R4 template, stores agent_id + prompt length + commit SHA in resume_state
  - Iteration 2+ uses `Task({ resume: agent_id, prompt: delta })` when delta ≤ 50%
  - Delta > 50% triggers fresh dispatch, resets resume_state for that role
  - Resume error triggers I3 fallback + `RESUME-FALLBACK` marker logged
  - NO_CHANGES → issue a fresh I1-R4 dispatch (plain I1-R4 template, NOT I3 fallback). Use the same template structure as iteration 1 with iteration context updated to iteration N. Do NOT reuse a prior delta. Reset resume_state[role] so the fresh dispatch result becomes the new resume anchor.
  - COMMIT_FAILED → falls back to fresh I1-R4 dispatch, resume_state[role] reset
  - Context compaction fallback: before each resume attempt, check if `resume_state[role]` exists and has a non-null `agent_id`. If not (due to context compaction or any other loss), treat as fresh dispatch with I1-R4 template. Log `RESUME-FALLBACK` if the agent_id was previously populated but is now missing.
  - resume_state tracks: agent_id, iteration1_prompt_length, last_iteration, last_commit_sha

## Task 9: R1 resume logic in design.md

- **Phase:** 3 — R1 Resume Logic
- **File(s):** `plugins/iflow/commands/design.md`
- **Dependencies:** Task 1 (R1.0 pass), Task 3 (R4 reorder design.md), Task 8 (pattern established)
- **Skip condition:** If Task 1 "R1 DEFERRED", skip.
- **Description:** Apply the resume pattern from Task 8 to design-reviewer (Stage 3) and phase-reviewer (Stage 4) review loops. Same resume_state management, git commit+diff, delta guard, I2 template, I3 fallback, COMMIT_FAILED fallback. Preserve design-reviewer's `"suggestion"` field in I2 template JSON schema.
- **Acceptance criteria:**
  - Same as Task 8 criteria, applied to design.md's two review loops
  - Design-reviewer `"suggestion"` field preserved in I2 resumed template

## Task 10: R1 resume logic in create-plan.md

- **Phase:** 3 — R1 Resume Logic
- **File(s):** `plugins/iflow/commands/create-plan.md`
- **Dependencies:** Task 1 (R1.0 pass), Task 4 (R4 reorder create-plan.md), Task 8 (pattern)
- **Skip condition:** If Task 1 "R1 DEFERRED", skip.
- **Description:** Apply resume pattern to plan-reviewer (Stage 1) and phase-reviewer (Stage 2). Plan-reviewer has no iteration context and compact JSON — adapt I2 template accordingly.
- **Acceptance criteria:**
  - Same as Task 8 criteria, applied to create-plan.md's two review loops
  - Plan-reviewer's compact JSON format preserved in I2 template

## Task 11: R1 resume logic in create-tasks.md

- **Phase:** 3 — R1 Resume Logic
- **File(s):** `plugins/iflow/commands/create-tasks.md`
- **Dependencies:** Task 1 (R1.0 pass), Task 5 (R4 reorder create-tasks.md), Task 8 (pattern)
- **Skip condition:** If Task 1 "R1 DEFERRED", skip.
- **Description:** Apply resume pattern to task-reviewer (Stage 1) and phase-reviewer (Stage 2). Task-reviewer uses `"task"` field instead of `"location"` — adapt I2 template accordingly.
- **Acceptance criteria:**
  - Same as Task 8 criteria, applied to create-tasks.md's two review loops
  - Task-reviewer `"task"` field preserved in I2 template

## Task 12: R1 resume logic in implement.md

- **Phase:** 3 — R1 Resume Logic
- **File(s):** `plugins/iflow/commands/implement.md`
- **Dependencies:** Task 1 (R1.0 pass), Task 6 (R4 reorder implement.md), Task 8 (pattern)
- **Skip condition:** If Task 1 "R1 DEFERRED", skip.
- **Description:** Add resume logic for selective re-dispatch reviewers (7a/7b/7c), implementer fix dispatch (7e), and final validation (R1.9). Implement: (a) resume_state dict tracking 4 roles (implementation-reviewer, code-quality-reviewer, security-reviewer, implementer), (b) I2 resumed template for failed reviewer re-dispatch, (c) I2-FV template for final validation (no delta size guard per design), (d) I7 resumed template for implementer fix iteration 2+, (e) `git add -A` per design TD2 for per-iteration commits, (f) I3 fallback + RESUME-FALLBACK logging — also triggered if context compaction loses agent_id, (g) Template Selection Decision Matrix logic (9 scenarios from design), (h) COMMIT_OK/COMMIT_FAILED detection. `resume_state` persists across all iterations including final validation.
- **Acceptance criteria:**
  - Selective re-dispatch logic preserved (only failed reviewers re-dispatched)
  - Final validation resumes passing reviewers with I2-FV template
  - Implementer fix iteration 2+ uses I7 resumed template with new issues + changed files
  - All 9 Template Selection Decision Matrix scenarios have distinct code branches. After implementation, verify with: `grep -n "I2-FV\|I7 resumed\|I1-R4\|I3 fallback\|resume_state" plugins/iflow/commands/implement.md` — confirm at least one match per scenario type. Scenarios: (1) Reviewer iter 1 → I1-R4, (2) Reviewer iter 2+ delta ≤ 50% → I2, (3) Reviewer iter 2+ delta > 50% → I1-R4 fresh, (4) Resume error → I3, (5) Final validation passed → I2-FV, (6) Final validation resume error → I3, (7) Implementer fix iter 1 → I7 fresh, (8) Implementer fix iter 2+ delta ≤ 50% → I7 resumed, (9) Implementer fix delta > 50% → I7 fresh.
  - resume_state persists across iterations for all 4 roles
  - `reviewer_status` tracking unchanged

## Task 13: Remove "Fresh dispatch per iteration" annotations

- **Phase:** 4 — Annotation Cleanup
- **File(s):** `plugins/iflow/commands/specify.md`, `design.md`, `create-plan.md`, `create-tasks.md`
- **Dependencies:** Task 7 (R4 Checkpoint complete). If R1.0 passed: also Tasks 8-12 (Phase 3 complete).
- **Description:** Remove all 12 "Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support." annotations. Distribution: 3 each in specify.md, design.md, create-plan.md, create-tasks.md. implement.md has zero such annotations.
- **Acceptance criteria:**
  - `grep -r "Fresh dispatch per iteration" plugins/iflow/` returns zero matches
  - No other content modified beyond the annotation removal

## Task 14: Add R4 ordering regression test

- **Phase:** 4 — Test Update
- **File(s):** `plugins/iflow/hooks/tests/test-token-efficiency-content.sh`
- **Dependencies:** Tasks 2-6 (Phase 2 R4 complete)
- **Description:** Add `test_json_schema_before_artifact_content` function to the test file. Insert it immediately after the existing `test_fresh_dispatch_in_all_reviewer_loops` function (search for the function's closing `}` brace, insert the new function after it). For each command file, verify the line number of JSON schema / "Return your assessment" blocks is LESS THAN the line number of the corresponding artifact content section. Same logic as R4 Checkpoint step 2, but as a persistent automated test. To identify dispatch block boundaries: use `grep -n "subagent_type:" plugins/iflow/commands/{file}.md` to find dispatch start lines, then check that within each block the schema line number is less than the content line number. Alternatively, use the `description:` line that precedes each dispatch as a delimiter.
- **Acceptance criteria:**
  - New test function exists and passes: `bash plugins/iflow/hooks/tests/test-token-efficiency-content.sh`
  - Test fails if JSON schema is moved after artifact content in any command file (regression detection)

## Task 15: Update annotation test function

- **Phase:** 4 — Test Update
- **File(s):** `plugins/iflow/hooks/tests/test-token-efficiency-content.sh`
- **Dependencies:** Task 13 (annotations removed)
- **Description:** First, determine R1.0 outcome: check `docs/dev_artifacts/workitems/031-prompt-caching-reviewer-reuse/.meta.json` for `r1_deferred_reason` field (`[ -f docs/features/031-prompt-caching-reviewer-reuse/.meta.json ] && grep -q r1_deferred_reason docs/features/031-prompt-caching-reviewer-reuse/.meta.json && echo DEFERRED || echo PASSED`). If present → R1.0 failed branch. If absent → R1.0 passed branch. Then update `test_fresh_dispatch_in_all_reviewer_loops` (line ~811). If R1.0 passed: replace with `test_resume_in_all_reviewer_loops` that verifies `resume:` is present in all 5 command files. If R1.0 failed: replace with inverted assertion verifying "Fresh dispatch per iteration" does NOT appear in any command file. Also update test file header comment (line 12): if R1.0 passed, replace with `# - resume: pattern present in all 5 command files (reviewer loops use resume on iteration 2+)`. If R1.0 failed, replace with `# - "Fresh dispatch per iteration" annotations removed from all command files`.
- **Acceptance criteria:**
  - `bash plugins/iflow/hooks/tests/test-token-efficiency-content.sh` passes with no failures
  - Old test function name removed, new function present
  - Header comment updated

## Task 16: Audit LAZY-LOAD-WARNING count

- **Phase:** 4 — Test Update
- **File(s):** `plugins/iflow/hooks/tests/test-token-efficiency-content.sh` (only if count changed)
- **Dependencies:** Tasks 2-6 (Phase 2 complete). If R1.0 passed: also Tasks 8-12 (Phase 3 complete).
- **Description:** Run `grep -rc 'LAZY-LOAD-WARNING' plugins/iflow/commands/` and compare against `test_total_i9_warning_count`'s expected value (15). R1 resumed prompts intentionally omit Required Artifacts blocks, so the count should remain 15. If the count differs, update the test's expected value.
- **Acceptance criteria:**
  - `grep -rc 'LAZY-LOAD-WARNING' plugins/iflow/commands/` output matches test expected value
  - Test passes: `bash plugins/iflow/hooks/tests/test-token-efficiency-content.sh`

## Task 17: Run verification audits

- **Phase:** 5 — Verification
- **File(s):** None modified
- **Dependencies:** Tasks 13-16 (Phase 4 complete)
- **Description:** Execute three verification audits, recording pass/fail for each independently: (1) Annotation audit: `grep -r "Fresh dispatch per iteration" plugins/iflow/` → zero matches. Record: PASS/FAIL. (2) Resume pattern audit (R1 only): `grep -rn "resume:" plugins/iflow/commands/` → 5 files. Skip if R1.0 failed. Record: PASS/FAIL/SKIPPED. (3) Prompt ordering audit: `grep -En 'Return.*JSON|Return your assessment|## Spec.*what|## Design.*what|## Plan.*what|## Tasks.*what|## Implementation Files' plugins/iflow/commands/*.md` → JSON schema line < artifact content line in each dispatch block. Record: PASS/FAIL.
- **Acceptance criteria:**
  - Annotation audit: PASS (zero matches)
  - Resume audit: PASS (5 command files listed) or SKIPPED (if R1.0 failed)
  - Prompt ordering: PASS (JSON schema precedes artifact content in all dispatch blocks)
  - Each audit has explicit PASS/FAIL/SKIPPED marker recorded

## Task 18: NFR3 character count validation

- **Phase:** 5 — Verification
- **File(s):** None modified
- **Dependencies:** Task 17 (audits pass). Skip if R1.0 failed.
- **Skip condition:** If Task 1 "R1 DEFERRED", skip.
- **Description:** Compute total character count comparison for specify.md spec-reviewer 5-iteration loop. (a) Measure I1-R4 template character count with representative 3,000-char spec → `I1_chars`. (b) Measure I2 template with representative 500-char diff → `I2_chars`. (c) Fresh total: `5 * I1_chars`. (d) Resume total: `1 * I1_chars + 4 * I2_chars`. (e) Ratio: `resume_total / fresh_total` must be < 50%. Document worst-case at guard boundary (60%) as known limitation.
- **Acceptance criteria:**
  - Ratio < 50% under representative inputs
  - Actual character counts documented
  - Worst-case limitation documented

## Task 19: Fallback tracking test (interactive)

- **Phase:** 5 — Verification
- **File(s):** None modified permanently
- **Dependencies:** Task 17 (audits pass). Skip if R1.0 failed.
- **Skip condition:** If Task 1 "R1 DEFERRED", skip.
- **Description:** Interactive, non-automatable test. Run a feature through specify to trigger a review loop. After iteration 1, instruct the orchestrator to replace stored agent_id with `invalid-agent-id-000`. Verify resume fails, I3 fallback triggers, and RESUME-FALLBACK marker is logged. If interactive corruption is impractical, defer to end-to-end validation.
- **Acceptance criteria:**
  - `grep "RESUME-FALLBACK" docs/features/031-prompt-caching-reviewer-reuse/.review-history.md` returns a match
  - Marker format: `RESUME-FALLBACK: {agent_role} iteration {n} — {error summary}`

## Dependency Graph

Note: Tasks 2-5 have no hard dependency on Task 1 — they can proceed regardless of Task 1 outcome. The arrow represents recommended order only. The gate decision from Task 1 only affects whether Tasks 8-12 execute.

```
Task 1 (R1.0 gate)
    │ (recommended order, not hard dependency)
    ▼
┌── Tasks 2-5 (R4: specify, design, create-plan, create-tasks) ──┐  ← parallel group
│                                                                  │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                 Task 6 (R4: implement.md) ← recommended after 2-5
                       │
                 Task 7 (R4 Checkpoint) -- gate for Phase 3+4
                       │
          ┌────────────┴─────────────┐
          │ (if R1.0 pass)           │ (if R1.0 fail)
          ▼                          │
    Task 8 (R1: specify.md)          │
          │                          │
    ┌─────┼─────┬─────┐             │
    ▼     ▼     ▼     │             │
  Task 9  10   11     │             │  ← parallel group (9-11)
    └─────┼─────┘     │             │
          ▼           │             │
    Task 12 (R1: implement.md)      │
          │           │             │
          └─────┬─────┘             │
                │                   │
                ▼                   ▼
          Task 13 (remove annotations) ◄──────┘
                │
          ┌─────┼─────┐
          ▼     ▼     ▼
     Task 14   15    16    ← parallel group
          └─────┼─────┘
                ▼
          Task 17 (verification audits)
                │
          ┌─────┴─────┐
          ▼           ▼
     Task 18 (NFR3)  Task 19 (fallback test)  ← parallel, R1 only
```

## Summary

- **19 tasks** across **5 phases**
- **4 parallel groups**: Tasks 2-5 (R4 phase commands), Tasks 9-11 (R1 phase commands), Tasks 14-16 (test updates), Tasks 18-19 (R1 verification)
- **Conditional branch**: Tasks 8-12, 18, 19 skipped if R1.0 fails (Task 1)
- **Critical path**: Task 1 → Task 2 → Task 7 → Task 8 → Task 12 → Task 13 → Task 15 → Task 17 → Task 18
