#!/bin/bash
# Tests for run-memory-server.sh bootstrap wrapper.
# Run: bash plugins/pd/mcp/test_run_memory_server.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WRAPPER="$SCRIPT_DIR/run-memory-server.sh"

PASS=0
FAIL=0

# ---- Setup ----
TMPDIR_BASE=$(mktemp -d)
PASS_FILE="$TMPDIR_BASE/.pass_count"
FAIL_FILE="$TMPDIR_BASE/.fail_count"
echo 0 > "$PASS_FILE"
echo 0 > "$FAIL_FILE"
trap 'rm -rf "$TMPDIR_BASE"' EXIT

pass() { echo "  PASS: $1"; echo $(( $(cat "$PASS_FILE") + 1 )) > "$PASS_FILE"; }
fail() { echo "  FAIL: $1"; echo $(( $(cat "$FAIL_FILE") + 1 )) > "$FAIL_FILE"; }

# ---- Test 1: Venv path used when present ----
echo "Test 1: Uses venv python when .venv exists"
(
    T="$TMPDIR_BASE/t1"
    mkdir -p "$T/plugin/.venv/bin" "$T/plugin/mcp" "$T/plugin/hooks/lib"

    # Create a mock python that records it was called
    cat > "$T/plugin/.venv/bin/python" <<'MOCK'
#!/bin/bash
echo "VENV_PYTHON_CALLED" > "$(dirname "$0")/../../mcp/.test_marker"
exit 0
MOCK
    chmod +x "$T/plugin/.venv/bin/python"

    # Create a minimal server script
    echo '# mock server' > "$T/plugin/mcp/memory_server.py"

    # Copy the wrapper and shared bootstrap library
    cp "$WRAPPER" "$T/plugin/mcp/run-memory-server.sh"
    cp "$SCRIPT_DIR/bootstrap-venv.sh" "$T/plugin/mcp/"
    chmod +x "$T/plugin/mcp/run-memory-server.sh"

    # Run the wrapper (exec is replaced by the mock python)
    cd "$T/plugin/mcp"
    bash run-memory-server.sh 2>/dev/null || true

    if [ -f "$T/plugin/mcp/.test_marker" ] && grep -q "VENV_PYTHON_CALLED" "$T/plugin/mcp/.test_marker"; then
        pass "venv python used"
    else
        fail "venv python NOT used"
    fi
)

# ---- Test 2: PYTHONPATH includes hooks/lib ----
echo "Test 2: PYTHONPATH includes hooks/lib"
(
    T="$TMPDIR_BASE/t2"
    mkdir -p "$T/plugin/.venv/bin" "$T/plugin/mcp" "$T/plugin/hooks/lib"

    # Mock python that dumps PYTHONPATH
    cat > "$T/plugin/.venv/bin/python" <<'MOCK'
#!/bin/bash
echo "$PYTHONPATH" > "$(dirname "$0")/../../mcp/.pythonpath_marker"
exit 0
MOCK
    chmod +x "$T/plugin/.venv/bin/python"

    echo '# mock' > "$T/plugin/mcp/memory_server.py"
    cp "$WRAPPER" "$T/plugin/mcp/run-memory-server.sh"
    cp "$SCRIPT_DIR/bootstrap-venv.sh" "$T/plugin/mcp/"
    chmod +x "$T/plugin/mcp/run-memory-server.sh"

    cd "$T/plugin/mcp"
    bash run-memory-server.sh 2>/dev/null || true

    if [ -f "$T/plugin/mcp/.pythonpath_marker" ] && grep -q "hooks/lib" "$T/plugin/mcp/.pythonpath_marker"; then
        pass "PYTHONPATH contains hooks/lib"
    else
        fail "PYTHONPATH missing hooks/lib"
    fi
)

# ---- Test 3: PYTHONUNBUFFERED=1 is set ----
echo "Test 3: PYTHONUNBUFFERED=1 is set"
(
    T="$TMPDIR_BASE/t3"
    mkdir -p "$T/plugin/.venv/bin" "$T/plugin/mcp" "$T/plugin/hooks/lib"

    cat > "$T/plugin/.venv/bin/python" <<'MOCK'
#!/bin/bash
echo "$PYTHONUNBUFFERED" > "$(dirname "$0")/../../mcp/.unbuf_marker"
exit 0
MOCK
    chmod +x "$T/plugin/.venv/bin/python"

    echo '# mock' > "$T/plugin/mcp/memory_server.py"
    cp "$WRAPPER" "$T/plugin/mcp/run-memory-server.sh"
    cp "$SCRIPT_DIR/bootstrap-venv.sh" "$T/plugin/mcp/"
    chmod +x "$T/plugin/mcp/run-memory-server.sh"

    cd "$T/plugin/mcp"
    bash run-memory-server.sh 2>/dev/null || true

    if [ -f "$T/plugin/mcp/.unbuf_marker" ] && grep -q "1" "$T/plugin/mcp/.unbuf_marker"; then
        pass "PYTHONUNBUFFERED=1 is set"
    else
        fail "PYTHONUNBUFFERED not set correctly"
    fi
)

# ---- Test 4: No stdout before exec ----
echo "Test 4: No stdout before exec (MCP stdio safety)"
(
    T="$TMPDIR_BASE/t4"
    mkdir -p "$T/plugin/.venv/bin" "$T/plugin/mcp" "$T/plugin/hooks/lib"

    cat > "$T/plugin/.venv/bin/python" <<'MOCK'
#!/bin/bash
exit 0
MOCK
    chmod +x "$T/plugin/.venv/bin/python"

    echo '# mock' > "$T/plugin/mcp/memory_server.py"
    cp "$WRAPPER" "$T/plugin/mcp/run-memory-server.sh"
    cp "$SCRIPT_DIR/bootstrap-venv.sh" "$T/plugin/mcp/"
    chmod +x "$T/plugin/mcp/run-memory-server.sh"

    cd "$T/plugin/mcp"
    stdout_output=$(bash run-memory-server.sh 2>/dev/null)

    if [ -z "$stdout_output" ]; then
        pass "no stdout output"
    else
        fail "unexpected stdout: $stdout_output"
    fi
)

# ---- Test 5: Wrapper is executable ----
echo "Test 5: Wrapper script is executable"
if [ -x "$WRAPPER" ]; then
    pass "run-memory-server.sh is executable"
else
    fail "run-memory-server.sh is NOT executable"
fi

# ---- Summary ----
PASS=$(cat "$PASS_FILE")
FAIL=$(cat "$FAIL_FILE")
echo ""
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
