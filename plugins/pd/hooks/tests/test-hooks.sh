#!/usr/bin/env bash
# Hook integration tests
# Run: ./hooks/tests/test-hooks.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Walk up to find repo root (has .git: a directory in a main checkout, a file
# in a linked worktree)
PROJECT_ROOT="$(cd "${HOOKS_DIR}" && while [[ ! -e .git ]] && [[ $PWD != / ]]; do cd ..; done && pwd)"

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

    # A throwaway repo on main, so the test runs whatever branch this checkout is on.
    local repo output
    repo=$(mktemp -d)
    git -C "$repo" init -q -b main
    if ! git -C "$repo" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q --allow-empty --no-verify -m init; then
        log_fail "setup: couldn't commit in a throwaway repo"; rm -rf "$repo"; return
    fi
    # Run from a repo on another branch, so only the -C path can report 'main'.
    local elsewhere
    elsewhere=$(mktemp -d)
    git -C "$elsewhere" init -q -b other
    # -c and -C before the subcommand: both global-option forms must still count as a commit.
    output=$(cd "$elsewhere" && echo "{\"tool_name\": \"Bash\", \"tool_input\": {\"command\": \"git -c user.name=t -C $repo commit -m test\"}}" | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null)
    rm -rf "$repo" "$elsewhere"

    # A reminder, not a block: allow, with a reason only the protected-branch path gives.
    if echo "$output" | python3 -c "import json,sys; h=json.load(sys.stdin)['hookSpecificOutput']; assert h['permissionDecision'] == 'allow' and \"Committing directly to 'main'\" in h['permissionDecisionReason']" 2>/dev/null; then
        log_pass
    else
        log_fail "Should remind on commits to main"
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

# Feature 094: pre-release adversarial QA gate anti-drift assertions

test_finish_feature_contract_present() {
    # thin pd: the finish contract lives in the finishing-branch playbook; the command only invokes it.
    log_test "finishing-branch/SKILL.md carries the finish contract essentials"
    local file="${PROJECT_ROOT}/plugins/pd/skills/finishing-branch/SKILL.md"
    local fails=0
    grep -q 'pd:finishing-branch' "${PROJECT_ROOT}/plugins/pd/commands/finish-feature.md" || { echo "  finish-feature.md doesn't invoke pd:finishing-branch"; ((fails++)); }
    grep -q 'pd:security-reviewer' "$file" || { echo "  missing pd:security-reviewer dispatch (security surface)"; ((fails++)); }
    grep -q 'phase-gate.sh finish' "$file" || { echo "  missing mechanical finish gate"; ((fails++)); }
    grep -q 'retrospecting' "$file" || { echo "  missing retrospecting skill reference"; ((fails++)); }
    grep -q '{pd_base_branch}' "$file" || { echo "  missing {pd_base_branch} merge target"; ((fails++)); }
    grep -q 'retro runs before cleanup' "$file" || { echo "  missing retro-before-cleanup ordering"; ((fails++)); }
    # Retired machinery must NOT come back:
    grep -q 'pd:implementation-reviewer' "$file" && { echo "  retired implementation-reviewer reference present"; ((fails++)); }
    grep -q '\.qa-gate\.json' "$file" && { echo "  retired .qa-gate.json reference present"; ((fails++)); }
    if [[ $fails -eq 0 ]]; then log_pass; else log_fail "$fails assertion(s) failed"; fi
}

test_finish_feature_under_600_lines() {
    log_test "finish-feature.md kept under 600 lines (contract command, not procedure)"
    local lines
    lines=$(wc -l < "${PROJECT_ROOT}/plugins/pd/commands/finish-feature.md")
    if [[ $lines -lt 600 ]]; then log_pass; else log_fail "finish-feature.md is $lines lines (>=600)"; fi
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

# === Config Helper Tests ===

# Helper: create a temp project
setup_temp_project() {
    TEMP_PROJECT_DIR=$(mktemp -d)
    mkdir -p "${TEMP_PROJECT_DIR}/.claude"
    mkdir -p "${TEMP_PROJECT_DIR}/docs/features"
    mkdir -p "${TEMP_PROJECT_DIR}/.git"
}

teardown_temp_project() {
    rm -rf "$TEMP_PROJECT_DIR"
    cd "${PROJECT_ROOT}"
}

# Test: read_local_md_field reads existing value
test_read_local_md_field() {
    log_test "read_local_md_field reads existing value"

    source "${HOOKS_DIR}/lib/common.sh"
    setup_temp_project

    cat > "${TEMP_PROJECT_DIR}/.claude/pd.local.md" << 'TMPL'
---
base_branch: develop
artifacts_root: docs
---
TMPL

    local val
    val=$(read_local_md_field "${TEMP_PROJECT_DIR}/.claude/pd.local.md" "base_branch" "main")
    if [[ "$val" == "develop" ]]; then
        log_pass
    else
        log_fail "Expected 'develop', got '$val'"
    fi

    teardown_temp_project
}

# Test: read_local_md_field returns default for missing file
test_read_local_md_field_missing() {
    log_test "read_local_md_field returns default for missing file"

    source "${HOOKS_DIR}/lib/common.sh"

    local val
    val=$(read_local_md_field "/nonexistent/file.md" "base_branch" "main")
    if [[ "$val" == "main" ]]; then
        log_pass
    else
        log_fail "Expected 'main', got '$val'"
    fi
}

# Test: read/write_hook_state round-trip
test_hook_state_roundtrip() {
    log_test "read/write_hook_state round-trip"

    source "${HOOKS_DIR}/lib/common.sh"
    setup_temp_project

    local state_file="${TEMP_PROJECT_DIR}/.claude/.hook-state"

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

    teardown_temp_project
}

# === Robustness Tests ===

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

# Test: cleanup-stale-versions keeps a version a live session runs from
test_cleanup_keeps_versions_in_use() {
    log_test "cleanup-stale-versions removes stale versions but keeps one marked in use by a live process"

    local tmpdir cache dead_pid
    tmpdir=$(mktemp -d) || { log_fail "mktemp failed"; return; }
    cache="$tmpdir/.claude/plugins/cache/pedantic-drip-marketplace/pd"
    mkdir -p "$cache/7.0.0/.in_use" "$cache/7.0.1" "$cache/7.0.2/.in_use" "$cache/7.0.3"
    sleep 0 & dead_pid=$!; wait "$dead_pid" || true
    echo '{}' > "$cache/7.0.0/.in_use/$dead_pid"
    echo '{}' > "$cache/7.0.2/.in_use/$$"
    echo '{"plugins":{"pd@pedantic-drip-marketplace":[{"version":"7.0.3"}]}}' \
        > "$tmpdir/.claude/plugins/installed_plugins.json"

    HOME="$tmpdir" bash "${HOOKS_DIR}/cleanup-stale-versions.sh" 2>/dev/null || true

    local left
    left=$(cd "$cache" && ls | tr '\n' ' ')
    if [[ "$left" == "7.0.2 7.0.3 " ]]; then
        log_pass
    else
        log_fail "expected '7.0.2 7.0.3 ' left, got '$left'"
    fi
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
    log_test "No hardcoded plugins/pd/ in command .md files (non-fallback)"

    local violations
    violations=$(_count_hardcoded_paths "${PLUGIN_COMP_DIR}/commands" "*.md")

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
    test_pre_commit_guard_allows_non_commit
    test_pre_commit_guard_allows_non_git
    test_pre_commit_guard_warns_main
    test_pre_commit_guard_from_subdirectory
    test_finish_feature_contract_present
    test_finish_feature_under_600_lines
    test_bash_version_capture_script_emits_three_sections

    echo ""
    echo "--- Config Helper Tests ---"
    echo ""

    test_read_local_md_field
    test_read_local_md_field_missing
    test_hook_state_roundtrip

    echo ""
    echo "--- Robustness Tests ---"
    echo ""

    test_err_trap_produces_json
    test_cleanup_keeps_versions_in_use

    echo ""
    echo "--- Path Portability Tests ---"
    echo ""

    test_no_hardcoded_plugin_paths_in_agents
    test_no_hardcoded_plugin_paths_in_skills
    test_no_hardcoded_plugin_paths_in_commands
    test_no_at_includes_with_hardcoded_paths
    test_advisors_use_base_directory_derivation

    echo ""
    echo "--- External Test Scripts (feature 106 FR-2) ---"
    echo ""

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
