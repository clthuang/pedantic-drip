#!/usr/bin/env bash
# test-capture-tool-failure.sh — Unit tests for capture-tool-failure.sh hook
# Tests PostToolUseFailure capture with stub writer to verify invocation/exclusion.
#
# Usage: bash plugins/pd/hooks/tests/test-capture-tool-failure.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
HOOK_SCRIPT="${HOOKS_DIR}/capture-tool-failure.sh"
PROJECT_ROOT="$(cd "${HOOKS_DIR}/../../../.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

log_test() {
    echo -e "TEST: $1"
    ((TESTS_RUN++)) || true
}

log_pass() {
    echo -e "${GREEN}  PASS${NC}"
    ((TESTS_PASSED++)) || true
}

log_fail() {
    echo -e "${RED}  FAIL: $1${NC}"
    ((TESTS_FAILED++)) || true
}

# --- Setup ---
TMPDIR_TEST=$(mktemp -d)
STUB_LOG="${TMPDIR_TEST}/writer-calls.log"
STUB_PYTHON="${TMPDIR_TEST}/python"
MOCK_PD_LOCAL="${TMPDIR_TEST}/pd.local.md"

cleanup() {
    rm -rf "$TMPDIR_TEST"
}
trap cleanup EXIT

# Create stub python that logs calls instead of running writer
cat > "$STUB_PYTHON" <<'STUBEOF'
#!/usr/bin/env bash
# Stub: log invocation args to writer-calls.log
echo "$@" >> "$(dirname "$0")/writer-calls.log"
STUBEOF
chmod +x "$STUB_PYTHON"

# Create mock pd.local.md with default config (silent mode)
cat > "$MOCK_PD_LOCAL" <<'EOF'
memory_model_capture_mode: silent
EOF

# Helper: run the hook with given stdin JSON and environment overrides
# Uses PD_TEST_VENV_PYTHON to override the venv python path in the hook
run_hook() {
    local stdin_json="$1"
    shift
    # Override the venv python to our stub, and set PROJECT_ROOT to our temp dir
    # The hook derives PLUGIN_ROOT from SCRIPT_DIR (hooks/ -> parent)
    # We need to make .claude/pd.local.md available at PROJECT_ROOT
    mkdir -p "${TMPDIR_TEST}/.claude"
    cp "$MOCK_PD_LOCAL" "${TMPDIR_TEST}/.claude/pd.local.md"

    # Clear previous stub log
    rm -f "$STUB_LOG"

    echo "$stdin_json" | \
        PD_TEST_VENV_PYTHON="$STUB_PYTHON" \
        PD_TEST_PROJECT_ROOT="$TMPDIR_TEST" \
        "$@" \
        bash "$HOOK_SCRIPT" 2>/dev/null || true
}

# --- Stdin JSON templates ---
make_bash_failure() {
    local cmd="$1"
    local error="$2"
    cat <<JSONEOF
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Bash",
  "tool_input": {"command": "$cmd", "description": "test"},
  "tool_response": {"stdout": "$error", "stderr": "", "interrupted": false},
  "tool_use_id": "test-id",
  "session_id": "test-session",
  "cwd": "/tmp"
}
JSONEOF
}

make_bash_success() {
    local cmd="$1"
    local output="$2"
    cat <<JSONEOF
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Bash",
  "tool_input": {"command": "$cmd", "description": "test"},
  "tool_response": {"stdout": "$output", "stderr": "", "interrupted": false},
  "tool_use_id": "test-id",
  "session_id": "test-session",
  "cwd": "/tmp"
}
JSONEOF
}

make_edit_failure() {
    local file_path="$1"
    local error="$2"
    cat <<JSONEOF
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Edit",
  "tool_input": {"file_path": "$file_path", "old_string": "foo", "new_string": "bar"},
  "tool_response": {"stdout": "$error", "stderr": "", "interrupted": false},
  "tool_use_id": "test-id",
  "session_id": "test-session",
  "cwd": "/tmp"
}
JSONEOF
}

# =====================================================================
# Test 1: Bash failure with path error -> writer called with category
# =====================================================================
test_bash_path_error() {
    log_test "Bash failure with path error invokes writer"

    local input
    input=$(make_bash_failure "ls /nonexistent" "ls: /nonexistent: No such file or directory")
    run_hook "$input"

    if [[ -f "$STUB_LOG" ]] && grep -q "semantic_memory.writer" "$STUB_LOG"; then
        # Verify category is "Path error" in the entry JSON
        if grep -q "Path error" "$STUB_LOG"; then
            log_pass
        else
            log_fail "Writer called but category 'Path error' not found in args: $(cat "$STUB_LOG")"
        fi
    else
        log_fail "Writer was not called. Stub log: $(cat "$STUB_LOG" 2>/dev/null || echo 'missing')"
    fi
}

# =====================================================================
# Test 2: Edit failure -> writer called
# =====================================================================
test_edit_failure() {
    log_test "Edit failure invokes writer"

    local input
    input=$(make_edit_failure "/some/file.py" "FileNotFoundError: /some/file.py")
    run_hook "$input"

    if [[ -f "$STUB_LOG" ]] && grep -q "semantic_memory.writer" "$STUB_LOG"; then
        log_pass
    else
        log_fail "Writer was not called for Edit failure. Stub log: $(cat "$STUB_LOG" 2>/dev/null || echo 'missing')"
    fi
}

# =====================================================================
# Test 3: Test runner command (pytest) -> writer NOT called
# =====================================================================
test_runner_exclusion() {
    log_test "Test runner command (pytest) does NOT invoke writer"

    local input
    input=$(make_bash_failure "python -m pytest tests/ -v" "FAILED tests/test_foo.py::test_bar - AssertionError")
    run_hook "$input"

    if [[ -f "$STUB_LOG" ]] && grep -q "semantic_memory.writer" "$STUB_LOG"; then
        log_fail "Writer was called for test runner command (should be excluded)"
    else
        log_pass
    fi
}

# =====================================================================
# Test 4: Git read-only command -> writer NOT called
# =====================================================================
test_git_readonly_exclusion() {
    log_test "Git read-only command does NOT invoke writer"

    local input
    input=$(make_bash_failure "git status" "fatal: not a git repository")
    run_hook "$input"

    if [[ -f "$STUB_LOG" ]] && grep -q "semantic_memory.writer" "$STUB_LOG"; then
        log_fail "Writer was called for git read-only command (should be excluded)"
    else
        log_pass
    fi
}

# =====================================================================
# Test 5: agent_sandbox/ path -> writer NOT called
# =====================================================================
test_agent_sandbox_exclusion() {
    log_test "agent_sandbox/ path does NOT invoke writer"

    local input
    input=$(make_bash_failure "ls agent_sandbox/test/" "ls: agent_sandbox/test/: No such file or directory")
    run_hook "$input"

    if [[ -f "$STUB_LOG" ]] && grep -q "semantic_memory.writer" "$STUB_LOG"; then
        log_fail "Writer was called for agent_sandbox path (should be excluded)"
    else
        log_pass
    fi
}

# =====================================================================
# Test 6: memory_model_capture_mode: off -> writer NOT called
# =====================================================================
test_off_mode() {
    log_test "capture_mode off does NOT invoke writer"

    # Override pd.local.md with off mode
    cat > "$MOCK_PD_LOCAL" <<'EOF'
memory_model_capture_mode: off
EOF

    local input
    input=$(make_bash_failure "ls /nonexistent" "ls: /nonexistent: No such file or directory")
    run_hook "$input"

    if [[ -f "$STUB_LOG" ]] && grep -q "semantic_memory.writer" "$STUB_LOG"; then
        log_fail "Writer was called in off mode (should be skipped)"
    else
        log_pass
    fi

    # Restore default config
    cat > "$MOCK_PD_LOCAL" <<'EOF'
memory_model_capture_mode: silent
EOF
}

# =====================================================================
# Test 7: No pattern match -> writer NOT called
# =====================================================================
test_no_pattern_match() {
    log_test "Unmatched error pattern does NOT invoke writer"

    local input
    input=$(make_bash_failure "some-command" "Something went wrong with an unknown reason")
    run_hook "$input"

    if [[ -f "$STUB_LOG" ]] && grep -q "semantic_memory.writer" "$STUB_LOG"; then
        log_fail "Writer was called for unmatched error pattern (should be skipped)"
    else
        log_pass
    fi
}

# =====================================================================
# Test 8: Performance check - completes within 2 seconds
# =====================================================================
test_performance() {
    log_test "Hook completes within 2 seconds"

    local input
    input=$(make_bash_failure "ls /nonexistent" "ls: /nonexistent: No such file or directory")

    local start_time end_time elapsed
    start_time=$(python3 -c "import time; print(time.time())" 2>/dev/null)

    run_hook "$input"

    end_time=$(python3 -c "import time; print(time.time())" 2>/dev/null)
    elapsed=$(python3 -c "print(float($end_time) - float($start_time))" 2>/dev/null)

    local within_budget
    within_budget=$(python3 -c "print('yes' if float('$elapsed') < 2.0 else 'no')" 2>/dev/null)

    if [[ "$within_budget" == "yes" ]]; then
        log_pass
    else
        log_fail "Hook took ${elapsed}s (budget: 2s)"
    fi
}

# =====================================================================
# Test 9: Edit with agent_sandbox path -> writer NOT called
# =====================================================================
test_edit_agent_sandbox_exclusion() {
    log_test "Edit with agent_sandbox/ file_path does NOT invoke writer"

    local input
    input=$(make_edit_failure "agent_sandbox/2026-04-03/test/foo.py" "FileNotFoundError: agent_sandbox/2026-04-03/test/foo.py")
    run_hook "$input"

    if [[ -f "$STUB_LOG" ]] && grep -q "semantic_memory.writer" "$STUB_LOG"; then
        log_fail "Writer was called for Edit with agent_sandbox path (should be excluded)"
    else
        log_pass
    fi
}

# =====================================================================
# Test 10: Git read-only with cd prefix -> writer NOT called
# =====================================================================
test_git_readonly_with_cd_prefix() {
    log_test "Git read-only with cd prefix does NOT invoke writer"

    local input
    input=$(make_bash_failure "cd /some/path && git diff HEAD" "fatal: bad revision 'HEAD'")
    run_hook "$input"

    if [[ -f "$STUB_LOG" ]] && grep -q "semantic_memory.writer" "$STUB_LOG"; then
        log_fail "Writer was called for 'cd ... && git diff' (should be excluded)"
    else
        log_pass
    fi
}

# =====================================================================
# Test 11: Hook outputs valid JSON
# =====================================================================
test_hook_outputs_json() {
    log_test "Hook outputs valid JSON (empty object)"

    local input
    input=$(make_bash_failure "ls /nonexistent" "ls: /nonexistent: No such file or directory")

    mkdir -p "${TMPDIR_TEST}/.claude"
    cp "$MOCK_PD_LOCAL" "${TMPDIR_TEST}/.claude/pd.local.md"
    rm -f "$STUB_LOG"

    local output
    output=$(echo "$input" | \
        PD_TEST_VENV_PYTHON="$STUB_PYTHON" \
        PD_TEST_PROJECT_ROOT="$TMPDIR_TEST" \
        bash "$HOOK_SCRIPT" 2>/dev/null) || true

    if echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        log_pass
    else
        log_fail "Output is not valid JSON: '$output'"
    fi
}

# =====================================================================
# Test 12: PostToolUseFailure event with error field triggers writer
# =====================================================================
make_posttoolusefailure() {
    local tool_name="$1"
    local subject="$2"
    local error="$3"
    local input_field
    if [[ "$tool_name" == "Bash" ]]; then
        input_field="\"command\": \"$subject\""
    else
        input_field="\"file_path\": \"$subject\", \"old_string\": \"foo\", \"new_string\": \"bar\""
    fi
    cat <<JSONEOF
{
  "hook_event_name": "PostToolUseFailure",
  "tool_name": "$tool_name",
  "tool_input": {$input_field},
  "error": "$error",
  "is_interrupt": false,
  "tool_use_id": "test-id",
  "session_id": "test-session",
  "cwd": "/tmp"
}
JSONEOF
}

test_posttoolusefailure_triggers_writer() {
    log_test "PostToolUseFailure event with error field invokes writer"

    local input
    input=$(make_posttoolusefailure "Edit" "/some/file.py" "String to replace not found in file")
    run_hook "$input"

    if [[ -f "$STUB_LOG" ]] && grep -q "semantic_memory.writer" "$STUB_LOG"; then
        log_pass
    else
        log_fail "Writer was not called for PostToolUseFailure event. Stub log: ${STUB_LOG}"
    fi
}

# =====================================================================
# Test 13: PostToolUseFailure with agent_sandbox path is excluded
# =====================================================================
test_posttoolusefailure_agent_sandbox_excluded() {
    log_test "PostToolUseFailure with agent_sandbox/ path does NOT invoke writer"

    local input
    input=$(make_posttoolusefailure "Edit" "agent_sandbox/test.py" "File not found")
    run_hook "$input"

    if [[ ! -f "$STUB_LOG" ]]; then
        log_pass
    else
        log_fail "Writer was called for agent_sandbox PostToolUseFailure"
    fi
}

# --- Run all tests ---
echo "=== capture-tool-failure.sh unit tests ==="
echo ""

test_bash_path_error
test_edit_failure
test_runner_exclusion
test_git_readonly_exclusion
test_agent_sandbox_exclusion
test_off_mode
test_no_pattern_match
test_performance
test_edit_agent_sandbox_exclusion
test_git_readonly_with_cd_prefix
test_hook_outputs_json
test_posttoolusefailure_triggers_writer
test_posttoolusefailure_agent_sandbox_excluded

# --- Summary ---
echo ""
echo "=== Results ==="
echo -e "Passed: ${GREEN}${TESTS_PASSED}${NC}"
echo -e "Failed: ${RED}${TESTS_FAILED}${NC}"
echo -e "Total:  ${TESTS_RUN}"

if [[ "$TESTS_FAILED" -gt 0 ]]; then
    exit 1
fi
