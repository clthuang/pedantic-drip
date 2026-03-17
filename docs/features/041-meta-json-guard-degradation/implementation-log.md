# Implementation Log: meta-json-guard Degradation Path

## Phase 1: Test Preparation

### Tasks 1.1-1.3: Refactor deny tests to helpers
- Converted 3 deny tests from inline `HOME="$(mktemp -d)"` to `setup_meta_guard_test`/`teardown_meta_guard_test` pattern
- Files changed: `plugins/iflow/hooks/tests/test-hooks.sh`

### Task 1.4: Add sentinel to 5 existing tests
- Added `.bootstrap-complete` sentinel creation to all 5 tests that expect deny behavior
- Path: `$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/iflow-test/1.0.0/.venv/.bootstrap-complete`

### Tasks 1.5-1.8: Add 4 new tests
- `test_meta_json_guard_permits_when_no_sentinel` — no sentinel, expects `{}`
- `test_meta_json_guard_logs_permit_degraded` — no sentinel, checks log action field
- `test_meta_json_guard_deny_message_has_feature_type_id` — sentinel present, checks reason string
- `test_meta_json_guard_deny_message_has_fallback` — sentinel present, checks reason string

## Phase 2: Code Changes

### Task 2.1: Add `check_mcp_available()` function
- `ls` glob with stdout+stderr suppressed, returns exit code

### Task 2.2: Rename + action param (atomic)
- `log_blocked_attempt` -> `log_guard_event`
- Added optional 3rd param `action`, builds conditional `action_field` in JSONL
- Updated call site simultaneously

### Task 2.3: Add degraded permit path
- `if ! check_mcp_available` block after python3 parse, before deny
- Logs `permit-degraded`, echoes `{}`, exits 0

### Task 2.4: Update REASON string
- Added `feature_type_id` format, parameter hints, fallback instruction

### Task 2.5: Full test suite
- 67/67 passed, 1 skipped (not on main branch)
- 13 meta-json-guard tests: 9 existing + 4 new, all green

## Files Changed
- `plugins/iflow/hooks/meta-json-guard.sh`
- `plugins/iflow/hooks/tests/test-hooks.sh`

## Decisions
- Implemented all tasks directly (no per-task agent dispatch) since changes were mechanical and well-specified
- Kept TDD ordering: test changes committed alongside code changes (both phases in single commit since all tests pass)
