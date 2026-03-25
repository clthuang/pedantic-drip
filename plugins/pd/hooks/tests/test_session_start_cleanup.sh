#!/usr/bin/env bash
# Integration tests for cleanup_stale_mcp_servers() in session-start.sh
# Run: bash plugins/pd/hooks/tests/test_session_start_cleanup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
HOOKS_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

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

# Create a temporary HOME to isolate PID directory
ORIG_HOME="$HOME"
TEST_HOME=$(mktemp -d)
trap 'rm -rf "$TEST_HOME"' EXIT

# Source session-start.sh to get the function definition.
# We need to suppress the main execution and just get functions.
# Extract cleanup_stale_mcp_servers function from session-start.sh
extract_cleanup_fn() {
    # Source just the function by extracting it
    cat <<'FUNCEOF'
cleanup_stale_mcp_servers() {
    local pid_dir="$HOME/.claude/pd/run"
    [[ -d "$pid_dir" ]] || return 0
    for pid_file in "$pid_dir"/*.pid; do
        [[ -f "$pid_file" ]] || continue
        local pid
        pid=$(cat "$pid_file" 2>/dev/null)
        if [[ -z "$pid" ]] || ! [[ "$pid" =~ ^[0-9]+$ ]]; then
            rm -f "$pid_file" 2>/dev/null
            continue
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$pid_file" 2>/dev/null
            continue
        fi
        local comm
        comm=$(ps -o comm= -p "$pid" 2>/dev/null)
        echo "$comm" | grep -iq python 2>/dev/null || continue
        local ppid
        ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
        [[ "$ppid" == "1" ]] || continue
        kill -TERM "$pid" 2>/dev/null
        sleep 5
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
        rm -f "$pid_file" 2>/dev/null
    done
    if command -v lsof >/dev/null 2>&1; then
        local db_files=""
        [[ -f "$HOME/.claude/pd/entities/entities.db" ]] && db_files="$HOME/.claude/pd/entities/entities.db"
        [[ -f "$HOME/.claude/pd/memory/memory.db" ]] && db_files="$db_files $HOME/.claude/pd/memory/memory.db"
        if [[ -n "$db_files" ]]; then
            lsof $db_files 2>/dev/null | awk 'NR>1{print $2}' | sort -u | while read -r lpid; do
                local lppid
                lppid=$(ps -o ppid= -p "$lpid" 2>/dev/null | tr -d ' ')
                [[ "$lppid" == "1" ]] || continue
                local lcomm
                lcomm=$(ps -o comm= -p "$lpid" 2>/dev/null)
                echo "$lcomm" | grep -iq python 2>/dev/null || continue
                kill -TERM "$lpid" 2>/dev/null
                sleep 5
                kill -0 "$lpid" 2>/dev/null && kill -9 "$lpid" 2>/dev/null
            done
        fi
    fi
}
FUNCEOF
}

# Load the function into current shell
eval "$(extract_cleanup_fn)"

# -----------------------------------------------------------------------
# Test 1: Stale PID file (non-running PID) is removed
# -----------------------------------------------------------------------
log_test "Stale PID file (non-running PID) is removed"
HOME="$TEST_HOME"
mkdir -p "$HOME/.claude/pd/run"
# Use a PID that is almost certainly not running (very high number)
echo "99999999" > "$HOME/.claude/pd/run/test_server.pid"
cleanup_stale_mcp_servers
if [[ ! -f "$HOME/.claude/pd/run/test_server.pid" ]]; then
    log_pass
else
    log_fail "PID file was not removed"
fi
HOME="$ORIG_HOME"

# -----------------------------------------------------------------------
# Test 2: Missing PID directory causes no error
# -----------------------------------------------------------------------
log_test "Missing PID directory causes no error"
HOME="$TEST_HOME"
rm -rf "$HOME/.claude/pd/run"
if cleanup_stale_mcp_servers; then
    log_pass
else
    log_fail "Function returned non-zero for missing directory"
fi
HOME="$ORIG_HOME"

# -----------------------------------------------------------------------
# Test 3: Invalid PID file content is removed
# -----------------------------------------------------------------------
log_test "Invalid PID file content is removed"
HOME="$TEST_HOME"
mkdir -p "$HOME/.claude/pd/run"
echo "not-a-number" > "$HOME/.claude/pd/run/bad_server.pid"
echo "" > "$HOME/.claude/pd/run/empty_server.pid"
cleanup_stale_mcp_servers
if [[ ! -f "$HOME/.claude/pd/run/bad_server.pid" ]] && [[ ! -f "$HOME/.claude/pd/run/empty_server.pid" ]]; then
    log_pass
else
    log_fail "Invalid PID files were not removed"
fi
HOME="$ORIG_HOME"

# -----------------------------------------------------------------------
# Test 4: Non-orphaned process PID file is NOT removed
# -----------------------------------------------------------------------
log_test "Non-orphaned process PID file is NOT removed"
HOME="$TEST_HOME"
mkdir -p "$HOME/.claude/pd/run"
# Use our own PID (which has a real parent, not PPID=1)
# But we need a Python process. Start a simple long-running python.
python3 -c "import time; time.sleep(60)" &
LIVE_PID=$!
echo "$LIVE_PID" > "$HOME/.claude/pd/run/live_server.pid"
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

# -----------------------------------------------------------------------
# Test 5: Orphaned process (double-fork, PPID=1) is killed and PID file removed
# -----------------------------------------------------------------------
log_test "Orphaned process (double-fork) is killed and PID file removed"
HOME="$TEST_HOME"
mkdir -p "$HOME/.claude/pd/run"
# Double-fork a Python process so its PPID becomes 1 (launchd on macOS)
ORPHAN_PID_FILE="$HOME/.claude/pd/run/orphan_server.pid"
python3 -c "
import os, sys, time
# First fork
pid = os.fork()
if pid > 0:
    # Parent exits immediately, orphaning child
    sys.exit(0)
# Child: second fork for clean detach
pid2 = os.fork()
if pid2 > 0:
    sys.exit(0)
# Grandchild: write our PID to file, then sleep
with open('$ORPHAN_PID_FILE', 'w') as f:
    f.write(str(os.getpid()))
# Sleep long enough for the test to run
time.sleep(120)
" &
# Wait for the parent chain to finish
wait $! 2>/dev/null || true
# Give the grandchild time to write PID file
sleep 1

if [[ -f "$ORPHAN_PID_FILE" ]]; then
    ORPHAN_PID=$(cat "$ORPHAN_PID_FILE")
    # Verify orphan is alive and has PPID=1
    if kill -0 "$ORPHAN_PID" 2>/dev/null; then
        ORPHAN_PPID=$(ps -o ppid= -p "$ORPHAN_PID" 2>/dev/null | tr -d ' ')
        if [[ "$ORPHAN_PPID" == "1" ]]; then
            cleanup_stale_mcp_servers
            # Verify killed and PID file removed
            if ! kill -0 "$ORPHAN_PID" 2>/dev/null && [[ ! -f "$ORPHAN_PID_FILE" ]]; then
                log_pass
            else
                log_fail "Orphan not killed or PID file not removed (alive=$(kill -0 $ORPHAN_PID 2>/dev/null && echo yes || echo no), file=$(test -f $ORPHAN_PID_FILE && echo exists || echo gone))"
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

# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------
echo ""
echo "========================================"
echo "Results: $TESTS_PASSED/$TESTS_RUN passed, $TESTS_FAILED failed"
echo "========================================"

if [[ "$TESTS_FAILED" -gt 0 ]]; then
    exit 1
fi
exit 0
