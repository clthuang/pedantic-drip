# Tasks: meta-json-guard Degradation Path

## Phase 1: Prepare All Tests

### Task 1.1: Refactor deny test `denies_write` to use helpers
- [ ] In `test_meta_json_guard_denies_write` (line ~1323), transform:
  - Before: `output=$(echo '...' | HOME="$(mktemp -d)" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)`
  - After: `setup_meta_guard_test` at function start, `output=$(echo '...' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)` for the invocation, `teardown_meta_guard_test` at function end
- [ ] Run test in isolation to verify it still passes

**Done when:** `test_meta_json_guard_denies_write` passes using helper pattern instead of inline mktemp.

### Task 1.2: Refactor deny test `denies_edit` to use helpers
- [ ] Same before/after transformation as Task 1.1 for `test_meta_json_guard_denies_edit` (line ~1337)

**Done when:** `test_meta_json_guard_denies_edit` passes using helper pattern.

### Task 1.3: Refactor deny test `denies_project_meta` to use helpers
- [ ] Same before/after transformation as Task 1.1 for `test_meta_json_guard_denies_project_meta` (line ~1351)

**Done when:** `test_meta_json_guard_denies_project_meta` passes using helper pattern.

### Task 1.4: Add sentinel to 5 existing tests
> Depends on: Tasks 1.1, 1.2, 1.3

- [ ] In each of the 3 refactored deny tests (1.1-1.3), add after `setup_meta_guard_test`:
  ```bash
  mkdir -p "$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/iflow-test/1.0.0/.venv"
  touch "$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/iflow-test/1.0.0/.venv/.bootstrap-complete"
  ```
- [ ] Add same sentinel creation to `test_meta_json_guard_logs_blocked_attempt` (after existing `setup_meta_guard_test`)
- [ ] Add same sentinel creation to `test_meta_json_guard_extracts_feature_id` (after existing `setup_meta_guard_test`)
- [ ] Run all 9 existing meta-json-guard tests — all pass (sentinel is harmless, no check exists yet)

**Done when:** All 9 existing tests pass with sentinels created in temp HOME.

### Task 1.5: Add test `permits_when_no_sentinel`
- [ ] Add new test function `test_meta_json_guard_permits_when_no_sentinel` after `test_meta_json_guard_latency`
- [ ] Use `setup_meta_guard_test` / `teardown_meta_guard_test` — do NOT create sentinel
- [ ] Invoke hook and assert with defensive capture:
  ```bash
  output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true
  if [[ "$output" == "{}" ]]; then
      log_pass
  else
      log_fail "Expected {}, got: $output"
  fi
  ```
- [ ] Add function call to the test runner section (after `test_meta_json_guard_latency`)
- [ ] **Red-phase note:** Before Phase 2, hook has no sentinel check — it will deny, returning deny JSON (not `{}`). The `output != '{}'` assertion is the expected red failure point. The `|| true` prevents `set -e` from aborting the suite.

**Done when:** Test exists and will pass once Phase 2 adds degraded permit path (fails red now — expected).

### Task 1.6: Add test `logs_permit_degraded`
- [ ] Add new test function `test_meta_json_guard_logs_permit_degraded`
- [ ] Use helpers, no sentinel. Invoke hook with `.meta.json` Write input (defensive capture with `|| true`)
- [ ] Read log file at `$META_GUARD_TMPDIR/.claude/iflow/meta-json-guard.log`
- [ ] Assert last JSONL line has `"action": "permit-degraded"` via python3 parse
- [ ] Add function call to the test runner section (after `test_meta_json_guard_permits_when_no_sentinel`)
- [ ] **Red-phase note:** Before Phase 2, the log file will be created with a standard deny entry (no `action` field). The assertion for `"action": "permit-degraded"` is the expected red failure point, not the log file existence check.

**Done when:** Test exists and will pass once Phase 2 adds degraded logging (fails red now — expected).

### Task 1.7: Add test `deny_message_has_feature_type_id`
- [ ] Add new test function `test_meta_json_guard_deny_message_has_feature_type_id`
- [ ] Use helpers, create sentinel. Invoke hook with `.meta.json` Write for feature `034-enforced-state-machine`
- [ ] Capture deny output, parse `permissionDecisionReason`
- [ ] Assert reason contains `feature:` substring (the `feature:{id}-{slug}` pattern)
- [ ] Add function call to the test runner section (after `test_meta_json_guard_logs_permit_degraded`)

**Done when:** Test exists and will pass once Phase 2 updates REASON string (fails red now — expected).

### Task 1.8: Add test `deny_message_has_fallback`
- [ ] Add new test function `test_meta_json_guard_deny_message_has_fallback`
- [ ] Use helpers, create sentinel. Invoke hook with `.meta.json` Write
- [ ] Capture deny output, parse `permissionDecisionReason`
- [ ] Assert reason contains `fallback` substring
- [ ] Add function call to the test runner section (after `test_meta_json_guard_deny_message_has_feature_type_id`)

**Done when:** Test exists and will pass once Phase 2 updates REASON string (fails red now — expected).

### Task 1.9: Verify Phase 1 test state
- [ ] Run `bash plugins/iflow/hooks/tests/test-hooks.sh`
- [ ] Confirm 9 existing meta-json-guard tests pass
- [ ] Confirm 4 new tests fail (red — expected, no code changes yet)
- [ ] **Note:** The suite will exit non-zero due to the 4 red tests — this is expected. Verify the pass/fail breakdown in the output rather than relying on exit code.

**Done when:** 9 pass, 4 fail.

## Phase 2: Implement Code Changes

> Depends on: Phase 1 complete

### Task 2.1: Add `check_mcp_available()` function
- [ ] Add function before `log_blocked_attempt` (around line 39) in `meta-json-guard.sh` (this function will be renamed to `log_guard_event` in Task 2.2 — placement anchor is valid at time of this task):
  ```bash
  check_mcp_available() {
      ls "$HOME"/.claude/plugins/cache/*/iflow*/*/.venv/.bootstrap-complete >/dev/null 2>/dev/null
  }
  ```
- [ ] Verify no syntax errors: `bash -n plugins/iflow/hooks/meta-json-guard.sh`

**Done when:** Function exists, file parses without errors.

### Task 2.2: Rename `log_blocked_attempt` to `log_guard_event` with action param AND update deny call site

This task is atomic — rename the function and update its call site in the same edit to avoid a broken intermediate state (the old call site would reference a non-existent function).

- [ ] Rename function `log_blocked_attempt` → `log_guard_event`
- [ ] Add third parameter: `local action="${3:-}"`
- [ ] Add to the `local` declaration line: `action_field`
- [ ] Add conditional action field building:
  ```bash
  if [[ -n "$action" ]]; then
      action_field=",\"action\":\"$(escape_json "$action")\""
  else
      action_field=""
  fi
  ```
- [ ] Update the JSONL echo line to append `${action_field}` before the closing `}`
- [ ] Update the call site: change `log_blocked_attempt "$FILE_PATH" "$TOOL_NAME"` → `log_guard_event "$FILE_PATH" "$TOOL_NAME"` (no action param for deny)
- [ ] Verify: `bash -n plugins/iflow/hooks/meta-json-guard.sh` passes AND run existing deny tests to confirm no regression

**Done when:** Function renamed, accepts optional action param, call site updated. No references to `log_blocked_attempt` remain. Existing tests pass.

### Task 2.3: Add degraded permit path
> Depends on: Task 2.2

- [ ] After the `if [[ "$FILE_PATH" != *".meta.json" ]]` block and before the `log_guard_event "$FILE_PATH" "$TOOL_NAME"` call (the deny path), add:
  ```bash
  if ! check_mcp_available; then
      log_guard_event "$FILE_PATH" "$TOOL_NAME" "permit-degraded"
      echo '{}'
      exit 0
  fi
  ```

**Done when:** Degraded permit path exists. Hook permits writes when no sentinel found.

### Task 2.4: Update REASON string
> No blocking dependency — can run in parallel with Tasks 2.1-2.3

- [ ] Replace the REASON string with:
  ```bash
  REASON="Direct .meta.json writes are blocked. Use MCP workflow tools instead: transition_phase(feature_type_id, target_phase) to enter a phase, complete_phase(feature_type_id, phase) to finish a phase, or init_feature_state(...) to create a new feature. The feature_type_id format is \"feature:{id}-{slug}\" (e.g., \"feature:041-meta-json-guard-degradation\"). If MCP workflow tools are not available in this session, the guard will allow direct writes as a fallback."
  ```

**Done when:** REASON contains `feature_type_id` format guidance and fallback instruction.

### Task 2.5: Run full test suite
> Depends on: Tasks 2.1-2.4

- [ ] Run `bash plugins/iflow/hooks/tests/test-hooks.sh`
- [ ] Verify all 13 meta-json-guard tests pass (9 existing + 4 new)
- [ ] Verify no regressions in other hook test sections (common.sh, detect_project_root, session-start, pre-commit-guard, sync-cache, YOLO, path portability)

**Done when:** All 13 meta-json-guard tests pass. Zero regressions in other sections.
