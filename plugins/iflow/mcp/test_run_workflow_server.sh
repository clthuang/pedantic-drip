#!/bin/bash
# Tests for run-workflow-server.sh bootstrap wrapper.
# Run: bash plugins/iflow/mcp/test_run_workflow_server.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WRAPPER="$SCRIPT_DIR/run-workflow-server.sh"

# ---- Setup ----
TMPDIR_BASE=$(mktemp -d)
PASS_FILE="$TMPDIR_BASE/.pass_count"
FAIL_FILE="$TMPDIR_BASE/.fail_count"
echo 0 > "$PASS_FILE"
echo 0 > "$FAIL_FILE"

ENTITY_DB_PATH=$(mktemp /tmp/test-workflow-XXXXXX.db)
export ENTITY_DB_PATH

trap 'rm -rf "$TMPDIR_BASE"; rm -f "$ENTITY_DB_PATH"' EXIT

pass() { echo "  PASS: $1"; echo $(( $(cat "$PASS_FILE") + 1 )) > "$PASS_FILE"; }
fail() { echo "  FAIL: $1"; echo $(( $(cat "$FAIL_FILE") + 1 )) > "$FAIL_FILE"; }

# ---- Test 1: Syntax check ----
echo "Test 1: bash -n syntax check passes"
if bash -n "$WRAPPER" 2>/dev/null; then
    pass "syntax check"
else
    fail "syntax check"
fi

# ---- Test 2: Script is executable ----
echo "Test 2: Wrapper script is executable"
if [[ -x "$WRAPPER" ]]; then
    pass "run-workflow-server.sh is executable"
else
    fail "run-workflow-server.sh is NOT executable"
fi

# ---- Test 3: PYTHONPATH includes hooks/lib ----
echo "Test 3: PYTHONPATH includes hooks/lib"
(
    T="$TMPDIR_BASE/t3"
    mkdir -p "$T/plugin/.venv/bin" "$T/plugin/mcp" "$T/plugin/hooks/lib"

    # Mock python that dumps PYTHONPATH
    cat > "$T/plugin/.venv/bin/python" <<'MOCK'
#!/bin/bash
echo "$PYTHONPATH" > "$(dirname "$0")/../../mcp/.pythonpath_marker"
exit 0
MOCK
    chmod +x "$T/plugin/.venv/bin/python"

    echo '# mock' > "$T/plugin/mcp/workflow_state_server.py"
    cp "$WRAPPER" "$T/plugin/mcp/run-workflow-server.sh"
    chmod +x "$T/plugin/mcp/run-workflow-server.sh"

    cd "$T/plugin/mcp"
    bash run-workflow-server.sh 2>/dev/null || true

    if [ -f "$T/plugin/mcp/.pythonpath_marker" ] && grep -q "hooks/lib" "$T/plugin/mcp/.pythonpath_marker"; then
        pass "PYTHONPATH contains hooks/lib"
    else
        fail "PYTHONPATH missing hooks/lib"
    fi
)

# ---- Test 4: Server process starts without immediate crash ----
echo "Test 4: Server starts without immediate crash"
(
    PID=""
    cleanup() { [[ -n "$PID" ]] && kill "$PID" 2>/dev/null || true; }
    trap cleanup EXIT

    timeout 5 bash "$WRAPPER" >/dev/null 2>&1 &
    PID=$!
    sleep 2

    if kill -0 "$PID" 2>/dev/null; then
        pass "server started and stayed running"
        kill "$PID" 2>/dev/null || true
    else
        wait "$PID" 2>/dev/null || true
        EXIT_CODE=$?
        if [[ $EXIT_CODE -eq 124 ]]; then
            pass "server ran until timeout"
        elif [[ $EXIT_CODE -eq 0 ]]; then
            pass "server started and exited cleanly (stdin closed)"
        else
            fail "server crashed (exit code: $EXIT_CODE)"
        fi
    fi
)

# ---- Test 5: PYTHONUNBUFFERED=1 is set ----
echo "Test 5: PYTHONUNBUFFERED=1 is set"
(
    T="$TMPDIR_BASE/t5"
    mkdir -p "$T/plugin/.venv/bin" "$T/plugin/mcp" "$T/plugin/hooks/lib"

    cat > "$T/plugin/.venv/bin/python" <<'MOCK'
#!/bin/bash
echo "$PYTHONUNBUFFERED" > "$(dirname "$0")/../../mcp/.unbuf_marker"
exit 0
MOCK
    chmod +x "$T/plugin/.venv/bin/python"

    echo '# mock' > "$T/plugin/mcp/workflow_state_server.py"
    cp "$WRAPPER" "$T/plugin/mcp/run-workflow-server.sh"
    chmod +x "$T/plugin/mcp/run-workflow-server.sh"

    cd "$T/plugin/mcp"
    bash run-workflow-server.sh 2>/dev/null || true

    if [ -f "$T/plugin/mcp/.unbuf_marker" ] && grep -q "1" "$T/plugin/mcp/.unbuf_marker"; then
        pass "PYTHONUNBUFFERED=1 is set"
    else
        fail "PYTHONUNBUFFERED not set correctly"
    fi
)

# ---- Test 6: No stdout before exec (MCP stdio safety) ----
echo "Test 6: No stdout before exec"
(
    T="$TMPDIR_BASE/t6"
    mkdir -p "$T/plugin/.venv/bin" "$T/plugin/mcp" "$T/plugin/hooks/lib"

    cat > "$T/plugin/.venv/bin/python" <<'MOCK'
#!/bin/bash
exit 0
MOCK
    chmod +x "$T/plugin/.venv/bin/python"

    echo '# mock' > "$T/plugin/mcp/workflow_state_server.py"
    cp "$WRAPPER" "$T/plugin/mcp/run-workflow-server.sh"
    chmod +x "$T/plugin/mcp/run-workflow-server.sh"

    cd "$T/plugin/mcp"
    stdout_output=$(bash run-workflow-server.sh 2>/dev/null)

    if [ -z "$stdout_output" ]; then
        pass "no stdout output"
    else
        fail "unexpected stdout: $stdout_output"
    fi
)

# ---- Summary ----
PASS=$(cat "$PASS_FILE")
FAIL=$(cat "$FAIL_FILE")
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
