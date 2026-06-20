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

# --- pre-push-guard.sh tests ---

# Test: pre-push-guard.sh allows non-push commands
test_pre_push_guard_allows_non_push() {
    log_test "pre-push-guard.sh allows non-push commands"

    cd "${PROJECT_ROOT}"
    local output
    output=$(echo '{"tool_name": "Bash", "tool_input": {"command": "ls -la"}}' | "${HOOKS_DIR}/pre-push-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d == {}" 2>/dev/null; then
        log_pass
    else
        log_fail "Should return empty JSON for non-push, got: $output"
    fi
}

# Test: pre-push-guard.sh allows clean push
test_pre_push_guard_allows_clean_push() {
    log_test "pre-push-guard.sh allows clean git push"

    cd "${PROJECT_ROOT}"
    local output
    output=$(echo '{"tool_name": "Bash", "tool_input": {"command": "git push origin develop"}}' | "${HOOKS_DIR}/pre-push-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d == {}" 2>/dev/null; then
        log_pass
    else
        log_fail "Should return empty JSON for clean push, got: $output"
    fi
}

# Test: pre-push-guard.sh blocks push with broken .meta.json
test_pre_push_guard_blocks_broken_meta() {
    log_test "pre-push-guard.sh blocks push with broken .meta.json"

    local tmpdir
    tmpdir=$(mktemp -d)
    git init "$tmpdir" >/dev/null 2>&1
    mkdir -p "$tmpdir/docs/features/099-broken-feature"
    cat > "$tmpdir/docs/features/099-broken-feature/.meta.json" << 'META'
{"id":"099","slug":"broken-feature","status":"completed"}
META

    cd "$tmpdir"
    local output
    output=$(echo '{"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}' | "${HOOKS_DIR}/pre-push-guard.sh" 2>/dev/null)

    if echo "$output" | python3 -c "
import json,sys
d=json.load(sys.stdin)
hso = d['hookSpecificOutput']
assert hso['permissionDecision'] == 'deny', f'expected deny, got {hso[\"permissionDecision\"]}'
assert 'BLOCKED' in hso['permissionDecisionReason'], 'reason should contain BLOCKED'
" 2>/dev/null; then
        log_pass
    else
        log_fail "Should deny push with broken .meta.json, got: $output"
    fi

    cd "${PROJECT_ROOT}"
    rm -rf "$tmpdir"
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

# Test 13b: sync-cache.sh detects pd install under any marketplace name
# (regression guard for the my-local-plugins hardcode bug)
test_sync_cache_detects_arbitrary_marketplace() {
    log_test "sync-cache.sh detects pd install under non-my-local-plugins marketplace"

    local tmpdir cache_dir
    tmpdir=$(mktemp -d) || { log_fail "mktemp failed"; return; }
    cache_dir="$tmpdir/.claude/plugins/cache/test-marketplace/pd/9.9.9"
    mkdir -p "$cache_dir/.claude-plugin"
    mkdir -p "$tmpdir/.claude/plugins/marketplaces/test-marketplace/.claude-plugin"

    # Pre-populate cache plugin.json with stale content to detect overwrite
    echo '{"name":"stale-marker"}' > "$cache_dir/.claude-plugin/plugin.json"

    # Inject fake installed_plugins.json with non-my-local-plugins marketplace
    cat > "$tmpdir/.claude/plugins/installed_plugins.json" <<EOF
{
  "version": 1,
  "plugins": {
    "pd@test-marketplace": [
      {"scope":"user","installPath":"$cache_dir","version":"9.9.9"}
    ]
  }
}
EOF

    local exit_code=0
    HOME="$tmpdir" "${HOOKS_DIR}/sync-cache.sh" >/dev/null 2>&1 || exit_code=$?

    # Cache plugin.json should now match source (rsync overwrote stale content)
    local source_plugin_json="${HOOKS_DIR}/../.claude-plugin/plugin.json"
    if [[ $exit_code -eq 0 ]] && cmp -s "$source_plugin_json" "$cache_dir/.claude-plugin/plugin.json"; then
        log_pass
    else
        log_fail "expected sync to test-marketplace cache (exit=$exit_code, files differ)"
    fi

    rm -rf "$tmpdir"
}

# Test 13c: marketplace.json target derives from installPath, not hardcode
test_sync_cache_marketplace_json_target_derives() {
    log_test "sync-cache.sh derives marketplace.json target from installPath"

    local tmpdir cache_dir mkt_cache_dir mkt_cache
    tmpdir=$(mktemp -d) || { log_fail "mktemp failed"; return; }
    cache_dir="$tmpdir/.claude/plugins/cache/derived-mkt/pd/1.0.0"
    mkt_cache_dir="$tmpdir/.claude/plugins/marketplaces/derived-mkt/.claude-plugin"
    mkt_cache="$mkt_cache_dir/marketplace.json"
    mkdir -p "$cache_dir/.claude-plugin"
    mkdir -p "$mkt_cache_dir"

    # Pre-populate target with stale content
    echo '{"stale":true}' > "$mkt_cache"

    cat > "$tmpdir/.claude/plugins/installed_plugins.json" <<EOF
{
  "plugins": {
    "pd@derived-mkt": [
      {"scope":"user","installPath":"$cache_dir","version":"1.0.0"}
    ]
  }
}
EOF

    local exit_code=0
    HOME="$tmpdir" "${HOOKS_DIR}/sync-cache.sh" >/dev/null 2>&1 || exit_code=$?

    local source_mkt="${PROJECT_ROOT}/.claude-plugin/marketplace.json"
    if [[ $exit_code -eq 0 ]] && [[ -f "$source_mkt" ]] && cmp -s "$source_mkt" "$mkt_cache"; then
        log_pass
    else
        log_fail "expected marketplace.json synced to derived-mkt path (exit=$exit_code)"
    fi

    rm -rf "$tmpdir"
}

# Feature 094: pre-release adversarial QA gate anti-drift assertions

test_finish_feature_step_5b_present() {
    log_test "finish-feature.md contains Step 5b QA gate dispatch"
    local file="${PROJECT_ROOT}/plugins/pd/commands/finish-feature.md"
    local fails=0
    grep -qE '^#{2,4}\s.*Step 5b.*Pre-Release Adversarial QA Gate' "$file" || { echo "  AC-14.1 missing Step 5b heading"; ((fails++)); }
    grep -q 'pd:security-reviewer' "$file" || { echo "  AC-14.2 missing pd:security-reviewer"; ((fails++)); }
    grep -q 'pd:code-quality-reviewer' "$file" || { echo "  AC-14.3 missing pd:code-quality-reviewer"; ((fails++)); }
    grep -q 'pd:implementation-reviewer' "$file" || { echo "  AC-14.4 missing pd:implementation-reviewer"; ((fails++)); }
    grep -q 'pd:test-deepener' "$file" || { echo "  AC-14.5 missing pd:test-deepener"; ((fails++)); }
    grep -q 'Step A' "$file" || { echo "  AC-14.6 missing 'Step A' token"; ((fails++)); }
    grep -q '\.qa-gate\.json' "$file" || { echo "  AC-14.7 missing .qa-gate.json reference"; ((fails++)); }
    grep -q '\.qa-gate-low-findings\.md' "$file" || { echo "  AC-14.8 missing .qa-gate-low-findings.md reference"; ((fails++)); }
    grep -q 'dispatch all 4 reviewers in parallel' "$file" || { echo "  AC-3 missing literal parallel-dispatch phrase"; ((fails++)); }
    grep -q 'no spec.md found' "$file" || { echo "  AC-15 missing spec-absent fallback string"; ((fails++)); }
    grep -q 'securitySeverity' "$file" || { echo "  AC-5 missing severity predicate"; ((fails++)); }
    grep -q 'mutation_caught' "$file" || { echo "  AC-5b missing test-deepener narrowed-remap predicate"; ((fails++)); }
    if [[ $fails -eq 0 ]]; then log_pass; else log_fail "$fails assertion(s) failed"; fi
}

test_finish_feature_under_600_lines() {
    log_test "finish-feature.md kept under 600 lines (Step 5b detail extracted)"
    local lines
    lines=$(wc -l < "${PROJECT_ROOT}/plugins/pd/commands/finish-feature.md")
    if [[ $lines -lt 600 ]]; then log_pass; else log_fail "finish-feature.md is $lines lines (>=600)"; fi
}

test_qa_gate_procedure_doc_exists() {
    log_test "qa-gate-procedure.md exists and references key FRs"
    local doc="${PROJECT_ROOT}/docs/dev_guides/qa-gate-procedure.md"
    if [[ ! -f "$doc" ]]; then log_fail "missing $doc"; return; fi
    grep -q 'FR-3\|FR-8\|FR-9' "$doc" || { log_fail "qa-gate-procedure.md missing key FR section markers"; return; }
    log_pass
}

# Feature 113 FR-2: AC-12 evidence helper script must be executable and emit
# exactly 3 '=== ... ===' section headers (host bash, /bin/bash, test-hooks.sh).
# Recursion guard: bash-version-capture.sh invokes test-hooks.sh in its 3rd
# section. Without the env-var sentinel, we'd infinite-loop: test-hooks → cap
# → test-hooks → cap → ... When BASH_VERSION_CAPTURE_RUNNING=1, this test
# skips itself (the outer cap invocation captures the result instead).
test_bash_version_capture_script_emits_three_sections() {
    log_test "bash-version-capture.sh is executable and emits 3 section headers"
    if [[ "${BASH_VERSION_CAPTURE_RUNNING:-0}" == "1" ]]; then
        log_skip "recursion guard (invoked from bash-version-capture.sh)"
        return
    fi
    local script="${PROJECT_ROOT}/plugins/pd/hooks/tests/bash-version-capture.sh"
    if [[ ! -x "$script" ]]; then
        log_fail "bash-version-capture.sh missing or not executable: $script"
        return
    fi
    local out
    out=$("$script" 2>&1 || true)
    local count
    count=$(printf '%s\n' "$out" | grep -c '^=== ' || true)
    if [[ "$count" -eq 3 ]]; then
        log_pass
    else
        log_fail "expected 3 section headers, got $count"
    fi
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
    echo "{\"timestamp\":\"$ts\",\"server\":\"workflow-state\",\"error\":\"python_version\",\"message\":\"Python >= 3.12 required\"}" > "$tmpdir/.claude/pd/mcp-bootstrap-errors.log"

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
    echo '{"timestamp":"2020-01-01T00:00:00Z","server":"workflow-state","error":"python_version","message":"old error"}' > "$tmpdir/.claude/pd/mcp-bootstrap-errors.log"

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


# Test: session-start first-run message appears when .venv missing
test_session_start_first_run_when_venv_missing() {
    log_test "session-start first-run setup message when .venv missing"

    # Create a temp HOME and project without .venv
    local tmpdir
    tmpdir=$(mktemp -d)
    local fake_home
    fake_home=$(mktemp -d)
    mkdir -p "$tmpdir/.git" "$tmpdir/.claude"

    cd "$tmpdir"
    local output
    # Override HOME so the first-run check sees no pd setup; PLUGIN_ROOT is
    # derived from the real hook script location.
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
    test_pre_push_guard_allows_non_push
    test_pre_push_guard_allows_clean_push
    test_pre_push_guard_blocks_broken_meta
    test_sync_cache_json
    test_sync_cache_missing_source
    test_sync_cache_detects_arbitrary_marketplace
    test_sync_cache_marketplace_json_target_derives
    test_finish_feature_step_5b_present
    test_finish_feature_under_600_lines
    test_qa_gate_procedure_doc_exists
    test_bash_version_capture_script_emits_three_sections

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
    echo "--- Feature 042: MCP Bootstrap Python Discovery Tests ---"
    echo ""

    test_check_mcp_health_recent_errors
    test_check_mcp_health_old_entries
    test_check_mcp_health_no_log
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
    echo "--- External Test Scripts (feature 106 FR-2) ---"
    echo ""

    if [[ -x "${SCRIPT_DIR}/test-session-start.sh" ]]; then
        echo "Running test-session-start.sh..."
        "${SCRIPT_DIR}/test-session-start.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    if [[ -x "${SCRIPT_DIR}/test-session-start-broken-pipe.sh" ]]; then
        echo "Running test-session-start-broken-pipe.sh (feature 107)..."
        "${SCRIPT_DIR}/test-session-start-broken-pipe.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    if [[ -x "${SCRIPT_DIR}/check-no-unsafe-writes.sh" ]]; then
        echo "Running check-no-unsafe-writes.sh (feature 107 FR8 guard, negative control)..."
        "${SCRIPT_DIR}/check-no-unsafe-writes.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))
        if [[ -f "${SCRIPT_DIR}/fixture-unsafe-write.sh" ]]; then
            echo "Running check-no-unsafe-writes.sh (feature 107 AC11 positive control)..."
            if "${SCRIPT_DIR}/check-no-unsafe-writes.sh" "${SCRIPT_DIR}/fixture-unsafe-write.sh" >/dev/null 2>&1; then
                echo "  FAIL: FR8 guard did not catch fixture-unsafe-write.sh"
                TESTS_FAILED=$((TESTS_FAILED + 1))
            fi
        fi
    fi
    if [[ -x "${SCRIPT_DIR}/repro-broken-pipe.sh" ]]; then
        echo "Running repro-broken-pipe.sh (feature 107 AC1)..."
        "${SCRIPT_DIR}/repro-broken-pipe.sh" || TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
    if [[ -x "${SCRIPT_DIR}/probe-a1-exit0-under-broken-pipe.sh" ]]; then
        echo "Running probe-a1-exit0-under-broken-pipe.sh (feature 107 AC10)..."
        "${SCRIPT_DIR}/probe-a1-exit0-under-broken-pipe.sh" | dd of=/dev/null bs=1 count=0 2>/dev/null
        if [[ "${PIPESTATUS[0]}" -ne 0 ]]; then
            echo "  FAIL: A1 probe did not exit 0 under closed-stdout"
            TESTS_FAILED=$((TESTS_FAILED + 1))
        fi
    fi

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
