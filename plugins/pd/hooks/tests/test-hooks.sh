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

    cd "${PROJECT_ROOT}/plugins/pd/hooks/lib"
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

# Test 8: pre-commit-guard.sh passes non-commit commands through silently
test_pre_commit_guard_allows_non_commit() {
    log_test "pre-commit-guard.sh passes non-commit commands through silently"

    cd "${PROJECT_ROOT}"
    local output
    output=$(echo '{"tool_name": "Bash", "tool_input": {"command": "git status"}}' | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then  # silent: no decision, so the normal permission flow decides
        log_pass
    else
        log_fail "Should print nothing for git status, got: $output"
    fi
}

# Test 9: pre-commit-guard.sh passes non-git commands through silently
test_pre_commit_guard_allows_non_git() {
    log_test "pre-commit-guard.sh passes non-git commands through silently"

    cd "${PROJECT_ROOT}"
    local output
    output=$(echo '{"tool_name": "Bash", "tool_input": {"command": "ls -la"}}' | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then  # silent: no decision, so the normal permission flow decides
        log_pass
    else
        log_fail "Should print nothing for ls, got: $output"
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
    local rc=0
    output=$(cd "$elsewhere" && echo "{\"tool_name\": \"Bash\", \"tool_input\": {\"command\": \"git -c user.name=t -C $repo commit -m test\"}}" | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null) || rc=$?  # a non-zero guard is a failed assertion, not an aborted suite
    rm -rf "$repo" "$elsewhere"
    [[ $rc -eq 0 ]] || { log_fail "Should exit 0 on a reminder, got $rc"; return; }

    # A reminder for Claude, with no permission decision (an allow would skip the user's prompt).
    if echo "$output" | python3 -c "import json,sys; h=json.load(sys.stdin)['hookSpecificOutput']; assert 'permissionDecision' not in h and h['hookEventName'] == 'PreToolUse' and \"Committing directly to 'main'\" in h['additionalContext']" 2>/dev/null; then
        log_pass
    else
        log_fail "Should remind on commits to main"
    fi
}

# Test 10b: pre-commit-guard.sh reminds about tests on a feature branch when the project has test files
test_pre_commit_guard_reminds_tests() {
    log_test "pre-commit-guard.sh reminds about tests when the project has test files"

    local repo output rc=0
    repo=$(mktemp -d)
    git -C "$repo" init -q -b feature/x
    touch "$repo/test_probe.py"
    output=$(cd "$repo" && echo '{"tool_name": "Bash", "tool_input": {"command": "git commit -m test"}}' | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null) || rc=$?
    rm -rf "$repo"
    [[ $rc -eq 0 ]] || { log_fail "Should exit 0 on a reminder, got $rc"; return; }

    if echo "$output" | python3 -c "import json,sys; h=json.load(sys.stdin)['hookSpecificOutput']; assert 'permissionDecision' not in h and 'Test files exist' in h['additionalContext']" 2>/dev/null; then
        log_pass
    else
        log_fail "Should remind about tests with no permission decision, got: $output"
    fi
}

# Test 10c: pre-commit-guard.sh judges the branch a commit lands on, and only a real commit
test_pre_commit_guard_compound_commands() {
    log_test "pre-commit-guard.sh judges the branch a compound command commits to"

    # A throwaway repo on main with a work item branch.
    local repo
    repo=$(mktemp -d)
    git -C "$repo" init -q -b main
    if ! git -C "$repo" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q --allow-empty --no-verify -m init; then
        log_fail "setup: couldn't commit in a throwaway repo"; rm -rf "$repo"; return
    fi
    git -C "$repo" branch workitem/x
    mkdir "$repo/sub"

    # Each case: the branch checked out, the command, and whether "Committing directly to 'main'" is right.
    # The hook runs from another directory with the repo as stdin's `cwd`, as Claude Code sends it.
    local cases=(
        "main|git checkout -b workitem/y main && git add . && git commit -m t|no"
        "main|git switch -c workitem/z && git commit -m t|no"
        "main|git switch --create=workitem/q && git commit -m t|no"
        "main|grep -n 'git commit' README.md|no"
        "workitem/x|git checkout main && git commit -m t|yes"
        "workitem/x|git checkout main -- README.md && git commit -m t|no"
        "main|git checkout README.md && git commit -m t|yes"
        "main|git checkout HEAD && git commit -m t|yes"
        "main|git checkout - && git commit -m t|no"
        "main|if ! git diff --quiet; then git commit -m t; fi|yes"
        "main|"$'git add .\ngit commit -m t'"|yes"
        "main|"$'git commit -F - <<\'EOF\'\nfix: don\'t break\nEOF'"|yes"
        "main|"$'cat > n.md <<\'EOF\'\nstep; git commit -m x\nEOF'"|no"
        "main|"$'# prepare\ngit commit -m t'"|yes"
        "workitem/x|"$'git status # look\ngit switch main && git commit -m t'"|yes"
        "workitem/x|"$'printf \'%s\\n\' \'<<EOF\'\ngit switch main && git commit -m t'"|yes"
        "workitem/x|"$'cat <<\'EOF-1\'\ndon\'t\nEOF-1\ngit switch main && git commit -m t'"|yes"
        "workitem/x|printf '%s\\n' ';' git switch main ';' git commit|no"
        "workitem/x|git -C sub switch main && git commit -m t|yes"
        "workitem/x|git switch main && git checkout HEAD~0 && git commit -m t|no"
        "main|cd -- sub && git commit -m t|yes"
        "main|(cd /; true); git commit -m t|yes"
        "workitem/x|git checkout main 2>&1 && git commit -m t|yes"
        "workitem/x|"$'git checkout main >/dev/null 2>&1\ngit commit -m t'"|yes"
        "main|"$'echo $((1<<2))\ngit commit -m t'"|yes"
        "main|"$'git commit -m "$(cat <<\'EOF\'\nfix: say "hi, don\'t\nEOF\n)"'"|yes"
    )
    local failures="" case branch rest cmd want got output elsewhere
    elsewhere=$(mktemp -d)
    for case in "${cases[@]}"; do
        branch=${case%%|*} rest=${case#*|}
        cmd=${rest%|*} want=${rest##*|}
        git -C "$repo" checkout -q "$branch"
        output=$(cd "$elsewhere" && python3 -c 'import json,sys; print(json.dumps({"tool_name": "Bash", "tool_input": {"command": sys.argv[1]}, "cwd": sys.argv[2]}))' "$cmd" "$repo" | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null) || true
        if [[ "$output" == *"Committing directly to 'main'"* ]]; then got=yes; else got=no; fi
        [[ "$got" == "$want" ]] || failures+=" [on $branch: ${cmd//$'\n'/⏎} -> reminder $got]"
    done
    rm -rf "$elsewhere"
    rm -rf "$repo"

    if [[ -z "$failures" ]]; then
        log_pass
    else
        log_fail "Wrong main reminder:$failures"
    fi
}

# Test 11: pre-commit-guard.sh works from subdirectory
test_pre_commit_guard_from_subdirectory() {
    log_test "pre-commit-guard.sh works from subdirectory"

    cd "${PROJECT_ROOT}/docs"
    local output
    output=$(echo '{"tool_name": "Bash", "tool_input": {"command": "git status"}}' | "${HOOKS_DIR}/pre-commit-guard.sh" 2>/dev/null)

    if [[ -z "$output" ]]; then  # silent: no decision, so the normal permission flow decides
        log_pass
    else
        log_fail "Should print nothing from a subdirectory, got: $output"
    fi

    cd "${PROJECT_ROOT}"
}

# Feature 094: pre-release adversarial QA gate anti-drift assertions

test_finish_workitem_contract_present() {
    # thin pd: the finish contract lives in the finishing-branch playbook; the command only invokes it.
    log_test "finishing-branch/SKILL.md carries the finish contract essentials"
    local file="${PROJECT_ROOT}/plugins/pd/skills/finishing-branch/SKILL.md"
    local fails=0
    grep -q 'pd:finishing-branch' "${PROJECT_ROOT}/plugins/pd/commands/finish-workitem.md" || { echo "  finish-workitem.md doesn't invoke pd:finishing-branch"; ((fails++)); }
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

test_finish_workitem_under_600_lines() {
    log_test "finish-workitem.md kept under 600 lines (contract command, not procedure)"
    local lines
    lines=$(wc -l < "${PROJECT_ROOT}/plugins/pd/commands/finish-workitem.md")
    if [[ $lines -lt 600 ]]; then log_pass; else log_fail "finish-workitem.md is $lines lines (>=600)"; fi
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
    test_pre_commit_guard_reminds_tests
    test_pre_commit_guard_compound_commands
    test_pre_commit_guard_from_subdirectory
    test_finish_workitem_contract_present
    test_finish_workitem_under_600_lines

    echo ""
    echo "--- Config Helper Tests ---"
    echo ""

    test_read_local_md_field
    test_read_local_md_field_missing

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
