# Plan: meta-json-guard Degradation Path

## Implementation Order

Single file (`plugins/iflow/hooks/meta-json-guard.sh`) with test updates in `plugins/iflow/hooks/tests/test-hooks.sh`. TDD order: write/update tests first, then implement code changes.

### Phase 1: Prepare All Tests

**Why first:** All test changes (both updating existing tests and adding new ones) must land before code changes in Phase 2. The sentinel additions to existing tests are harmless now (no sentinel check exists yet) but required before Phase 2 introduces the check. New tests will fail (red) until Phase 2.

**Step 1: Refactor 3 deny tests to use helpers**

Convert `test_meta_json_guard_denies_write`, `test_meta_json_guard_denies_edit`, `test_meta_json_guard_denies_project_meta` from inline `HOME="$(mktemp -d)"` to `setup_meta_guard_test`/`teardown_meta_guard_test` pattern. Specifically:
- (a) Call `setup_meta_guard_test` at test start
- (b) Use `HOME="$META_GUARD_TMPDIR"` in the hook invocation line (replacing inline mktemp)
- (c) Keep existing stdout capture pattern (`output=$(... | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)`) — note: tests invoke the script directly, not via `bash`
- (d) Call `teardown_meta_guard_test` at test end

**Step 2: Add sentinel to all 5 existing tests**

Create `.bootstrap-complete` sentinel in `META_GUARD_TMPDIR` for:
- 3 refactored deny tests (from step 1)
- 2 existing log tests (`test_meta_json_guard_logs_blocked_attempt`, `test_meta_json_guard_extracts_feature_id`)

**Step 3: Add 4 new tests**

- `test_meta_json_guard_permits_when_no_sentinel` — No sentinel in temp HOME → hook returns `{}` (uses helpers, no sentinel created). **Note:** Before Phase 2, hook has no sentinel check so this test will get a deny instead of permit. Use defensive assertion: capture exit code and output, assert non-zero exit or `{}` — the test will fail (red) until Phase 2 adds the degraded path.
- `test_meta_json_guard_logs_permit_degraded` — No sentinel → verify JSONL log has `"action": "permit-degraded"` (uses helpers, no sentinel created). Will fail (red) until Phase 2.
- `test_meta_json_guard_deny_message_has_feature_type_id` — Sentinel present → deny message contains `feature:{id}-{slug}` (uses helpers, creates sentinel). Will fail (red) until Phase 2 updates REASON string.
- `test_meta_json_guard_deny_message_has_fallback` — Sentinel present → deny message contains fallback instruction (uses helpers, creates sentinel). Will fail (red) until Phase 2 updates REASON string.

**Test safety under `set -euo pipefail`:** New tests that expect failure (non-zero exit) must capture output and exit code defensively (e.g., `output=$(...) || true` or `if output=$(...); then fail; fi`) to avoid aborting the test suite.

**Step 4: Verify existing tests still pass** — Run `bash plugins/iflow/hooks/tests/test-hooks.sh`. Expect 9 existing meta-json-guard tests pass. The 4 new tests from Step 3 will fail (red — expected, no code changes yet).

### Phase 2: Implement Code Changes (Green)

**Why second:** Make the new tests pass while keeping existing tests green.

**Step 5: Add `check_mcp_available()` function** — New function using `ls` glob with `>/dev/null 2>/dev/null`, defined near existing function block (before call site).

**Step 6: Rename `log_blocked_attempt` → `log_guard_event`** — Add optional `action` parameter, build conditional `action_field` in JSONL output.

**Step 7: Add degraded permit path** — `if ! check_mcp_available; then log_guard_event + echo '{}' + exit 0` block after python3 parse, before existing log+deny block. Must happen after Step 6 (calls `log_guard_event`). Note: if logging fails, the ERR trap (`install_err_trap` emitting `{}`) provides crash-level safety — no additional error handling needed.

**Step 8: Update deny call site** — Change `log_blocked_attempt` → `log_guard_event` (no action param). Must happen after Step 6 (rename).

**Step 9: Update REASON string** — Add `feature_type_id` format, parameter hints, and fallback instruction.

**Step 10: Run full test suite** — Verify all 13 meta-json-guard tests pass (9 existing + 4 new).

## Dependencies

```
Phase 1 (steps 1-4) → Phase 2 (steps 5-10)
```

Within Phase 2, linear order: Step 5 → Step 6 → Step 7 → Step 8 → Step 9 → Step 10. Steps 6 must precede both Steps 7 and 8 (both call `log_guard_event`). Step 5 is independent but placed first for readability. Step 10 runs after all code changes.

## Files Modified

| File | Changes |
|------|---------|
| `plugins/iflow/hooks/meta-json-guard.sh` | Add `check_mcp_available()`, rename `log_blocked_attempt` → `log_guard_event` with action param, add degraded permit path, update REASON string |
| `plugins/iflow/hooks/tests/test-hooks.sh` | Refactor 3 deny tests to helpers, add sentinel to 5 existing tests, add 4 new tests (2 with sentinel, 2 without) |

## Verification

- All 9 existing meta-json-guard tests pass after Phase 1 step 4 (no regression from test refactor + sentinel addition)
- 4 new tests fail after Phase 1 (red — expected, code not yet changed)
- All 13 meta-json-guard tests pass after Phase 2 step 10 (green)
- Latency: existing `test_meta_json_guard_latency` covers the fast-path (hot path). The deny path already includes python3 overhead (~50-100ms); sentinel check is negligible by comparison. New deny-path latency test is out of scope.
