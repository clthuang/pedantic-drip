#!/bin/bash
# Feature 104 FR-6: cleanup_stale_correction_buffers (AC-6.1).
# Feature 106 FR-3: cleanup_stale_mcp_servers (5 tests, consolidated from
# test_session_start_cleanup.sh; sed-extract pattern per feature 104 TD-1).
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

ORIG_HOME="$HOME"
TEST_HOME=$(mktemp -d)
trap 'rm -rf "$TEST_HOME"' EXIT

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

# Helper: sed-extract cleanup_stale_mcp_servers from session-start.sh
# (replaces the copy-paste extraction from test_session_start_cleanup.sh)
extract_mcp_cleanup_fn() {
    local fn_tmpfile
    fn_tmpfile=$(mktemp -t pd-fn-extract.XXXXXX)
    sed -n '/^cleanup_stale_mcp_servers()/,/^}/p' "${HOOKS_DIR}/session-start.sh" > "$fn_tmpfile"
    # shellcheck disable=SC1090
    source "$fn_tmpfile"
    rm -f "$fn_tmpfile"
}

# FR-3 Test 1: Stale PID file (non-running PID) is removed
test_stale_pid_file_removed() {
    log_test "Stale PID file (non-running PID) is removed"
    HOME="$TEST_HOME"
    mkdir -p "$HOME/.claude/pd/run"
    echo "99999999" > "$HOME/.claude/pd/run/test_server.pid"
    extract_mcp_cleanup_fn
    cleanup_stale_mcp_servers
    if [[ ! -f "$HOME/.claude/pd/run/test_server.pid" ]]; then
        log_pass
    else
        log_fail "PID file was not removed"
    fi
    HOME="$ORIG_HOME"
}

# FR-3 Test 2: Missing PID directory causes no error
test_missing_pid_dir() {
    log_test "Missing PID directory causes no error"
    HOME="$TEST_HOME"
    rm -rf "$HOME/.claude/pd/run"
    extract_mcp_cleanup_fn
    if cleanup_stale_mcp_servers; then
        log_pass
    else
        log_fail "Function returned non-zero for missing directory"
    fi
    HOME="$ORIG_HOME"
}

# FR-3 Test 3: Invalid PID file content is removed
test_invalid_pid_content() {
    log_test "Invalid PID file content is removed"
    HOME="$TEST_HOME"
    mkdir -p "$HOME/.claude/pd/run"
    echo "not-a-number" > "$HOME/.claude/pd/run/bad_server.pid"
    echo "" > "$HOME/.claude/pd/run/empty_server.pid"
    extract_mcp_cleanup_fn
    cleanup_stale_mcp_servers
    if [[ ! -f "$HOME/.claude/pd/run/bad_server.pid" ]] && [[ ! -f "$HOME/.claude/pd/run/empty_server.pid" ]]; then
        log_pass
    else
        log_fail "Invalid PID files were not removed"
    fi
    HOME="$ORIG_HOME"
}

# FR-3 Test 4: Non-orphaned process PID file is NOT removed
test_non_orphaned_process() {
    log_test "Non-orphaned process PID file is NOT removed"
    HOME="$TEST_HOME"
    mkdir -p "$HOME/.claude/pd/run"
    python3 -c "import time; time.sleep(60)" &
    local LIVE_PID=$!
    echo "$LIVE_PID" > "$HOME/.claude/pd/run/live_server.pid"
    extract_mcp_cleanup_fn
    cleanup_stale_mcp_servers
    if [[ -f "$HOME/.claude/pd/run/live_server.pid" ]]; then
        log_pass
    else
        log_fail "PID file for non-orphaned process was removed"
    fi
    kill "$LIVE_PID" 2>/dev/null || true
    wait "$LIVE_PID" 2>/dev/null || true
    rm -f "$HOME/.claude/pd/run/live_server.pid"
    HOME="$ORIG_HOME"
}

# FR-3 Test 5: Orphaned process (double-fork, PPID=1) is killed and PID file removed
test_orphan_double_fork() {
    log_test "Orphaned process (double-fork) is killed and PID file removed"
    HOME="$TEST_HOME"
    mkdir -p "$HOME/.claude/pd/run"
    local ORPHAN_PID_FILE="$HOME/.claude/pd/run/orphan_server.pid"
    python3 -c "
import os, sys, time
pid = os.fork()
if pid > 0:
    sys.exit(0)
pid2 = os.fork()
if pid2 > 0:
    sys.exit(0)
with open('$ORPHAN_PID_FILE', 'w') as f:
    f.write(str(os.getpid()))
time.sleep(120)
" &
    wait $! 2>/dev/null || true
    sleep 1

    if [[ -f "$ORPHAN_PID_FILE" ]]; then
        local ORPHAN_PID
        ORPHAN_PID=$(cat "$ORPHAN_PID_FILE")
        if kill -0 "$ORPHAN_PID" 2>/dev/null; then
            local ORPHAN_PPID
            ORPHAN_PPID=$(ps -o ppid= -p "$ORPHAN_PID" 2>/dev/null | tr -d ' ')
            if [[ "$ORPHAN_PPID" == "1" ]]; then
                extract_mcp_cleanup_fn
                cleanup_stale_mcp_servers
                if ! kill -0 "$ORPHAN_PID" 2>/dev/null && [[ ! -f "$ORPHAN_PID_FILE" ]]; then
                    log_pass
                else
                    log_fail "Orphan not killed or PID file not removed"
                    kill -9 "$ORPHAN_PID" 2>/dev/null || true
                fi
            else
                log_fail "Double-fork did not produce PPID=1 (got PPID=$ORPHAN_PPID)"
                kill -9 "$ORPHAN_PID" 2>/dev/null || true
            fi
        else
            log_fail "Orphan process not running after double-fork"
        fi
    else
        log_fail "Orphan PID file was not created"
    fi
    HOME="$ORIG_HOME"
}

# Run all 6 tests
test_cleanup_stale_correction_buffers
test_stale_pid_file_removed
test_missing_pid_dir
test_invalid_pid_content
test_non_orphaned_process
test_orphan_double_fork

echo ""
echo "Results: $TESTS_PASSED/$TESTS_RUN passed (failed: $TESTS_FAILED)"
[[ $TESTS_FAILED -eq 0 ]]
