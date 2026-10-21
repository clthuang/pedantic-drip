# Plan: Promptimize Skill Redesign

## Implementation Order

Three files change: `SKILL.md` (the skill), `promptimize.md` (the command), and `test-promptimize-content.sh` (content regression tests). The skill must be rewritten first because the command parses its output format. Tests update last because they assert against the final state of both files.

### Why not TDD

These are Markdown prompt files, not executable code. TDD (write failing test → implement → pass) doesn't apply because there's no runnable unit — the tests are grep-based content assertions that verify structural properties of the Markdown. The natural order is: rewrite the files, then update the assertions to match the new structure.

### Dependency Graph

```
P1: Rewrite SKILL.md (C1 + C2)
  ↓
P2: Rewrite command — core orchestration (C3, C4, C5)
  ↓
P3: Add command — drift detection + report (C6, C7)
  ↓
P4: Add command — approval + merge (C8, C9, C10)
  ↓
P5: Update content regression tests
  ↓
P6: Validation and cleanup
```

P1 is the foundation — P2-P4 all parse or process P1's output format. P2-P4 are sequential within the command file because each section references state from earlier sections (e.g., C8 references flags set by C5/C6). P5 updates tests to match the new file structure. P6 runs `validate.sh` and `test-promptimize-content.sh` and verifies end-to-end coherence.

---

## P1: Rewrite SKILL.md — Phase 1 (Grader) + Phase 2 (Rewriter)

**File:** `plugins/iflow/skills/promptimize/SKILL.md`
**Design refs:** C1, C2, I1, I3, I6, TD1
**Spec refs:** R1.1, R1.2, R1.3, R1.5, R2.1-R2.5

### Changes

1. **Keep Steps 1-3 unchanged** (detect type, load references, staleness check). Two changes to Step 2c:
   - **Rename variable:** change `original_content` to `target_content` to avoid naming collision with the command's `original_content` (Step 2.5). The skill's copy is used only within Phase 1/Phase 2 evaluation; the command's `original_content` is the authoritative reference for all drift detection and merge operations.
   - **Update rationale:** change "needed for Accept-some restoration in Step 8" to "needed by Phase 2 as rewrite context" — the old rationale references Step 8 which is being removed.

2. **Replace Steps 4-5 with Phase 1 (Grade):**
   - Remove current Step 4 (evaluate dimensions) and Step 5 (calculate score)
   - Add Phase 1 section that evaluates all 9 dimensions using scoring rubric behavioral anchors
   - Output JSON matching R1.2 schema (I2): file, component_type, guidelines_date, staleness_warning, dimensions array with name/score/finding/suggestion/auto_passed
   - Wrap in `<phase1_output>...</phase1_output>` tags
   - Explicitly instruct: "Do NOT compute an overall score. Output only the raw dimension scores."
   - Include the canonical dimension name mapping table from I2 so the LLM uses exact JSON names

3. **Replace Steps 6-7 with Phase 2 (Rewrite):**
   - Remove current Step 6 (generate improved version with HTML markers) and Step 7 (generate report)
   - Add Phase 2 section that references Phase 1 JSON via `<grading_result>` block (R1.3)
   - Instruct: "Wrap the Phase 1 JSON output above in a `<grading_result>` block and use it as context for the rewrite"
   - Use XML `<change>` tags instead of HTML `<!-- CHANGE -->` markers (R2.1)
   - **Critical: Attribute order enforcement (I3, TD2):** Include explicit example `<change dimension="token_economy" rationale="Remove redundant preamble">` and rule: "Attribute order is fixed: dimension, then rationale. Do not reorder."
   - Multi-region rules (R2.2): each region gets its own `<change>` tag with the same dimension
   - Overlapping dimensions (R2.3): comma-separated dimension names
   - Pass dimensions (R2.4): no `<change>` tags
   - Preservation instruction (R2.5): "Preserve all text outside `<change>` tags identical to the original file. Do not modify whitespace, formatting, or content outside change blocks."
   - Wrap in `<phase2_output>...</phase2_output>` tags

4. **Remove Step 8 (user approval + merge):** This entire section moves to the command.

5. **Remove YOLO Mode Overrides section:** Approval handling is now the command's responsibility (C8).

6. **Update PROHIBITED section per File Change Summary:**
   - Remove: "NEVER write the improved version to disk without explicit user approval" (moved to C8)
   - Remove: "NEVER skip Step 8 (approval)" (moved to C8)
   - Remove: "NEVER apply changes that would push…over budget" (moved to C7)
   - Retain: "NEVER score a dimension without referencing the behavioral anchors from scoring-rubric.md"

### Verification

- Skill file stays under 500 lines / 5,000 tokens (CLAUDE.md budget). Estimate: current is 216 lines; removing Steps 4-8 (~135 lines) and YOLO section (~5 lines), adding Phase 1 (~50 lines) + Phase 2 (~60 lines) yields ~186 lines — well within budget.
- Step 2c variable renamed to `target_content` (not `original_content`) and rationale says "needed by Phase 2 as rewrite context"
- `<phase1_output>`, `<phase2_output>`, and `<grading_result>` delimiters are present
- All 9 dimension names from I2 mapping table appear in Phase 1 instructions
- No HTML `<!-- CHANGE -->` markers remain
- No score calculation remains in skill
- No approval/merge logic remains in skill

---

## P2: Rewrite Command — Core Orchestration (Output Parser, Score Calculator, Tag Validator)

**File:** `plugins/iflow/commands/promptimize.md`
**Design refs:** C3, C4, C5, I2, I4, I5, TD2, TD5
**Spec refs:** R1.5, R3.1-R3.3, R4.3

### Changes

1. **Keep Steps 1-2 unchanged** (file selection, interactive component selection, YOLO file auto-select).

2. **Add Step 2.5: Read original file.**
   - After file selection, read the target file and store as `original_content`
   - This is a fresh read using the resolved path from Steps 1-2
   - Reference as `original_content` consistently in all subsequent steps
   - If file read fails, display error and STOP

3. **Replace Step 3 (delegate to skill):**
   - Still invoke `Skill(skill: "iflow:promptimize", args: "<selected-path>")`
   - Add note: "The skill output appears in conversation context containing `<phase1_output>` and `<phase2_output>` sections"

4. **Add Step 4: Parse skill output (C3).**
   - Step 4a: Extract content between `<phase1_output>` and `</phase1_output>` tags. Parse as JSON.
   - Step 4b: Extract content between `<phase2_output>` and `</phase2_output>` tags. Store as Phase 2 content.
   - Step 4c: Validate Phase 1 JSON — exactly 9 dimensions, scores 1-3, required fields per I2 schema. Validate dimension names against canonical list from I2.
   - If any parsing or validation fails: display error with snippet of raw output, STOP.

5. **Add Step 5: Compute score (C4).**
   - Sum all 9 dimension scores from Phase 1 JSON
   - Compute `round((sum / 27) * 100)` to nearest integer
   - Store as `overall_score`

6. **Add Step 6a: Validate `<change>` tag structure (C5).**
   - Use regex patterns from TD2: open tag `<change\s+dimension="([^"]+)"\s+rationale="([^"]*)">`  close tag `</change>`
   - Skip tags inside fenced code blocks: track a boolean `in_fence` state, toggled by lines starting with three or more backticks (```` ``` ````) or three or more tildes (`~~~`), per CommonMark spec. While `in_fence == true`, ignore any `<change>` or `</change>` patterns.
   - Check: every open has close, no nesting, no overlapping, non-empty dimension attribute
   - Build array of ChangeBlock structures (I4) with dimensions, rationale, content, before_context (up to 3 lines from Phase 2 output preceding the `<change>` tag), after_context (up to 3 lines from Phase 2 output following the `</change>` tag). **Implementation note:** Step 6a extracts context lines from the Phase 2 output and populates each ChangeBlock. A single anchor-matching sub-procedure (`match_anchors_in_original`) is defined here to locate those context lines in `original_content` and return the matched region. Both drift detection (P3/Step 6b) and Accept some merge (P4/Step 8c) call this same sub-procedure — do not implement anchor matching separately in each step. Define `match_anchors_in_original` as a labeled, standalone section in the command file (e.g., `## Sub-procedure: match_anchors_in_original`). P3 and P4 reference it by label. Do not inline. **Contract:** Inputs: a ChangeBlock (with before_context, after_context), `original_content` lines, and optional merge-adjacent flag. Returns: `{ matched: true, start_line, end_line }` on unique match, or `{ matched: false, reason }` on zero matches, multiple matches, or overlapping anchor regions.
   - If validation fails: set `tag_validation_failed = true`
   - **Test scenario (from TD2):** Reversed attribute order (e.g., `<change rationale="..." dimension="...">`) must trigger validation failure and degrade to Accept all / Reject

### Verification

- Phase 1 JSON parsing produces exactly 9 dimension entries
- Score calculation matches expected: scores [3,2,1,3,2,3,3,3,2] → sum=22, score=81
- Tag validator catches: missing close tags, nested tags, empty dimension, overlapping pairs
- Tag validator skips tags inside code fences
- Reversed attribute order triggers validation failure (TD2 testing note)

---

## P3: Add Command — Drift Detection + Report Assembly

**File:** `plugins/iflow/commands/promptimize.md` (continuing from P2)
**Design refs:** C6, C7, I5, TD3, TD4
**Spec refs:** R2.5, R5.1-R5.3

### Changes

1. **Add Step 6b: Drift detection (C6).**
   - For each ChangeBlock from Step 6a, locate before_context and after_context anchors in `original_content`
   - Handle edge cases per C6: file start (0-2 before-context lines), file end (0-2 after-context lines), adjacent blocks (merge into single region). Note: the adjacent-block merge logic here (drift detection) and in P4 step 3 (Accept some merge) must use the same anchor-matching algorithm — both operate on the same ChangeBlock array from Step 6a.
   - Replace each `<change>` block with the matched original text between anchors
   - Normalize: strip trailing whitespace per line, ignore blank-line differences at file boundaries
   - Compare normalized reconstructed file to normalized `original_content`
   - If different: set `drift_detected = true`
   - If tag_validation_failed from Step 6a, skip drift detection (tags can't be reliably parsed)

2. **Add Step 6c: Token budget check (C7 partial).**
   - Strip all `<change>` and `</change>` tags from Phase 2 content
   - Count lines and words. The spec says "5,000 tokens" but the LLM cannot count tokens, so use 5,000 words as a conservative proxy per design decision C7 (roughly 1.3 tokens per word for English Markdown, so 5,000 words ≈ 6,500 tokens — this intentionally over-warns rather than under-warns).
   - If exceeds 500 lines or 5,000 words: set `over_budget_warning = true`

3. **Add Step 7: Assemble report (C7).**
   - Use same report template structure as current Step 7 in SKILL.md
   - Populate from Phase 1 JSON: component type, dimension scores, findings, suggestions
   - Populate `overall_score` from Step 5
   - Strengths: evaluated dimensions scoring pass (3), excluding auto-passed
   - Issues table: partial (warning) and fail (blocker) dimensions, blockers first
   - Improved Version: Phase 2 output verbatim
   - Conditional warnings: staleness (from Phase 1 JSON `staleness_warning`/`guidelines_date`), over-budget (from Step 6c)

### Verification

- Drift detection catches: modified whitespace outside `<change>` blocks, added/removed lines
- Drift detection ignores: trailing whitespace differences, file-boundary blank lines
- Adjacent block merging works correctly (no false anchor overlap)
- Report template matches current format (AC1a, AC8)
- Staleness warning appears when `staleness_warning: true`
- Over-budget warning appears when exceeding thresholds

---

## P4: Add Command — Approval Handler + Merge Engine + Accept All

**File:** `plugins/iflow/commands/promptimize.md` (continuing from P3)
**Design refs:** C8, C9, C10, I5, TD4, TD5
**Spec refs:** R4.1-R4.5, R6.3

### Changes

1. **Add Step 8: Approval handler (C8).**
   - If `overall_score == 100` AND tag validation found zero ChangeBlocks: display "All dimensions passed — no improvements needed." STOP. (R4.5)
   - Edge cases (defensive checks for LLM error conditions not covered by spec ACs — both must be implemented): if `overall_score == 100` but ChangeBlocks exist (LLM error — produced changes for pass dimensions), log warning "Score is 100 but change blocks found" and show normal approval menu with standard option-gating (Accept some only if `tag_validation_failed == false` AND `drift_detected == false`). If `overall_score < 100` but zero ChangeBlocks (LLM failed to produce changes for non-pass dimensions), show report with note "Dimensions scored partial/fail but no changes were generated."
   - If `[YOLO_MODE]` is active: auto-select "Accept all" (R6.3)
   - Otherwise: present AskUserQuestion with options based on validation state
     - Always: "Accept all", "Reject"
     - Only if `tag_validation_failed == false` AND `drift_detected == false`: "Accept some"
     - Distinct warning messages per C8: tag validation failure, drift detected, anchor match failure

2. **Add Accept all handler (C10).**
   - Strip all `<change ...>` and `</change>` tags via regex from Phase 2 output
   - Write to original file path
   - Display: "Improvements applied to {filename}. Run `./validate.sh` to verify."

3. **Add Accept some handler (C9).**
   - Present dimension multiSelect — overlapping dimensions (comma-separated) as single option
   - Start from `original_content` (from Step 2.5)
   - For selected dimensions: call `match_anchors_in_original` (defined in P2/Step 6a) to find unique before+after context anchors in `original_content`, replace matched region with `<change>` block content. Apply the same adjacent-block merging logic defined in P3 Step 6b — merge ChangeBlocks whose anchor windows overlap before computing simultaneous replacements.
   - For unselected dimensions: keep original text (no replacement)
   - All replacements computed simultaneously against original (TD4) — collect (start_line, end_line, replacement) tuples, sort by start_line, verify no overlaps, interleave
   - If anchor match fails for any block: degrade to Accept all / Reject with warning
   - Strip residual `<change>` tags (defensive, final operation per C9 step 9)
   - Write to original file path

4. **Add Reject handler.**
   - Display "No changes applied." STOP.

5. **Add PROHIBITED section to command.**
   - "NEVER write improvements without user approval via AskUserQuestion (Step 8). Exception: YOLO mode auto-selects Accept all."
   - "NEVER skip the approval step in non-YOLO mode."
   - "NEVER present Accept some when tag_validation_failed or drift_detected is true."

### Verification

- Accept all produces clean file with no XML tags (AC5)
- Accept some with 3 dimensions (A, B, C), selecting A and C: output has A and C changes applied, B region has original content, zero residual tags (AC3)
- Malformed tags trigger fallback warning (AC4)
- YOLO mode auto-selects Accept all (AC7)
- All-pass scenario skips approval menu (R4.5)
- Simultaneous replacement: no line-offset drift between blocks

---

## P5: Update Content Regression Tests

**File:** `plugins/iflow/hooks/tests/test-promptimize-content.sh`
**Spec refs:** AC9

The redesign moves several responsibilities from SKILL.md to the command. Nine existing tests grep for patterns that will no longer exist in SKILL.md. These must be updated so the test suite passes against the new structure.

### Tests to Update

| # | Test function | Current assertion (SKILL.md) | New assertion | Reason |
|---|---------------|------------------------------|---------------|--------|
| 1 | `test_skill_uses_xml_not_html_markers` (renamed from `test_skill_documents_change_end_change_format`) | Greps `CHANGE:` + `END CHANGE` | Two assertions: (1) grep `<change` + `</change>` present in SKILL.md, (2) grep `CHANGE:` + `END CHANGE` absent from SKILL.md (use `grep -v` or assert exit code 1) | HTML markers replaced with XML tags; absence check prevents accidental retention of old markers |
| 2 | `test_skill_has_accept_all_option` | Greps `Accept all` in SKILL.md | Grep `Accept all` in **promptimize.md** | Approval moved to command |
| 3 | `test_skill_has_accept_some_option` | Greps `Accept some` in SKILL.md | Grep `Accept some` in **promptimize.md** | Approval moved to command |
| 4 | `test_skill_has_reject_option` | Greps `Reject` in SKILL.md | Grep `Reject` in **promptimize.md** | Approval moved to command |
| 5 | `test_skill_has_yolo_mode_overrides` | Greps `YOLO` in SKILL.md | **Delete test** — replaced by new `test_cmd_has_yolo_mode_handling` (see New Tests table) | YOLO section removed from skill, moved to command |
| 6 | `test_skill_has_malformed_marker_fallback` | Greps `malformed.*marker` in SKILL.md | Grep `tag_validation_failed` or `malformed` in **promptimize.md** | Tag validation moved to command |
| 7 | `test_skill_documents_scoring_formula` | Greps `27` in SKILL.md | Grep `27` in **promptimize.md** | Score calculation moved to command |
| 8 | `test_skill_report_template_has_required_fields` | Greps `Overall score` + `Component type` in SKILL.md | Grep `overall_score\|Overall score` + `component_type\|Component type` in **promptimize.md** (matches either JSON field names or report template display names) | Report assembly moved to command |
| 9 | `test_skill_severity_mapping_documented` | Greps `blocker` + `warning` in SKILL.md | Grep `blocker` + `warning` in **promptimize.md** | Severity mapping moved to command |

### New Tests to Add

| # | Test function | Assertion | Purpose |
|---|---------------|-----------|---------|
| 1 | `test_skill_has_phase1_output_tags` | SKILL.md contains `phase1_output` | Verify two-phase output structure |
| 2 | `test_skill_has_phase2_output_tags` | SKILL.md contains `phase2_output` | Verify two-phase output structure |
| 3 | `test_skill_has_grading_result_block` | SKILL.md contains `grading_result` | Verify Phase 1→2 handoff (AC1b) |
| 4 | `test_cmd_has_score_computation` | promptimize.md contains `round` and `27` | Score computed in command (AC2) |
| 5 | `test_cmd_has_drift_detection` | promptimize.md contains `drift_detected` | Drift detection present (AC10) |
| 6 | `test_cmd_has_tag_validation` | promptimize.md contains `tag_validation_failed` | Tag validation present (AC4) |
| 7 | `test_cmd_has_yolo_mode_handling` | promptimize.md contains `YOLO_MODE` or `YOLO` | YOLO auto-accept behavior documented in command (replaces deleted skill-level YOLO test) |

### Implementation Notes

- After updating/adding/deleting test functions, update the `main()` function at the bottom of the file: rename the call from `test_skill_documents_change_end_change_format` to `test_skill_uses_xml_not_html_markers`, remove the call to `test_skill_has_yolo_mode_overrides`, and add calls to the 7 new test functions in the appropriate dimension section.

### Verification

- `bash plugins/iflow/hooks/tests/test-promptimize-content.sh` passes with 0 failures
- No tests reference removed patterns (`CHANGE:`, `END CHANGE` in SKILL.md; `27` in SKILL.md; `Accept all/some` in SKILL.md)
- New tests cover the key structural contracts of the redesign
- Test #1 in the Tests to Update table (renamed `test_skill_uses_xml_not_html_markers`) asserts both presence of new XML patterns AND absence of old HTML patterns

---

## P6: Validation and Cleanup

**Design refs:** File Change Summary
**Spec refs:** AC9

### Changes

1. **Run `./validate.sh`** — verify all modified files pass structural validation.

2. **Run `test-promptimize-content.sh`** — verify all content regression tests pass.

3. **Cross-file consistency checks:**
   - SKILL.md no longer contains: HTML `<!-- CHANGE -->` markers, score calculation, approval logic, YOLO overrides section
   - Command references skill output format (`<phase1_output>`, `<phase2_output>`) correctly
   - `original_content` label is used consistently in command Steps 2.5, 6b (drift detection), and 8c (note: SKILL.md uses `target_content` — `original_content` should only appear in the command)
   - All 9 dimension names from I2 are consistent between skill and command
   - TD2 regex pattern in command matches the tag format specified in skill: grep command for `<change\s+dimension=` pattern and confirm skill Phase 2 instructions show an example tag with dimension before rationale
   - Command PROHIBITED section contains all three rules moved from skill: (1) no writing without approval, (2) no skipping approval in non-YOLO mode, (3) no presenting Accept some when tag_validation_failed or drift_detected is true

4. **Token budget verification:**
   - SKILL.md under 500 lines / 5,000 tokens
   - Command file is within reasonable bounds (no hard limit but should be maintainable)

---

## Acceptance Criteria Traceability

| AC | Plan Step | Verification |
|----|-----------|-------------|
| AC1a | P1 (Phase 1 + Phase 2 output format) | Skill produces `<phase1_output>` JSON + `<phase2_output>` with `<change>` tags |
| AC1b | P1 step 3 (`<grading_result>` block) | Code review: Phase 2 wraps Phase 1 JSON in `<grading_result>` |
| AC2 | P2 step 5 (score calculation) | Command computes score from JSON, not in LLM output |
| AC3 | P4 step 3 (Accept some merge) | Selected dimensions applied, unselected keep original, no residual tags |
| AC4 | P2 step 6a + P4 step 1 (tag validation + approval) | Malformed tags → warning → degrade to Accept all / Reject |
| AC5 | P4 step 2 (Accept all) | Strip all tags, clean file output |
| AC6 | P1 change 2 (Phase 1 JSON schema, auto_passed field) + P1 change 3 (Phase 2 no `<change>` tags for pass dims per R2.4) | Auto-passed dims score 3, no `<change>` tags |
| AC7 | P4 step 1 (YOLO mode) | YOLO auto-selects Accept all |
| AC8 | P3 step 3 (report assembly) | Staleness and over-budget warnings from structured data |
| AC9 | P5 (test updates) + P6 steps 1-2 (validate.sh + test-promptimize-content.sh) | Both pass after changes |
| AC10 | P3 step 1 (drift detection) | Drift disables Accept some, warns user |
