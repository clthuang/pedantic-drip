# Tasks: QA Findings Batch Cleanup

All tasks reference verbatim diffs from `design.md` interfaces I-1..I-9. No re-statement of bodies; implementer reads design.md for the exact text.

## Phase 1: Independent Code Edits (parallelizable group A)

### T1: Add CLAUDE_CODE_DEV_MODE guard to capture-on-stop.sh seam (FR-5, #00315)

- [ ] Read design.md I-1 for the exact replacement.
- [ ] Apply edit to `plugins/pd/hooks/capture-on-stop.sh` lines 42-43: prepend `[[ "${CLAUDE_CODE_DEV_MODE:-}" == "1" ]] &&` to each `[[ -n "${PD_TEST_WRITER_*}" ]]` line. Add `# Feature 106 FR-5:` comment above.
- [ ] Verify AC-5.1:
  ```bash
  section=$(awk '/# Feature 104 test-injection seam/,/^[[:space:]]*$/' plugins/pd/hooks/capture-on-stop.sh)
  echo "$section" | grep -q "CLAUDE_CODE_DEV_MODE" || { echo "AC-5.1 FAIL: guard missing"; exit 1; }
  echo "$section" | grep -q "PD_TEST_WRITER_PYTHONPATH" || { echo "AC-5.1 FAIL: seam missing"; exit 1; }
  echo "AC-5.1 PASS"
  ```
- [ ] DoD: AC-5.1 prints PASS.

### T5: Swap validate.sh log_info ordering (FR-6, #00316)

- [ ] Read design.md I-5 for the exact diff.
- [ ] Apply edit to `validate.sh`: swap the two `log_info` lines so `"Codex Reviewer Routing exclusions validated"` prints before `"Codex routing coverage allowlist validated (11 expected files)"`.
- [ ] Verify AC-6.1:
  ```bash
  exclusion_line=$(grep -n "exclusions validated" validate.sh | head -1 | cut -d: -f1)
  allowlist_line=$(grep -n "allowlist validated" validate.sh | head -1 | cut -d: -f1)
  [ "$exclusion_line" -lt "$allowlist_line" ] && echo "AC-6.1 PASS" || echo "AC-6.1 FAIL"
  ```
- [ ] DoD: AC-6.1 prints PASS; `./validate.sh` exits 0 (AC-6.2).

### T6: Drop "(line 726)" from secretary.md R-8 note (FR-7, #00318)

- [ ] Read design.md I-6 for the exact edit.
- [ ] Apply edit to `plugins/pd/commands/secretary.md`: remove ` (line 726)` parenthetical from the R-8 note paragraph. "Step 7 DELEGATE" anchor text preserved.
- [ ] Verify AC-7.1 + AC-7.2:
  ```bash
  grep -A 1 "Dynamic agent dispatch at Step 7 DELEGATE" plugins/pd/commands/secretary.md | grep -q "(line 726)" && echo "AC-7.1 FAIL" || echo "AC-7.1 PASS"
  grep -q "Step 7 DELEGATE" plugins/pd/commands/secretary.md && echo "AC-7.2 PASS" || echo "AC-7.2 FAIL"
  ```
- [ ] DoD: AC-7.1 + AC-7.2 both PASS.

### T7: Append TD-2 amendment to feature 104 design.md (FR-1a, #00310)

- [ ] Read design.md I-7 for the exact paragraph.
- [ ] Append the verbatim TD-2 amendment paragraph to `docs/features/104-batch-b-test-hardening/design.md` at the end of the existing TD-2 section (before TD-3 heading or end of TD section).
- [ ] Verify AC-1.1:
  ```bash
  grep -A 30 "^### TD-2" docs/features/104-batch-b-test-hardening/design.md | grep -q "PD_TEST_WRITER_PYTHONPATH" || { echo "FAIL"; exit 1; }
  grep -A 30 "^### TD-2" docs/features/104-batch-b-test-hardening/design.md | grep -q "PD_TEST_WRITER_PYTHON" || { echo "FAIL"; exit 1; }
  echo "AC-1.1 PASS"
  ```
- [ ] DoD: AC-1.1 PASS.

### T8: Add dev_guide subsection on evidence paths (FR-1b, #00319)

- [ ] Read design.md I-8 for the exact subsection.
- [ ] Append the verbatim "## Committed vs gitignored evidence paths" subsection to `docs/dev_guides/component-authoring.md`.
- [ ] Verify AC-1.2:
  ```bash
  awk '/^##/{section=$0} /agent_sandbox/{found_sb=1; sb_section=section} /gitignore|gitignored/{if(section==sb_section)found_gi=1} END{exit !(found_sb && found_gi)}' docs/dev_guides/component-authoring.md && echo "AC-1.2 PASS" || echo "AC-1.2 FAIL"
  ```
- [ ] DoD: AC-1.2 PASS.

## Phase 2: Test Refactor + Consolidation (parallelizable group B — different files)

### T3: Consolidate test-session-start files (FR-3, #00312, subsumes #00314)

- [ ] Read design.md I-3 for the merged-file structure.
- [ ] Read existing `plugins/pd/hooks/tests/test_session_start_cleanup.sh` (5 mcp-server tests with copy-paste extraction).
- [ ] Read existing `plugins/pd/hooks/tests/test-session-start.sh` (1 correction-buffers test with sed-extract, AC-6.1).
- [ ] In `plugins/pd/hooks/tests/test-session-start.sh`:
  - Update header comment to mention both functions covered.
  - Add 5 new test functions for `cleanup_stale_mcp_servers` (test_stale_pid_file_removed, test_missing_pid_dir, test_invalid_pid_content, test_non_orphaned_process, test_orphan_double_fork) — copy logic from underscored file but REPLACE the copy-paste extraction with sed-extract:
    ```bash
    sed -n '/^cleanup_stale_mcp_servers()/,/^}/p' "${HOOKS_DIR}/session-start.sh" > "$fn_tmpfile"
    source "$fn_tmpfile"
    ```
  - Update bottom-of-file to invoke all 6 tests sequentially.
- [ ] Delete `plugins/pd/hooks/tests/test_session_start_cleanup.sh`: `git rm plugins/pd/hooks/tests/test_session_start_cleanup.sh`.
- [ ] Verify AC-3.1:
  ```bash
  test -f plugins/pd/hooks/tests/test-session-start.sh || { echo "FAIL: hyphenated file missing"; exit 1; }
  test ! -f plugins/pd/hooks/tests/test_session_start_cleanup.sh || { echo "FAIL: underscored file still present"; exit 1; }
  grep -q "cleanup_stale_correction_buffers" plugins/pd/hooks/tests/test-session-start.sh || { echo "FAIL: correction-buffers ref missing"; exit 1; }
  grep -q "cleanup_stale_mcp_servers" plugins/pd/hooks/tests/test-session-start.sh || { echo "FAIL: mcp-servers ref missing"; exit 1; }
  echo "AC-3.1 PASS"
  ```
- [ ] Verify AC-3.2:
  ```bash
  count_corr=$(grep -c "sed -n '/^cleanup_stale_correction_buffers" plugins/pd/hooks/tests/test-session-start.sh)
  count_mcp=$(grep -c "sed -n '/^cleanup_stale_mcp_servers" plugins/pd/hooks/tests/test-session-start.sh)
  [[ "$count_corr" -ge 1 && "$count_mcp" -ge 1 ]] && echo "AC-3.2 PASS" || echo "AC-3.2 FAIL"
  ```
- [ ] Verify AC-3.3:
  ```bash
  test_count=$(grep -cE "^[[:space:]]*test_[a-zA-Z_]+\(\)" plugins/pd/hooks/tests/test-session-start.sh)
  [[ "$test_count" -ge 6 ]] || { echo "FAIL: only $test_count tests, expected ≥6"; exit 1; }
  echo "AC-3.3 PASS ($test_count tests)"
  ```
- [ ] Verify AC-3.4: `bash plugins/pd/hooks/tests/test-session-start.sh` exits 0.
- [ ] DoD: AC-3.1 + AC-3.2 + AC-3.3 + AC-3.4 all PASS.

### T4: Refactor test_category_mapping in test-capture-on-stop.sh (FR-4, #00313)

- [ ] Read design.md I-4 for the refactor structure.
- [ ] Read `plugins/pd/hooks/tests/test-capture-on-stop.sh:188` for the existing `test_category_mapping` body.
- [ ] Replace `test_category_mapping()` with two functions:
  - `test_category_mapping_anti_patterns()` — anti-pattern branch, own setup/teardown
  - `test_category_mapping_preference()` — preference (patterns) branch, own setup/teardown
- [ ] Update bottom-of-file invocation: replace `test_category_mapping` line with `test_category_mapping_anti_patterns` and `test_category_mapping_preference` (two lines).
- [ ] Verify AC-4.1:
  ```bash
  count=$(grep -cE "^test_category_(anti_patterns|preference)\(\)" plugins/pd/hooks/tests/test-capture-on-stop.sh)
  [[ "$count" -ge 2 ]] && echo "AC-4.1 PASS ($count functions)" || echo "AC-4.1 FAIL"
  ```
- [ ] Verify AC-4.2: `bash plugins/pd/hooks/tests/test-capture-on-stop.sh` exits 0.
- [ ] DoD: AC-4.1 + AC-4.2 PASS.

## Phase 3: Runner Wiring (after T3 + T4)

### T2: Wire 3 test scripts into test-hooks.sh runner + commands-reference.md (FR-2, #00311)

- [ ] Read design.md I-2 for the exact insertion block.
- [ ] Locate `main()` in `plugins/pd/hooks/tests/test-hooks.sh`. Find the result-summary block (`echo "=========================================="` near end of `main()`).
- [ ] Insert the I-2 block (External Test Scripts section with 3 conditional invocations) before the result-summary block.
- [ ] Locate or add a Test Commands section in `docs/dev_guides/commands-reference.md`. Add a one-liner: `bash plugins/pd/hooks/tests/test-hooks.sh` runs hook integration tests including consolidated external test scripts.
- [ ] Verify AC-2.1:
  ```bash
  grep -cE "^[[:space:]]*(bash|\./|\"\\\$SCRIPT_DIR\"/|\\\$SCRIPT_DIR/)[^#]*test-tag-correction\.sh" plugins/pd/hooks/tests/test-hooks.sh
  grep -cE "^[[:space:]]*(bash|\./|\"\\\$SCRIPT_DIR\"/|\\\$SCRIPT_DIR/)[^#]*test-capture-on-stop\.sh" plugins/pd/hooks/tests/test-hooks.sh
  grep -cE "^[[:space:]]*(bash|\./|\"\\\$SCRIPT_DIR\"/|\\\$SCRIPT_DIR/)[^#]*test-session-start\.sh" plugins/pd/hooks/tests/test-hooks.sh
  ```
  Required: each grep ≥1.
- [ ] Verify AC-2.2: `bash plugins/pd/hooks/tests/test-hooks.sh` exits 0 (now invokes 3 external scripts; all must pass).
- [ ] Verify AC-2.3: `grep -E "test-hooks\.sh" docs/dev_guides/commands-reference.md | head -1` returns ≥1 match.
- [ ] DoD: AC-2.1 + AC-2.2 + AC-2.3 all PASS.

## Phase 4: Backlog Annotations

### T9: Annotate 10 backlog rows (FR-8)

- [ ] Read design.md I-9 for the per-row append text.
- [ ] For each of #00310 through #00319 in `docs/backlog.md`, append the disposition text per the I-9 table.
- [ ] Verify AC-8.1:
  ```bash
  for id in 00310 00311 00312 00313 00314 00315 00316 00317 00318 00319; do
    grep -E "^- \*\*#$id\*\*.*(\(closed:|fixed in feature:106|wontfix)" docs/backlog.md > /dev/null \
      || { echo "FAIL: #$id not annotated"; exit 1; }
  done
  echo "AC-8.1 PASS"
  ```
- [ ] DoD: AC-8.1 PASS.

## Phase 5: Final Validation

### T10: Run validate.sh + test-hooks.sh + pattern_promotion pytest

- [ ] Run `./validate.sh` → expect exit 0.
- [ ] Run `bash plugins/pd/hooks/tests/test-hooks.sh` → expect exit 0 (includes 3 external scripts via FR-2 wiring).
- [ ] Run `cd plugins/pd && .venv/bin/python -m pytest hooks/lib/pattern_promotion/ -q && cd -` → expect exit 0.
- [ ] DoD: all 3 commands pass.

## Phase 6: Final Commit + Phase Complete

After T10 passes: commit any uncommitted artifacts, push, and let the create-plan skill flow into the relevance gate + auto-chain to /pd:implement (per skill Step 4b).
