# Plan: Prompt Caching & Reviewer Reuse

## Implementation Order

### Phase 1: Validation Gate (R1.0)

No dependencies. Must execute first to gate R1 implementation.

1. **R1.0 Validation Gate** — Execute V1-V4 structured validation tests to determine if Task tool `resume` works with tool-using agents
   - **Why this item:** R1.0 is the prerequisite gate for all R1 (resume) work. Spec R1.0 requires ALL four tests to pass before any resume logic is implemented.
   - **Why this order:** Must be first — the outcome determines whether Phase 3 (R1 resume logic) is implemented or skipped.
   - **Deliverable:** V1-V4 test results documented. Gate decision recorded. If any test fails, `.meta.json` updated with `r1_deferred_reason` field.
   - **Complexity:** Medium — requires dispatching a real agent, capturing agent_id, and resuming it. Outcome is uncertain (GitHub #13619 fix status ambiguous).
   - **Files:** No file modifications. Interactive validation only. `.meta.json` updated only if tests fail. V1 dispatch uses this feature's own spec.md (`docs/dev_artifacts/workitems/031-prompt-caching-reviewer-reuse/spec.md`) as the test artifact.
   - **Verification:** V1-V4 checklist completed with binary pass/fail for each test. Gate decision documented. **Known limitation:** V1-V4 use a simplified prompt (per design I10), not the full I1-R4 template. This validates the resume mechanism (agent_id capture, context preservation, tool-use agent resume) but not prompt-template-specific behavior. If the mechanism works, template-specific issues would manifest as logical errors (not API failures) and are handled by I3 fallback.

### Phase 2: Prompt Structure Reordering (R4)

Independent of Phase 1 outcome. Can proceed regardless of R1.0 result. Phase 2 can begin before Phase 1 completes (no dependency), but the recommended execution order is Phase 1 first, then Phase 2, to establish the gate decision early and avoid unnecessary context switching.

1. **R4 reorder specify.md** — Reorder spec-reviewer and phase-reviewer dispatch prompts to place static content (rubric, rubric coda, Required Artifacts, JSON schema) before dynamic content (artifact content, iteration context, domain outcome)
   - **Why this item:** R4.1 requires canonical section ordering. specify.md has 2 reviewer dispatch prompts to reorder.
   - **Why this order:** No dependency on other files. First command file establishes the pattern for subsequent files.
   - **Deliverable:** specify.md with both dispatch prompts following I1-R4 canonical skeleton: static prefix (rubric + rubric coda + Required Artifacts + JSON schema) above dynamic suffix (spec content + iteration context).
   - **Complexity:** Medium — must carefully move sections without breaking prompt structure. Per-reviewer deviations documented in design (spec-reviewer: PRD is only Required Artifact, rubric coda moves to section 1; phase-reviewer: Next Phase Expectations is static, moves above domain outcome).
   - **Files:** `plugins/iflow/commands/specify.md`
   - **Verification:** Manual inspection confirms static sections precede dynamic sections in both dispatch prompts. No change to JSON schema content or field names.

2. **R4 reorder design.md** — Reorder design-reviewer (Stage 3) and phase-reviewer (Stage 4) dispatch prompts
   - **Why this item:** R4.1 requires canonical section ordering across all 5 command files.
   - **Why this order:** Same pattern as specify.md. No cross-file dependency.
   - **Deliverable:** design.md with both dispatch prompts following I1-R4 canonical skeleton. design-reviewer: rubric coda moves to section 1. phase-reviewer: Next Phase Expectations moves to stable prefix.
   - **Complexity:** Medium — same structural changes as specify.md, applied to design-specific reviewers.
   - **Files:** `plugins/iflow/commands/design.md`
   - **Verification:** Static sections precede dynamic sections. Rubric coda and Next Phase Expectations confirmed in stable prefix. No change to approval/rejection logic.

3. **R4 reorder create-plan.md** — Reorder plan-reviewer (Stage 1) and phase-reviewer (Stage 2) dispatch prompts
   - **Why this item:** R4.1 requires canonical section ordering.
   - **Why this order:** Same pattern, no dependency.
   - **Deliverable:** create-plan.md with both dispatch prompts following I1-R4. plan-reviewer: compact JSON schema moves above content. phase-reviewer: same as other commands.
   - **Complexity:** Simple — plan-reviewer has simpler structure (no iteration context, no rubric coda).
   - **Files:** `plugins/iflow/commands/create-plan.md`
   - **Verification:** JSON schema confirmed before artifact content in both prompts.

4. **R4 reorder create-tasks.md** — Reorder task-reviewer (Stage 1) and phase-reviewer (Stage 2) dispatch prompts
   - **Why this item:** R4.1 requires canonical section ordering.
   - **Why this order:** Same pattern, no dependency.
   - **Deliverable:** create-tasks.md with both dispatch prompts following I1-R4. task-reviewer: validate checklist and JSON schema move above content.
   - **Complexity:** Simple — similar to create-plan.md. task-reviewer's validate checklist is static, moves to stable prefix.
   - **Files:** `plugins/iflow/commands/create-tasks.md`
   - **Verification:** Validate checklist and JSON schema confirmed before artifact content.

5. **R4 reorder implement.md** — Reorder 7a/7b/7c reviewer prompts and 7e implementer fix prompt
   - **Why this item:** R4.1 requires canonical section ordering. implement.md has the most reviewers (3) and the most complex prompt structures.
   - **Why this order:** Last R4 item because it's the most complex and benefits from patterns established in items 1-4.
   - **Deliverable:** implement.md with all reviewer prompts reordered: implementation-reviewer gets explicit JSON schema block (replacing prose instruction), validate levels move above file list. code-quality-reviewer and security-reviewer: check lists move above file lists. All JSON schemas before dynamic file lists.
   - **Complexity:** Complex — 4 distinct dispatch prompts to modify. implementation-reviewer requires adding a new JSON schema block. Must preserve selective re-dispatch logic and reviewer_status tracking. **Pre-step:** Read `plugins/iflow/agents/implementation-reviewer/agent.md` to determine the expected JSON output structure before constructing the explicit schema block.
   - **Files:** `plugins/iflow/commands/implement.md`
   - **Verification:** All 4 dispatch prompts have static content before dynamic content. implementation-reviewer has explicit JSON schema block containing `"approved":` field structure. Selective re-dispatch logic unchanged. Verify implementation-reviewer schema by checking for `"approved"` pattern within the 7a dispatch block (the old prose instruction did not contain this literal).

**R4 Checkpoint:** After completing all 5 R4 items, verify both presence and ordering:
1. **Schema presence:** `grep -n '"approved"' plugins/iflow/commands/*.md` — verify JSON schema blocks exist in all dispatch prompts. For implementation-reviewer specifically, verify the new explicit schema by checking the 7a dispatch block contains `"approved"` (the old prose instruction did not).
2. **Section ordering:** For each command file, verify the line number of each JSON schema / "Return your assessment" block is LESS THAN the line number of the corresponding artifact content section (## Spec, ## Design, ## Plan, ## Tasks, ## Implementation Files). Run: `grep -n 'Return.*JSON\|Return your assessment\|## Spec.*what\|## Design.*what\|## Plan.*what\|## Tasks.*what\|## Implementation Files' plugins/iflow/commands/*.md` and confirm schema lines precede content lines within each dispatch block.

This catches both missing schemas and incorrect ordering before Phase 3 layers resume logic on top.

### Phase 3: Resume Logic (R1) — Conditional on Phase 1 Pass

Only implemented if ALL V1-V4 tests passed in Phase 1. If R1.0 failed, skip entirely to Phase 4. **Per-file prerequisite**: Phase 2 (R4 reordering) must be complete for a given file before Phase 3 (R1 resume) is applied to that same file, per design TD1 ("R4's reordered templates become the new I1 baseline that I3 fallback uses").

**Assumption**: The working tree is expected to be clean (no uncommitted changes from unrelated sources) at the start of each review iteration. This is true in normal iflow workflow since artifacts are committed between phases. For phase commands, `git add {artifact_path}` stages only the specific artifact, avoiding unrelated changes. For implement.md, `git add -A` is used per design TD2 (the implementer may create new files not in the original file list); the delta size guard provides self-correction if unrelated files are staged (noisy diff triggers fresh dispatch).

**Git failure detection**: The LLM orchestrator detects git command outcomes via explicit markers in Bash output. Unified three-state command pattern combining the design's NO_CHANGES check with orchestrator-observable markers:
```
git add {path} && git diff --cached --quiet && echo NO_CHANGES || (git commit -m "review iteration {n} fixes" && echo COMMIT_OK || echo COMMIT_FAILED)
```
The orchestrator checks for: `NO_CHANGES` → skip diff, reuse previous delta or proceed with fresh dispatch; `COMMIT_OK` → run `git diff {last_commit_sha} HEAD` to produce delta; `COMMIT_FAILED` → fall back to fresh dispatch per TD2 fallback. This extends the design's TD2 mechanism with orchestrator-observable signals.

1. **R1 resume in specify.md** — Add resume_state tracking, per-iteration git commit + diff, and resume dispatch logic for both Stage 1 (spec-reviewer) and Stage 2 (phase-reviewer) review loops
   - **Prerequisite:** Phase 2 item 1 (R4 reorder specify.md) must be complete.
   - **Why this item:** R1.1 requires resume in all review loop iteration 2+. R1.2a requires delta via git diff. R1.3 requires resume_state dict.
   - **Why this order:** First command file for resume. Establishes pattern for I2 template, resume_state management, delta generation (TD2), delta size guard (TD5), and fallback (I3/R1.6).
   - **Deliverable:** specify.md with: (a) resume_state dict initialized after iteration 1, (b) per-iteration git commit after revisions using the unified three-state Bash pattern (NO_CHANGES / COMMIT_OK / COMMIT_FAILED), (c) git diff delta computation on COMMIT_OK, (d) delta size guard check, (e) I2 resumed prompt template for iteration 2+, (f) I3 fallback on resume error with RESUME-FALLBACK logging — also triggered if context compaction loses resume_state agent_id, (g) resume_state reset on "Fix and rerun reviews" (old per-iteration commits remain in history but are harmless — the fresh iteration 1 dispatch establishes a new commit SHA as the diff anchor), (h) git commit/diff failure (COMMIT_FAILED) falls back to fresh dispatch per TD2 fallback.
   - **Complexity:** Complex — this is the first file to implement the full resume pattern. Requires careful integration of git commit/diff mechanism, delta size guard, resume_state lifecycle, and fallback logic.
   - **Files:** `plugins/iflow/commands/specify.md`
   - **Verification:** Review loop iteration 2+ uses `resume` parameter. Delta prompt is shorter than iteration 1 prompt. Fallback path produces RESUME-FALLBACK marker. resume_state tracks agent_id, iteration1_prompt_length, last_iteration, last_commit_sha.

2. **R1 resume in design.md** — Add resume logic for Stage 3 (design-reviewer) and Stage 4 (phase-reviewer) review loops
   - **Prerequisite:** Phase 2 item 2 (R4 reorder design.md) must be complete.
   - **Why this item:** R1.1 requires resume in all 5 command files.
   - **Why this order:** Same pattern as specify.md. No cross-file dependency.
   - **Deliverable:** design.md with resume_state, git commit+diff, delta guard, I2 template, I3 fallback, git commit/diff failure fallback to fresh dispatch (TD2) for both review loops.
   - **Complexity:** Medium — pattern established in specify.md, adapted for design-specific reviewers and stage structure.
   - **Files:** `plugins/iflow/commands/design.md`
   - **Verification:** Same verification as specify.md item. Design-reviewer 'suggestion' field preserved.

3. **R1 resume in create-plan.md** — Add resume logic for Stage 1 (plan-reviewer) and Stage 2 (phase-reviewer)
   - **Prerequisite:** Phase 2 item 3 (R4 reorder create-plan.md) must be complete.
   - **Why this item:** R1.1 requires resume in all 5 command files.
   - **Why this order:** Same pattern, no dependency.
   - **Deliverable:** create-plan.md with full resume pattern for both review loops, including git commit/diff failure fallback to fresh dispatch (TD2).
   - **Complexity:** Medium — same pattern as specify.md, adapted for plan-reviewer (no iteration context, compact JSON).
   - **Files:** `plugins/iflow/commands/create-plan.md`
   - **Verification:** Same as specify.md. plan-reviewer compact JSON schema in I2 template.

4. **R1 resume in create-tasks.md** — Add resume logic for Stage 1 (task-reviewer) and Stage 2 (phase-reviewer)
   - **Prerequisite:** Phase 2 item 4 (R4 reorder create-tasks.md) must be complete.
   - **Why this item:** R1.1 requires resume in all 5 command files.
   - **Why this order:** Same pattern, no dependency.
   - **Deliverable:** create-tasks.md with full resume pattern for both review loops, including git commit/diff failure fallback to fresh dispatch (TD2).
   - **Complexity:** Medium — same pattern, adapted for task-reviewer ('task' field, validate checklist).
   - **Files:** `plugins/iflow/commands/create-tasks.md`
   - **Verification:** Same as specify.md. task-reviewer 'task' field preserved in I2 template.

5. **R1 resume in implement.md** — Add resume logic for selective re-dispatch reviewers (7a/7b/7c), implementer fix dispatch (7e), and final validation (R1.9)
   - **Prerequisite:** Phase 2 item 5 (R4 reorder implement.md) must be complete.
   - **Why this item:** R1.1, R1.5, R1.9 require resume in implement.md with its unique selective re-dispatch pattern.
   - **Why this order:** Last because it's the most complex (3 reviewers + implementer fix + final validation + selective re-dispatch interaction). Benefits from patterns established in items 1-4.
   - **Deliverable:** implement.md with: (a) resume_state dict tracking 4 agent roles (3 reviewers + implementer), (b) I2 resumed template for failed reviewer re-dispatch, (c) I2-FV template for final validation (no delta size guard), (d) I7 resumed template for implementer fix iteration 2+, (e) per-iteration git commit + diff (R1.2b) using `git add -A` as specified in design TD2 (the implementer may create new files not in the original list; delta size guard provides self-correction if unrelated files produce noisy diffs), (f) I3 fallback + RESUME-FALLBACK logging — also triggered if context compaction loses resume_state agent_id (orchestrator checks if agent_id is present; if not, treats as fresh dispatch), (g) Template Selection Decision Matrix logic implemented, (h) git commit/diff failure falls back to fresh dispatch per TD2 fallback — orchestrator detects failure via explicit markers: `git commit ... && echo COMMIT_OK || echo COMMIT_FAILED`. **Note:** implement.md's I1 prompt length for delta size guard purposes includes only the dispatch prompt text (not file contents the agent reads via Read tool). This means the guard may trigger frequently — this is expected and tracked via post-deployment monitoring (spec NFR threshold: >50% trigger rate).
   - **Complexity:** Complex — most complex file. Selective re-dispatch + final validation + implementer fix resume + 3 reviewer resume_state entries. Must preserve reviewer_status tracking.
   - **Files:** `plugins/iflow/commands/implement.md`
   - **Verification:** (a) Selective re-dispatch logic preserved. (b) Final validation round resumes passing reviewers with I2-FV. (c) Implementer fix iteration 2+ uses I7 resumed template. (d) Template Selection Decision Matrix scenarios all covered. (e) resume_state persists across iterations for all 4 roles.

### Phase 4: Annotation Cleanup (R1.8)

Depends on Phase 2 (R4) completion. If R1.0 passed, also depends on Phase 3 (R1) completion. If R1.0 failed, proceeds after Phase 2 only (Phase 3 is skipped). Applies regardless of R1.0 outcome.

1. **Remove "Fresh dispatch per iteration" annotations** — Remove all 12 annotations across 4 command files
   - **Why this item:** R1.8 requires removing all "Fresh dispatch per iteration — Phase 1 behavior. Phase 2 design defines resume support." annotations. These are now obsolete — this IS Phase 2.
   - **Why this order:** After R4 and R1 changes are complete, so annotations aren't removed prematurely (they serve as implementation markers during Phase 2-3).
   - **Deliverable:** Zero "Fresh dispatch per iteration" annotations in any command file.
   - **Complexity:** Simple — mechanical find-and-remove across 4 files (specify.md: 3, design.md: 3, create-plan.md: 3, create-tasks.md: 3). implement.md has zero such annotations.
   - **Files:** `plugins/iflow/commands/specify.md`, `plugins/iflow/commands/design.md`, `plugins/iflow/commands/create-plan.md`, `plugins/iflow/commands/create-tasks.md`
   - **Verification:** `grep -r "Fresh dispatch per iteration" plugins/iflow/` returns zero matches.

2. **Add R4 ordering regression test** — Add `test_json_schema_before_artifact_content` to `test-token-efficiency-content.sh`
   - **Why this item:** The R4 Checkpoint grep is a one-time manual check. A persistent test prevents future regressions from reintroducing dynamic content before static content in dispatch prompts.
   - **Why this order:** After Phase 2 (R4 reordering) is complete, so the test can verify the new structure.
   - **Deliverable:** New test function that, for each command file, verifies the line number of JSON schema / "Return your assessment" blocks is LESS THAN the line number of the corresponding artifact content section. Implements the same logic as the R4 Checkpoint step 2 but as a persistent test.
   - **Complexity:** Medium — must parse grep output for line numbers and compare within each dispatch block. May need to identify dispatch block boundaries to avoid false positives from multiple dispatches in one file.
   - **Files:** `plugins/iflow/hooks/tests/test-token-efficiency-content.sh`
   - **Verification:** `bash plugins/iflow/hooks/tests/test-token-efficiency-content.sh` passes with the new test function.

3. **Update test for removed annotations** — Update or replace `test_fresh_dispatch_in_all_reviewer_loops` in `test-token-efficiency-content.sh`
   - **Why this item:** The existing test at `plugins/iflow/hooks/tests/test-token-efficiency-content.sh:811` asserts that "Fresh dispatch per iteration" is present in all 4 command files. Removing the annotations in item 1 without updating this test will cause test failure.
   - **Why this order:** Must be done alongside or immediately after item 1 (annotation removal).
   - **Deliverable:** Test updated to verify the new behavior. If R1.0 passed: replace test with `test_resume_in_all_reviewer_loops` that verifies `resume:` is present in all 5 command files. If R1.0 failed: replace test with inverted assertion that verifies "Fresh dispatch per iteration" does NOT appear in any command file (maintains behavioral pinning for the annotation removal). Also update the test file header comment (line 12, which references "Fresh dispatch per iteration" as historical context) to reflect the new state.
   - **Complexity:** Simple — replace one test function with an updated assertion plus header comment update.
   - **Files:** `plugins/iflow/hooks/tests/test-token-efficiency-content.sh`
   - **Verification:** `bash plugins/iflow/hooks/tests/test-token-efficiency-content.sh` passes with no failures.

4. **Audit LAZY-LOAD-WARNING count** — Verify `test_total_i9_warning_count` accuracy after R4/R1 changes
   - **Why this item:** The existing test at `plugins/iflow/hooks/tests/test-token-efficiency-content.sh:914` asserts 15 LAZY-LOAD-WARNINGs across command files. R4 reordering and R1 resume additions could change this count.
   - **Why this order:** After Phase 2 (R4) and Phase 3 (R1) are complete, so the count reflects final state.
   - **Deliverable:** Run `grep -rc 'LAZY-LOAD-WARNING' plugins/iflow/commands/` and compare result against the test's expected count (15). R1 resumed prompts intentionally omit Required Artifacts blocks (no LAZY-LOAD-WARNING needed for resumed dispatches), so the count should remain 15. If the count differs, update the test's expected value.
   - **Complexity:** Simple — single grep command and potential one-line test update.
   - **Files:** `plugins/iflow/hooks/tests/test-token-efficiency-content.sh` (only if count changed)
   - **Verification:** `grep -rc 'LAZY-LOAD-WARNING' plugins/iflow/commands/` output matches the test's expected value.

### Phase 5: Verification

Depends on all previous phases.

1. **Annotation audit** — Verify all "Fresh dispatch per iteration" annotations removed
   - **Why this item:** Spec test strategy requires zero matches.
   - **Why this order:** After all implementation complete.
   - **Deliverable:** `grep -r "Fresh dispatch per iteration" plugins/iflow/` returns zero matches.
   - **Complexity:** Simple — single grep command.
   - **Files:** None modified.
   - **Verification:** Command output is empty.

2. **Resume pattern audit** — Verify resume usage in all 5 command files (R1 only)
   - **Why this item:** Spec test strategy requires resume usage in all command files.
   - **Why this order:** After R1 implementation.
   - **Deliverable:** `grep -rn "resume:" plugins/iflow/commands/` shows resume usage in all 5 files.
   - **Complexity:** Simple — single grep command. Skip if R1.0 failed.
   - **Files:** None modified.
   - **Verification:** 5 command files appear in grep output.

3. **Prompt ordering audit** — Verify R4 canonical skeleton ordering in all dispatch prompts
   - **Why this item:** R4 acceptance criteria requires rubric + artifacts + schema before content + iteration context.
   - **Why this order:** After R4 implementation.
   - **Deliverable:** Run `grep -n 'Return.*JSON\|Return your assessment\|## Spec.*what\|## Design.*what\|## Plan.*what\|## Tasks.*what\|## Implementation Files' plugins/iflow/commands/*.md` and verify that within each dispatch block, the JSON schema / "Return your assessment" line number is LESS THAN the corresponding artifact content section line number. Same verification method as R4 Checkpoint step 2.
   - **Complexity:** Simple — concrete grep command with line number comparison.
   - **Files:** None modified.
   - **Verification:** In each dispatch prompt: JSON schema line number < artifact content line number < iteration context line number. Verified via grep output, not visual inspection alone.

4. **NFR3 validation** — Compute total character count comparison for 5-iteration loop
   - **Why this item:** NFR3 requires resumed loop total < 50% of fresh loop total.
   - **Why this order:** After all implementation complete. Skip if R1.0 failed.
   - **Deliverable:** Character count computation for specify.md spec-reviewer as reference. Method: (a) Measure I1-R4 template character count (with placeholder values for dynamic content, e.g., `{content of spec.md}` replaced by a representative 3,000-char spec). Call this `I1_chars`. (b) Measure I2 template character count with a representative diff of 500 chars (typical unified diff for a few-line revision). Call this `I2_chars`. (c) Fresh-only total: `5 * I1_chars`. (d) Resume total: `1 * I1_chars + 4 * I2_chars`. (e) Ratio: `resume_total / fresh_total`. Must be < 50%.
   - **Worst-case analysis:** At the delta guard boundary (delta = 50% of I1_chars), worst-case ratio = `(1 × I1 + 4 × 0.5 × I1) / (5 × I1)` = 3/5 = 60%, which FAILS NFR3. However, this boundary case is rare — it requires every iteration's diff to be exactly at the 50% limit. Typical diffs are far smaller (a few hundred characters vs. multi-thousand-character I1 templates). The representative 500-char diff used in the formula reflects realistic behavior. **Decision:** NFR3 is validated under representative conditions (typical delta << 50% threshold), not worst-case. The spec's NFR3 wording ("total characters sent across a 5-iteration review loop with resume must be less than 50%") describes expected behavior, not a mathematical guarantee at all possible delta sizes. If post-deployment monitoring shows typical deltas approaching the guard boundary (>50% trigger rate per spec monitoring thresholds), the delta guard threshold should be lowered from 50% to 37% — a single-line threshold update per command file.
   - **Complexity:** Simple — arithmetic from template character counts with specified inputs.
   - **Files:** None modified.
   - **Verification:** Ratio computed and documented with actual character counts. Must be < 50% under representative inputs. Worst-case at guard boundary documented as known limitation.

5. **Fallback tracking test** — Trigger resume with invalid agent_id, verify RESUME-FALLBACK marker (R1 only)
   - **Why this item:** NFR2 acceptance criterion requires simulated resume failure to produce RESUME-FALLBACK marker.
   - **Why this order:** After R1 implementation. Skip if R1.0 failed.
   - **Deliverable:** `.review-history.md` contains correctly formatted RESUME-FALLBACK marker after simulated failure.
   - **Test procedure (interactive, non-automatable):** (1) Run a test feature through specify (or use any active feature) to trigger a review loop. (2) After iteration 1 completes and resume_state stores the agent_id, instruct the orchestrator via chat: "For testing purposes, replace the stored agent_id for spec-reviewer with invalid-agent-id-000 before proceeding to iteration 2." (3) The orchestrator uses the invalid ID in the next resume attempt: `Task({ resume: "invalid-agent-id-000", ... })`. (4) The resume should fail, triggering R1.6 fallback — fresh dispatch with I3 template + `RESUME-FALLBACK` marker logged. (5) Verify: `grep "RESUME-FALLBACK" {feature_path}/.review-history.md` returns a match with format `RESUME-FALLBACK: {agent_role} iteration {n} — {error summary}`. **Note:** This test is interactive and cannot be automated in the test suite. If interactive corruption is impractical, defer to the end-to-end validation (Testing Strategy) which exercises the full review loop and would surface fallback issues naturally.
   - **Complexity:** Medium — requires manually triggering a resume failure and verifying the fallback path.
   - **Files:** None modified permanently.
   - **Verification:** RESUME-FALLBACK marker present in `.review-history.md` with correct format.

## Dependency Graph

```
Phase 1: R1.0 Validation
    │
    │ (gate: pass/fail)
    ▼
Phase 2: R4 Reordering
  ├── specify.md
  ├── design.md
  ├── create-plan.md
  ├── create-tasks.md
  └── implement.md
    │
    │ (per-file prerequisite)
    ▼
Phase 3: R1 Resume (if R1.0 pass)
  ├── specify.md
  ├── design.md
  ├── create-plan.md
  ├── create-tasks.md
  └── implement.md
    │
    ▼
Phase 4: Annotation Cleanup + Test Update
    │
    ▼
Phase 5: Verification
  ├── Annotation audit
  ├── Resume pattern audit (R1 only)
  ├── Prompt ordering audit
  ├── NFR3 validation (R1 only)
  └── Fallback tracking test (R1 only)
```

Notes:
- Phase 2 items (R4) are independent of each other — can be done in any order within the phase.
- Phase 3 items (R1) are independent of each other within the phase, but Phase 3 as a whole depends on Phase 1 passing.
- Phase 3 has a per-file dependency on Phase 2: R4 reordering must complete for a given command file before R1 resume logic is applied to that same file (per TD1: "R4's reordered templates become the new I1 baseline that I3 fallback uses"). In practice, this means for each file: do R4 first, then R1.
- **Execution strategy:** Phases execute sequentially (complete all Phase 2 items, then all Phase 3 items), NOT interleaved per-file. Rationale: (1) the R4 Checkpoint after Phase 2 validates all 5 files together before Phase 3 begins, (2) sequential phases are simpler for the implementer to follow, (3) the implementer dispatches work per-task from tasks.md and phases map cleanly to task groups.
- Phase 4 depends on both Phase 2 and Phase 3 (or just Phase 2 if R1.0 fails).
- Within Phase 2, items can be done in any order or parallelized. Within Phase 3, items are logically independent but practically sequential — item 1 (specify.md) establishes the resume pattern that items 2-5 replicate. Recommended order: items 1 through 5 as listed.

## Risk Areas

- **R1.0 validation gate (Phase 1):** Uncertain outcome. If it fails, Phase 3 is entirely skipped. This is the highest-risk item — but the risk is managed by the gate mechanism (no wasted effort).
- **implement.md R1 resume (Phase 3, item 5):** Most complex single item. Selective re-dispatch + final validation + implementer fix resume all interact. Must preserve existing reviewer_status tracking while adding resume_state management.
- **R4 implement.md (Phase 2, item 5):** Adding explicit JSON schema to implementation-reviewer changes its prompt structure. Must verify the reviewer still produces parseable JSON output.
- **Existing test regression (Phase 4):** `test_fresh_dispatch_in_all_reviewer_loops` in `test-token-efficiency-content.sh` asserts the annotations being removed. Must update alongside annotation removal to avoid test failure.

## Testing Strategy

- **R1.0 gate:** V1-V4 structured validation (interactive, documented)
- **R4 checkpoint:** After all R4 items, `grep -n '"approved"' plugins/iflow/commands/*.md` verifies JSON schema placement
- **R4 regression test:** `test_json_schema_before_artifact_content` in test-token-efficiency-content.sh provides ongoing verification
- **Annotation audit:** `grep -r "Fresh dispatch per iteration" plugins/iflow/` = zero matches
- **Test suite:** `bash plugins/iflow/hooks/tests/test-token-efficiency-content.sh` passes after annotation removal + test update
- **Resume audit:** `grep -rn "resume:" plugins/iflow/commands/` = 5 files
- **Prompt ordering:** `grep -n` line number comparison verifying JSON schema precedes artifact content in each dispatch prompt (same method as R4 Checkpoint step 2)
- **NFR3:** Character count computation from template structure (concrete formula in Phase 5, item 4)
- **Fallback test:** Simulated resume failure produces RESUME-FALLBACK marker
- **End-to-end:** Run a feature through specify with intentional deficiency to trigger 2+ iterations, verify resume works in practice

## Definition of Done

- [ ] R1.0 validation gate executed and documented
- [ ] All 5 command files have R4-reordered dispatch prompts (static before dynamic)
- [ ] R4 checkpoint grep confirms JSON schema placement
- [ ] R4 regression test (`test_json_schema_before_artifact_content`) added and passing
- [ ] All 5 command files have R1 resume logic (if R1.0 passed)
- [ ] Zero "Fresh dispatch per iteration" annotations remain
- [ ] `test-token-efficiency-content.sh` passes (test updated for annotation removal)
- [ ] All verification audits pass
- [ ] NFR3 character count ratio < 50% (if R1.0 passed)
- [ ] No regression in review approval/rejection logic
- [ ] No regression in selective re-dispatch (implement.md)
