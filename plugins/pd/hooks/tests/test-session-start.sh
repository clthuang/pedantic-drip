#!/bin/bash
# Feature 104 FR-6: integration test for session-start.sh
# cleanup_stale_correction_buffers function (AC-6.1).
# Reuses log helper conventions from test-hooks.sh.
set -uo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
HOOKS_DIR=$(dirname "$SCRIPT_DIR")

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

log_test() { TESTS_RUN=$((TESTS_RUN + 1)); echo -e "TEST: $1"; }
log_pass() { TESTS_PASSED=$((TESTS_PASSED + 1)); echo -e "  ${GREEN}PASS${NC}"; }
log_fail() { TESTS_FAILED=$((TESTS_FAILED + 1)); echo -e "  ${RED}FAIL: $1${NC}"; }

# AC-6.1: cleanup_stale_correction_buffers deletes 25h-old, keeps 1h-old
test_cleanup_stale_correction_buffers() {
    log_test "AC-6.1: cleanup_stale_correction_buffers deletes 25h-old, keeps 1h-old"
    local tmp_home
    tmp_home=$(mktemp -d -t pd-test-home.XXXXXX)
    local buffer_dir="$tmp_home/.claude/pd"
    mkdir -p "$buffer_dir"

    # Cross-platform mtime: BSD (macOS) uses date -v, GNU (Linux) uses date -d
    local mtime_old
    if date -v-25H >/dev/null 2>&1; then
        mtime_old=$(date -v-25H +"%Y%m%d%H%M.%S")
    else
        mtime_old=$(date -d '25 hours ago' +"%Y%m%d%H%M.%S")
    fi

    touch -t "$mtime_old" "$buffer_dir/correction-buffer-test-old.jsonl"
    touch "$buffer_dir/correction-buffer-test-fresh.jsonl"

    # Extract cleanup_stale_correction_buffers via sed (do NOT source whole file —
    # session-start.sh runs `main` and exit 0 at end-of-file). Per design TD-1.
    local fn_tmpfile
    fn_tmpfile=$(mktemp -t pd-fn-extract.XXXXXX)
    sed -n '/^cleanup_stale_correction_buffers()/,/^}/p' "${HOOKS_DIR}/session-start.sh" > "$fn_tmpfile"
    # shellcheck disable=SC1090
    HOME="$tmp_home" source "$fn_tmpfile"

    local stderr_capture
    stderr_capture=$(HOME="$tmp_home" cleanup_stale_correction_buffers 2>&1 >/dev/null)
    rm -f "$fn_tmpfile"

    if [[ ! -f "$buffer_dir/correction-buffer-test-old.jsonl" ]] && \
       [[ -f "$buffer_dir/correction-buffer-test-fresh.jsonl" ]] && \
       echo "$stderr_capture" | grep -q "Cleaned 1 stale correction buffers"; then
        log_pass
    else
        local old_status="missing"
        local fresh_status="missing"
        [[ -f "$buffer_dir/correction-buffer-test-old.jsonl" ]] && old_status="present"
        [[ -f "$buffer_dir/correction-buffer-test-fresh.jsonl" ]] && fresh_status="present"
        log_fail "old=$old_status (want missing), fresh=$fresh_status (want present), stderr='$stderr_capture'"
    fi
    rm -rf "$tmp_home"
}

test_cleanup_stale_correction_buffers

echo ""
echo "Results: $TESTS_PASSED/$TESTS_RUN passed (failed: $TESTS_FAILED)"
[[ $TESTS_FAILED -eq 0 ]]
