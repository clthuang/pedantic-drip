#!/usr/bin/env bash
# Test: deprecation warning when memory_semantic_enabled=false
# Structural grep-based test — verifies session-start.sh contains the deprecation
# warning in the false branch without sourcing (avoids side effects).
# Run: bash plugins/pd/hooks/tests/test-deprecation-warning.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SESSION_START="${HOOKS_DIR}/session-start.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
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

# --- Test 1: session-start.sh contains deprecation warning string ---
log_test "session-start.sh contains deprecation warning string"
if grep -q '\[DEPRECATED\].*memory_semantic_enabled=false' "$SESSION_START"; then
    log_pass
else
    log_fail "Expected deprecation warning string not found in session-start.sh"
fi

# --- Test 2: deprecation warning is in the false branch (not the else/default branch) ---
# Verify the structure: "= \"false\"" check appears BEFORE the deprecation warning,
# and both are inside build_memory_context()
log_test "deprecation warning is in the semantic_enabled=false branch"
# Extract build_memory_context function body and check ordering
# The variable is $semantic_enabled (read from memory_semantic_enabled config key)
FUNC_BODY=$(sed -n '/^build_memory_context()/,/^[^ ]/p' "$SESSION_START")
if echo "$FUNC_BODY" | grep -q 'semantic_enabled.*==.*"false"'; then
    # Verify the false check comes before the deprecation warning in the function
    FALSE_LINE=$(echo "$FUNC_BODY" | grep -n 'semantic_enabled.*==.*"false"' | head -1 | cut -d: -f1)
    DEPRECATION_LINE=$(echo "$FUNC_BODY" | grep -n '\[DEPRECATED\]' | head -1 | cut -d: -f1)
    if [[ -n "$FALSE_LINE" && -n "$DEPRECATION_LINE" ]] && (( DEPRECATION_LINE > FALSE_LINE )); then
        log_pass
    else
        log_fail "Deprecation warning does not appear after the false check (false:${FALSE_LINE}, deprecation:${DEPRECATION_LINE})"
    fi
else
    log_fail "No semantic_enabled=='false' check found in build_memory_context()"
fi

# --- Test 3: deprecation warning goes to stdout (echo, not >&2) ---
log_test "deprecation warning is output to stdout (not stderr)"
# The deprecation echo line should NOT have >&2 redirection
DEPRECATION_ECHO=$(grep '\[DEPRECATED\].*memory_semantic_enabled' "$SESSION_START" || true)
if [[ -n "$DEPRECATION_ECHO" ]]; then
    if echo "$DEPRECATION_ECHO" | grep -q '>&2'; then
        log_fail "Deprecation warning is sent to stderr (should be stdout per CLAUDE.md hook convention)"
    else
        log_pass
    fi
else
    log_fail "Deprecation echo line not found"
fi

# --- Test 4: semantic injector is in the else (default) branch ---
log_test "semantic injector path is in the else (default) branch"
# After the false branch, the else should contain the semantic injector
if echo "$FUNC_BODY" | grep -A 50 'semantic_enabled.*==.*"false"' | grep -q 'semantic_memory.injector'; then
    log_pass
else
    log_fail "semantic_memory.injector not found in the else branch after the false check"
fi

# --- Test 5: legacy memory.py path is in the false branch ---
log_test "legacy memory.py path is in the false (deprecated) branch"
# The memory.py call should appear between the false check and the else
FALSE_TO_ELSE=$(echo "$FUNC_BODY" | sed -n '/semantic_enabled.*==.*"false"/,/else/p')
if echo "$FALSE_TO_ELSE" | grep -q 'memory\.py'; then
    log_pass
else
    log_fail "memory.py not found in the false branch"
fi

# --- Summary ---
echo ""
echo "================================"
echo "Deprecation Warning Tests: ${TESTS_RUN} run, ${TESTS_PASSED} passed, ${TESTS_FAILED} failed"
echo "================================"

if (( TESTS_FAILED > 0 )); then
    exit 1
fi
exit 0
