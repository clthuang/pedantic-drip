#!/usr/bin/env bash
# test-workflow-regression.sh — Behavioral regression tests for workflow phases (feature 078, FR-5 / REQ-4)
#
# Skeleton: sets up a temp dir with a mock feature folder + minimal .meta.json
# and a temp entity DB path for use by later test cases. Tears down the whole
# temp dir on any exit path.
#
# This file currently implements Task 1.1 only: the harness (setup, teardown,
# placeholder test). Real regression test cases (T1.2-T1.4) are added later.
#
# Usage: bash plugins/pd/hooks/tests/test-workflow-regression.sh

set -euo pipefail

# --- Colors / logging helpers ---
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

log_info() {
    echo -e "${YELLOW}  INFO: $1${NC}"
}

# --- Paths ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_ROOT="$(cd "${HOOKS_DIR}/.." && pwd)"

# Mock feature identity — a fake feature outside the real docs/features tree.
MOCK_FEATURE_ID="999"
MOCK_FEATURE_SLUG="mock-feature"
MOCK_FEATURE_DIRNAME="${MOCK_FEATURE_ID}-${MOCK_FEATURE_SLUG}"

# --- Setup ---
# TMPDIR_TEST:   scratch root for the whole test run.
# FEATURES_ROOT: mock `features/` dir housing the mock feature folder.
# MOCK_FEATURE_DIR: the mock feature folder (contains .meta.json).
# ENTITY_DB_PATH:   temp SQLite path for an isolated entity registry DB.
TMPDIR_TEST=$(mktemp -d -t pd-workflow-regression-XXXXXX)
FEATURES_ROOT="${TMPDIR_TEST}/features"
MOCK_FEATURE_DIR="${FEATURES_ROOT}/${MOCK_FEATURE_DIRNAME}"
MOCK_META_JSON="${MOCK_FEATURE_DIR}/.meta.json"
ENTITY_DB_PATH="${TMPDIR_TEST}/entities.db"

cleanup() {
    local exit_code=$?
    # Best-effort teardown: remove the entire temp dir. Never let cleanup fail.
    rm -rf "$TMPDIR_TEST" 2>/dev/null || true
    exit "$exit_code"
}
# Cleans up on normal exit AND on interrupt (Ctrl-C, SIGTERM, etc.).
trap cleanup EXIT INT TERM HUP

setup_mock_feature() {
    log_info "Setting up mock feature at: $MOCK_FEATURE_DIR"
    mkdir -p "$MOCK_FEATURE_DIR"

    # Minimal .meta.json modeled after real feature .meta.json files:
    # id, slug, status=active, lastCompletedPhase=specify. Timestamps are
    # stable strings (tests assert on structure, not exact times).
    cat > "$MOCK_META_JSON" <<EOF
{
  "id": "${MOCK_FEATURE_ID}",
  "slug": "${MOCK_FEATURE_SLUG}",
  "mode": "Standard",
  "status": "active",
  "created": "2026-04-15T00:00:00+00:00",
  "branch": "feature/${MOCK_FEATURE_DIRNAME}",
  "lastCompletedPhase": "specify",
  "phases": {
    "specify": {
      "started": "2026-04-15T00:00:00+00:00",
      "completed": "2026-04-15T00:10:00+00:00",
      "iterations": 1
    }
  }
}
EOF

    log_info "Mock entity DB path (not yet created): $ENTITY_DB_PATH"
}

# --- Tests ---

# Placeholder test: confirms the harness produced the expected mock feature
# artifacts. T1.2+ will add real regression tests against the entity DB,
# complete_phase, and phase transition guards.
test_skeleton_ok() {
    log_test "skeleton: mock feature dir and .meta.json exist; entity DB path is set"

    if [[ ! -d "$MOCK_FEATURE_DIR" ]]; then
        log_fail "mock feature dir missing: $MOCK_FEATURE_DIR"
        return
    fi

    if [[ ! -f "$MOCK_META_JSON" ]]; then
        log_fail ".meta.json missing: $MOCK_META_JSON"
        return
    fi

    # Validate .meta.json is well-formed and carries expected fields.
    if ! python3 -c "
import json, sys
with open('$MOCK_META_JSON') as f:
    meta = json.load(f)
assert meta.get('id') == '${MOCK_FEATURE_ID}', 'id mismatch: %r' % meta.get('id')
assert meta.get('slug') == '${MOCK_FEATURE_SLUG}', 'slug mismatch: %r' % meta.get('slug')
assert meta.get('status') == 'active', 'status mismatch: %r' % meta.get('status')
assert meta.get('lastCompletedPhase') == 'specify', 'lastCompletedPhase mismatch: %r' % meta.get('lastCompletedPhase')
" 2>/dev/null; then
        log_fail ".meta.json content did not match expected schema"
        return
    fi

    if [[ -z "${ENTITY_DB_PATH:-}" ]]; then
        log_fail "ENTITY_DB_PATH not set"
        return
    fi

    log_pass
}

# --- Main ---
main() {
    echo "Running test-workflow-regression.sh (skeleton mode)"
    echo "Temp dir: $TMPDIR_TEST"
    echo

    setup_mock_feature
    test_skeleton_ok

    echo
    echo "Ran: $TESTS_RUN | Passed: $TESTS_PASSED | Failed: $TESTS_FAILED"

    if [[ "$TESTS_FAILED" -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
