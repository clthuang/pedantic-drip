# Tasks: Promptimize Skill Redesign

## Phase 1: Rewrite SKILL.md — Two-Pass Structure

### Task 1.1: Update Step 2c variable and rationale
**File:** `plugins/iflow/skills/promptimize/SKILL.md`
**Plan ref:** P1 change 1
**Depends on:** none
**AC:** `original_content` renamed to `target_content` in Step 2c; rationale reads "needed by Phase 2 as rewrite context" (not "Accept-some restoration in Step 8")

Change Step 2c:
- Rename `original_content` → `target_content`
- Update rationale from "needed for Accept-some restoration in Step 8" to "needed by Phase 2 as rewrite context"

### Task 1.2: Replace Steps 4-5 with Phase 1 (Grade)
**File:** `plugins/iflow/skills/promptimize/SKILL.md`
**Plan ref:** P1 change 2
**Depends on:** 1.1
**AC:** Steps 4-5 removed; new Phase 1 section evaluates 9 dimensions, outputs JSON matching R1.2 schema wrapped in `<phase1_output>` tags; no score calculation remains; canonical dimension name mapping table from I2 present; table placed immediately before JSON output schema example. Scope: single contiguous section replacement (Steps 4-5 → Phase 1).

Remove current Step 4 (evaluate dimensions) and Step 5 (calculate score). Add Phase 1 section:
- Evaluate 9 dimensions using scoring rubric behavioral anchors
- Place the canonical dimension name mapping table (from design.md I2 — 9 rows, Rubric Name → JSON name value) **after** the behavioral-anchor evaluation instructions and **immediately before** the JSON output schema example (as forward context the LLM reads before emitting JSON field names)
- Output JSON: `{ file, component_type, guidelines_date, staleness_warning, dimensions: [{ name, score, finding, suggestion, auto_passed }] }`
- Wrap output in `<phase1_output>...</phase1_output>` tags
- Explicit instruction: "Do NOT compute an overall score. Output only the raw dimension scores."

### Task 1.3: Replace Steps 6-7 with Phase 2 (Rewrite)
**File:** `plugins/iflow/skills/promptimize/SKILL.md`
**Plan ref:** P1 change 3
**Depends on:** 1.2
**AC:** Steps 6-7 removed; Phase 2 references Phase 1 JSON via `<grading_result>` block; uses `<change dimension="..." rationale="...">` XML tags (not HTML); attribute order enforced (dimension before rationale); multi-region, overlapping, and pass-dimension rules present; wrapped in `<phase2_output>` tags; preservation instruction present. Scope: single contiguous section replacement (Steps 6-7 → Phase 2).

Remove current Step 6 (generate improved version) and Step 7 (report). Add Phase 2 section:
- Instruct LLM to wrap Phase 1 JSON in `<grading_result>` block as context for rewrite
- Use XML `<change>` tags with explicit attribute order: `<change dimension="..." rationale="...">`
- Include rule: "Attribute order is fixed: dimension, then rationale. Do not reorder."
- Multi-region rules (R2.2), overlapping dimensions (R2.3), pass dimensions no tags (R2.4)
- Preservation instruction (R2.5): text outside `<change>` tags identical to original
- Wrap in `<phase2_output>...</phase2_output>` tags

### Task 1.4: Remove Step 8, YOLO section, and update PROHIBITED
**File:** `plugins/iflow/skills/promptimize/SKILL.md`
**Plan ref:** P1 change 4
**Depends on:** 1.3
**AC:** Step 8 (approval/merge) removed; YOLO Mode Overrides section removed; PROHIBITED section retains only scoring rubric rule; no approval, merge, or over-budget rules remain in skill; no dangling step references to Steps 5-8

- Delete YOLO Mode Overrides section — moves to command
- Delete Step 8 (user approval) entirely — moves to command
- Update PROHIBITED: remove 3 rules (write without approval, skip Step 8, over-budget), retain "NEVER score a dimension without referencing behavioral anchors"
- Verify (run **after** all deletions above): SKILL.md contains no references to Step 8, Step 7, Step 6, or Step 5 as step numbers. The YOLO section itself references Step 8, so it must be deleted before the step-number check is valid. The only numbered steps remaining are Steps 1-3 (original), followed by Phase 1 and Phase 2 sections.

### Task 1.5: Verify SKILL.md post-rewrite
**File:** `plugins/iflow/skills/promptimize/SKILL.md`
**Plan ref:** P1 Verification
**Depends on:** 1.4
**AC:** File under 500 lines; contains `<phase1_output>`, `<phase2_output>`, `<grading_result>` delimiters; all 9 dimension names present; no HTML `<!-- CHANGE -->` markers; no score calculation; no approval/merge logic

Verification checklist (read file and confirm):
- Under 500 lines / 5,000 tokens
- `<phase1_output>`, `<phase2_output>`, `<grading_result>` present
- 9 canonical dimension names present
- No `<!-- CHANGE` or `END CHANGE` patterns
- No `/ 27` or score calculation
- No `Accept all`, `Accept some`, `Reject` approval logic

---

## Phase 2: Rewrite Command — Core Orchestration

### Task 2.1: Add Step 2.5 — Read original file
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P2 step 1 (design I5 Step 2.5)
**Depends on:** 1.5
**AC:** Step 2.5 reads target file after selection, stores as `original_content`; error handling if read fails; Step 1's direct-path skip target updated from "Step 3" to "Step 2.5"; no other steps bypass Step 2.5

After existing Steps 1-2 (file selection), add Step 2.5:
- Read target file at resolved path
- Store as `original_content`
- If read fails: display error, STOP
- Reference `original_content` consistently in all subsequent steps
- **Also update Step 1:** change the direct-path skip target from "skip to Step 3" to "skip to Step 2.5" so direct-path invocations also read the file before invoking the skill. New flow for direct path: Step 1 → Step 2.5 → Step 3.
- **Cross-reference audit:** verify no other steps in the command reference "Step 3" by number in a way that would bypass Step 2.5. The command's Step 2 (interactive selection) naturally leads to Step 2.5, so only the direct-path skip in Step 1 needs updating.

### Task 2.2: Update Step 3 — Skill invocation note
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P2 step 2
**Depends on:** 2.1
**AC:** Step 3 still invokes skill; includes note about `<phase1_output>` and `<phase2_output>` sections in output

Update Step 3:
- Keep skill invocation: `Skill(skill: "iflow:promptimize", args: "<selected-path>")`
- Add note: "The skill output appears in conversation context containing `<phase1_output>` and `<phase2_output>` sections"

### Task 2.3: Add Step 4 — Parse skill output
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P2 step 3 (design C3-C4)
**Depends on:** 2.2
**AC:** Step 4a extracts Phase 1 JSON from `<phase1_output>` tags; Step 4b extracts Phase 2 content from `<phase2_output>` tags; Step 4c validates 9 dimensions, scores 1-3, required fields, canonical dimension names, suggestion null/non-null constraint; parsing failure displays error and stops

Add Step 4:
- 4a: Extract content between `<phase1_output>` and `</phase1_output>`, parse as JSON
- 4b: Extract content between `<phase2_output>` and `</phase2_output>`, store as Phase 2 content
- 4c: Validate Phase 1 JSON — exactly 9 dimensions, scores 1-3, required fields per I2 schema. **Canonical dimension names (embed inline):** `structure_compliance`, `token_economy`, `description_quality`, `persuasion_strength`, `technique_currency`, `prohibition_clarity`, `example_quality`, `progressive_disclosure`, `context_engineering`. **Suggestion constraint (R1.1):** for each dimension, if `score < 3` then `suggestion` must be non-null (string); if `score == 3` then `suggestion` must be null.
- Error format: `"Phase 1 JSON validation failed: {reason}. Raw output snippet: {first 200 chars}"` — display and STOP

### Task 2.4: Add Step 5 — Compute score
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P2 step 4 (design C4, spec R3)
**Depends on:** 2.3
**AC:** Score computed as `round((sum / 27) * 100)`; stored as `overall_score`; not present in LLM output

Add Step 5:
- Sum all 9 dimension scores from Phase 1 JSON
- Compute `round((sum / 27) * 100)` to nearest integer
- Store as `overall_score`

### Task 2.5: Add Step 6a — Tag validation and ChangeBlock extraction
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P2 step 5 (design C5, TD2)
**Depends on:** 2.4
**AC:** Regex patterns from TD2 for open/close tags; fenced code block skipping; validation checks (paired tags, no nesting, no overlap, non-empty dimension); ChangeBlock array built with dimensions, rationale, content, before_context, after_context; `tag_validation_failed` flag set on failure; reversed attribute order triggers failure

Add Step 6a:
- Regex: open `<change\s+dimension="([^"]+)"\s+rationale="([^"]*)">`, close `</change>`
- Code fence tracking: toggle `in_fence` on lines starting with ``` or ~~~
- Validation: every open has close, no nesting, no overlapping, non-empty dimension
- Build ChangeBlock array: dimensions, rationale, content, before_context (3 lines), after_context (3 lines)
- If validation fails: set `tag_validation_failed = true`
- **Zero-match behavior:** If the open-tag regex matches zero tags (e.g., reversed attribute order `<change rationale="..." dimension="...">`), the ChangeBlock array is empty and `tag_validation_failed = true`. No special reversed-attribute code path needed — the regex non-match naturally produces the correct outcome (TD2 test scenario).

### Task 2.6: Add match_anchors_in_original sub-procedure
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P2 step 5 (design C6/C9 shared algorithm)
**Depends on:** 2.5
**AC:** Labeled standalone section `## Sub-procedure: match_anchors_in_original`; contract documented (inputs: ChangeBlock + original_content lines + optional merge-adjacent flag; returns: `{ matched: true, start_line, end_line }` or `{ matched: false, reason }`); referenced by name from drift detection and Accept some steps

Add as labeled standalone section after Step 6a:
- `## Sub-procedure: match_anchors_in_original`
- Inputs: ChangeBlock (with before_context, after_context), `original_content` lines, merge-adjacent flag (default: false)
- When merge-adjacent is true: adjacent ChangeBlocks whose anchor windows overlap are merged into a single logical region before matching. Both drift detection (Step 6b) and Accept some (Task 4.3) pass merge-adjacent=true.
- Returns: `{ matched: true, start_line, end_line }` on unique match, `{ matched: false, reason }` on zero/multiple/overlapping matches
- Locate before_context and after_context anchor lines in original_content
- Handle edge cases: file start (0-2 before-context lines), file end (0-2 after-context lines)
- Note: this sub-procedure handles anchor matching only. Attribute order enforcement is handled by the open-tag regex in Task 2.5 — do not add attribute-order checking here.

---

## Phase 3: Add Command — Drift Detection + Report

### Task 3.1: Add Step 6b — Drift detection
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P3 step 1 (design C6)
**Depends on:** 2.6
**AC:** For each ChangeBlock, calls `match_anchors_in_original` to locate anchors; replaces `<change>` blocks with matched original text; normalizes (strip trailing whitespace, ignore boundary blank lines); compares to `original_content`; sets `drift_detected = true` if different; skips if `tag_validation_failed`; handles adjacent blocks via merge. Verify: given two ChangeBlocks separated by 2 lines in Phase 2 output, match_anchors_in_original with merge-adjacent=true returns a single (start_line, end_line) span covering both blocks, and the reconstructed content for that span matches the original text.

Add Step 6b:
- For each ChangeBlock: call `match_anchors_in_original` (defined in Task 2.6 sub-procedure) to locate anchors in `original_content`
- Handle adjacent blocks: use `match_anchors_in_original` with the merge-adjacent flag — do not duplicate the merging logic here
- Replace each `<change>` block with matched original text between anchors
- Normalize: strip trailing whitespace per line, ignore blank-line differences at file boundaries
- Compare normalized reconstruction to normalized `original_content`
- If different: set `drift_detected = true`
- If `tag_validation_failed`: skip drift detection

### Task 3.2: Add Step 6c — Token budget check
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P3 step 2 (design C7)
**Depends on:** 3.1
**AC:** Strips `<change>`/`</change>` tags from Phase 2 content; counts lines and words; sets `over_budget_warning = true` if exceeds 500 lines or 5,000 words

Add Step 6c:
- Strip all `<change ...>` and `</change>` tags from Phase 2 content
- Count lines and words (5,000 words as conservative proxy for tokens per C7)
- If exceeds 500 lines or 5,000 words: set `over_budget_warning = true`

### Task 3.3: Add Step 7 — Report assembly
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P3 step 3 (design C7, spec R5)
**Depends on:** 3.2
**AC:** Report template matches current structure; populated from Phase 1 JSON (scores, findings, suggestions); uses computed `overall_score`; strengths list evaluated pass dimensions (not auto-passed); issues table with severity mapping (fail=blocker, partial=warning); improved version is Phase 2 output verbatim; conditional staleness and over-budget warnings

Add Step 7:
- Template: component type, overall score, guidelines version, strengths, issues table, improved version
- Populate from Phase 1 JSON: component type, dimension scores, findings, suggestions
- `overall_score` from Step 5
- Strengths: evaluated dimensions scoring pass (3), excluding auto-passed
- Issues: partial=warning, fail=blocker, blockers first
- Improved Version: Phase 2 output verbatim
- Conditional warnings: staleness (from Phase 1 `staleness_warning`/`guidelines_date`), over-budget (from Step 6c)

---

## Phase 4: Add Command — Approval + Merge

### Task 4.1: Add Step 8 — Approval handler
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P4 step 1 (design C8)
**Depends on:** 3.3
**AC:** All-pass shortcut (score=100 + zero ChangeBlocks → "All dimensions passed" STOP); YOLO auto-selects "Accept all"; non-YOLO presents AskUserQuestion with "Accept all"/"Reject" always, "Accept some" only when `tag_validation_failed == false` AND `drift_detected == false`; edge cases handled (score=100 with ChangeBlocks logs warning + standard option-gating; score<100 with no ChangeBlocks shows note); distinct warning messages

Add Step 8:
- If `overall_score == 100` AND zero ChangeBlocks: "All dimensions passed — no improvements needed." STOP
- Edge case 1: score=100 but ChangeBlocks exist → display standalone warning message immediately before the AskUserQuestion prompt (not by modifying the already-assembled report from Step 7): "Warning: Score is 100 but change blocks were found — this may indicate a grading error." Then show normal menu with standard option-gating
- Edge case 2: score<100 but zero ChangeBlocks → show report with note about missing changes
- YOLO mode: auto-select "Accept all"
- Non-YOLO: AskUserQuestion with Accept all, Reject (always), Accept some (conditionally)
- Warning messages for tag validation failure, drift detected

### Task 4.2: Add Accept all handler
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P4 step 2 (design C10)
**Depends on:** 4.1
**AC:** Strips all `<change ...>` and `</change>` tags via regex; writes to original file path; displays confirmation message

Add Accept all handler:
- Strip `<change ...>` and `</change>` tags via regex from Phase 2 output
- Write to original file path (overwrite)
- Display: "Improvements applied to {filename}. Run `./validate.sh` to verify."

### Task 4.3: Add Accept some handler — dimension selection and anchoring
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P4 step 3, first half (design C9 steps 1-3)
**Depends on:** 4.1
**AC:** Presents dimension multiSelect (overlapping as single option); starts from `original_content`; for selected dims calls `match_anchors_in_original` to locate anchor regions; anchor match failure for any block degrades to Accept all / Reject

Add Accept some handler (part 1 — selection and anchoring):
- Present dimension multiSelect — overlapping dimensions (comma-separated in `dimension` attribute per R2.3) as single inseparable option
- Start from `original_content` (Step 2.5)
- For selected dimensions: call `match_anchors_in_original` (Task 2.6 sub-procedure) with merge-adjacent flag to locate anchor regions in original
- Anchor match failure for any block: degrade to Accept all / Reject with warning

### Task 4.4: Add Accept some handler — replacement assembly and write
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P4 step 3, second half (design C9 steps 4-9)
**Depends on:** 4.3
**AC:** Collects (start_line, end_line, replacement) tuples for selected dims; sorts by start_line; verifies no overlapping regions (closed-interval: blocks overlap if block[i].start_line <= block[i-1].end_line); interleaves original + replacement content; unselected dims keep original text; strips residual `<change>` tags; writes to file

Add Accept some handler (part 2 — assembly and write):
- Collect (start_line, end_line, replacement) tuples from anchored blocks for selected dimensions
- Sort by start_line, verify no overlapping regions. Overlap check uses closed interval: blocks overlap if `block[i].start_line <= block[i-1].end_line` (adjacent blocks sharing a boundary line are treated as overlapping). If overlap detected: degrade to Accept all / Reject with warning.
- Interleave: original content up to start_line, then replacement content, then original after end_line — repeat for each tuple in order
- Unselected dimensions: their regions keep original text (no replacement applied)
- Strip residual `<change>` tags (defensive final pass)
- Write assembled content to original file path

### Task 4.5: Add Reject handler
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P4 step 4
**Depends on:** 4.1
**AC:** Displays "No changes applied." and stops

Add Reject handler:
- Display "No changes applied." STOP

### Task 4.6: Add PROHIBITED section to command
**File:** `plugins/iflow/commands/promptimize.md`
**Plan ref:** P4 step 5 (design C8)
**Depends on:** 4.4
**AC:** Three rules: no writing without approval (exception: YOLO), no skipping approval in non-YOLO, no presenting Accept some when tag_validation_failed or drift_detected

Add PROHIBITED section:
- "NEVER write improvements without user approval via AskUserQuestion (Step 8). Exception: YOLO mode auto-selects Accept all."
- "NEVER skip the approval step in non-YOLO mode."
- "NEVER present Accept some when tag_validation_failed or drift_detected is true."

---

## Phase 5: Update Content Regression Tests

### Task 5.1: Update 4 tests that moved from SKILL.md to command
**File:** `plugins/iflow/hooks/tests/test-promptimize-content.sh`
**Plan ref:** P5 Tests to Update rows 2-4, 6
**Depends on:** 4.6
**AC:** Tests 2-4 (Accept all, Accept some, Reject) grep `promptimize.md` instead of SKILL.md; Test 6 (malformed marker fallback) greps `tag_validation_failed` or `malformed` in `promptimize.md`; main() call for renamed function updated in the same position

Update tests:
- `test_skill_has_accept_all_option`: grep `Accept all` in **promptimize.md** (not SKILL.md)
- `test_skill_has_accept_some_option`: grep `Accept some` in **promptimize.md**
- `test_skill_has_reject_option`: grep `Reject` in **promptimize.md**
- `test_skill_has_malformed_marker_fallback`: rename to `test_cmd_has_malformed_marker_fallback`; grep `tag_validation_failed` in **promptimize.md**; update the main() call — replace the old name with `test_cmd_has_malformed_marker_fallback` in the same position where the old call was

### Task 5.2: Update 3 tests for relocated content
**File:** `plugins/iflow/hooks/tests/test-promptimize-content.sh`
**Plan ref:** P5 Tests to Update rows 7-9
**Depends on:** 5.1
**AC:** Test 7 (scoring formula) greps `27` in `promptimize.md`; Test 8 (report fields) greps `overall_score|Overall score` + `component_type|Component type` in `promptimize.md`; Test 9 (severity) greps `blocker` + `warning` in `promptimize.md`

Update tests:
- `test_skill_documents_scoring_formula`: grep `27` in **promptimize.md**
- `test_skill_report_template_has_required_fields`: grep `overall_score\|Overall score` + `component_type\|Component type` in **promptimize.md**
- `test_skill_severity_mapping_documented`: grep `blocker` + `warning` in **promptimize.md**

### Task 5.3: Rename and update Test 1 (XML markers)
**File:** `plugins/iflow/hooks/tests/test-promptimize-content.sh`
**Plan ref:** P5 Tests to Update row 1
**Depends on:** 5.2
**AC:** Function renamed to `test_skill_uses_xml_not_html_markers`; asserts presence of `<change` + `</change>` in SKILL.md; asserts absence of `CHANGE:` AND `END CHANGE` in SKILL.md; main() call updated

Rename `test_skill_documents_change_end_change_format` → `test_skill_uses_xml_not_html_markers`:
- Assert `<change` and `</change>` present in SKILL.md (new XML format) using existing `grep -q` pattern
- Assert `CHANGE:` absent from SKILL.md (old HTML format): `if grep -q "CHANGE:" "$SKILL_FILE"; then log_fail "Old HTML CHANGE: marker still present"; return; fi`
- Assert `END CHANGE` absent from SKILL.md (old HTML close marker): `if grep -q "END CHANGE" "$SKILL_FILE"; then log_fail "Old HTML END CHANGE marker still present"; return; fi`
- Update main() function: rename the call from `test_skill_documents_change_end_change_format` to `test_skill_uses_xml_not_html_markers`. Keep the renamed call in the same position in main() — it remains in the SKILL.md section under Dimension 1.

### Task 5.4: Delete YOLO test from skill
**File:** `plugins/iflow/hooks/tests/test-promptimize-content.sh`
**Plan ref:** P5 Tests to Update row 5
**Depends on:** 5.3
**AC:** `test_skill_has_yolo_mode_overrides` function and its main() call deleted; replaced by new `test_cmd_has_yolo_mode_handling`

- Delete `test_skill_has_yolo_mode_overrides` function
- Remove its call from main()
- Note: after this task, main() will temporarily have no YOLO-related test call — this is expected and resolved by Task 5.5. Do not add the new `test_cmd_has_yolo_mode_handling` call here; that is Task 5.5's responsibility.

### Task 5.5: Add 7 new tests
**File:** `plugins/iflow/hooks/tests/test-promptimize-content.sh`
**Plan ref:** P5 New Tests table
**Depends on:** 5.4
**AC:** 7 new test functions added and called from main(); each asserts against the correct file (SKILL.md or promptimize.md)

Add new test functions:
1. `test_skill_has_phase1_output_tags` — SKILL.md contains `phase1_output`
2. `test_skill_has_phase2_output_tags` — SKILL.md contains `phase2_output`
3. `test_skill_has_grading_result_block` — SKILL.md contains `grading_result`
4. `test_cmd_has_score_computation` — promptimize.md contains `round` and `27`
5. `test_cmd_has_drift_detection` — promptimize.md contains `drift_detected`
6. `test_cmd_has_tag_validation` — promptimize.md contains `tag_validation_failed`
7. `test_cmd_has_yolo_mode_handling` — promptimize.md contains `YOLO_MODE` or `YOLO`

**Placement map for main():** Tests 1-3 (phase1/phase2/grading_result) → SKILL.md structure section (alongside existing skill structural tests). Tests 4-7 (score, drift, tag_validation, YOLO in command) → command structure section (after existing command tests, or as new "Command Structure" subsection if none exists).

---

## Phase 6: Validation and Cleanup

### Task 6.1: Run validate.sh
**Plan ref:** P6 step 1
**Depends on:** 5.5
**AC:** `./validate.sh` exits with 0

Run `./validate.sh` and fix any failures.

### Task 6.2: Run test-promptimize-content.sh
**Plan ref:** P6 step 2
**Depends on:** 6.1
**AC:** `bash plugins/iflow/hooks/tests/test-promptimize-content.sh` passes with 0 failures. All pre-existing tests asserting on unchanged SKILL.md content (Steps 1-3: staleness, component type detection, invalid path error, reference file error handling, STOP directive) must still pass without modification — these are not touched by Phase 1-4 tasks.

Run content regression tests and fix any failures. **Triage:** if a test fails, check whether the failure is (a) a stale grep pattern from P5 that needs updating, (b) a missing structural element in the rewritten file, or (c) a test logic error. Fix at the source — do not patch tests to pass over real issues.

### Task 6.3: Cross-file consistency checks
**Plan ref:** P6 step 3
**Depends on:** 6.2
**AC:** SKILL.md has no HTML markers, score calc, approval logic, YOLO section; command references `<phase1_output>`/`<phase2_output>` correctly; `original_content` only in command, `target_content` only in skill; 9 dimension names consistent; TD2 regex matches skill tag format; command PROHIBITED has all 3 moved rules

Verify using these concrete commands:
- `grep -n "original_content" plugins/iflow/skills/promptimize/SKILL.md` → expect zero hits
- `grep -n "target_content" plugins/iflow/commands/promptimize.md` → expect zero hits
- `grep -c "phase1_output" plugins/iflow/commands/promptimize.md` → expect >= 1
- `grep -c "phase2_output" plugins/iflow/commands/promptimize.md` → expect >= 1
- `grep -n "CHANGE" plugins/iflow/skills/promptimize/SKILL.md` → no `<!-- CHANGE` or `END CHANGE` patterns (only `<change` XML)
- `grep -c "27" plugins/iflow/commands/promptimize.md` → expect >= 1 (score formula present)
- `grep -n "27" plugins/iflow/skills/promptimize/SKILL.md` → expect zero hits (no score calc)
- `grep -c "PROHIBITED" plugins/iflow/commands/promptimize.md` → expect >= 1
- `grep -c "dimension.*rationale" plugins/iflow/commands/promptimize.md` → expect >= 1 (TD2 regex matches skill tag format)

### Task 6.4: Token budget verification
**Plan ref:** P1 Verification
**Depends on:** 6.3
**AC:** SKILL.md under 500 lines / 5,000 tokens; command file reasonable size

Verify final file sizes are within acceptable bounds.

---

## Summary

- **Total tasks:** 25
- **Phases:** 6
- **Parallel groups:** None — all tasks within each phase edit the same file and must execute sequentially. Cross-phase dependencies are strictly linear (P1 → P2 → P3 → P4 → P5 → P6).
