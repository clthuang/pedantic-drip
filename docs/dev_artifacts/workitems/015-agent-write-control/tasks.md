# Tasks: Agent Write Control

## Overview

Tasks for implementing the PreToolUse hook for Write/Edit tools with path-based write restrictions.
Total: 27 tasks across 8 phases, 3 parallel groups.

---

## Phase 1: Infrastructure & Test Setup

**Parallel Group: None (sequential foundation)**

**Internal dependency structure:**
```
1.1 → 1.2 (config dir before config file)
1.4 → 1.3 → 1.6 (hook skeleton before test file before chmod)
1.5 → 1.7 (hooks.json entry before verification)
```
Note: The 1.1→1.2 chain and 1.4→1.3→1.6 chain can run in parallel.

### Task 1.1: Create config directory
- **Action:** Create `plugins/iflow-dev/hooks/config/` directory
- **Done when:** Directory exists
- **Time:** 1 min

### Task 1.2: Create write-policies.json
- **Action:** Create `plugins/iflow-dev/hooks/config/write-policies.json` with default patterns from design Contract 2
- **Done when:** File exists with valid JSON containing protected, warned, safe arrays
- **Time:** 3 min
- **Depends on:** 1.1

### Task 1.3: Create test file skeleton
- **Action:** Create `plugins/iflow-dev/hooks/tests/test-write-control.sh` with:
  - Shebang, set options
  - Test counters (TESTS_RUN, TESTS_PASSED, TESTS_FAILED)
  - TEST_CONFIG_DIR setup with trap cleanup
  - log_test, log_pass, log_fail helpers
  - Source statement for write-control.sh --source-only
  - Empty test function stubs
  - run_all_tests function
- **Done when:** `./test-write-control.sh` runs without error (exits 0)
- **Time:** 10 min
- **Depends on:** 1.4

### Task 1.4: Create write-control.sh skeleton
- **Action:** Create `plugins/iflow-dev/hooks/write-control.sh` with:
  - Shebang: `#!/usr/bin/env bash`
  - `set -euo pipefail`
  - SCRIPT_DIR variable: `SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"`
  - Source lib/common.sh: `source "$SCRIPT_DIR/lib/common.sh"`
  - Check if escape_json exists in common.sh. If missing, define inline fallback:
    ```bash
    # Fallback: JSON-encode string with python3, strip outer quotes
    # Note: json.dumps always wraps strings in quotes, so sed pattern is safe
    if ! type escape_json &>/dev/null; then
      escape_json() { python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$1" | sed 's/^"//; s/"$//'; }
    fi
    ```
  - DEFAULT_PROTECTED, DEFAULT_WARNED, DEFAULT_SAFE arrays (from Contract 2)
  - Empty function stubs: matches_pattern, normalize_path, load_policies, check_protected, check_warned, check_safe, emit_deny, emit_allow_warning, read_tool_input, main
  - `--source-only` guard at bottom
- **Done when:** `source write-control.sh --source-only` works without error AND escape_json is available (either from common.sh or inline fallback)
- **Time:** 10 min

### Task 1.5: Add hooks.json entry
- **Action:** Edit `plugins/iflow-dev/hooks/hooks.json`:
  - Add new entry to PreToolUse array (after the pre-commit-guard.sh entry)
  - Exact entry to add:
    ```json
    {
      "matcher": "Write|Edit",
      "hooks": [
        {
          "type": "command",
          "command": "${CLAUDE_PLUGIN_ROOT}/hooks/write-control.sh"
        }
      ]
    }
    ```
- **Done when:** hooks.json is valid JSON with new entry (verify with `python3 -m json.tool hooks.json`)
- **Time:** 3 min

### Task 1.6: Make script executable
- **Action:** Run `chmod +x write-control.sh` and `chmod +x tests/test-write-control.sh`
- **Done when:** Both scripts are executable
- **Time:** 1 min
- **Depends on:** 1.3, 1.4

### Task 1.7: Verify hooks.json format
- **Action:** Validate hooks.json is valid JSON after adding entry
- **Command:** `python3 -m json.tool plugins/iflow-dev/hooks/hooks.json > /dev/null`
- **Done when:** JSON parses without error
- **Time:** 1 min
- **Depends on:** 1.5

---

## Phase 2: Core Functions (TDD)

**Parallel Group A: Phase 2 can run in parallel with Phase 4 and Phase 5 (all depend only on Phase 1)**

**Internal sequencing:** Within Phase 2, RED/GREEN pairs are sequential:
- 2.1→2.2 (matches_pattern)
- 2.3→2.4 (normalize_path) - can run parallel with 2.1→2.2
- 2.5→2.6 (load_policies) - can start after 1.6, runs parallel with others

### Task 2.1: RED - Write matches_pattern tests
- **Action:** Add test_matches_pattern() to test file with 6 test cases from plan
- **Done when:** Tests exist and FAIL (function not implemented)
- **Time:** 5 min
- **Depends on:** 1.6

### Task 2.2: GREEN - Implement matches_pattern
- **Action:** Implement matches_pattern() in write-control.sh per Contract 5:
  - Escape `.`, `+`, `?`
  - Convert `**` to `(.*)?`
  - Convert `*` to `[^/]*`
  - Use bash regex match `[[ "$path" =~ ^${regex}$ ]]`
- **Done when:** All test_matches_pattern tests pass
- **Time:** 10 min
- **Depends on:** 2.1

### Task 2.3: RED - Write normalize_path tests
- **Action:** Add test_normalize_path() with 7 test cases from plan
- **Done when:** Tests exist and FAIL
- **Time:** 5 min
- **Depends on:** 1.6

### Task 2.4: GREEN - Implement normalize_path
- **Action:** Implement normalize_path() per TD-3:
  - Handle `../` as OUTSIDE_PROJECT
  - Handle absolute paths: strip PWD prefix or OUTSIDE_PROJECT
  - Strip `./` prefix
  - Strip trailing slash
  - Defensive check for empty PWD
- **Done when:** All test_normalize_path tests pass
- **Time:** 10 min
- **Depends on:** 2.3

### Task 2.5: RED - Write load_policies tests
- **Action:** Add test_load_policies() with 4 test cases:
  - Valid config loads patterns
  - Missing config uses defaults
  - Invalid JSON uses defaults
- **Done when:** Tests exist and FAIL
- **Time:** 5 min
- **Depends on:** 1.6
- **Note:** Can start in parallel with 2.1-2.4. Tests don't require matches_pattern to be implemented.

### Task 2.6: GREEN - Implement load_policies
- **Action:** Implement load_policies() per Contract 2:
  - Check if config file exists
  - Use python3 to parse JSON and output patterns
  - Use mapfile to convert to arrays
  - Fallback to DEFAULT_* arrays on any error
- **Done when:** All test_load_policies tests pass
- **Time:** 10 min
- **Depends on:** 2.5

---

## Phase 3: Check Functions (TDD)

**Parallel Group B: Tasks 3.1-3.6 can run in parallel after Phase 2 completes**

### Task 3.1: RED - Write check_protected tests
- **Action:** Add test_check_protected() with 6 test cases
- **Done when:** Tests exist and FAIL
- **Time:** 3 min
- **Depends on:** 2.6

### Task 3.2: GREEN - Implement check_protected
- **Action:** Implement check_protected():
  - Iterate PROTECTED_PATTERNS
  - Return 0 if any matches_pattern returns true
  - Return 1 otherwise
- **Done when:** All test_check_protected tests pass
- **Time:** 5 min
- **Depends on:** 3.1

### Task 3.3: RED - Write check_warned tests
- **Action:** Add test_check_warned() with 4 test cases
- **Done when:** Tests exist and FAIL
- **Time:** 3 min
- **Depends on:** 2.6

### Task 3.4: GREEN - Implement check_warned
- **Action:** Implement check_warned() (same pattern as check_protected)
- **Done when:** All test_check_warned tests pass
- **Time:** 5 min
- **Depends on:** 3.3

### Task 3.5: RED - Write check_safe tests
- **Action:** Add test_check_safe() with 5 test cases
- **Done when:** Tests exist and FAIL
- **Time:** 3 min
- **Depends on:** 2.6

### Task 3.6: GREEN - Implement check_safe
- **Action:** Implement check_safe() (same pattern as check_protected)
- **Done when:** All test_check_safe tests pass
- **Time:** 5 min
- **Depends on:** 3.5

---

## Phase 4: Output Functions (TDD)

**Parallel Group A: Can run in parallel with Phase 2 and Phase 5**

### Task 4.1: RED - Write emit_deny tests
- **Action:** Add test_emit_deny() that validates JSON structure with python3
- **Done when:** Test exists and FAILS
- **Time:** 5 min
- **Depends on:** 1.6

### Task 4.2: GREEN - Implement emit_deny
- **Action:** Implement emit_deny() per TD-5:
  - Use heredoc for JSON structure
  - Use escape_json for path and reason
  - Output hookSpecificOutput with permissionDecision: "deny"
- **Done when:** test_emit_deny passes
- **Time:** 8 min
- **Depends on:** 4.1

### Task 4.3: RED - Write emit_allow_warning tests
- **Action:** Add test_emit_allow_warning() that validates JSON structure
- **Done when:** Test exists and FAILS
- **Time:** 5 min
- **Depends on:** 1.6

### Task 4.4: GREEN - Implement emit_allow_warning
- **Action:** Implement emit_allow_warning() (same pattern as emit_deny with "allow")
- **Done when:** test_emit_allow_warning passes
- **Time:** 5 min
- **Depends on:** 4.3

---

## Phase 5: Input Functions (TDD)

**Parallel Group A: Can run in parallel with Phase 2 and Phase 4**

### Task 5.1: RED - Write read_tool_input tests
- **Action:** Add test_read_tool_input() with 4 test cases + test_read_tool_input_timeout() as SKIP
- **Done when:** Tests exist and FAIL (except timeout which is SKIP)
- **Time:** 5 min
- **Depends on:** 1.6

### Task 5.2: GREEN - Implement read_tool_input
- **Action:** Implement read_tool_input() per Contract 1:
  - Detect gtimeout or timeout command
  - Read stdin with 5s timeout
  - Extract file_path using python3
  - Return empty string on any error
- **Done when:** All test_read_tool_input tests pass
- **Time:** 10 min
- **Depends on:** 5.1

---

## Phase 6: Main Flow Integration

**Depends on:** Phases 2, 3, 4, 5 all complete

### Task 6.1: Implement main()
- **Action:** Implement main() per Contract 1 algorithm:
  - Read input with read_tool_input
  - Early exit if empty path
  - Normalize path
  - Block OUTSIDE_PROJECT
  - Load policies
  - Check protected → emit_deny
  - Check warned → emit_allow_warning
  - Otherwise exit 0
- **Done when:** Function implemented
- **Time:** 10 min
- **Depends on:** 3.2, 3.4, 3.6, 4.2, 4.4, 5.2

### Task 6.2: Add integration tests
- **Action:** Add test_integration() with 7 test cases from plan
- **Done when:** Tests added to test file
- **Time:** 8 min
- **Depends on:** 6.1

### Task 6.3: Run integration tests
- **Action:** Execute test file and verify all integration tests pass
- **Done when:** All tests pass (including integration)
- **Time:** 5 min
- **Depends on:** 6.2

---

## Phase 7: Test Finalization

### Task 7.1: Run full test suite
- **Action:** Run `./test-write-control.sh` and verify all tests pass
- **Done when:** Exit code 0, no failures
- **Time:** 3 min
- **Depends on:** 6.3

### Task 7.2: Run validate.sh
- **Action:** Run `./validate.sh` from plugin root
- **Done when:** validate.sh discovers and runs test-write-control.sh successfully
- **Time:** 5 min
- **Depends on:** 7.1

### Task 7.3: Fix any test failures (conditional)
- **Action:** Debug and fix any test failures identified in 7.1/7.2
- **Skip criteria:** If 7.1 and 7.2 both passed with 0 failures, skip this task entirely
- **Done when:** All tests pass (exit code 0, TESTS_FAILED=0)
- **Time:** 10 min (contingency - skip if no failures)
- **Depends on:** 7.2

---

## Phase 8: Documentation & Cleanup

### Task 8.1: Add agent_sandbox to .gitignore
- **Action:** Check if `agent_sandbox/` exists in .gitignore; if not, append with comment
- **Done when:** Entry exists in .gitignore (verified with `grep -q '^agent_sandbox/' .gitignore`)
- **Time:** 2 min
- **Depends on:** 7.2 (runs after validate.sh, regardless of 7.3 skip)

### Task 8.2: Manual end-to-end test
- **Action:** In Claude session, attempt Write to .git/config and verify hook blocks it
- **Expected output:** JSON with `"permissionDecision": "deny"` and reason containing "Protected path"
- **Done when:** Write is blocked with "Protected path" message in Claude response
- **Time:** 5 min
- **Depends on:** 7.2 (runs after validate.sh, regardless of 7.3 skip)
- **Alternative:** If no Claude session available, test via direct invocation:
  ```bash
  echo '{"tool_input":{"file_path":".git/config"}}' | ./write-control.sh | grep -q '"permissionDecision": "deny"'
  ```

---

## Summary

| Phase | Tasks | Parallel Group | Est. Time |
|-------|-------|----------------|-----------|
| 1: Infrastructure | 7 | Sequential | 29 min |
| 2: Core Functions | 6 | Group A | 45 min |
| 3: Check Functions | 6 | Group B | 24 min |
| 4: Output Functions | 4 | Group A | 23 min |
| 5: Input Functions | 2 | Group A | 15 min |
| 6: Integration | 3 | Sequential | 23 min |
| 7: Finalization | 3 | Sequential | 18 min |
| 8: Cleanup | 2 | Sequential | 7 min |

**Total:** 27 tasks, ~184 min estimated (sequential)
**With parallelization:** Group A (Phases 2, 4, 5) saves ~38 min
