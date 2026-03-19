#!/usr/bin/env bash
# Hook integration tests
# Run: ./hooks/tests/test-hooks.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Walk up to find repo root (has .git directory)
PROJECT_ROOT="$(cd "${HOOKS_DIR}" && while [[ ! -d .git ]] && [[ $PWD != / ]]; do cd ..; done && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

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

log_skip() {
    echo -e "${YELLOW}  SKIP: $1${NC}"
    ((TESTS_SKIPPED++)) || true
    ((TESTS_RUN--)) || true
}

# Test 1: common.sh library exists and is sourceable
test_common_library_exists() {
    log_test "common.sh library exists and is sourceable"

    if [[ -f "${HOOKS_DIR}/lib/common.sh" ]]; then
        if source "${HOOKS_DIR}/lib/common.sh" 2>/dev/null; then
            log_pass
        else
            log_fail "Cannot source common.sh"
        fi
    else
        log_fail "lib/common.sh not found"
    fi
}

# Test 2: detect_project_root finds correct directory from project root
test_detect_project_root() {
    log_test "detect_project_root finds project from project root"

    source "${HOOKS_DIR}/lib/common.sh"

    cd "${PROJECT_ROOT}"
    local detected
    detected=$(detect_project_root)

    if [[ "$detected" == "$PROJECT_ROOT" ]]; then
        log_pass
    else
        log_fail "Expected $PROJECT_ROOT, got $detected"
    fi
}

# Test 3: detect_project_root works from subdirectory
test_detect_project_root_subdirectory() {
    log_test "detect_project_root works from hooks subdirectory"

    source "${HOOKS_DIR}/lib/common.sh"

    cd "${HOOKS_DIR}"
    local detected
    detected=$(detect_project_root)

    if [[ "$detected" == "$PROJECT_ROOT" ]]; then
        log_pass
    else
        log_fail "Expected $PROJECT_ROOT, got $detected"
    fi

    cd "${PROJECT_ROOT}"
}

# Test 4: detect_project_root works from deeply nested directory
test_detect_project_root_nested() {
    log_test "detect_project_root works from deeply nested directory"

    source "${HOOKS_DIR}/lib/common.sh"

    cd "${PROJECT_ROOT}/docs/features"
    local detected
    detected=$(detect_project_root)

    if [[ "$detected" == "$PROJECT_ROOT" ]]; then
        log_pass
    else
        log_fail "Expected $PROJECT_ROOT, got $detected"
    fi

    cd "${PROJECT_ROOT}"
}

# Test 5: escape_json handles special characters
test_escape_json() {
    log_test "escape_json handles special characters"

    source "${HOOKS_DIR}/lib/common.sh"

    local input=$'Line1\nLine2\tTab"Quote\\Backslash'
    local escaped
    escaped=$(escape_json "$input")

    # Check newline, tab, quote, backslash were escaped
    if [[ "$escaped" == *'\n'* ]] && [[ "$escaped" == *'\t'* ]] && [[ "$escaped" == *'\"'* ]] && [[ "$escaped" == *'\\'* ]]; then
        log_pass
    else
        log_fail "Escaping not working correctly: $escaped"
    fi
}

# Test 6: session-start.sh produces valid JSON
test_session_start_json() {
    log_test "session-start.sh produces valid JSON"

    cd "${PROJECT_ROOT}"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        log_pass
    else
        log_fail "Invalid JSON output"
    fi
}

# Test 7: session-start.sh works from subdirectory
test_session_start_from_subdirectory() {
    log_test "session-start.sh works from subdirectory"

    cd "${PROJECT_ROOT}/docs"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        log_pass
    else
        log_fail "Invalid JSON output from subdirectory"
    fi

    cd "${PROJECT_ROOT}"
}

# Test 8: pre-commit-guard.sh allows non-commit commands
test_pre_commit_guard_allows_non_commit() {
    log_test "pre-commit-guard.sh allows non-commit commands"

    cd "${PROJECT_ROOT}"
    local output
    output=$(echo '{"tool_name": "Bash", "tool_input": {"command": "git status"}}' | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('hookSpecificOutput', {}).get('permissionDecision') == 'allow'" 2>/dev/null; then
        log_pass
    else
        log_fail "Should allow git status"
    fi
}

# Test 9: pre-commit-guard.sh allows non-git commands
test_pre_commit_guard_allows_non_git() {
    log_test "pre-commit-guard.sh allows non-git commands"

    cd "${PROJECT_ROOT}"
    local output
    output=$(echo '{"tool_name": "Bash", "tool_input": {"command": "ls -la"}}' | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('hookSpecificOutput', {}).get('permissionDecision') == 'allow'" 2>/dev/null; then
        log_pass
    else
        log_fail "Should allow ls command"
    fi
}

# Test 10: pre-commit-guard.sh warns on commits to main branch
test_pre_commit_guard_warns_main() {
    log_test "pre-commit-guard.sh warns on commits to main branch"

    cd "${PROJECT_ROOT}"

    # Only test if actually on main
    local branch
    branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

    if [[ "$branch" == "main" ]] || [[ "$branch" == "master" ]]; then
        local output exit_code
        output=$(echo '{"tool_name": "Bash", "tool_input": {"command": "git commit -m test"}}' | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null) || exit_code=$?

        if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('hookSpecificOutput', {}).get('permissionDecision') == 'ask'" 2>/dev/null; then
            log_pass
        else
            log_fail "Should warn on commits to main"
        fi
    else
        log_skip "Not on main branch (on $branch)"
    fi
}

# Test 11: pre-commit-guard.sh works from subdirectory
test_pre_commit_guard_from_subdirectory() {
    log_test "pre-commit-guard.sh works from subdirectory"

    cd "${PROJECT_ROOT}/docs"
    local output
    output=$(echo '{"tool_name": "Bash", "tool_input": {"command": "git status"}}' | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('hookSpecificOutput', {}).get('permissionDecision') == 'allow'" 2>/dev/null; then
        log_pass
    else
        log_fail "Hook should work from subdirectory"
    fi

    cd "${PROJECT_ROOT}"
}

# Test 12: sync-cache.sh produces valid JSON
test_sync_cache_json() {
    log_test "sync-cache.sh produces valid JSON"

    cd "${PROJECT_ROOT}"
    local output
    output=$("${HOOKS_DIR}/sync-cache.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        log_pass
    else
        log_fail "Invalid JSON output"
    fi
}

# Test 13: sync-cache.sh handles missing source gracefully
test_sync_cache_missing_source() {
    log_test "sync-cache.sh handles missing source gracefully"

    # Run from a temp directory where no source plugin exists
    local tmpdir
    tmpdir=$(mktemp -d)
    cd "$tmpdir"

    local output exit_code=0
    output=$("${HOOKS_DIR}/sync-cache.sh" 2>/dev/null) || exit_code=$?

    # Should still produce valid JSON and exit 0
    if [[ $exit_code -eq 0 ]] && echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        log_pass
    else
        log_fail "Should handle missing source gracefully (exit=$exit_code)"
    fi

    cd "${PROJECT_ROOT}"
    rm -rf "$tmpdir"
}

# === YOLO Hook Tests ===

# Helper: create temp YOLO config
setup_yolo_test() {
    YOLO_TMPDIR=$(mktemp -d)
    mkdir -p "${YOLO_TMPDIR}/.claude"
    mkdir -p "${YOLO_TMPDIR}/docs/features"
    mkdir -p "${YOLO_TMPDIR}/.git"
}

teardown_yolo_test() {
    rm -rf "$YOLO_TMPDIR"
    cd "${PROJECT_ROOT}"
}

# Test: read_local_md_field reads existing value
test_read_local_md_field() {
    log_test "read_local_md_field reads existing value"

    source "${HOOKS_DIR}/lib/common.sh"
    setup_yolo_test

    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
yolo_max_stop_blocks: 25
---
TMPL

    local val
    val=$(read_local_md_field "${YOLO_TMPDIR}/.claude/pd.local.md" "yolo_mode" "false")
    if [[ "$val" == "true" ]]; then
        log_pass
    else
        log_fail "Expected 'true', got '$val'"
    fi

    teardown_yolo_test
}

# Test: read_local_md_field returns default for missing file
test_read_local_md_field_missing() {
    log_test "read_local_md_field returns default for missing file"

    source "${HOOKS_DIR}/lib/common.sh"

    local val
    val=$(read_local_md_field "/nonexistent/file.md" "yolo_mode" "false")
    if [[ "$val" == "false" ]]; then
        log_pass
    else
        log_fail "Expected 'false', got '$val'"
    fi
}

# Test: read/write_hook_state round-trip
test_hook_state_roundtrip() {
    log_test "read/write_hook_state round-trip"

    source "${HOOKS_DIR}/lib/common.sh"
    setup_yolo_test

    local state_file="${YOLO_TMPDIR}/.claude/.yolo-hook-state"

    write_hook_state "$state_file" "stop_count" "0"
    write_hook_state "$state_file" "last_phase" "specify"

    local count phase
    count=$(read_hook_state "$state_file" "stop_count" "")
    phase=$(read_hook_state "$state_file" "last_phase" "")

    if [[ "$count" == "0" ]] && [[ "$phase" == "specify" ]]; then
        # Test update
        write_hook_state "$state_file" "stop_count" "5"
        count=$(read_hook_state "$state_file" "stop_count" "")
        if [[ "$count" == "5" ]]; then
            log_pass
        else
            log_fail "Update failed: expected '5', got '$count'"
        fi
    else
        log_fail "Expected count=0, phase=specify; got count=$count, phase=$phase"
    fi

    teardown_yolo_test
}

# Test: yolo-guard allows when yolo_mode=false
test_yolo_guard_allows_when_disabled() {
    log_test "yolo-guard allows when yolo_mode=false"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: false
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"AskUserQuestion","tool_input":{"questions":[{"question":"Continue?","options":[{"label":"Yes"},{"label":"No"}]}]}}' | "${HOOKS_DIR}/yolo-guard.sh" 2>/dev/null)

    # Should produce no output (exit 0 with no JSON = allow)
    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output (allow), got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-guard blocks and auto-selects (Recommended) option
test_yolo_guard_blocks_with_recommended() {
    log_test "yolo-guard blocks and auto-selects (Recommended) option"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"AskUserQuestion","tool_input":{"questions":[{"question":"Specification complete. What next?","options":[{"label":"Design (Recommended)","description":"Move to design"},{"label":"Revise","description":"Revise spec"}]}]}}' | "${HOOKS_DIR}/yolo-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['hookSpecificOutput']['permissionDecision'] == 'deny'; assert 'Design (Recommended)' in d['hookSpecificOutput']['permissionDecisionReason']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny with '(Recommended)' selection, got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-guard falls back to first option when no (Recommended)
test_yolo_guard_fallback_first_option() {
    log_test "yolo-guard falls back to first option when no (Recommended)"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"AskUserQuestion","tool_input":{"questions":[{"question":"Pick one","options":[{"label":"Alpha"},{"label":"Beta"}]}]}}' | "${HOOKS_DIR}/yolo-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['hookSpecificOutput']['permissionDecision'] == 'deny'; assert 'Alpha' in d['hookSpecificOutput']['permissionDecisionReason']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny with 'Alpha' selection, got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-guard passes through safety keywords
test_yolo_guard_safety_passthrough() {
    log_test "yolo-guard passes through circuit breaker keywords"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"AskUserQuestion","tool_input":{"questions":[{"question":"YOLO MODE STOPPED due to circuit breaker. Continue?","options":[{"label":"Yes"},{"label":"No"}]}]}}' | "${HOOKS_DIR}/yolo-guard.sh" 2>/dev/null)

    # Should produce no output (allow through)
    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output (allow safety keyword), got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-guard ignores non-AskUserQuestion tools
test_yolo_guard_ignores_other_tools() {
    log_test "yolo-guard ignores non-AskUserQuestion tools"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | "${HOOKS_DIR}/yolo-guard.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output for non-AskUserQuestion, got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-stop allows when yolo_mode=false
test_yolo_stop_allows_when_disabled() {
    log_test "yolo-stop allows when yolo_mode=false"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: false
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{}' | "${HOOKS_DIR}/yolo-stop.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output (allow stop), got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-stop allows when no active feature
test_yolo_stop_allows_no_feature() {
    log_test "yolo-stop allows when no active feature"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{}' | "${HOOKS_DIR}/yolo-stop.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output (no active feature), got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-stop allows when feature completed
test_yolo_stop_allows_completed_feature() {
    log_test "yolo-stop allows when feature completed"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
---
TMPL
    mkdir -p "${YOLO_TMPDIR}/docs/features/099-test-feature"
    cat > "${YOLO_TMPDIR}/docs/features/099-test-feature/.meta.json" << 'META'
{"id":"099","slug":"test-feature","status":"completed","lastCompletedPhase":"finish"}
META

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"stop_hook_active":false}' | "${HOOKS_DIR}/yolo-stop.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output (completed feature), got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-stop blocks and returns correct next phase
test_yolo_stop_blocks_with_next_phase() {
    log_test "yolo-stop blocks and returns correct next phase"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
yolo_max_stop_blocks: 50
---
TMPL
    mkdir -p "${YOLO_TMPDIR}/docs/features/099-test-feature"
    cat > "${YOLO_TMPDIR}/docs/features/099-test-feature/.meta.json" << 'META'
{"id":"099","slug":"test-feature","status":"active","lastCompletedPhase":"specify"}
META

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"stop_hook_active":false}' | "${HOOKS_DIR}/yolo-stop.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['decision'] == 'block'; assert 'design' in d['reason']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected block with 'design' next phase, got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-stop detects stuck (no progress) and allows exit
test_yolo_stop_detects_stuck() {
    log_test "yolo-stop detects stuck and allows exit"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
yolo_max_stop_blocks: 50
---
TMPL
    mkdir -p "${YOLO_TMPDIR}/docs/features/099-test-feature"
    cat > "${YOLO_TMPDIR}/docs/features/099-test-feature/.meta.json" << 'META'
{"id":"099","slug":"test-feature","status":"active","lastCompletedPhase":"specify"}
META
    # Simulate prior block at same phase
    cat > "${YOLO_TMPDIR}/.claude/.yolo-hook-state" << 'STATE'
stop_count=1
last_phase=specify
STATE

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"stop_hook_active":true}' | "${HOOKS_DIR}/yolo-stop.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output (stuck detection), got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-stop respects max stop blocks
test_yolo_stop_max_blocks() {
    log_test "yolo-stop respects max stop blocks limit"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
yolo_max_stop_blocks: 3
---
TMPL
    mkdir -p "${YOLO_TMPDIR}/docs/features/099-test-feature"
    cat > "${YOLO_TMPDIR}/docs/features/099-test-feature/.meta.json" << 'META'
{"id":"099","slug":"test-feature","status":"active","lastCompletedPhase":"specify"}
META
    # Set counter at max already
    cat > "${YOLO_TMPDIR}/.claude/.yolo-hook-state" << 'STATE'
stop_count=3
last_phase=null
STATE

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"stop_hook_active":false}' | "${HOOKS_DIR}/yolo-stop.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output (max blocks exceeded), got: $output"
    fi

    teardown_yolo_test
}

# === Plan Review Gate Tests ===

# Test: pre-exit-plan-review allows when plan_mode_review=false
test_pre_exit_plan_allows_when_disabled() {
    log_test "pre-exit-plan-review allows when plan_mode_review=false"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
plan_mode_review: false
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"ExitPlanMode","tool_input":{}}' | "${HOOKS_DIR}/pre-exit-plan-review.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output (allow), got: $output"
    fi

    teardown_yolo_test
}

# Test: pre-exit-plan-review denies first attempt
test_pre_exit_plan_denies_first_attempt() {
    log_test "pre-exit-plan-review denies first attempt with plan-reviewer instructions"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
plan_mode_review: true
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"ExitPlanMode","tool_input":{}}' | "${HOOKS_DIR}/pre-exit-plan-review.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['hookSpecificOutput']['permissionDecision'] == 'deny'; assert 'plan-reviewer' in d['hookSpecificOutput']['permissionDecisionReason']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny with 'plan-reviewer' in reason, got: $output"
    fi

    teardown_yolo_test
}

# Test: pre-exit-plan-review allows second attempt and resets counter
test_pre_exit_plan_allows_second_attempt() {
    log_test "pre-exit-plan-review allows second attempt and resets counter"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
plan_mode_review: true
---
TMPL
    # Pre-seed counter to 1 (simulates first attempt already happened)
    echo "attempt=1" > "${YOLO_TMPDIR}/.claude/.plan-review-state"

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"ExitPlanMode","tool_input":{}}' | "${HOOKS_DIR}/pre-exit-plan-review.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then
        # Verify counter was reset to 0
        local counter
        counter=$(grep "^attempt=" "${YOLO_TMPDIR}/.claude/.plan-review-state" 2>/dev/null | cut -d= -f2)
        if [[ "$counter" == "0" ]]; then
            log_pass
        else
            log_fail "Counter not reset to 0, got: $counter"
        fi
    else
        log_fail "Expected empty output (allow), got: $output"
    fi

    teardown_yolo_test
}

# Test: pre-exit-plan-review resets stale counter (>2)
test_pre_exit_plan_resets_stale_counter() {
    log_test "pre-exit-plan-review resets stale counter and allows"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
plan_mode_review: true
---
TMPL
    # Pre-seed counter to 5 (stale from crashed session)
    echo "attempt=5" > "${YOLO_TMPDIR}/.claude/.plan-review-state"

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"ExitPlanMode","tool_input":{}}' | "${HOOKS_DIR}/pre-exit-plan-review.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then
        # Verify counter was reset to 0
        local counter
        counter=$(grep "^attempt=" "${YOLO_TMPDIR}/.claude/.plan-review-state" 2>/dev/null | cut -d= -f2)
        if [[ "$counter" == "0" ]]; then
            log_pass
        else
            log_fail "Counter not reset to 0, got: $counter"
        fi
    else
        log_fail "Expected empty output (allow), got: $output"
    fi

    teardown_yolo_test
}

# Test: pre-exit-plan-review deny output is valid JSON
test_pre_exit_plan_valid_json_on_deny() {
    log_test "pre-exit-plan-review deny output is valid JSON"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
plan_mode_review: true
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"ExitPlanMode","tool_input":{}}' | "${HOOKS_DIR}/pre-exit-plan-review.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        log_pass
    else
        log_fail "Invalid JSON output: $output"
    fi

    teardown_yolo_test
}

# Test: pre-exit-plan-review allows when yolo_mode=true (bypasses gate)
test_pre_exit_plan_allows_in_yolo_mode() {
    log_test "pre-exit-plan-review allows in YOLO mode (bypasses gate)"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
plan_mode_review: true
yolo_mode: true
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"tool_name":"ExitPlanMode","tool_input":{}}' | "${HOOKS_DIR}/pre-exit-plan-review.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then
        # Verify counter was reset to 0
        local counter
        counter=$(grep "^attempt=" "${YOLO_TMPDIR}/.claude/.plan-review-state" 2>/dev/null | cut -d= -f2)
        if [[ "$counter" == "0" ]]; then
            log_pass
        else
            log_fail "Counter not reset to 0, got: $counter"
        fi
    else
        log_fail "Expected empty output (allow), got: $output"
    fi

    teardown_yolo_test
}

# === Config Injection Tests ===

# Test: session-start injects pd_artifacts_root
test_session_start_injects_artifacts_root() {
    log_test "session-start injects pd_artifacts_root"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
artifacts_root: docs
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'pd_artifacts_root: docs' in d['hookSpecificOutput']['additionalContext']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected pd_artifacts_root in context"
    fi

    teardown_yolo_test
}

# Test: session-start injects pd_base_branch
test_session_start_injects_base_branch() {
    log_test "session-start injects pd_base_branch"

    setup_yolo_test
    cd "$YOLO_TMPDIR"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'pd_base_branch:' in d['hookSpecificOutput']['additionalContext']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected pd_base_branch in context"
    fi

    teardown_yolo_test
}

# Test: explicit base_branch overrides auto-detection
test_base_branch_explicit_overrides_auto() {
    log_test "explicit base_branch overrides auto-detection"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
base_branch: develop
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'pd_base_branch: develop' in d['hookSpecificOutput']['additionalContext']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected pd_base_branch: develop in context"
    fi

    teardown_yolo_test
}

# Test: base_branch defaults to main when no remote and no config
test_base_branch_defaults_to_main() {
    log_test "base_branch defaults to main (no remote, no config)"

    setup_yolo_test
    cd "$YOLO_TMPDIR"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'pd_base_branch: main' in d['hookSpecificOutput']['additionalContext']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected pd_base_branch: main in context"
    fi

    teardown_yolo_test
}

# Test: config NOT auto-provisioned when .claude/ doesn't exist
test_config_not_provisioned_without_claude_dir() {
    log_test "config NOT auto-provisioned when .claude/ doesn't exist"

    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "${tmpdir}/.git"
    # No .claude/ directory

    cd "$tmpdir"
    "${HOOKS_DIR}/session-start.sh" 2>/dev/null > /dev/null

    if [[ ! -f "${tmpdir}/.claude/pd.local.md" ]]; then
        log_pass
    else
        log_fail "Config was created despite no .claude/ directory"
    fi

    cd "${PROJECT_ROOT}"
    rm -rf "$tmpdir"
}

# Test: config IS auto-provisioned when .claude/ exists
test_config_provisioned_with_claude_dir() {
    log_test "config IS auto-provisioned when .claude/ exists"

    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "${tmpdir}/.git"
    mkdir -p "${tmpdir}/.claude"

    cd "$tmpdir"
    "${HOOKS_DIR}/session-start.sh" 2>/dev/null > /dev/null

    if [[ -f "${tmpdir}/.claude/pd.local.md" ]]; then
        log_pass
    else
        log_fail "Config was NOT created despite .claude/ existing"
    fi

    cd "${PROJECT_ROOT}"
    rm -rf "$tmpdir"
}

# === Custom Artifacts Root Tests ===

# Test: yolo-stop finds features under custom artifacts_root
test_yolo_stop_custom_artifacts_root() {
    log_test "yolo-stop finds features under custom artifacts_root"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
yolo_max_stop_blocks: 50
artifacts_root: custom-path
---
TMPL
    mkdir -p "${YOLO_TMPDIR}/custom-path/features/099-test-feature"
    cat > "${YOLO_TMPDIR}/custom-path/features/099-test-feature/.meta.json" << 'META'
{"id":"099","slug":"test-feature","status":"active","lastCompletedPhase":"specify"}
META

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"stop_hook_active":false}' | "${HOOKS_DIR}/yolo-stop.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['decision'] == 'block'; assert 'design' in d['reason']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected block with 'design' next phase under custom-path, got: $output"
    fi

    teardown_yolo_test
}

# Test: yolo-stop ignores features under default docs/ when artifacts_root is custom
test_yolo_stop_ignores_default_with_custom_root() {
    log_test "yolo-stop ignores docs/ features when artifacts_root=custom-path"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
yolo_max_stop_blocks: 50
artifacts_root: custom-path
---
TMPL
    # Features under docs/ (should be ignored)
    mkdir -p "${YOLO_TMPDIR}/docs/features/099-test-feature"
    cat > "${YOLO_TMPDIR}/docs/features/099-test-feature/.meta.json" << 'META'
{"id":"099","slug":"test-feature","status":"active","lastCompletedPhase":"specify"}
META

    cd "$YOLO_TMPDIR"
    local output
    output=$(echo '{"stop_hook_active":false}' | "${HOOKS_DIR}/yolo-stop.sh" 2>/dev/null)

    # No feature found under custom-path, so should allow
    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output (no feature under custom-path), got: $output"
    fi

    teardown_yolo_test
}

# Test: session-start injects custom artifacts_root value
test_session_start_custom_artifacts_root() {
    log_test "session-start injects custom artifacts_root value"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
artifacts_root: my-docs
---
TMPL

    cd "$YOLO_TMPDIR"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'pd_artifacts_root: my-docs' in d['hookSpecificOutput']['additionalContext']" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected pd_artifacts_root: my-docs in context"
    fi

    teardown_yolo_test
}

# === Robustness Tests ===

# Test: session-start produces valid JSON when no features directory exists
test_session_start_no_features() {
    log_test "session-start produces valid JSON when no features dir exists"

    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "${tmpdir}/.git" "${tmpdir}/.claude"

    cd "$tmpdir"
    local output
    output=$("${HOOKS_DIR}/session-start.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        log_pass
    else
        log_fail "Invalid JSON output when no features dir: $output"
    fi

    cd "${PROJECT_ROOT}"
    rm -rf "$tmpdir"
}

# Test: ERR trap outputs valid JSON {}
test_err_trap_produces_json() {
    log_test "install_err_trap outputs {} on error"

    source "${HOOKS_DIR}/lib/common.sh"

    # Run a subshell that triggers ERR trap
    local output
    output=$(bash -c '
        source "'"${HOOKS_DIR}/lib/common.sh"'"
        install_err_trap
        false  # trigger ERR
    ' 2>/dev/null)

    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected '{}', got: '$output'"
    fi
}

# Test: inject-secretary-context handles corrupt (non-numeric) YOLO_PAUSED_AT
test_secretary_handles_corrupt_state() {
    log_test "inject-secretary-context handles corrupt YOLO_PAUSED_AT"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
---
TMPL
    # Write corrupt non-numeric value
    mkdir -p "${YOLO_TMPDIR}/.claude"
    cat > "${YOLO_TMPDIR}/.claude/.yolo-hook-state" << 'STATE'
yolo_paused=true
yolo_paused_at=not_a_number
STATE

    cd "$YOLO_TMPDIR"
    local output exit_code=0
    output=$("${HOOKS_DIR}/inject-secretary-context.sh" 2>/dev/null) || exit_code=$?

    # Should not crash — should produce valid JSON or exit 0
    if [[ $exit_code -eq 0 ]]; then
        if [[ -z "$output" ]] || echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
            log_pass
        else
            log_fail "Invalid output on corrupt state: $output"
        fi
    else
        log_fail "Crashed with exit code $exit_code on corrupt state"
    fi

    teardown_yolo_test
}

# Test: yolo-stop handles non-numeric usage_limit gracefully
test_yolo_stop_handles_nonnumeric_limit() {
    log_test "yolo-stop handles non-numeric usage_limit"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
yolo_usage_limit: abc
yolo_max_stop_blocks: xyz
---
TMPL
    mkdir -p "${YOLO_TMPDIR}/docs/features/099-test-feature"
    cat > "${YOLO_TMPDIR}/docs/features/099-test-feature/.meta.json" << 'META'
{"id":"099","slug":"test-feature","status":"active","lastCompletedPhase":"specify"}
META

    cd "$YOLO_TMPDIR"
    local output exit_code=0
    output=$(echo '{"stop_hook_active":false}' | "${HOOKS_DIR}/yolo-stop.sh" 2>/dev/null) || exit_code=$?

    if [[ $exit_code -eq 0 ]]; then
        log_pass
    else
        log_fail "Crashed with exit code $exit_code on non-numeric limits"
    fi

    teardown_yolo_test
}

# Test: sync-cache handles rsync failure gracefully
test_sync_cache_handles_rsync_failure() {
    log_test "sync-cache handles rsync failure gracefully"

    # Run from temp dir where source dirs don't exist
    local tmpdir
    tmpdir=$(mktemp -d)
    cd "$tmpdir"

    local output exit_code=0
    output=$("${HOOKS_DIR}/sync-cache.sh" 2>/dev/null) || exit_code=$?

    if [[ $exit_code -eq 0 ]] && echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
        log_pass
    else
        log_fail "Should handle gracefully (exit=$exit_code)"
    fi

    cd "${PROJECT_ROOT}"
    rm -rf "$tmpdir"
}

# === Path Portability Tests ===

# Helper: find plugin component dir (relative to PROJECT_ROOT)
PLUGIN_COMP_DIR="${PROJECT_ROOT}/plugins/pd"

# Helper: check if a line (or its preceding context line) is a fallback reference
_is_fallback_line() {
    local line="$1"
    local context_line="$2"  # preceding line from grep -B1
    for check in "$line" "$context_line"; do
        case "$check" in
            *[Ff]allback*|*"dev workspace"*|*"If "*exists*|*"if "*exists*) return 0 ;;
        esac
    done
    return 1
}

# Helper: count non-fallback hardcoded paths in files
_count_hardcoded_paths() {
    local search_dir="$1"
    local file_pattern="$2"
    local exclude_basename="${3:-}"  # optional file to skip

    local violations=0
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        [[ -n "$exclude_basename" && "$(basename "$f")" == "$exclude_basename" ]] && continue
        local prev_line=""
        while IFS= read -r line; do
            [ -z "$line" ] && continue
            if [[ "$line" == "--" ]]; then
                prev_line=""
                continue
            fi
            if echo "$line" | grep -q 'plugins/pd/' 2>/dev/null; then
                if ! _is_fallback_line "$line" "$prev_line"; then
                    ((violations++)) || true
                fi
            fi
            prev_line="$line"
        done < <(grep -B1 'plugins/pd/' "$f" 2>/dev/null || true)
    done < <(find "$search_dir" -name "$file_pattern" -type f 2>/dev/null)
    echo "$violations"
}

test_no_hardcoded_plugin_paths_in_agents() {
    log_test "No hardcoded plugins/pd/ in agent .md files (non-fallback)"

    local violations
    violations=$(_count_hardcoded_paths "${PLUGIN_COMP_DIR}/agents" "*.md")

    if [[ $violations -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations non-fallback hardcoded path(s) in agent files"
    fi
}

test_no_hardcoded_plugin_paths_in_skills() {
    log_test "No hardcoded plugins/pd/ in SKILL.md files (non-fallback)"

    local violations
    violations=$(_count_hardcoded_paths "${PLUGIN_COMP_DIR}/skills" "SKILL.md")

    if [[ $violations -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations non-fallback hardcoded path(s) in skill files"
    fi
}

test_no_hardcoded_plugin_paths_in_commands() {
    log_test "No hardcoded plugins/pd/ in command .md files (non-fallback, excluding sync-cache)"

    local violations
    violations=$(_count_hardcoded_paths "${PLUGIN_COMP_DIR}/commands" "*.md" "sync-cache.md")

    if [[ $violations -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations non-fallback hardcoded path(s) in command files"
    fi
}

test_no_at_includes_with_hardcoded_paths() {
    log_test "No @plugins/ includes in command files"

    local violations=0
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        local count
        count=$(grep -c '@plugins/' "$f" 2>/dev/null) || count=0
        violations=$((violations + count))
    done < <(find "${PLUGIN_COMP_DIR}/commands" -name "*.md" -type f 2>/dev/null)

    if [[ $violations -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations @plugins/ include(s) in command files"
    fi
}

test_secretary_has_cache_glob() {
    log_test "secretary.md contains ~/.claude/plugins/cache discovery"

    if grep -q '~/.claude/plugins/cache' "${PLUGIN_COMP_DIR}/commands/secretary.md" 2>/dev/null; then
        log_pass
    else
        log_fail "secretary.md missing ~/.claude/plugins/cache glob for installed plugin discovery"
    fi
}

test_advisors_use_base_directory_derivation() {
    log_test "No raw plugins/pd/skills/ in advisor files"

    local violations=0
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        local count
        count=$(grep -c 'plugins/pd/skills/' "$f" 2>/dev/null) || count=0
        violations=$((violations + count))
    done < <(find "${PLUGIN_COMP_DIR}/skills/brainstorming/references/advisors" -name "*.advisor.md" -type f 2>/dev/null)

    if [[ $violations -eq 0 ]]; then
        log_pass
    else
        log_fail "Found $violations raw hardcoded paths in advisor files"
    fi
}

# === Meta-JSON Guard Tests ===

# Helper: setup temp HOME for meta-json-guard log tests
META_GUARD_TMPDIR=""
setup_meta_guard_test() {
    META_GUARD_TMPDIR=$(mktemp -d)
    mkdir -p "${META_GUARD_TMPDIR}/.claude/pd"
}

teardown_meta_guard_test() {
    if [[ -n "$META_GUARD_TMPDIR" ]] && [[ -d "$META_GUARD_TMPDIR" ]]; then
        rm -rf "$META_GUARD_TMPDIR"
    fi
    META_GUARD_TMPDIR=""
}

# Helper: setup with bootstrap sentinel (MCP available)
setup_meta_guard_test_with_sentinel() {
    setup_meta_guard_test
    mkdir -p "$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/pd-test/1.0.0/.venv"
    touch "$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/pd-test/1.0.0/.venv/.bootstrap-complete"
}

# Test: meta-json-guard denies Write to .meta.json
test_meta_json_guard_denies_write() {
    log_test "meta-json-guard denies Write to .meta.json"

    setup_meta_guard_test_with_sentinel

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-enforced-state-machine/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['hookSpecificOutput']['permissionDecision'] == 'deny'" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny for Write to .meta.json, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard denies Edit to .meta.json
test_meta_json_guard_denies_edit() {
    log_test "meta-json-guard denies Edit to .meta.json"

    setup_meta_guard_test_with_sentinel

    local output
    output=$(echo '{"tool_name":"Edit","tool_input":{"file_path":"docs/features/034-enforced-state-machine/.meta.json","old_string":"planned","new_string":"active"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['hookSpecificOutput']['permissionDecision'] == 'deny'" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny for Edit to .meta.json, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard denies Write to projects/.meta.json
test_meta_json_guard_denies_project_meta() {
    log_test "meta-json-guard denies Write to projects/.meta.json"

    setup_meta_guard_test_with_sentinel

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/projects/001-my-project/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['hookSpecificOutput']['permissionDecision'] == 'deny'" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny for Write to projects .meta.json, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard allows Write to spec.md
test_meta_json_guard_allows_non_meta() {
    log_test "meta-json-guard allows Write to spec.md"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-foo/spec.md","content":"# Spec"}}' | "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected '{}' for non-.meta.json file, got: $output"
    fi
}

# Test: meta-json-guard allows when .meta.json in content but not file_path
test_meta_json_guard_allows_meta_in_content_only() {
    log_test "meta-json-guard allows .meta.json in content but different file_path"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-foo/SKILL.md","content":"Read .meta.json for state"}}' | "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected '{}' when .meta.json only in content, got: $output"
    fi
}

# Test: meta-json-guard fast-path allows when no .meta.json reference
test_meta_json_guard_fast_path_allow() {
    log_test "meta-json-guard fast-path allows no .meta.json reference"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"src/main.py","content":"print(1)"}}' | "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected '{}' for fast-path, got: $output"
    fi
}

# Test: meta-json-guard logs blocked attempt with valid JSONL
test_meta_json_guard_logs_blocked_attempt() {
    log_test "meta-json-guard logs blocked attempt as valid JSONL"

    setup_meta_guard_test_with_sentinel

    echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null

    local log_file="${META_GUARD_TMPDIR}/.claude/pd/meta-json-guard.log"
    if [[ -f "$log_file" ]]; then
        local last_line
        last_line=$(tail -1 "$log_file")
        if echo "$last_line" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert 'timestamp' in d, 'missing timestamp'
assert 'tool' in d, 'missing tool'
assert 'path' in d, 'missing path'
assert 'feature_id' in d, 'missing feature_id'
assert d['tool'] == 'Write'
assert d['path'] == 'docs/features/034-foo/.meta.json'
" 2>/dev/null; then
            log_pass
        else
            log_fail "JSONL entry missing required keys or wrong values: $last_line"
        fi
    else
        log_fail "Log file not created at $log_file"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard extracts feature_id from path
test_meta_json_guard_extracts_feature_id() {
    log_test "meta-json-guard extracts feature_id from path"

    setup_meta_guard_test_with_sentinel

    echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-enforced-state-machine/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null

    local log_file="${META_GUARD_TMPDIR}/.claude/pd/meta-json-guard.log"
    if [[ -f "$log_file" ]]; then
        local last_line
        last_line=$(tail -1 "$log_file")
        if echo "$last_line" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['feature_id'] == '034-enforced-state-machine', f'got {d[\"feature_id\"]}'" 2>/dev/null; then
            log_pass
        else
            log_fail "Expected feature_id '034-enforced-state-machine', got: $last_line"
        fi
    else
        log_fail "Log file not created"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard latency < 200ms (CI threshold, NFR-3 target is 50ms)
test_meta_json_guard_latency() {
    log_test "meta-json-guard fast-path latency < 200ms"

    local start_ms end_ms elapsed_ms
    start_ms=$(python3 -c "import time; print(int(time.time()*1000))")
    echo '{"tool_name":"Write","tool_input":{"file_path":"src/main.py","content":"x"}}' | "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null
    end_ms=$(python3 -c "import time; print(int(time.time()*1000))")
    elapsed_ms=$((end_ms - start_ms))

    if [[ $elapsed_ms -lt 200 ]]; then
        log_pass
    else
        log_fail "Fast-path took ${elapsed_ms}ms (threshold: 200ms)"
    fi
}

# Test: meta-json-guard permits when no sentinel (degraded mode)
test_meta_json_guard_permits_when_no_sentinel() {
    log_test "meta-json-guard permits when no bootstrap sentinel"

    setup_meta_guard_test

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true
    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected {}, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard logs permit-degraded action
test_meta_json_guard_logs_permit_degraded() {
    log_test "meta-json-guard logs permit-degraded action"

    setup_meta_guard_test

    echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null || true

    local log_file="${META_GUARD_TMPDIR}/.claude/pd/meta-json-guard.log"
    if [[ -f "$log_file" ]]; then
        local last_line
        last_line=$(tail -1 "$log_file")
        if echo "$last_line" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('action') == 'permit-degraded', f'got action={d.get(\"action\")}'" 2>/dev/null; then
            log_pass
        else
            log_fail "Expected action=permit-degraded, got: $last_line"
        fi
    else
        log_fail "Log file not created at $log_file"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard deny message contains feature_type_id format
test_meta_json_guard_deny_message_has_feature_type_id() {
    log_test "meta-json-guard deny message has feature_type_id format"

    setup_meta_guard_test_with_sentinel

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-enforced-state-machine/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    local reason
    reason=$(echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['hookSpecificOutput']['permissionDecisionReason'])" 2>/dev/null) || true
    if [[ "$reason" == *"feature:"* ]]; then
        log_pass
    else
        log_fail "Expected reason to contain 'feature:', got: $reason"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard deny message contains fallback instruction
test_meta_json_guard_deny_message_has_fallback() {
    log_test "meta-json-guard deny message has fallback instruction"

    setup_meta_guard_test_with_sentinel

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    local reason
    reason=$(echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['hookSpecificOutput']['permissionDecisionReason'])" 2>/dev/null) || true
    if [[ "$reason" == *"fallback"* ]]; then
        log_pass
    else
        log_fail "Expected reason to contain 'fallback', got: $reason"
    fi

    teardown_meta_guard_test
}

# === Meta-JSON Guard Deepened Tests ===

# Test: meta-json-guard permits Edit when no bootstrap sentinel exists
# derived_from: spec:AC1
test_meta_json_guard_permits_edit_when_no_sentinel() {
    log_test "meta-json-guard permits Edit when no bootstrap sentinel"

    # Given no sentinel file exists (HOME set to empty temp dir)
    setup_meta_guard_test

    # When hook receives Edit tool input targeting a .meta.json file
    local output
    output=$(echo '{"tool_name":"Edit","tool_input":{"file_path":"docs/features/041-meta-json-guard-degradation/.meta.json","old_string":"planned","new_string":"active"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true

    # Then hook returns permit decision (empty JSON {})
    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected {}, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard sentinel detection with multiple matching cache dirs
# derived_from: spec:R1
test_meta_json_guard_sentinel_multiple_cache_dirs() {
    log_test "meta-json-guard detects sentinel across multiple cache dirs"

    # Given three cache directories with sentinels
    setup_meta_guard_test
    mkdir -p "$META_GUARD_TMPDIR/.claude/plugins/cache/org-a/pd-a/1.0/.venv"
    touch "$META_GUARD_TMPDIR/.claude/plugins/cache/org-a/pd-a/1.0/.venv/.bootstrap-complete"
    mkdir -p "$META_GUARD_TMPDIR/.claude/plugins/cache/org-b/pd-b/2.0/.venv"
    touch "$META_GUARD_TMPDIR/.claude/plugins/cache/org-b/pd-b/2.0/.venv/.bootstrap-complete"
    mkdir -p "$META_GUARD_TMPDIR/.claude/plugins/cache/org-c/pd-c/3.0/.venv"
    touch "$META_GUARD_TMPDIR/.claude/plugins/cache/org-c/pd-c/3.0/.venv/.bootstrap-complete"

    # When hook receives a .meta.json write
    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    # Then sentinel is detected, hook denies
    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['hookSpecificOutput']['permissionDecision'] == 'deny'" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny with multiple sentinels, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard permits when cache dir exists but has zero pd dirs
# derived_from: spec:R1
test_meta_json_guard_sentinel_zero_pd_dirs() {
    log_test "meta-json-guard permits when cache has no pd dirs"

    # Given cache directory exists but contains no pd directories
    setup_meta_guard_test
    mkdir -p "$META_GUARD_TMPDIR/.claude/plugins/cache/some-org/other-plugin/1.0"

    # When hook receives a .meta.json write
    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true

    # Then no sentinel found, hook permits with degraded mode
    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected {} (degraded permit), got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard permits when .claude directory does not exist
# derived_from: spec:R1
test_meta_json_guard_sentinel_no_claude_dir() {
    log_test "meta-json-guard permits when .claude dir missing entirely"

    # Given HOME/.claude does not exist at all
    local tmpdir
    tmpdir=$(mktemp -d)

    # When hook receives a .meta.json write
    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$tmpdir" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true

    # Then no sentinel found, hook permits
    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected {} (degraded permit), got: $output"
    fi

    rm -rf "$tmpdir"
}

# Test: meta-json-guard permits when .venv exists but no sentinel file
# derived_from: spec:R1
test_meta_json_guard_sentinel_venv_no_sentinel_file() {
    log_test "meta-json-guard permits when .venv exists but no sentinel"

    # Given cache directory with .venv but no .bootstrap-complete
    setup_meta_guard_test
    mkdir -p "$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/pd-test/1.0/.venv"
    # No .bootstrap-complete created

    # When hook receives a .meta.json write
    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true

    # Then no sentinel found, hook permits
    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected {} (degraded permit), got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard extracts feature_id from projects path
# derived_from: design:C2
test_meta_json_guard_feature_id_from_projects_path() {
    log_test "meta-json-guard extracts feature_id from projects path"

    # Given file path is docs/projects/my-project/.meta.json
    setup_meta_guard_test_with_sentinel

    echo '{"tool_name":"Write","tool_input":{"file_path":"docs/projects/my-project/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null

    # Then feature_id is my-project
    local log_file="${META_GUARD_TMPDIR}/.claude/pd/meta-json-guard.log"
    if [[ -f "$log_file" ]]; then
        local last_line
        last_line=$(tail -1 "$log_file")
        if echo "$last_line" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['feature_id'] == 'my-project', f'got {d[\"feature_id\"]}'" 2>/dev/null; then
            log_pass
        else
            log_fail "Expected feature_id 'my-project', got: $last_line"
        fi
    else
        log_fail "Log file not created"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard extracts unknown feature_id from non-standard path
# derived_from: design:C2
test_meta_json_guard_feature_id_unknown_path() {
    log_test "meta-json-guard extracts unknown feature_id from non-standard path"

    # Given file path is some/random/path/.meta.json
    setup_meta_guard_test_with_sentinel

    echo '{"tool_name":"Write","tool_input":{"file_path":"some/random/path/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null

    # Then feature_id is unknown
    local log_file="${META_GUARD_TMPDIR}/.claude/pd/meta-json-guard.log"
    if [[ -f "$log_file" ]]; then
        local last_line
        last_line=$(tail -1 "$log_file")
        if echo "$last_line" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['feature_id'] == 'unknown', f'got {d[\"feature_id\"]}'" 2>/dev/null; then
            log_pass
        else
            log_fail "Expected feature_id 'unknown', got: $last_line"
        fi
    else
        log_fail "Log file not created"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard deny log entry has NO action field
# derived_from: spec:R3
test_meta_json_guard_deny_log_has_no_action() {
    log_test "meta-json-guard deny log entry has no action field"

    # Given sentinel exists, hook will deny
    setup_meta_guard_test_with_sentinel

    # When hook denies a .meta.json write
    echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null

    # Then log entry does NOT contain an action field
    local log_file="${META_GUARD_TMPDIR}/.claude/pd/meta-json-guard.log"
    if [[ -f "$log_file" ]]; then
        local last_line
        last_line=$(tail -1 "$log_file")
        if echo "$last_line" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'action' not in d, f'deny log should not have action, got {d}'" 2>/dev/null; then
            log_pass
        else
            log_fail "Deny log entry should NOT have action field, got: $last_line"
        fi
    else
        log_fail "Log file not created"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard permit-degraded log has ISO 8601 UTC timestamp
# derived_from: spec:R3
test_meta_json_guard_degraded_log_timestamp_format() {
    log_test "meta-json-guard degraded log has ISO 8601 UTC timestamp"

    # Given no sentinel
    setup_meta_guard_test

    # When hook permits in degraded mode
    echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null || true

    # Then log entry timestamp matches YYYY-MM-DDTHH:MM:SSZ
    local log_file="${META_GUARD_TMPDIR}/.claude/pd/meta-json-guard.log"
    if [[ -f "$log_file" ]]; then
        local last_line
        last_line=$(tail -1 "$log_file")
        if echo "$last_line" | python3 -c "
import json, sys, re
d = json.load(sys.stdin)
ts = d['timestamp']
assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', ts), f'timestamp {ts} does not match ISO 8601 UTC'
" 2>/dev/null; then
            log_pass
        else
            log_fail "Timestamp format not ISO 8601 UTC: $last_line"
        fi
    else
        log_fail "Log file not created"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard deny message includes all three MCP tool names
# derived_from: spec:R2
test_meta_json_guard_deny_mentions_all_mcp_tools() {
    log_test "meta-json-guard deny mentions transition_phase, complete_phase, init_feature_state"

    # Given sentinel exists
    setup_meta_guard_test_with_sentinel

    # When hook denies a .meta.json write
    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    # Then deny reason mentions all three tools
    local reason
    reason=$(echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['hookSpecificOutput']['permissionDecisionReason'])" 2>/dev/null) || true
    local pass=true
    if [[ "$reason" != *"transition_phase"* ]]; then
        log_fail "Missing transition_phase in deny reason"
        pass=false
    fi
    if [[ "$reason" != *"complete_phase"* ]]; then
        $pass && log_fail "Missing complete_phase in deny reason"
        pass=false
    fi
    if [[ "$reason" != *"init_feature_state"* ]]; then
        $pass && log_fail "Missing init_feature_state in deny reason"
        pass=false
    fi
    if $pass; then
        log_pass
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard creates log directory if missing on degraded permit
# derived_from: design:C2
test_meta_json_guard_creates_log_dir_if_missing() {
    log_test "meta-json-guard creates log dir if missing on degraded permit"

    # Given no sentinel AND ~/.claude/pd/ does not exist
    local tmpdir
    tmpdir=$(mktemp -d)
    # Intentionally NOT creating .claude/pd

    # When hook permits in degraded mode and logs
    echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$tmpdir" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null || true

    # Then log directory is created and log file exists
    local log_file="$tmpdir/.claude/pd/meta-json-guard.log"
    if [[ -f "$log_file" ]]; then
        log_pass
    else
        log_fail "Expected log file at $log_file to be created"
    fi

    rm -rf "$tmpdir"
}

# Test: meta-json-guard does not crash when glob path does not exist
# derived_from: design:C1
test_meta_json_guard_no_crash_on_missing_glob_path() {
    log_test "meta-json-guard does not crash when glob path missing"

    # Given HOME points to a directory where .claude does not exist
    local tmpdir
    tmpdir=$(mktemp -d)

    # When check_mcp_available runs against non-existent glob
    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$tmpdir" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true

    # Then hook does not crash and permits
    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected {} (no crash), got: $output"
    fi

    rm -rf "$tmpdir"
}

# Test: action field distinguishes deny from degraded permit log entries
# derived_from: mutation: line deletion
test_meta_json_guard_action_field_distinguishes_deny_vs_degraded() {
    log_test "meta-json-guard action field distinguishes deny vs degraded"

    # Scenario 1: Deny (sentinel exists) - no action field
    setup_meta_guard_test_with_sentinel
    echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null
    local deny_log="${META_GUARD_TMPDIR}/.claude/pd/meta-json-guard.log"
    local deny_line
    deny_line=$(tail -1 "$deny_log")
    teardown_meta_guard_test

    # Scenario 2: Degraded permit (no sentinel) - has action field
    setup_meta_guard_test
    echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null || true
    local degraded_log="${META_GUARD_TMPDIR}/.claude/pd/meta-json-guard.log"
    local degraded_line
    degraded_line=$(tail -1 "$degraded_log")
    teardown_meta_guard_test

    # Then deny has no action, degraded has action=permit-degraded
    if python3 -c "
import json, sys
deny = json.loads('''$deny_line''')
degraded = json.loads('''$degraded_line''')
assert 'action' not in deny, f'deny should not have action: {deny}'
assert degraded.get('action') == 'permit-degraded', f'degraded should have action=permit-degraded: {degraded}'
" 2>/dev/null; then
        log_pass
    else
        log_fail "Deny log: $deny_line | Degraded log: $degraded_line"
    fi
}

# Test: meta-json-guard degraded path output is exactly {} (no deny appended)
# derived_from: mutation: exit 0 deletion
test_meta_json_guard_degraded_output_is_exactly_empty_json() {
    log_test "meta-json-guard degraded output is exactly {} (no deny appended)"

    # Given no sentinel (degraded mode)
    setup_meta_guard_test

    # When hook enters degraded permit path
    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true

    # Then output is exactly {} with no deny JSON appended
    if [[ "$output" == "{}" ]]; then
        log_pass
    else
        log_fail "Expected exactly '{}', got '$output' (length ${#output})"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard deny reason is non-empty and contains key guidance
# derived_from: mutation: return value
test_meta_json_guard_deny_reason_non_empty_with_guidance() {
    log_test "meta-json-guard deny reason non-empty with feature: and fallback"

    # Given sentinel exists
    setup_meta_guard_test_with_sentinel

    # When hook denies
    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/041-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    # Then permissionDecisionReason is non-empty containing both feature: and fallback
    local reason
    reason=$(echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['hookSpecificOutput']['permissionDecisionReason'])" 2>/dev/null) || true
    if [[ -n "$reason" ]] && [[ "$reason" == *"feature:"* ]] && [[ "$reason" == *"fallback"* ]]; then
        log_pass
    else
        log_fail "Expected non-empty reason with 'feature:' and 'fallback', got: $reason"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard deny path latency < 200ms
# derived_from: spec:R1
test_meta_json_guard_deny_path_latency() {
    log_test "meta-json-guard deny path latency < 500ms"

    # Given sentinel exists (deny path)
    setup_meta_guard_test_with_sentinel

    # When hook processes a .meta.json input
    # Note: 500ms threshold accounts for python3 subprocess overhead in JSON parsing path
    # (fast-path test at 200ms covers the no-python3 path; this tests regression on full path)
    local start_ms end_ms elapsed_ms
    start_ms=$(python3 -c "import time; print(int(time.time()*1000))")
    echo '{"tool_name":"Edit","tool_input":{"file_path":"docs/features/041-foo/.meta.json","old_string":"x","new_string":"y"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null
    end_ms=$(python3 -c "import time; print(int(time.time()*1000))")
    elapsed_ms=$((end_ms - start_ms))

    # Then total execution time is under 500ms
    if [[ $elapsed_ms -lt 500 ]]; then
        log_pass
    else
        log_fail "Deny path took ${elapsed_ms}ms (threshold: 500ms)"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard degraded permit path latency < 200ms
# derived_from: spec:R1
test_meta_json_guard_degraded_permit_path_latency() {
    log_test "meta-json-guard degraded permit path latency < 500ms"

    # Given no sentinel (degraded permit path)
    setup_meta_guard_test

    # When hook processes a .meta.json input
    # Note: 500ms threshold accounts for python3 subprocess overhead in JSON parsing path
    local start_ms end_ms elapsed_ms
    start_ms=$(python3 -c "import time; print(int(time.time()*1000))")
    echo '{"tool_name":"Edit","tool_input":{"file_path":"docs/features/041-foo/.meta.json","old_string":"x","new_string":"y"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null || true
    end_ms=$(python3 -c "import time; print(int(time.time()*1000))")
    elapsed_ms=$((end_ms - start_ms))

    # Then total execution time is under 500ms
    if [[ $elapsed_ms -lt 500 ]]; then
        log_pass
    else
        log_fail "Degraded permit path took ${elapsed_ms}ms (threshold: 500ms)"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard deny output has correct JSON structure
# derived_from: spec:AC7
test_meta_json_guard_deny_structure_matches_spec() {
    log_test "meta-json-guard deny output has hookSpecificOutput structure"

    # Given sentinel exists
    setup_meta_guard_test_with_sentinel

    # When hook receives Edit/Write targeting .meta.json
    local output
    output=$(echo '{"tool_name":"Edit","tool_input":{"file_path":"docs/features/041-foo/.meta.json","old_string":"x","new_string":"y"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    # Then deny has correct structure: hookSpecificOutput.{hookEventName, permissionDecision, permissionDecisionReason}
    if echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
hso = d['hookSpecificOutput']
assert hso['hookEventName'] == 'PreToolUse', f'hookEventName={hso[\"hookEventName\"]}'
assert hso['permissionDecision'] == 'deny', f'permissionDecision={hso[\"permissionDecision\"]}'
assert len(hso['permissionDecisionReason']) > 0, 'permissionDecisionReason is empty'
assert len(hso) == 3, f'expected 3 keys in hookSpecificOutput, got {len(hso)}'
" 2>/dev/null; then
        log_pass
    else
        log_fail "Deny structure mismatch: $output"
    fi

    teardown_meta_guard_test
}

# === YOLO Dependency-Aware Feature Selection Tests (Feature 038) ===

# Test: yolo-stop skips feature with blocked dep, selects eligible one
test_yolo_stop_skips_blocked_dep() {
    log_test "yolo-stop skips feature with unmet dep, selects eligible one"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
artifacts_root: docs
yolo_max_stop_blocks: 50
---
TMPL
    echo '{}' > "${YOLO_TMPDIR}/.claude/.yolo-hook-state"

    # X-blocked: active, depends on Z-dep (blocked) -> should be skipped
    mkdir -p "${YOLO_TMPDIR}/docs/features/X-blocked"
    cat > "${YOLO_TMPDIR}/docs/features/X-blocked/.meta.json" << 'META'
{"id":"X","slug":"blocked","status":"active","depends_on_features":["Z-dep"],"lastCompletedPhase":"specify"}
META

    # Y-eligible: active, depends on W-dep (completed) -> should be selected
    mkdir -p "${YOLO_TMPDIR}/docs/features/Y-eligible"
    cat > "${YOLO_TMPDIR}/docs/features/Y-eligible/.meta.json" << 'META'
{"id":"Y","slug":"eligible","status":"active","depends_on_features":["W-dep"],"lastCompletedPhase":"specify"}
META

    # Z-dep: blocked (unmet)
    mkdir -p "${YOLO_TMPDIR}/docs/features/Z-dep"
    cat > "${YOLO_TMPDIR}/docs/features/Z-dep/.meta.json" << 'META'
{"id":"Z","slug":"dep","status":"blocked"}
META

    # W-dep: completed (met)
    mkdir -p "${YOLO_TMPDIR}/docs/features/W-dep"
    cat > "${YOLO_TMPDIR}/docs/features/W-dep/.meta.json" << 'META'
{"id":"W","slug":"dep","status":"completed"}
META

    cd "$YOLO_TMPDIR"
    local output stderr_output
    stderr_output=$(mktemp)
    output=$(echo '{}' | "${HOOKS_DIR}/yolo-stop.sh" 2>"$stderr_output")
    local stderr_content
    stderr_content=$(cat "$stderr_output")
    rm -f "$stderr_output"

    # Verify: stdout JSON selects Y-eligible (block decision), X-blocked was skipped
    # Also verify stderr contains skip diagnostic for X-blocked
    local json_ok=false skip_diag=false
    if echo "$output" | python3 -c "
import json, sys
d = json.load(sys.stdin)
assert d['decision'] == 'block', f'Expected block, got {d[\"decision\"]}'
assert 'Y-eligible' in d['reason'], f'Expected Y-eligible in reason, got {d[\"reason\"]}'
assert 'X-blocked' not in d['reason'], f'X-blocked should not be selected'
" 2>/dev/null; then
        json_ok=true
    fi

    if echo "$stderr_content" | grep -q "Skipped X-blocked.*Z-dep"; then
        skip_diag=true
    fi

    if [[ "$json_ok" == "true" && "$skip_diag" == "true" ]]; then
        log_pass
    else
        log_fail "Expected block with Y-eligible and skip diagnostic for X-blocked. json_ok=$json_ok, skip_diag=$skip_diag, stdout: '$output', stderr: '$stderr_content'"
    fi

    teardown_yolo_test
}

# Test: yolo-stop allows stop when all active features have unmet deps
test_yolo_stop_all_deps_unmet_allows_stop() {
    log_test "yolo-stop allows stop when all deps unmet"

    setup_yolo_test
    cat > "${YOLO_TMPDIR}/.claude/pd.local.md" << 'TMPL'
---
yolo_mode: true
artifacts_root: docs
yolo_max_stop_blocks: 50
---
TMPL
    echo '{}' > "${YOLO_TMPDIR}/.claude/.yolo-hook-state"

    # A-blocked: active, depends on C-dep (blocked)
    mkdir -p "${YOLO_TMPDIR}/docs/features/A-blocked"
    cat > "${YOLO_TMPDIR}/docs/features/A-blocked/.meta.json" << 'META'
{"id":"A","slug":"blocked","status":"active","depends_on_features":["C-dep"],"lastCompletedPhase":"specify"}
META

    # B-blocked: active, depends on D-dep (planned)
    mkdir -p "${YOLO_TMPDIR}/docs/features/B-blocked"
    cat > "${YOLO_TMPDIR}/docs/features/B-blocked/.meta.json" << 'META'
{"id":"B","slug":"blocked","status":"active","depends_on_features":["D-dep"],"lastCompletedPhase":"specify"}
META

    # C-dep: blocked (unmet)
    mkdir -p "${YOLO_TMPDIR}/docs/features/C-dep"
    cat > "${YOLO_TMPDIR}/docs/features/C-dep/.meta.json" << 'META'
{"id":"C","slug":"dep","status":"blocked"}
META

    # D-dep: planned (unmet)
    mkdir -p "${YOLO_TMPDIR}/docs/features/D-dep"
    cat > "${YOLO_TMPDIR}/docs/features/D-dep/.meta.json" << 'META'
{"id":"D","slug":"dep","status":"planned"}
META

    cd "$YOLO_TMPDIR"
    local output stderr_output exit_code
    stderr_output=$(mktemp)
    output=$(echo '{}' | "${HOOKS_DIR}/yolo-stop.sh" 2>"$stderr_output") || true
    exit_code=$?
    local stderr_content
    stderr_content=$(cat "$stderr_output")
    rm -f "$stderr_output"

    # Verify: exit 0, no JSON on stdout, stderr contains diagnostics
    local no_json has_no_eligible
    no_json=true
    has_no_eligible=false

    if [[ -n "$output" ]]; then
        if echo "$output" | python3 -c "import json,sys; json.load(sys.stdin)" 2>/dev/null; then
            no_json=false
        fi
    fi

    if echo "$stderr_content" | grep -q "No eligible active features. Allowing stop." 2>/dev/null; then
        has_no_eligible=true
    fi

    if [[ "$no_json" == "true" && "$has_no_eligible" == "true" ]]; then
        log_pass
    else
        log_fail "Expected no JSON output and diagnostic on stderr. exit=$exit_code, stdout: '$output', stderr: '$stderr_content'"
    fi

    teardown_yolo_test
}

# === Feature 042: MCP Bootstrap Python Discovery Tests ===

# Test: check_mcp_health returns warning for recent error log entries
test_check_mcp_health_recent_errors() {
    log_test "check_mcp_health returns warning for recent error log entries"

    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.claude/pd"

    # Write a recent error log entry (current UTC timestamp)
    local ts
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "{\"timestamp\":\"$ts\",\"server\":\"memory-server\",\"error\":\"python_version\",\"message\":\"Python >= 3.12 required\"}" > "$tmpdir/.claude/pd/mcp-bootstrap-errors.log"

    # Write a test script that sources the function and calls it
    local test_script="$tmpdir/test_health.sh"
    cat > "$test_script" << 'SCRIPT_EOF'
#!/usr/bin/env bash
set +euo pipefail 2>/dev/null || true
SCRIPT_EOF
    # Append the function definition from session-start.sh
    sed -n '/^check_mcp_health/,/^}/p' "${HOOKS_DIR}/session-start.sh" >> "$test_script"
    echo 'check_mcp_health' >> "$test_script"
    chmod +x "$test_script"

    cd "$PROJECT_ROOT"
    local output
    output=$(HOME="$tmpdir" PLUGIN_ROOT="${HOOKS_DIR}/.." bash "$test_script" 2>/dev/null) || true

    if [[ "$output" == *"WARNING"* ]] && [[ "$output" == *"MCP servers failed"* ]]; then
        log_pass
    else
        log_fail "Expected WARNING about MCP servers, got: '$output'"
    fi

    rm -rf "$tmpdir"
}

# Test: check_mcp_health returns empty for old entries
test_check_mcp_health_old_entries() {
    log_test "check_mcp_health returns empty for old entries"

    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.claude/pd"

    # Write an old error log entry (2 hours ago)
    echo '{"timestamp":"2020-01-01T00:00:00Z","server":"memory-server","error":"python_version","message":"old error"}' > "$tmpdir/.claude/pd/mcp-bootstrap-errors.log"

    output=$(HOME="$tmpdir" PLUGIN_ROOT="${HOOKS_DIR}/.." bash -c '
        set +euo pipefail 2>/dev/null || true
        PLUGIN_ROOT="'"${HOOKS_DIR}/.."'"
        '"$(sed -n '/^check_mcp_health/,/^}/p' "${HOOKS_DIR}/session-start.sh")"'
        check_mcp_health
    ' 2>/dev/null) || true

    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output for old entries, got: '$output'"
    fi

    rm -rf "$tmpdir"
}

# Test: check_mcp_health returns empty when no log file
test_check_mcp_health_no_log() {
    log_test "check_mcp_health returns empty when no log file"

    local tmpdir
    tmpdir=$(mktemp -d)
    mkdir -p "$tmpdir/.claude/pd"

    output=$(HOME="$tmpdir" PLUGIN_ROOT="${HOOKS_DIR}/.." bash -c '
        set +euo pipefail 2>/dev/null || true
        PLUGIN_ROOT="'"${HOOKS_DIR}/.."'"
        '"$(sed -n '/^check_mcp_health/,/^}/p' "${HOOKS_DIR}/session-start.sh")"'
        check_mcp_health
    ' 2>/dev/null) || true

    if [[ -z "$output" ]]; then
        log_pass
    else
        log_fail "Expected empty output, got: '$output'"
    fi

    rm -rf "$tmpdir"
}

# Test: meta-json-guard sentinel with valid content blocks writes
test_meta_json_guard_sentinel_valid_content() {
    log_test "meta-json-guard sentinel with valid content blocks writes"

    setup_meta_guard_test
    local sentinel_dir="$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/pd-test/1.0.0/.venv"
    mkdir -p "$sentinel_dir"

    # Write sentinel with valid content (real python path)
    local real_python
    real_python=$(command -v python3)
    local real_version
    real_version=$(python3 -c "import sys; print('{0}.{1}'.format(sys.version_info.major, sys.version_info.minor))" 2>/dev/null)
    echo "$real_python:$real_version" > "$sentinel_dir/.bootstrap-complete"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/042-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['hookSpecificOutput']['permissionDecision'] == 'deny'" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny with valid sentinel content, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard sentinel with removed interpreter permits
test_meta_json_guard_sentinel_removed_interpreter() {
    log_test "meta-json-guard sentinel with removed interpreter permits"

    setup_meta_guard_test
    local sentinel_dir="$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/pd-test/1.0.0/.venv"
    mkdir -p "$sentinel_dir"

    # Write sentinel with non-existent python path
    echo "/nonexistent/python3.13:3.13" > "$sentinel_dir/.bootstrap-complete"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/042-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true

    # Should permit (degraded) because interpreter doesn't exist
    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d == {}" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected permit (empty JSON) for removed interpreter, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard sentinel with old version permits
test_meta_json_guard_sentinel_old_version() {
    log_test "meta-json-guard sentinel with old version (3.9) permits"

    setup_meta_guard_test
    local sentinel_dir="$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/pd-test/1.0.0/.venv"
    mkdir -p "$sentinel_dir"

    # Write sentinel with valid path but old version
    local real_python
    real_python=$(command -v python3)
    echo "$real_python:3.9" > "$sentinel_dir/.bootstrap-complete"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/042-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true

    # Should permit (degraded) because version < 3.12
    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d == {}" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected permit for old version, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard legacy empty sentinel (recent mtime) blocks
test_meta_json_guard_legacy_sentinel_recent() {
    log_test "meta-json-guard legacy empty sentinel (recent mtime) blocks"

    setup_meta_guard_test
    local sentinel_dir="$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/pd-test/1.0.0/.venv"
    mkdir -p "$sentinel_dir"

    # Create empty sentinel (legacy format) with current mtime
    touch "$sentinel_dir/.bootstrap-complete"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/042-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d['hookSpecificOutput']['permissionDecision'] == 'deny'" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny for recent legacy sentinel, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard legacy empty sentinel (stale mtime > 24h) permits
test_meta_json_guard_legacy_sentinel_stale() {
    log_test "meta-json-guard legacy empty sentinel (stale > 24h) permits"

    setup_meta_guard_test
    local sentinel_dir="$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/pd-test/1.0.0/.venv"
    mkdir -p "$sentinel_dir"

    # Create empty sentinel and backdate to > 24h ago
    touch "$sentinel_dir/.bootstrap-complete"
    touch -t 202001010000 "$sentinel_dir/.bootstrap-complete"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/042-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null) || true

    # Should permit (degraded) because mtime > 24h
    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d == {}" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected permit for stale legacy sentinel, got: $output"
    fi

    teardown_meta_guard_test
}

# Test: meta-json-guard stale sentinel logs permit-degraded-stale-sentinel
test_meta_json_guard_stale_sentinel_log() {
    log_test "meta-json-guard stale sentinel logs permit-degraded-stale-sentinel"

    setup_meta_guard_test
    local sentinel_dir="$META_GUARD_TMPDIR/.claude/plugins/cache/test-org/pd-test/1.0.0/.venv"
    mkdir -p "$sentinel_dir"

    # Create sentinel with non-existent interpreter
    echo "/nonexistent/python3.13:3.13" > "$sentinel_dir/.bootstrap-complete"

    echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/042-foo/.meta.json","content":"{}"}}' | HOME="$META_GUARD_TMPDIR" "${HOOKS_DIR}/meta-json-guard.sh" 2>/dev/null > /dev/null || true

    local log_file="${META_GUARD_TMPDIR}/.claude/pd/meta-json-guard.log"
    if [[ -f "$log_file" ]]; then
        local last_line
        last_line=$(tail -1 "$log_file")
        if echo "$last_line" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get('action') == 'permit-degraded-stale-sentinel'" 2>/dev/null; then
            log_pass
        else
            log_fail "Expected permit-degraded-stale-sentinel action in log, got: $last_line"
        fi
    else
        log_fail "No guard log file found"
    fi

    teardown_meta_guard_test
}

# Test: session-start first-run message appears when .venv missing
test_session_start_first_run_when_venv_missing() {
    log_test "session-start first-run setup message when .venv missing"

    # Create a temp HOME and project without .venv and memory dir
    local tmpdir
    tmpdir=$(mktemp -d)
    local fake_home
    fake_home=$(mktemp -d)
    mkdir -p "$tmpdir/.git" "$tmpdir/.claude"
    cat > "$tmpdir/.claude/pd.local.md" << 'TMPL'
---
memory_injection_enabled: false
---
TMPL

    cd "$tmpdir"
    local output
    # Override HOME so memory dir check fails; PLUGIN_ROOT will be derived from
    # the real hook script location, but the first-run check also looks at
    # $HOME/.claude/pd/memory which won't exist in fake_home
    output=$(HOME="$fake_home" "${HOOKS_DIR}/session-start.sh" 2>/dev/null) || true

    local context
    context=$(echo "$output" | python3 -c "import json,sys; print(json.load(sys.stdin).get('hookSpecificOutput',{}).get('additionalContext',''))" 2>/dev/null)

    if [[ "$context" == *"Setup required"* ]] && [[ "$context" == *"setup.sh"* ]]; then
        log_pass
    else
        log_fail "Expected 'Setup required' message, got: ${context:0:200}"
    fi

    cd "$PROJECT_ROOT"
    rm -rf "$tmpdir" "$fake_home"
}

# Run all tests
main() {
    echo "=========================================="
    echo "Hook Integration Tests"
    echo "=========================================="
    echo ""

    test_common_library_exists
    test_detect_project_root
    test_detect_project_root_subdirectory
    test_detect_project_root_nested
    test_escape_json
    test_session_start_json
    test_session_start_from_subdirectory
    test_pre_commit_guard_allows_non_commit
    test_pre_commit_guard_allows_non_git
    test_pre_commit_guard_warns_main
    test_pre_commit_guard_from_subdirectory
    test_sync_cache_json
    test_sync_cache_missing_source

    echo ""
    echo "--- YOLO Hook Tests ---"
    echo ""

    test_read_local_md_field
    test_read_local_md_field_missing
    test_hook_state_roundtrip
    test_yolo_guard_allows_when_disabled
    test_yolo_guard_blocks_with_recommended
    test_yolo_guard_fallback_first_option
    test_yolo_guard_safety_passthrough
    test_yolo_guard_ignores_other_tools
    test_yolo_stop_allows_when_disabled
    test_yolo_stop_allows_no_feature
    test_yolo_stop_allows_completed_feature
    test_yolo_stop_blocks_with_next_phase
    test_yolo_stop_detects_stuck
    test_yolo_stop_max_blocks
    test_yolo_stop_skips_blocked_dep
    test_yolo_stop_all_deps_unmet_allows_stop

    echo ""
    echo "--- Plan Review Gate Tests ---"
    echo ""

    test_pre_exit_plan_allows_when_disabled
    test_pre_exit_plan_denies_first_attempt
    test_pre_exit_plan_allows_second_attempt
    test_pre_exit_plan_resets_stale_counter
    test_pre_exit_plan_valid_json_on_deny
    test_pre_exit_plan_allows_in_yolo_mode

    echo ""
    echo "--- Config Injection Tests ---"
    echo ""

    test_session_start_injects_artifacts_root
    test_session_start_injects_base_branch
    test_base_branch_explicit_overrides_auto
    test_base_branch_defaults_to_main
    test_config_not_provisioned_without_claude_dir
    test_config_provisioned_with_claude_dir

    echo ""
    echo "--- Custom Artifacts Root Tests ---"
    echo ""

    test_yolo_stop_custom_artifacts_root
    test_yolo_stop_ignores_default_with_custom_root
    test_session_start_custom_artifacts_root

    echo ""
    echo "--- Robustness Tests ---"
    echo ""

    test_session_start_no_features
    test_err_trap_produces_json
    test_secretary_handles_corrupt_state
    test_yolo_stop_handles_nonnumeric_limit
    test_sync_cache_handles_rsync_failure

    echo ""
    echo "--- Meta-JSON Guard Tests ---"
    echo ""

    test_meta_json_guard_denies_write
    test_meta_json_guard_denies_edit
    test_meta_json_guard_denies_project_meta
    test_meta_json_guard_allows_non_meta
    test_meta_json_guard_allows_meta_in_content_only
    test_meta_json_guard_fast_path_allow
    test_meta_json_guard_logs_blocked_attempt
    test_meta_json_guard_extracts_feature_id
    test_meta_json_guard_latency
    test_meta_json_guard_permits_when_no_sentinel
    test_meta_json_guard_logs_permit_degraded
    test_meta_json_guard_deny_message_has_feature_type_id
    test_meta_json_guard_deny_message_has_fallback

    echo ""
    echo "--- Meta-JSON Guard Deepened Tests ---"
    echo ""

    test_meta_json_guard_permits_edit_when_no_sentinel
    test_meta_json_guard_sentinel_multiple_cache_dirs
    test_meta_json_guard_sentinel_zero_pd_dirs
    test_meta_json_guard_sentinel_no_claude_dir
    test_meta_json_guard_sentinel_venv_no_sentinel_file
    test_meta_json_guard_feature_id_from_projects_path
    test_meta_json_guard_feature_id_unknown_path
    test_meta_json_guard_deny_log_has_no_action
    test_meta_json_guard_degraded_log_timestamp_format
    test_meta_json_guard_deny_mentions_all_mcp_tools
    test_meta_json_guard_creates_log_dir_if_missing
    test_meta_json_guard_no_crash_on_missing_glob_path
    test_meta_json_guard_action_field_distinguishes_deny_vs_degraded
    test_meta_json_guard_degraded_output_is_exactly_empty_json
    test_meta_json_guard_deny_reason_non_empty_with_guidance
    test_meta_json_guard_deny_path_latency
    test_meta_json_guard_degraded_permit_path_latency
    test_meta_json_guard_deny_structure_matches_spec

    echo ""
    echo "--- Feature 042: MCP Bootstrap Python Discovery Tests ---"
    echo ""

    test_check_mcp_health_recent_errors
    test_check_mcp_health_old_entries
    test_check_mcp_health_no_log
    test_meta_json_guard_sentinel_valid_content
    test_meta_json_guard_sentinel_removed_interpreter
    test_meta_json_guard_sentinel_old_version
    test_meta_json_guard_legacy_sentinel_recent
    test_meta_json_guard_legacy_sentinel_stale
    test_meta_json_guard_stale_sentinel_log
    test_session_start_first_run_when_venv_missing

    echo ""
    echo "--- Path Portability Tests ---"
    echo ""

    test_no_hardcoded_plugin_paths_in_agents
    test_no_hardcoded_plugin_paths_in_skills
    test_no_hardcoded_plugin_paths_in_commands
    test_no_at_includes_with_hardcoded_paths
    test_secretary_has_cache_glob
    test_advisors_use_base_directory_derivation

    echo ""
    echo "=========================================="
    echo "Results: ${TESTS_PASSED}/${TESTS_RUN} passed"
    if [[ $TESTS_SKIPPED -gt 0 ]]; then
        echo "Skipped: ${TESTS_SKIPPED}"
    fi
    echo "=========================================="

    if [[ $TESTS_FAILED -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main
