#!/usr/bin/env bash
# Hook integration tests for plugins/pd/hooks/data-file-guard.sh (feature 110).
#
# Run: bash plugins/pd/hooks/tests/test-data-file-guard.sh
#
# Covers FR-7 (generalized data-file guard) acceptance criteria:
#   AC-7.2 — hooks.json registration consistency
#   AC-7.3 — .meta.json Write/Edit deny path
#   AC-7.4 — docs/backlog.md Write deny path
#   AC-7.5 — Hot-add new pattern via env overrides (config-driven)
#   AC-7.6 — meta-json-guard.sh absent from tree
#   AC-7.7 — docs/projects/*/.meta.json exclude_patterns
#   AC-7.8 — venv-load failure fail-open (allow + exit 0)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${HOOKS_DIR}" && while [[ ! -d .git ]] && [[ $PWD != / ]]; do cd ..; done && pwd)"

GUARD_SCRIPT="${HOOKS_DIR}/data-file-guard.sh"
HOOKS_JSON="${HOOKS_DIR}/hooks.json"
LEGACY_GUARD="${HOOKS_DIR}/meta-json-guard.sh"
FIXTURE_DIR="${SCRIPT_DIR}/fixtures"

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

# Pick a Python interpreter for assertion parsing inside the test harness.
# Prefer the plugin venv (cache or dev workspace) so we run the same Python
# the dispatcher uses; fall back to the system python3.
assert_py() {
    local cached
    cached=$(ls -d "$HOME"/.claude/plugins/cache/*/pd*/*/.venv/bin/python 2>/dev/null | head -1) || true
    if [[ -n "${cached:-}" ]] && [[ -x "$cached" ]]; then
        echo "$cached"
        return 0
    fi
    if [[ -x "${HOOKS_DIR}/../.venv/bin/python" ]]; then
        echo "${HOOKS_DIR}/../.venv/bin/python"
        return 0
    fi
    command -v python3
}

PY=$(assert_py)

# ---------------------------------------------------------------------------
# Migrated tests (from former plugins/pd/hooks/tests/test-hooks.sh meta-json
# guard suite). Each maps to a feature-110 AC.
# ---------------------------------------------------------------------------

# AC-7.3 — Write to a feature-type .meta.json is denied with the
# `complete_phase / transition_phase` MCP-tool hint.
test_data_file_guard_denies_write_meta() {
    log_test "data-file-guard denies Write to feature .meta.json (AC-7.3)"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/043-foo/.meta.json","content":"{}"}}' \
        | bash "$GUARD_SCRIPT" 2>/dev/null) || true

    if echo "$output" | "$PY" -c "
import json, sys
d = json.load(sys.stdin)
hso = d.get('hookSpecificOutput', {})
assert hso.get('permissionDecision') == 'deny', 'expected deny, got: ' + repr(hso)
reason = hso.get('permissionDecisionReason', '')
assert 'complete_phase' in reason and 'transition_phase' in reason, 'reason missing MCP hint: ' + reason
" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny with complete_phase / transition_phase hint, got: $output"
    fi
}

# AC-7.3 — Edit on a feature-type .meta.json is also denied (parity with Write).
test_data_file_guard_denies_edit_meta() {
    log_test "data-file-guard denies Edit to feature .meta.json (AC-7.3)"

    local output
    output=$(echo '{"tool_name":"Edit","tool_input":{"file_path":"docs/features/043-foo/.meta.json","old_string":"planned","new_string":"active"}}' \
        | bash "$GUARD_SCRIPT" 2>/dev/null) || true

    if echo "$output" | "$PY" -c "
import json, sys
d = json.load(sys.stdin)
hso = d.get('hookSpecificOutput', {})
assert hso.get('permissionDecision') == 'deny', 'expected deny, got: ' + repr(hso)
reason = hso.get('permissionDecisionReason', '')
assert 'complete_phase' in reason and 'transition_phase' in reason, 'reason missing MCP hint: ' + reason
" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected deny for Edit on .meta.json, got: $output"
    fi
}

# AC-7.7 — INVERTED from legacy behavior: project-type .meta.json paths are
# excluded via exclude_patterns and must NOT be denied.
test_data_file_guard_allows_project_meta() {
    log_test "data-file-guard allows Write to docs/projects/*/.meta.json (AC-7.7)"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/projects/P003/.meta.json","content":"{}"}}' \
        | bash "$GUARD_SCRIPT" 2>/dev/null) || true

    # Either `{}` (allow short-circuit) or no `permissionDecision: deny` is acceptable.
    if echo "$output" | "$PY" -c "
import json, sys
raw = sys.stdin.read().strip()
if not raw or raw == '{}':
    sys.exit(0)
d = json.loads(raw)
hso = d.get('hookSpecificOutput', {})
assert hso.get('permissionDecision') != 'deny', 'unexpected deny on project meta: ' + repr(hso)
" 2>/dev/null; then
        log_pass
    else
        log_fail "Project .meta.json should be allowed, got: $output"
    fi
}

# Sanity: non-data-file paths get the fast-path allow.
test_data_file_guard_allows_non_meta() {
    log_test "data-file-guard allows Write to non-data-file path"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/features/034-foo/spec.md","content":"# Spec"}}' \
        | bash "$GUARD_SCRIPT" 2>/dev/null) || true

    # Expect either empty {} or no deny field.
    if [[ "$(echo "$output" | tr -d '[:space:]')" == '{}' ]]; then
        log_pass
        return
    fi
    if echo "$output" | "$PY" -c "
import json, sys
d = json.load(sys.stdin)
hso = d.get('hookSpecificOutput', {})
assert hso.get('permissionDecision') != 'deny', 'unexpected deny: ' + repr(hso)
" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected allow for spec.md write, got: $output"
    fi
}

# ---------------------------------------------------------------------------
# New tests (feature 110)
# ---------------------------------------------------------------------------

# AC-7.4 — docs/backlog.md writes are denied with the add-to-backlog hint.
test_data_file_guard_denies_write_backlog() {
    log_test "data-file-guard denies Write to docs/backlog.md (AC-7.4)"

    local output
    output=$(echo '{"tool_name":"Write","tool_input":{"file_path":"docs/backlog.md","content":"- [ ] something"}}' \
        | bash "$GUARD_SCRIPT" 2>/dev/null) || true

    if echo "$output" | "$PY" -c "
import json, sys
d = json.load(sys.stdin)
hso = d.get('hookSpecificOutput', {})
assert hso.get('permissionDecision') == 'deny', 'expected deny, got: ' + repr(hso)
reason = hso.get('permissionDecisionReason', '')
assert ('/pd:add-to-backlog' in reason) or ('update via DB then re-project' in reason), 'reason missing backlog hint: ' + reason
" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected backlog deny with /pd:add-to-backlog hint, got: $output"
    fi
}

# AC-7.5 — Hot-add: a fixture pattern + decision module wired in solely via
# env vars must drive the dispatch with NO modification to data-file-guard.sh.
test_data_file_guard_hot_add_via_env_overrides() {
    log_test "data-file-guard supports hot-add via env overrides (AC-7.5)"

    # Snapshot the guard script's SHA to confirm it isn't mutated.
    local pre_sha
    pre_sha=$("$PY" -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$GUARD_SCRIPT")

    # Stage a config pointing at the fixture decision module (allow stub).
    # Use a tempdir-scoped config so the fixture file is never mutated
    # (byte-preservation is part of the AC: data-file-guard.sh hash must be
    # unchanged, and we extend that contract to any tracked fixture too).
    local tmp_cfg_dir
    tmp_cfg_dir=$(mktemp -d)
    local config_path="${tmp_cfg_dir}/test_data_file_guards.json"

    cat > "$config_path" <<'CFG'
[
  {
    "pattern": "test_fixture.md",
    "decision_module": "fixture_decision",
    "mcp_tool_hint": "test"
  }
]
CFG

    local output
    output=$(PD_DATA_FILE_GUARDS_CONFIG="$config_path" \
             PD_DATA_FILE_GUARDS_LIB="$FIXTURE_DIR" \
             bash "$GUARD_SCRIPT" \
        <<< '{"tool_name":"Write","tool_input":{"file_path":"test_fixture.md","content":"x"}}' 2>/dev/null) || true

    # Clean up the tempdir-scoped config (fixture file in tree never touched).
    rm -rf "$tmp_cfg_dir"

    # Verify guard script unchanged.
    local post_sha
    post_sha=$("$PY" -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$GUARD_SCRIPT")

    if [[ "$pre_sha" != "$post_sha" ]]; then
        log_fail "data-file-guard.sh hash changed during test: $pre_sha -> $post_sha"
        return
    fi

    # Fixture decision returns allow. Accept either {} (the dispatcher's
    # default short-circuit OR an explicit "allow" decision wrapping).
    if echo "$output" | "$PY" -c "
import json, sys
raw = sys.stdin.read().strip()
if not raw or raw == '{}':
    sys.exit(0)
d = json.loads(raw)
hso = d.get('hookSpecificOutput', {})
assert hso.get('permissionDecision') == 'allow', 'expected allow, got: ' + repr(hso)
" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected allow from fixture_decision via env overrides, got: $output"
    fi
}

# AC-7.8 — venv-load failure fail-open: when no python is reachable, the hook
# MUST emit `{}` (allow) and exit 0 — never block writes.
test_data_file_guard_venv_fallback_fail_open() {
    log_test "data-file-guard exits 0 with allow when venv unreachable (AC-7.8)"

    # Clear PATH and HOME so neither the cached venv glob nor any python3
    # fallback resolves. We still let the script's own SCRIPT_DIR helpers
    # source (they're path-anchored, not PATH-anchored).
    local fake_home
    fake_home=$(mktemp -d)
    local output
    local exit_code
    output=$(PATH= HOME="$fake_home" bash "$GUARD_SCRIPT" \
        <<< '{"tool_name":"Write","tool_input":{"file_path":"docs/features/043-foo/.meta.json","content":"{}"}}' 2>/dev/null) || true
    exit_code=$?

    rm -rf "$fake_home"

    if [[ $exit_code -ne 0 ]]; then
        log_fail "Expected exit 0 under venv-load failure, got exit $exit_code (output: $output)"
        return
    fi

    # Output must NOT carry a deny.
    if [[ -z "$output" ]] || [[ "$(echo "$output" | tr -d '[:space:]')" == '{}' ]]; then
        log_pass
        return
    fi
    if echo "$output" | "$PY" -c "
import json, sys
d = json.loads(sys.stdin.read())
hso = d.get('hookSpecificOutput', {})
assert hso.get('permissionDecision') != 'deny', 'unexpected deny in fail-open path: ' + repr(hso)
" 2>/dev/null; then
        log_pass
    else
        log_fail "Expected fail-open allow, got: $output"
    fi
}

# Task 10.6 — AC-7.2 + AC-7.6: hooks.json registration consistency and
# meta-json-guard.sh absence.
test_hooks_json_registration() {
    log_test "hooks.json registers data-file-guard.sh exactly once; meta-json-guard.sh absent (AC-7.2, AC-7.6)"

    local dfg_count mjg_count
    dfg_count=$(grep -c 'data-file-guard.sh' "$HOOKS_JSON" || true)
    mjg_count=$(grep -c 'meta-json-guard.sh' "$HOOKS_JSON" || true)

    if [[ "$dfg_count" -ne 1 ]]; then
        log_fail "Expected data-file-guard.sh count 1 in hooks.json, got $dfg_count"
        return
    fi
    if [[ "$mjg_count" -ne 0 ]]; then
        log_fail "Expected meta-json-guard.sh count 0 in hooks.json, got $mjg_count"
        return
    fi
    if [[ -f "$LEGACY_GUARD" ]]; then
        log_fail "Legacy meta-json-guard.sh must not exist in tree: $LEGACY_GUARD"
        return
    fi
    log_pass
}

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

main() {
    echo "=========================================="
    echo "data-file-guard.sh Integration Tests"
    echo "=========================================="
    echo ""

    test_data_file_guard_denies_write_meta
    test_data_file_guard_denies_edit_meta
    test_data_file_guard_allows_project_meta
    test_data_file_guard_allows_non_meta
    test_data_file_guard_denies_write_backlog
    test_data_file_guard_hot_add_via_env_overrides
    test_data_file_guard_venv_fallback_fail_open
    test_hooks_json_registration

    echo ""
    echo "=========================================="
    echo "Results: $TESTS_RUN run, $TESTS_PASSED passed, $TESTS_FAILED failed, $TESTS_SKIPPED skipped"
    echo "=========================================="

    if [[ $TESTS_FAILED -gt 0 ]]; then
        return 1
    fi
    return 0
}

main
