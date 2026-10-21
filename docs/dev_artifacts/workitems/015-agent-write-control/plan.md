# Implementation Plan: Agent Write Control

## Overview

This plan implements a PreToolUse hook for Write/Edit tools that enforces path-based write restrictions. The implementation follows TDD principles with a phased approach.

## Implementation Phases

### Phase 1: Infrastructure & Test Setup

**Goal:** Create the file structure, test file, and basic hook skeleton with testability support.

**Dependencies:** None

**Steps:**
1. Create config directory: `plugins/iflow-dev/hooks/config/`
2. Create `write-policies.json` with default patterns
3. Create `plugins/iflow-dev/hooks/tests/test-write-control.sh` with test framework:
   - Use consistent helper pattern from test-hooks.sh (log_test, log_pass, log_fail, TESTS_RUN counter)
   - Include TEST_CONFIG_DIR for test fixture isolation (tests use own temp config, not production write-policies.json)
4. Create `write-control.sh` skeleton with:
   - Shebang and set options
   - Source common.sh
   - Verify escape_json exists in common.sh; if missing, define inline fallback
   - --source-only guard at bottom (enables unit testing)
   - Empty function stubs for all functions
5. Add entry to `hooks.json` for Write|Edit matcher:
   - **Placement:** Append to existing PreToolUse array (after pre-commit-guard.sh entry)
   - Per Contract 3: Multiple hooks can apply to same tool; all are executed

**Test Framework Helpers (to include in test-write-control.sh):**
```bash
#!/usr/bin/env bash
set -euo pipefail

# Test counters (consistent with test-hooks.sh pattern)
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Test fixture directory for isolation
TEST_CONFIG_DIR=$(mktemp -d)
trap "rm -rf '$TEST_CONFIG_DIR'" EXIT

log_test() {
  ((TESTS_RUN++))
  echo "TEST: $1"
}

log_pass() {
  ((TESTS_PASSED++))
  echo "  PASS"
}

log_fail() {
  ((TESTS_FAILED++))
  echo "  FAIL: $1"
}

# Source the hook functions (not main)
SCRIPT_DIR="${BASH_SOURCE%/*}/.."
source "$SCRIPT_DIR/write-control.sh" --source-only

# Test functions defined in Phases 2-6...

# Run all tests
run_all_tests() {
  test_matches_pattern
  test_normalize_path
  test_load_policies
  test_check_protected
  test_check_warned
  test_check_safe
  test_emit_deny
  test_emit_allow_warning
  test_read_tool_input
  test_read_tool_input_timeout
  test_integration

  echo ""
  echo "Results: $TESTS_PASSED/$TESTS_RUN passed, $TESTS_FAILED failed"
  [[ $TESTS_FAILED -eq 0 ]]
}

run_all_tests
```

**Verification:**
- Hook is invoked on Write/Edit (visible in verbose output)
- `./test-write-control.sh` runs without error (even if no tests yet)
- `source write-control.sh --source-only` works

---

### Phase 2: Core Functions (TDD - RED/GREEN)

**Goal:** Implement and test core utility functions using TDD.

**Dependencies:** Phase 1 complete (test file and --source-only guard exist)

**Order:** Build from inner functions outward (no external dependencies first).

#### 2.1: matches_pattern()

**RED - Write tests first in test-write-control.sh:**
```bash
test_matches_pattern() {
  log_test "matches_pattern: *.md matches file.md"
  matches_pattern "file.md" "*.md" && log_pass || log_fail "*.md should match file.md"

  log_test "matches_pattern: *.md does NOT match dir/file.md"
  matches_pattern "dir/file.md" "*.md" && log_fail "*.md should NOT match dir/file.md" || log_pass

  log_test "matches_pattern: src/** matches src/a.ts"
  matches_pattern "src/a.ts" "src/**" && log_pass || log_fail "src/** should match src/a.ts"

  log_test "matches_pattern: src/** does NOT match src (no trailing content)"
  matches_pattern "src" "src/**" && log_fail "src/** should NOT match src" || log_pass

  log_test "matches_pattern: .env* matches .env.local"
  matches_pattern ".env.local" ".env*" && log_pass || log_fail ".env* should match .env.local"

  log_test "matches_pattern: .env* does NOT match myenv (requires literal dot)"
  matches_pattern "myenv" ".env*" && log_fail ".env* should NOT match myenv" || log_pass
}
```

**GREEN - Implement:** Regex conversion with escaping per Contract 5.

#### 2.2: normalize_path()

**RED - Write tests first:**
```bash
test_normalize_path() {
  # NOTE: PWD override in subshell: (PWD="$val" func) creates a subshell where
  # PWD is set before the function runs. This is necessary because normalize_path
  # reads PWD to determine project root.
  local test_pwd="/Users/terry/project"

  log_test "normalize_path: absolute path within project"
  result=$(PWD="$test_pwd" normalize_path "$test_pwd/src/file.ts")
  [[ "$result" == "src/file.ts" ]] && log_pass || log_fail "expected src/file.ts, got $result"

  log_test "normalize_path: ./ prefix stripped"
  result=$(normalize_path "./src/file.ts")
  [[ "$result" == "src/file.ts" ]] && log_pass || log_fail "expected src/file.ts"

  log_test "normalize_path: relative path unchanged"
  result=$(normalize_path "src/file.ts")
  [[ "$result" == "src/file.ts" ]] && log_pass || log_fail "expected src/file.ts"

  log_test "normalize_path: parent escape detected"
  result=$(normalize_path "../other/file")
  [[ "$result" == "OUTSIDE_PROJECT" ]] && log_pass || log_fail "expected OUTSIDE_PROJECT"

  log_test "normalize_path: absolute path outside project"
  result=$(PWD="$test_pwd" normalize_path "/etc/passwd")
  [[ "$result" == "OUTSIDE_PROJECT" ]] && log_pass || log_fail "expected OUTSIDE_PROJECT"

  log_test "normalize_path: trailing slash removed"
  result=$(normalize_path "src/")
  [[ "$result" == "src" ]] && log_pass || log_fail "expected src"

  log_test "normalize_path: empty PWD treated as outside"
  result=$(PWD="" normalize_path "/some/path")
  [[ "$result" == "OUTSIDE_PROJECT" ]] && log_pass || log_fail "empty PWD should return OUTSIDE_PROJECT"
}
```

**GREEN - Implement:** Path stripping and validation per TD-3, with PWD defensive check.

#### 2.3: load_policies()

**RED - Write tests first:**
```bash
test_load_policies() {
  # Setup: Use test fixture directory (not production config)
  local orig_script_dir="$SCRIPT_DIR"
  export SCRIPT_DIR="$TEST_CONFIG_DIR"

  # Test 1: Valid config file
  log_test "load_policies: loads from valid config"
  mkdir -p "$TEST_CONFIG_DIR/config"
  cat > "$TEST_CONFIG_DIR/config/write-policies.json" << 'EOF'
{"protected": [".git/**"], "warned": ["src/**"], "safe": ["docs/**"]}
EOF
  load_policies
  [[ ${#PROTECTED_PATTERNS[@]} -gt 0 ]] && log_pass || log_fail "protected not loaded"

  log_test "load_policies: warned patterns loaded"
  [[ ${#WARNED_PATTERNS[@]} -gt 0 ]] && log_pass || log_fail "warned not loaded"

  log_test "load_policies: safe patterns loaded"
  [[ ${#SAFE_PATTERNS[@]} -gt 0 ]] && log_pass || log_fail "safe not loaded"

  # Test 2: Missing config file - should use defaults
  log_test "load_policies: missing config uses defaults"
  rm -f "$TEST_CONFIG_DIR/config/write-policies.json"
  rmdir "$TEST_CONFIG_DIR/config" 2>/dev/null || true
  load_policies
  [[ ${#PROTECTED_PATTERNS[@]} -gt 0 ]] && log_pass || log_fail "defaults not applied"

  # Test 3: Invalid JSON - should use defaults
  log_test "load_policies: invalid JSON uses defaults"
  mkdir -p "$TEST_CONFIG_DIR/config"
  echo "not valid json {{{" > "$TEST_CONFIG_DIR/config/write-policies.json"
  load_policies
  [[ ${#PROTECTED_PATTERNS[@]} -gt 0 ]] && log_pass || log_fail "invalid JSON should fallback to defaults"

  # Cleanup
  rm -rf "$TEST_CONFIG_DIR"
  export SCRIPT_DIR="$orig_script_dir"
}
```

**GREEN - Implement:** JSON parsing via python3, mapfile for arrays.

---

### Phase 3: Check Functions (TDD - RED/GREEN)

**Goal:** Implement path category checking functions.

**Dependencies:** Phase 2 complete (matches_pattern, load_policies tested and working)

#### 3.1: check_protected()

**RED - Write tests first:**
```bash
test_check_protected() {
  load_policies  # Ensure patterns loaded

  log_test "check_protected: .git/config is protected"
  check_protected ".git/config" && log_pass || log_fail ".git/config should be protected"

  log_test "check_protected: node_modules/x is protected"
  check_protected "node_modules/x" && log_pass || log_fail "node_modules should be protected"

  log_test "check_protected: .env is protected"
  check_protected ".env" && log_pass || log_fail ".env should be protected"

  log_test "check_protected: .env.local is protected"
  check_protected ".env.local" && log_pass || log_fail ".env.local should be protected"

  log_test "check_protected: secrets.key is protected"
  check_protected "secrets.key" && log_pass || log_fail "*.key should be protected"

  log_test "check_protected: src/file.ts is NOT protected"
  check_protected "src/file.ts" && log_fail "src/file.ts should NOT be protected" || log_pass
}
```

**GREEN - Implement:** Iterate PROTECTED_PATTERNS, call matches_pattern.

#### 3.2: check_warned()

**RED - Write tests first:**
```bash
test_check_warned() {
  load_policies

  log_test "check_warned: src/index.ts is warned"
  check_warned "src/index.ts" && log_pass || log_fail "src/** should be warned"

  log_test "check_warned: plugins/iflow/agents/test.md is warned"
  check_warned "plugins/iflow/agents/test.md" && log_pass || log_fail "plugins agents should be warned"

  log_test "check_warned: .claude-plugin/foo is warned"
  check_warned ".claude-plugin/foo" && log_pass || log_fail ".claude-plugin/** should be warned"

  log_test "check_warned: docs/readme.md is NOT warned (it's safe)"
  check_warned "docs/readme.md" && log_fail "docs should NOT be warned" || log_pass
}
```

**GREEN - Implement:** Iterate WARNED_PATTERNS, call matches_pattern.

#### 3.3: check_safe()

**RED - Write tests first:**
```bash
test_check_safe() {
  load_policies

  log_test "check_safe: docs/readme.md is safe"
  check_safe "docs/readme.md" && log_pass || log_fail "docs/** should be safe"

  log_test "check_safe: agent_sandbox path is safe"
  check_safe "agent_sandbox/2026-02-04/test/x.py" && log_pass || log_fail "agent_sandbox/** should be safe"

  log_test "check_safe: tests/test.ts is safe"
  check_safe "tests/test.ts" && log_pass || log_fail "tests/** should be safe"

  log_test "check_safe: README.md at root is safe"
  check_safe "README.md" && log_pass || log_fail "*.md at root should be safe"

  log_test "check_safe: src/file.ts is NOT safe (it's warned)"
  check_safe "src/file.ts" && log_fail "src should NOT be safe" || log_pass
}
```

**GREEN - Implement:** Iterate SAFE_PATTERNS, call matches_pattern.

---

### Phase 4: Output Functions (TDD - RED/GREEN)

**Goal:** Implement JSON response emitters.

**Dependencies:** Phase 1 complete (common.sh sourced for escape_json)

**Verify First:** Confirm escape_json exists in lib/common.sh.
- If escape_json is missing: Define inline fallback in write-control.sh (simple sed-based escaping)
- This ensures the hook works even if common.sh is incomplete

#### 4.1: emit_deny()

**RED - Write tests first:**
```bash
test_emit_deny() {
  log_test "emit_deny: produces valid JSON with deny decision"
  output=$(emit_deny ".git/config" "Protected path")

  # Verify JSON structure using python3
  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert data['hookSpecificOutput']['permissionDecision'] == 'deny', 'decision must be deny'
assert '.git/config' in data['hookSpecificOutput']['permissionDecisionReason'], 'reason must contain path'
print('valid')
" 2>/dev/null && log_pass || log_fail "invalid deny JSON structure"
}
```

**GREEN - Implement:** Using escape_json and heredoc per TD-5.

#### 4.2: emit_allow_warning()

**RED - Write tests first:**
```bash
test_emit_allow_warning() {
  log_test "emit_allow_warning: produces valid JSON with allow decision"
  output=$(emit_allow_warning "src/file.ts" "Production path")

  echo "$output" | python3 -c "
import json, sys
data = json.load(sys.stdin)
assert data['hookSpecificOutput']['permissionDecision'] == 'allow', 'decision must be allow'
assert 'src/file.ts' in data['hookSpecificOutput']['permissionDecisionReason'], 'reason must contain path'
print('valid')
" 2>/dev/null && log_pass || log_fail "invalid allow JSON structure"
}
```

**GREEN - Implement:** Using escape_json and heredoc per TD-5.

---

### Phase 5: Input Functions (TDD - RED/GREEN)

**Goal:** Implement stdin reading with timeout protection.

**Dependencies:** Phase 1 complete

#### 5.1: read_tool_input()

**RED - Write tests first:**
```bash
test_read_tool_input() {
  log_test "read_tool_input: extracts file_path from valid JSON"
  result=$(echo '{"tool_input":{"file_path":"src/file.ts"}}' | read_tool_input)
  [[ "$result" == "src/file.ts" ]] && log_pass || log_fail "expected src/file.ts, got $result"

  log_test "read_tool_input: missing file_path returns empty"
  result=$(echo '{"tool_input":{}}' | read_tool_input)
  [[ -z "$result" ]] && log_pass || log_fail "expected empty"

  log_test "read_tool_input: invalid JSON returns empty"
  result=$(echo 'not json' | read_tool_input)
  [[ -z "$result" ]] && log_pass || log_fail "invalid JSON should return empty"

  log_test "read_tool_input: empty input returns empty"
  result=$(echo '' | read_tool_input)
  [[ -z "$result" ]] && log_pass || log_fail "empty input should return empty"
}

test_read_tool_input_timeout() {
  # Timeout behavior cannot be unit tested reliably because:
  # 1. Would require blocking stdin which affects test runner
  # 2. Timeout duration (5s) too long for unit tests
  # 3. Behavior is defense-in-depth and fail-open anyway
  #
  # Expected behavior when timeout triggers:
  # - gtimeout/timeout returns non-zero or empty
  # - Fallback to '{}' as input
  # - file_path='' → main() exits 0 (silent allow)
  #
  # Manual verification: Run hook without piped input, should exit 0 after 5s
  log_test "read_tool_input: timeout behavior (manual verification only)"
  log_pass "SKIP - see code comments for manual verification steps"
}
```

**GREEN - Implement:** Timeout wrapper + python3 JSON parsing per Contract 1.

---

### Phase 6: Main Flow Integration

**Goal:** Wire all functions together in main().

**Dependencies:** Phases 2-5 complete (all functions tested)

**Steps:**
1. Implement main() flow per Contract 1 algorithm
2. Verify --source-only guard works correctly

**Integration Tests (add to test file):**
```bash
test_integration() {
  log_test "integration: protected path (.git/config) → deny"
  output=$(echo '{"tool_input":{"file_path":".git/config"}}' | ./write-control.sh)
  echo "$output" | grep -q '"permissionDecision": "deny"' && log_pass || log_fail "protected should be denied"

  log_test "integration: warned path (src/index.ts) → allow with reason"
  output=$(echo '{"tool_input":{"file_path":"src/index.ts"}}' | ./write-control.sh)
  echo "$output" | grep -q '"permissionDecision": "allow"' && log_pass || log_fail "warned should be allowed with message"

  log_test "integration: safe path (docs/readme.md) → silent allow"
  output=$(echo '{"tool_input":{"file_path":"docs/readme.md"}}' | ./write-control.sh)
  [[ -z "$output" ]] && log_pass || log_fail "safe path should produce no output"

  log_test "integration: unmatched path (random/file.txt) → silent allow"
  output=$(echo '{"tool_input":{"file_path":"random/file.txt"}}' | ./write-control.sh)
  [[ -z "$output" ]] && log_pass || log_fail "unmatched should produce no output"

  log_test "integration: outside project (/etc/passwd) → deny"
  output=$(echo '{"tool_input":{"file_path":"/etc/passwd"}}' | ./write-control.sh)
  echo "$output" | grep -q '"permissionDecision": "deny"' && log_pass || log_fail "outside project should be denied"

  log_test "integration: absolute path within project → correct handling"
  # Use actual PWD to construct absolute path
  output=$(echo "{\"tool_input\":{\"file_path\":\"$PWD/src/file.ts\"}}" | ./write-control.sh)
  echo "$output" | grep -q '"permissionDecision": "allow"' && log_pass || log_fail "absolute path within project should work"

  log_test "integration: empty file_path → silent allow"
  output=$(echo '{"tool_input":{}}' | ./write-control.sh)
  [[ -z "$output" ]] && log_pass || log_fail "empty path should produce no output"
}
```

---

### Phase 7: Test Finalization

**Goal:** Ensure all tests are complete and passing.

**Dependencies:** Phase 6 complete

**Steps:**
1. Run full test suite: `./test-write-control.sh`
2. Run via validate.sh to ensure discovery works
3. Fix any remaining test failures
4. Add any edge case tests discovered during integration

---

### Phase 8: Documentation & Cleanup

**Goal:** Update project files and documentation.

**Dependencies:** Phase 7 complete (all tests passing)

**Steps:**
1. Add `agent_sandbox/` to `.gitignore` (with duplicate check per Contract 4)
2. Verify hooks.json is correctly formatted
3. Manual end-to-end test: Try Write to protected path in Claude session

**Note:** Sync to iflow plugin happens via release script, NOT as part of this feature implementation.

---

## Dependency Graph

```
Phase 1 (Infrastructure + Test Setup)
    │
    ├─────────────────────────┬─────────────────────┐
    ▼                         ▼                     ▼
Phase 2 (Core)           Phase 4 (Output)     Phase 5 (Input)
    │                         │                     │
    ▼                         │                     │
Phase 3 (Check)               │                     │
    │                         │                     │
    └─────────────────────────┴─────────────────────┘
                              │
                              ▼
                    Phase 6 (Main Flow + Integration Tests)
                              │
                              ▼
                    Phase 7 (Test Finalization)
                              │
                              ▼
                    Phase 8 (Documentation)
```

## Parallel Execution Opportunities

These phases can run in parallel:
- **Phase 2, 4, 5** can run in parallel after Phase 1
- Within Phase 2: 2.1 and 2.2 can run in parallel; 2.3 should come last (needs config file)
- Within Phase 3: 3.1, 3.2, 3.3 can run in parallel after ALL of Phase 2

**Clarification:** Phase 3 requires ALL of Phase 2 to complete (not individual functions) because check_* functions depend on both matches_pattern and load_policies.

## Risk Mitigation During Implementation

| Risk | Mitigation |
|------|------------|
| Regex escaping edge cases | Test each pattern type in Phase 2.1 before integrating |
| python3 parsing failures | Test invalid JSON inputs explicitly in Phase 5.1 |
| PWD not set correctly | Add defensive check in normalize_path (empty PWD → OUTSIDE_PROJECT) |
| Timeout command unavailable | Fallback to plain cat (documented in design) |
| escape_json missing | Verify exists in common.sh before Phase 4 |

## Success Criteria

1. All unit tests pass (Phases 2-5)
2. All integration tests pass (Phase 6)
3. validate.sh completes successfully
4. Hook correctly:
   - Blocks writes to .git/, node_modules/, .env*, *.key, *.pem
   - Warns on writes to src/, plugins/
   - Silently allows writes to docs/, agent_sandbox/, tests/
   - Silently allows unmatched paths
   - Blocks paths outside project
