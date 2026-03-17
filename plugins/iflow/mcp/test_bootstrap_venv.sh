#!/bin/bash
# Unit and integration tests for bootstrap-venv.sh. Expected runtime: ~2-5 minutes (integration tests create real venvs).
#
# Note: top-level uses set -uo (no -e) so subshell failures do not abort the
# entire script. Each test subshell is invoked with `|| true` to ensure all
# sections execute even in RED state.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# --- Test counters and helpers ---
# Written to files so subshell increments are visible to the parent.
PASS_FILE="$TMP_DIR/.pass_count"
FAIL_FILE="$TMP_DIR/.fail_count"
echo 0 > "$PASS_FILE"
echo 0 > "$FAIL_FILE"

pass() {
    local count
    count=$(cat "$PASS_FILE")
    echo $((count + 1)) > "$PASS_FILE"
    echo "  PASS: $1"
}

fail() {
    local count
    count=$(cat "$FAIL_FILE")
    echo $((count + 1)) > "$FAIL_FILE"
    echo "  FAIL: $1"
}

assert_eq() {
    local expected="$1"
    local actual="$2"
    local msg="$3"
    if [[ "$expected" == "$actual" ]]; then
        pass "$msg"
    else
        fail "$msg (expected='$expected', actual='$actual')"
    fi
}

assert_contains() {
    local haystack="$1"
    local needle="$2"
    local msg="$3"
    if [[ "$haystack" == *"$needle"* ]]; then
        pass "$msg"
    else
        fail "$msg (output does not contain '$needle')"
    fi
}

assert_exit_code() {
    local expected="$1"
    local actual="$2"
    local msg="$3"
    if [[ "$expected" == "$actual" ]]; then
        pass "$msg"
    else
        fail "$msg (expected exit code $expected, got $actual)"
    fi
}

# ============================================================================
# Task 1.1b: check_python_version unit test
# ============================================================================
echo ""
echo "=== Task 1.1b: check_python_version ==="

(
    # Resolve real python3 path BEFORE creating mock
    REAL_PYTHON3="$(command -v python3)"

    MOCK_DIR="$TMP_DIR/mock_python"
    mkdir -p "$MOCK_DIR"
    STDERR_FILE="$TMP_DIR/check_python_version_stderr.txt"

    # Create argument-aware mock python3 that returns 3.10 for the version check
    # invocation (matching design I2), and delegates everything else to real python3
    cat > "$MOCK_DIR/python3" << MOCK_EOF
#!/bin/bash
# Mock python3: returns 3.10 for version check, delegates otherwise
for arg in "\$@"; do
    if [[ "\$arg" == *"sys.version_info"* ]]; then
        echo "3.10"
        exit 0
    fi
done
exec "$REAL_PYTHON3" "\$@"
MOCK_EOF
    chmod +x "$MOCK_DIR/python3"

    # Source bootstrap-venv.sh to get function definitions
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    # Call check_python_version with mock python3 on PATH
    exit_code=0
    (PATH="$MOCK_DIR:$PATH"; check_python_version) 2>"$STDERR_FILE" || exit_code=$?

    stderr_output=$(cat "$STDERR_FILE")

    assert_exit_code 1 "$exit_code" "check_python_version exits 1 for Python 3.10"
    assert_contains "$stderr_output" "3.12" "stderr mentions required version 3.12"
    assert_contains "$stderr_output" "3.10" "stderr mentions detected version 3.10"
) || true

# ============================================================================
# Task 1.1c: check_venv_deps unit tests
# NOTE: Intentionally slow (~30-60s) -- creates a real venv and installs 8 deps.
# The venv is reused for both sub-tests (all-present and missing) to avoid
# double creation time.
# ============================================================================
echo ""
echo "=== Task 1.1c: check_venv_deps ==="

(
    VENV_PATH="$TMP_DIR/test_venv"

    # Source bootstrap-venv.sh to get function definitions and DEP arrays
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    # Create a real venv and install all 8 canonical deps
    echo "  (creating venv and installing deps -- this takes ~30-60s)..."
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install -q \
        "fastapi" "jinja2" "mcp" "numpy" \
        "pydantic" "pydantic-settings" "python-dotenv" "uvicorn" \
        2>&1 | tail -1 || true

    # Sub-test 1: all deps present -> should return 0
    exit_code=0
    check_venv_deps "$VENV_PATH/bin/python" || exit_code=$?
    assert_exit_code 0 "$exit_code" "check_venv_deps returns 0 when all deps present"

    # Sub-test 2: remove numpy -> should return 1
    "$VENV_PATH/bin/pip" uninstall -y numpy >/dev/null 2>&1 || true
    exit_code=0
    check_venv_deps "$VENV_PATH/bin/python" || exit_code=$?
    assert_exit_code 1 "$exit_code" "check_venv_deps returns 1 when numpy missing"
) || true

# ============================================================================
# Task 1.1d: Dep array alignment test
# ============================================================================
echo ""
echo "=== Task 1.1d: dep array alignment with pyproject.toml ==="

(
    PYPROJECT="$SCRIPT_DIR/../pyproject.toml"

    # Source bootstrap-venv.sh to get DEP_PIP_NAMES array
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    # Parse pyproject.toml [project].dependencies entries
    # Extract base package names (before any version specifier)
    pyproject_deps=()
    in_deps=0
    while IFS= read -r line; do
        if [[ "$line" == "dependencies = ["* ]]; then
            in_deps=1
            continue
        fi
        if [[ "$in_deps" == 1 ]]; then
            if [[ "$line" == "]"* ]]; then
                break
            fi
            # Extract package name: strip quotes, whitespace, version specifiers
            dep=$(echo "$line" | sed 's/^[[:space:]]*"//; s/[><=!].*//' | sed 's/".*//; s/,$//' | tr -d '[:space:]')
            if [[ -n "$dep" ]]; then
                pyproject_deps+=("$dep")
            fi
        fi
    done < "$PYPROJECT"

    pyproject_count="${#pyproject_deps[@]}"

    # Extract base names from DEP_PIP_NAMES (strip version specifiers)
    # Handle empty array (stub) gracefully -- ${arr[@]+...} avoids unbound error
    bootstrap_deps=()
    if [[ ${#DEP_PIP_NAMES[@]+x} && ${#DEP_PIP_NAMES[@]} -gt 0 ]]; then
        for pip_name in "${DEP_PIP_NAMES[@]}"; do
            base=$(echo "$pip_name" | sed 's/[><=!].*//' | tr -d '[:space:]')
            if [[ -n "$base" ]]; then
                bootstrap_deps+=("$base")
            fi
        done
    fi
    bootstrap_count="${#bootstrap_deps[@]}"

    # Compare count
    assert_eq "$pyproject_count" "$bootstrap_count" \
        "dep count matches (pyproject=$pyproject_count, bootstrap=$bootstrap_count)"

    # Compare names: each pyproject dep must appear in bootstrap deps
    all_match=true
    for pdep in "${pyproject_deps[@]}"; do
        found=false
        for bdep in "${bootstrap_deps[@]+"${bootstrap_deps[@]}"}"; do
            if [[ "$pdep" == "$bdep" ]]; then
                found=true
                break
            fi
        done
        if [[ "$found" != true ]]; then
            fail "pyproject dep '$pdep' not found in DEP_PIP_NAMES"
            all_match=false
        fi
    done

    # And vice versa: each bootstrap dep must appear in pyproject deps
    for bdep in "${bootstrap_deps[@]+"${bootstrap_deps[@]}"}"; do
        found=false
        for pdep in "${pyproject_deps[@]}"; do
            if [[ "$bdep" == "$pdep" ]]; then
                found=true
                break
            fi
        done
        if [[ "$found" != true ]]; then
            fail "bootstrap dep '$bdep' not found in pyproject.toml"
            all_match=false
        fi
    done

    if [[ "$all_match" == true && "$pyproject_count" -gt 0 && "$bootstrap_count" -gt 0 ]]; then
        pass "all dep names match between pyproject.toml and DEP_PIP_NAMES"
    fi
) || true

# ============================================================================
# Task 1.1e: Bash 3.2 compatibility test
# ============================================================================
echo ""
echo "=== Task 1.1e: Bash 3.2 compatibility ==="

(
    # Test that indexed array features work under /bin/bash (macOS ships 3.2)
    # Run a sub-script under /bin/bash explicitly
    compat_script="$TMP_DIR/bash_compat_test.sh"
    cat > "$compat_script" << 'COMPAT_EOF'
#!/bin/bash
# Verify Bash 3.2 compatible features
set -euo pipefail

# Indexed array declaration
arr=("a" "b" "c")

# Array iteration with [@]
result=""
for item in "${arr[@]}"; do
    result+="$item"
done

# String concatenation with +=
str="hello"
str+=" world"

# Verify results
if [[ "$result" != "abc" ]]; then
    echo "FAIL: array iteration produced '$result', expected 'abc'" >&2
    exit 1
fi
if [[ "$str" != "hello world" ]]; then
    echo "FAIL: string concat produced '$str', expected 'hello world'" >&2
    exit 1
fi

exit 0
COMPAT_EOF
    chmod +x "$compat_script"

    exit_code=0
    /bin/bash "$compat_script" 2>"$TMP_DIR/compat_stderr.txt" || exit_code=$?
    assert_exit_code 0 "$exit_code" "bash 3.2 array and string features work"

    # Source bootstrap-venv.sh under /bin/bash and verify no syntax errors
    syntax_script="$TMP_DIR/syntax_check.sh"
    cat > "$syntax_script" << SYNTAX_EOF
#!/bin/bash
set -euo pipefail
source "$SCRIPT_DIR/bootstrap-venv.sh"
exit 0
SYNTAX_EOF
    chmod +x "$syntax_script"

    exit_code=0
    /bin/bash "$syntax_script" 2>"$TMP_DIR/syntax_stderr.txt" || exit_code=$?
    assert_exit_code 0 "$exit_code" "bootstrap-venv.sh sources without syntax errors under /bin/bash"
) || true

# ============================================================================
# Task 1.1f: acquire_lock unit tests
# ============================================================================
echo ""
echo "=== Task 1.1f: acquire_lock ==="

# Sub-test 1: Lock acquired when lock dir does not exist
(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    lock_dir="$TMP_DIR/lock_test_1.lock"
    sentinel="$TMP_DIR/lock_test_1.sentinel"
    rm -rf "$lock_dir" "$sentinel"

    exit_code=0
    acquire_lock "$lock_dir" "$sentinel" "test-server" 2>/dev/null || exit_code=$?
    assert_exit_code 0 "$exit_code" "acquire_lock returns 0 when lock dir does not exist"

    # Cleanup
    rmdir "$lock_dir" 2>/dev/null || true
) || true

# Sub-test 2: Sentinel appears during wait
(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    lock_dir="$TMP_DIR/lock_test_2.lock"
    sentinel="$TMP_DIR/lock_test_2.sentinel"
    stderr_file="$TMP_DIR/lock_test_2_stderr.txt"

    rm -rf "$lock_dir" "$sentinel"
    mkdir -p "$lock_dir"  # Pre-create lock (simulate another process holding it)

    # In background: after 1 second, touch the sentinel
    (sleep 1 && touch "$sentinel") &
    bg_pid=$!

    start_time=$(date +%s)
    exit_code=0
    BOOTSTRAP_TIMEOUT=10 acquire_lock "$lock_dir" "$sentinel" "test-server" 2>"$stderr_file" || exit_code=$?
    end_time=$(date +%s)
    elapsed=$((end_time - start_time))

    # Wait for background process to finish
    wait "$bg_pid" 2>/dev/null || true

    stderr_output=$(cat "$stderr_file")

    assert_exit_code 1 "$exit_code" "acquire_lock returns 1 when sentinel appears"
    # Elapsed time should be < 5s (sentinel appears after ~1s, not timeout at 10s)
    if [[ "$elapsed" -lt 5 ]]; then
        pass "sentinel-triggered return is fast (${elapsed}s < 5s)"
    else
        fail "sentinel-triggered return too slow (${elapsed}s >= 5s, expected < 5s)"
    fi

    # Cleanup
    rm -f "$sentinel"
    rmdir "$lock_dir" 2>/dev/null || true
) || true

# Sub-test 3: Stale lock detection
(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    lock_dir="$TMP_DIR/lock_test_3.lock"
    sentinel="$TMP_DIR/lock_test_3.sentinel"
    rm -rf "$lock_dir" "$sentinel"

    # Pre-create lock dir and backdate it (well in the past)
    mkdir -p "$lock_dir"
    touch -t 202001010000 "$lock_dir"

    exit_code=0
    acquire_lock "$lock_dir" "$sentinel" "test-server" 2>/dev/null || exit_code=$?
    assert_exit_code 0 "$exit_code" "acquire_lock detects stale lock and re-acquires (returns 0)"

    # Cleanup
    rmdir "$lock_dir" 2>/dev/null || true
) || true

# Sub-test 4: Timeout
(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    lock_dir="$TMP_DIR/lock_test_4.lock"
    sentinel="$TMP_DIR/lock_test_4.sentinel"
    stderr_file="$TMP_DIR/lock_test_4_stderr.txt"
    rm -rf "$lock_dir" "$sentinel"

    # Pre-create lock dir with fresh mtime (not stale), no sentinel
    mkdir -p "$lock_dir"

    # Use short timeout to avoid slow test
    exit_code=0
    BOOTSTRAP_TIMEOUT=3 acquire_lock "$lock_dir" "$sentinel" "test-server" 2>"$stderr_file" || exit_code=$?

    stderr_output=$(cat "$stderr_file")

    assert_exit_code 1 "$exit_code" "acquire_lock exits 1 on timeout"
    # stderr should contain an error message about timeout
    if [[ -n "$stderr_output" ]]; then
        pass "timeout produces stderr output"
    else
        fail "timeout produces no stderr output (expected error message)"
    fi

    # Cleanup
    rmdir "$lock_dir" 2>/dev/null || true
) || true

# ============================================================================
# Task 1.1g: Empty lock directory invariant test
# ============================================================================
echo ""
echo "=== Task 1.1g: empty lock directory invariant ==="

(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    lock_dir="$TMP_DIR/lock_invariant_test.lock"
    rm -rf "$lock_dir"

    # Create lock dir with a file inside (non-empty)
    mkdir -p "$lock_dir"
    touch "$lock_dir/junk"

    # Call release_lock -- rmdir should fail on non-empty dir
    release_lock "$lock_dir" 2>/dev/null || true

    # Assert lock dir still exists (rmdir cannot remove non-empty dir)
    if [[ -d "$lock_dir" ]]; then
        pass "release_lock does not remove non-empty lock dir (rmdir invariant)"
    else
        fail "release_lock removed non-empty lock dir (should use rmdir, not rm -rf)"
    fi

    # Cleanup
    rm -rf "$lock_dir"
) || true

# ############################################################################
# INTEGRATION TESTS (Tasks 3.1a-3.1e)
# These tests do real venv creation and pip installs — expect ~30-60s each.
# Each test runs in its own subshell for isolation.
# ############################################################################

echo ""
echo "================================================================"
echo "  INTEGRATION TESTS"
echo "================================================================"

# ============================================================================
# Task 3.1a: Concurrent launch integration test (AC-1.1)
# Spawn 4 bootstrap_venv calls as background processes, wait for all,
# assert venv exists and all 8 deps importable.
# ============================================================================
echo ""
echo "=== Task 3.1a: concurrent launch (AC-1.1) ==="

(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    INT_DIR="$TMP_DIR/integration_3_1a"
    mkdir -p "$INT_DIR"
    VENV="$INT_DIR/.venv"

    # Spawn 4 concurrent bootstrap_venv calls as background processes
    for i in 1 2 3 4; do
        (
            source "$SCRIPT_DIR/bootstrap-venv.sh"
            bootstrap_venv "$VENV" "concurrent-server-$i"
        ) &
    done

    # Wait for all background processes
    wait

    # Assert venv exists
    if [ -x "$VENV/bin/python" ]; then
        pass "concurrent launch: venv exists with python executable"
    else
        fail "concurrent launch: venv missing or python not executable"
    fi

    # Assert all 8 deps importable
    if check_venv_deps "$VENV/bin/python"; then
        pass "concurrent launch: all 8 deps importable after concurrent bootstrap"
    else
        fail "concurrent launch: some deps missing after concurrent bootstrap"
    fi

    # Assert sentinel written
    if [ -f "$VENV/.bootstrap-complete" ]; then
        pass "concurrent launch: sentinel file exists"
    else
        fail "concurrent launch: sentinel file missing"
    fi
) || true

# ============================================================================
# Task 3.1b: Stale lock integration test (AC-1.3)
# Pre-create lock dir, backdate mtime, call bootstrap_venv,
# assert stale detection removes lock and bootstrap succeeds.
# ============================================================================
echo ""
echo "=== Task 3.1b: stale lock detection (AC-1.3) ==="

(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    INT_DIR="$TMP_DIR/integration_3_1b"
    mkdir -p "$INT_DIR"
    VENV="$INT_DIR/.venv"
    LOCK_DIR="${VENV}.bootstrap.lock"

    # Pre-create stale lock dir with old mtime
    mkdir -p "$LOCK_DIR"
    touch -t 202001010000 "$LOCK_DIR"

    # Run bootstrap — should detect stale lock, remove it, and succeed
    STDERR_FILE="$TMP_DIR/stale_lock_stderr.txt"
    exit_code=0
    bootstrap_venv "$VENV" "stale-test" 2>"$STDERR_FILE" || exit_code=$?
    stderr_output=$(cat "$STDERR_FILE")

    assert_exit_code 0 "$exit_code" "stale lock: bootstrap succeeds"

    # Assert venv was created and deps installed
    if check_venv_deps "$VENV/bin/python"; then
        pass "stale lock: all deps importable after stale lock recovery"
    else
        fail "stale lock: deps missing after stale lock recovery"
    fi

    # Assert stale lock was cleaned up (lock dir should not exist after bootstrap)
    if [ ! -d "$LOCK_DIR" ]; then
        pass "stale lock: lock directory removed after bootstrap"
    else
        fail "stale lock: lock directory still exists after bootstrap"
    fi

    # Assert stderr mentions stale detection
    assert_contains "$stderr_output" "stale" "stale lock: stderr mentions stale detection"
) || true

# ============================================================================
# Task 3.1c: Missing dep self-heal integration test (AC-2.4)
# Create venv with all deps + sentinel, uninstall numpy, run bootstrap,
# assert all deps restored.
# ============================================================================
echo ""
echo "=== Task 3.1c: missing dep self-heal (AC-2.4) ==="

(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    INT_DIR="$TMP_DIR/integration_3_1c"
    mkdir -p "$INT_DIR"
    VENV="$INT_DIR/.venv"

    # Create venv with all deps
    create_venv "$VENV" "selfheal-setup" 2>/dev/null
    install_all_deps "$VENV" "selfheal-setup" 2>/dev/null

    # Write sentinel
    touch "$VENV/.bootstrap-complete"

    # Verify setup: all deps present
    if ! check_venv_deps "$VENV/bin/python"; then
        fail "self-heal: setup failed — deps not installed"
        exit 1
    fi

    # Remove numpy to simulate missing dep
    # Use uv pip uninstall if available (uv venvs don't include pip by default),
    # fall back to venv pip
    if command -v uv >/dev/null 2>&1; then
        uv pip uninstall --python "$VENV/bin/python" numpy >/dev/null 2>&1
    else
        "$VENV/bin/pip" uninstall -y numpy >/dev/null 2>&1
    fi

    # Verify numpy is actually gone
    if "$VENV/bin/python" -c "import numpy" 2>/dev/null; then
        fail "self-heal: numpy still importable after uninstall"
        exit 1
    fi

    # Run bootstrap — sentinel exists but deps fail in Step 3,
    # should fall through to Step 4 and restore all deps
    STDERR_FILE="$TMP_DIR/selfheal_stderr.txt"
    exit_code=0
    bootstrap_venv "$VENV" "selfheal-test" 2>"$STDERR_FILE" || exit_code=$?

    assert_exit_code 0 "$exit_code" "self-heal: bootstrap succeeds"

    # Assert all deps restored (including numpy)
    if check_venv_deps "$VENV/bin/python"; then
        pass "self-heal: all deps restored after self-healing"
    else
        fail "self-heal: deps still missing after self-healing"
    fi

    # Assert numpy specifically
    if "$VENV/bin/python" -c "import numpy" 2>/dev/null; then
        pass "self-heal: numpy specifically restored"
    else
        fail "self-heal: numpy still missing after self-heal"
    fi
) || true

# ============================================================================
# Task 3.1d: uv-absent fallback integration test (DC-5)
# Run bootstrap_venv with uv removed from PATH, assert pip fallback
# used and all deps installed.
# ============================================================================
echo ""
echo "=== Task 3.1d: uv-absent fallback (DC-5) ==="

(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    INT_DIR="$TMP_DIR/integration_3_1d"
    mkdir -p "$INT_DIR"
    VENV="$INT_DIR/.venv"

    # Build a PATH without uv: remove any directory containing uv binary
    CLEAN_PATH=""
    IFS=':' read -ra PATH_PARTS <<< "$PATH"
    for p in "${PATH_PARTS[@]}"; do
        if [ ! -x "$p/uv" ]; then
            if [ -n "$CLEAN_PATH" ]; then
                CLEAN_PATH="$CLEAN_PATH:$p"
            else
                CLEAN_PATH="$p"
            fi
        fi
    done

    # Run bootstrap in a subshell with uv removed from PATH
    STDERR_FILE="$TMP_DIR/uv_absent_stderr.txt"
    exit_code=0
    (
        export PATH="$CLEAN_PATH"
        # Verify uv is actually absent
        if command -v uv >/dev/null 2>&1; then
            echo "WARNING: uv still on PATH after filtering" >&2
        fi
        source "$SCRIPT_DIR/bootstrap-venv.sh"
        bootstrap_venv "$VENV" "pip-fallback-test"
    ) 2>"$STDERR_FILE" || exit_code=$?
    stderr_output=$(cat "$STDERR_FILE")

    assert_exit_code 0 "$exit_code" "uv-absent: bootstrap succeeds with pip fallback"

    # Assert all deps installed
    if [ -x "$VENV/bin/python" ] && check_venv_deps "$VENV/bin/python"; then
        pass "uv-absent: all deps importable via pip fallback"
    else
        fail "uv-absent: deps missing after pip fallback bootstrap"
    fi

    # Assert stderr mentions pip (not uv) for installation
    assert_contains "$stderr_output" "pip" "uv-absent: stderr mentions pip fallback"
) || true

# ============================================================================
# Task 3.1e: Fast-path and sentinel recovery integration tests
# ============================================================================
echo ""
echo "=== Task 3.1e: fast-path and sentinel recovery ==="

# Sub-test 1: Fast-path — venv with all deps + sentinel, no lock created
(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    INT_DIR="$TMP_DIR/integration_3_1e_fastpath"
    mkdir -p "$INT_DIR"
    VENV="$INT_DIR/.venv"
    LOCK_DIR="${VENV}.bootstrap.lock"

    # Create venv with all deps + sentinel
    create_venv "$VENV" "fastpath-setup" 2>/dev/null
    install_all_deps "$VENV" "fastpath-setup" 2>/dev/null
    touch "$VENV/.bootstrap-complete"

    # Ensure no lock dir exists before test
    rmdir "$LOCK_DIR" 2>/dev/null || true

    # Run bootstrap — should take fast-path (Step 3)
    exit_code=0
    bootstrap_venv "$VENV" "fastpath-test" 2>/dev/null || exit_code=$?

    assert_exit_code 0 "$exit_code" "fast-path: bootstrap succeeds"

    # Assert PYTHON was exported correctly
    if [ "$PYTHON" = "$VENV/bin/python" ]; then
        pass "fast-path: PYTHON exported to venv python"
    else
        fail "fast-path: PYTHON='$PYTHON', expected '$VENV/bin/python'"
    fi

    # Assert no lock directory was created (fast-path skips locking)
    if [ ! -d "$LOCK_DIR" ]; then
        pass "fast-path: no lock directory created (fast-path taken)"
    else
        fail "fast-path: lock directory exists (should not for fast-path)"
    fi
) || true

# Sub-test 2: Sentinel recovery — venv with all deps but NO sentinel
(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    INT_DIR="$TMP_DIR/integration_3_1e_sentinel"
    mkdir -p "$INT_DIR"
    VENV="$INT_DIR/.venv"

    # Create venv with all deps but NO sentinel
    create_venv "$VENV" "sentinel-setup" 2>/dev/null
    install_all_deps "$VENV" "sentinel-setup" 2>/dev/null

    # Explicitly ensure no sentinel
    rm -f "$VENV/.bootstrap-complete"

    # Run bootstrap — should hit Step 3b (sentinel recovery)
    STDERR_FILE="$TMP_DIR/sentinel_recovery_stderr.txt"
    exit_code=0
    bootstrap_venv "$VENV" "sentinel-recovery-test" 2>"$STDERR_FILE" || exit_code=$?
    stderr_output=$(cat "$STDERR_FILE")

    assert_exit_code 0 "$exit_code" "sentinel recovery: bootstrap succeeds"

    # Assert sentinel was re-written
    if [ -f "$VENV/.bootstrap-complete" ]; then
        pass "sentinel recovery: sentinel file re-written"
    else
        fail "sentinel recovery: sentinel file not re-written"
    fi

    # Assert PYTHON exported correctly
    if [ "$PYTHON" = "$VENV/bin/python" ]; then
        pass "sentinel recovery: PYTHON exported correctly"
    else
        fail "sentinel recovery: PYTHON='$PYTHON', expected '$VENV/bin/python'"
    fi

    # Assert stderr mentions sentinel recovery
    assert_contains "$stderr_output" "sentinel recovered" "sentinel recovery: stderr confirms recovery"
) || true

# ############################################################################
# TEST DEEPENING — Spec-anchored adversarial & mutation-mindset tests
# These tests cover gaps not addressed by TDD scaffolding (Tasks 1.1b-1.1g,
# 3.1a-3.1e). Each test traces to a spec criterion or testing dimension.
# ############################################################################

echo ""
echo "================================================================"
echo "  TEST DEEPENING"
echo "================================================================"

# ============================================================================
# D1-BDD: test_lock_uses_mkdir_not_flock
# derived_from: spec:AC-1.2 (DC-4) — must use mkdir, not flock
# Anticipate: If someone adds flock for "reliability", the spec is violated.
# Challenge: grep is exact — catches any flock usage in the file.
# Verify: Deleting the mkdir call and adding flock would fail this test.
# ============================================================================
echo ""
echo "=== D1-BDD: lock uses mkdir, not flock ==="

(
    # Given the bootstrap-venv.sh library
    bootstrap_file="$SCRIPT_DIR/bootstrap-venv.sh"

    # When we search for flock usage
    if grep -q 'flock' "$bootstrap_file" 2>/dev/null; then
        fail "bootstrap-venv.sh uses flock (spec:AC-1.2/DC-4 requires mkdir only)"
    else
        pass "bootstrap-venv.sh does not use flock (spec:AC-1.2/DC-4)"
    fi

    # And mkdir must be used for locking
    mkdir_in_acquire=$(grep -c 'mkdir' "$bootstrap_file" 2>/dev/null || echo 0)
    if [[ "$mkdir_in_acquire" -gt 0 ]]; then
        pass "bootstrap-venv.sh uses mkdir for locking"
    else
        fail "bootstrap-venv.sh does not contain mkdir (expected for lock acquisition)"
    fi
) || true

# ============================================================================
# D1-BDD: test_bootstrap_output_only_to_stderr
# derived_from: spec:DC-1 — no stdout to avoid corrupting MCP stdio protocol
# Anticipate: An echo without >&2 redirect would corrupt MCP protocol.
# Challenge: We run bootstrap_venv capturing stdout; any content = failure.
# Verify: Adding a bare echo would make this test fail.
# ============================================================================
echo ""
echo "=== D1-BDD: bootstrap output only to stderr ==="

(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    INT_DIR="$TMP_DIR/deepening_stderr_test"
    mkdir -p "$INT_DIR"
    VENV="$INT_DIR/.venv"

    # Given a bootstrap invocation
    # When we capture stdout separately from stderr
    stdout_output=$(bootstrap_venv "$VENV" "stderr-test" 2>/dev/null)

    # Then stdout must be empty (all output goes to stderr per DC-1)
    if [[ -z "$stdout_output" ]]; then
        pass "bootstrap_venv produces no stdout output (spec:DC-1)"
    else
        fail "bootstrap_venv wrote to stdout: '$stdout_output' (spec:DC-1 violated)"
    fi
) || true

# ============================================================================
# D1-BDD: test_server_scripts_are_thin_wrappers
# derived_from: spec:AC-2.1 — single canonical dep list, not duplicated
# Anticipate: If a server script embeds its own venv/pip logic, deps diverge.
# Challenge: We check all 4 run-*.sh scripts for banned patterns.
# Verify: Adding "pip install" to any run-*.sh would fail this test.
# ============================================================================
echo ""
echo "=== D1-BDD: server scripts are thin wrappers ==="

(
    all_thin=true
    for script in run-memory-server.sh run-entity-server.sh run-workflow-server.sh run-ui-server.sh; do
        script_path="$SCRIPT_DIR/$script"
        if [[ ! -f "$script_path" ]]; then
            fail "server script not found: $script"
            all_thin=false
            continue
        fi

        # Given a server script
        # When we check for inline venv/pip logic
        # Then it must NOT contain "python3 -m venv" or "pip install"
        if grep -q 'python3 -m venv' "$script_path" 2>/dev/null; then
            fail "$script contains 'python3 -m venv' (should delegate to bootstrap-venv.sh)"
            all_thin=false
        fi
        if grep -q 'pip install' "$script_path" 2>/dev/null; then
            fail "$script contains 'pip install' (should delegate to bootstrap-venv.sh)"
            all_thin=false
        fi

        # And it MUST source bootstrap-venv.sh
        if ! grep -q 'source.*bootstrap-venv.sh' "$script_path" 2>/dev/null; then
            fail "$script does not source bootstrap-venv.sh"
            all_thin=false
        fi
    done

    if [[ "$all_thin" == true ]]; then
        pass "all 4 server scripts are thin wrappers sourcing bootstrap-venv.sh (spec:AC-2.1)"
    fi
) || true

# ============================================================================
# D2-BVA: test_python_version_exactly_3_12_accepted
# derived_from: spec:AC-3.1 — Python >= 3.12 required
# Anticipate: Off-by-one in version check could reject 3.12.
# Challenge: Mock python3 to return exactly 3.12, assert acceptance.
# Verify: Swapping < to <= in check would make 3.12 fail.
# ============================================================================
echo ""
echo "=== D2-BVA: Python version boundary tests ==="

(
    REAL_PYTHON3="$(command -v python3)"
    MOCK_DIR="$TMP_DIR/mock_python_bva"
    mkdir -p "$MOCK_DIR"

    # Helper: create a mock python3 that reports a specific version
    create_version_mock() {
        local version="$1"
        cat > "$MOCK_DIR/python3" << MOCK_EOF
#!/bin/bash
for arg in "\$@"; do
    if [[ "\$arg" == *"sys.version_info"* ]]; then
        echo "$version"
        exit 0
    fi
done
exec "$REAL_PYTHON3" "\$@"
MOCK_EOF
        chmod +x "$MOCK_DIR/python3"
    }

    source "$SCRIPT_DIR/bootstrap-venv.sh"

    # Test 3.12 — boundary: must be accepted (>= 3.12)
    create_version_mock "3.12"
    exit_code=0
    (PATH="$MOCK_DIR:$PATH"; check_python_version) 2>/dev/null || exit_code=$?
    assert_exit_code 0 "$exit_code" "Python 3.12 accepted (boundary, spec:AC-3.1)"

    # Test 3.13 — above boundary: must be accepted
    create_version_mock "3.13"
    exit_code=0
    (PATH="$MOCK_DIR:$PATH"; check_python_version) 2>/dev/null || exit_code=$?
    assert_exit_code 0 "$exit_code" "Python 3.13 accepted (above boundary, spec:AC-3.1)"

    # Test 3.11 — below boundary: must be rejected
    create_version_mock "3.11"
    exit_code=0
    (PATH="$MOCK_DIR:$PATH"; check_python_version) 2>/dev/null || exit_code=$?
    assert_exit_code 1 "$exit_code" "Python 3.11 rejected (below boundary, spec:AC-3.1)"
) || true

# ============================================================================
# D2-BVA: test_dep_check_uses_import_names_not_pip_names
# derived_from: spec:AC-2.2 — import names may differ from pip names
# Anticipate: Using "python-dotenv" as import name would fail silently.
# Challenge: Verify the import string uses "dotenv" not "python_dotenv".
# Verify: Swapping DEP_IMPORT_NAMES to DEP_PIP_NAMES would break this.
# ============================================================================
echo ""
echo "=== D2-BVA: dep check uses import names ==="

(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    # Given the DEP_IMPORT_NAMES array
    # When we check for the known pip!=import case: python-dotenv -> dotenv
    found_dotenv=false
    found_wrong=false
    for mod in "${DEP_IMPORT_NAMES[@]}"; do
        if [[ "$mod" == "dotenv" ]]; then
            found_dotenv=true
        fi
        # These would be wrong — pip names, not import names
        if [[ "$mod" == "python-dotenv" || "$mod" == "python_dotenv" ]]; then
            found_wrong=true
        fi
    done

    # Then "dotenv" must be present (correct import name)
    if [[ "$found_dotenv" == true ]]; then
        pass "DEP_IMPORT_NAMES uses 'dotenv' (correct import name, spec:AC-2.2)"
    else
        fail "DEP_IMPORT_NAMES missing 'dotenv' — should use import name, not pip name"
    fi

    # And the pip name variants must NOT appear
    if [[ "$found_wrong" == false ]]; then
        pass "DEP_IMPORT_NAMES does not contain pip name 'python-dotenv' or 'python_dotenv'"
    else
        fail "DEP_IMPORT_NAMES contains pip name variant instead of import name 'dotenv'"
    fi

    # Also verify pydantic_settings (underscore, not hyphen)
    found_ps=false
    for mod in "${DEP_IMPORT_NAMES[@]}"; do
        if [[ "$mod" == "pydantic_settings" ]]; then
            found_ps=true
        fi
    done
    if [[ "$found_ps" == true ]]; then
        pass "DEP_IMPORT_NAMES uses 'pydantic_settings' (correct import name)"
    else
        fail "DEP_IMPORT_NAMES missing 'pydantic_settings'"
    fi
) || true

# ============================================================================
# D3-ADV: test_lock_timeout_error_is_informative
# derived_from: spec:AC-1.5, dimension:adversarial
# Anticipate: A generic "error" message doesn't help debug which server timed out.
# Challenge: Assert stderr contains server name AND timeout duration.
# Verify: Removing server_name from error message would fail this test.
# ============================================================================
echo ""
echo "=== D3-ADV: lock timeout error is informative ==="

(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    lock_dir="$TMP_DIR/lock_timeout_info.lock"
    sentinel="$TMP_DIR/lock_timeout_info.sentinel"
    stderr_file="$TMP_DIR/lock_timeout_info_stderr.txt"
    rm -rf "$lock_dir" "$sentinel"

    # Given a fresh (non-stale) lock held by another process
    mkdir -p "$lock_dir"

    # When timeout occurs with a short timeout
    # Note: acquire_lock uses `exit 1` (not return 1) on timeout, so run in nested subshell
    exit_code=0
    (
        source "$SCRIPT_DIR/bootstrap-venv.sh"
        BOOTSTRAP_TIMEOUT=2 acquire_lock "$lock_dir" "$sentinel" "test-informative"
    ) 2>"$stderr_file" || exit_code=$?
    stderr_output=$(cat "$stderr_file")

    # Then the error message must contain the server name and timeout duration
    assert_contains "$stderr_output" "test-informative" "timeout error contains server name (spec:AC-1.5)"
    assert_contains "$stderr_output" "2" "timeout error contains timeout duration (spec:AC-1.5)"

    # Cleanup
    rmdir "$lock_dir" 2>/dev/null || true
) || true

# ============================================================================
# D4-ERR: test_exit_trap_releases_lock_on_unexpected_failure
# derived_from: spec:AC-1.3, dimension:error_propagation
# Anticipate: If install_all_deps fails and there's no trap, lock is orphaned.
# Challenge: Verify bootstrap-venv.sh sets an EXIT trap after acquiring lock.
# Verify: Removing the trap line would cause this grep-based check to fail.
# ============================================================================
echo ""
echo "=== D4-ERR: exit trap releases lock ==="

(
    bootstrap_file="$SCRIPT_DIR/bootstrap-venv.sh"

    # Given the bootstrap_venv function in bootstrap-venv.sh
    # When we check for EXIT trap after lock acquisition
    # Then a trap ... EXIT line must exist
    if grep -q "trap.*EXIT" "$bootstrap_file" 2>/dev/null; then
        pass "bootstrap-venv.sh has EXIT trap for lock cleanup (spec:AC-1.3)"
    else
        fail "bootstrap-venv.sh missing EXIT trap — lock could be orphaned on crash"
    fi
) || true

# ============================================================================
# D5-MUT: test_release_lock_uses_rmdir_not_rm_rf
# derived_from: spec:DC-4, dimension:mutation_mindset
# Anticipate: Using rm -rf in release_lock would silently destroy non-empty dirs.
# Challenge: Grep for "rm -rf" in release_lock context.
# Verify: Changing rmdir to rm -rf would fail this test.
# ============================================================================
echo ""
echo "=== D5-MUT: release_lock uses rmdir, not rm -rf ==="

(
    bootstrap_file="$SCRIPT_DIR/bootstrap-venv.sh"

    # Given the release_lock function
    # Extract release_lock body (from "release_lock()" to next function or EOF)
    release_body=$(sed -n '/^release_lock()/,/^[a-z_]*() {/p' "$bootstrap_file" | head -20)

    # When we check for rm -rf
    if echo "$release_body" | grep -q 'rm -rf'; then
        fail "release_lock uses 'rm -rf' (should use rmdir for empty-dir invariant)"
    else
        pass "release_lock does not use 'rm -rf' (uses rmdir, spec:DC-4)"
    fi

    # And rmdir must be present
    if echo "$release_body" | grep -q 'rmdir'; then
        pass "release_lock uses rmdir"
    else
        fail "release_lock does not use rmdir"
    fi
) || true

# ============================================================================
# D5-MUT: test_sentinel_written_before_lock_release
# derived_from: dimension:mutation_mindset — ordering matters for waiters
# Anticipate: If sentinel is written AFTER lock release, a waiter could see
#   no sentinel and no lock, then fail to find deps.
# Challenge: Verify "touch.*sentinel" appears before "release_lock" in code.
# Verify: Swapping the two lines would fail this test.
# ============================================================================
echo ""
echo "=== D5-MUT: sentinel written before lock release ==="

(
    bootstrap_file="$SCRIPT_DIR/bootstrap-venv.sh"

    # Given the bootstrap_venv function — leader path writes sentinel then releases lock
    # The leader path calls install_all_deps "$venv_dir" (not the function definition).
    # Find the first such call, then the first touch "$sentinel" and release_lock after it.
    install_line=$(grep -n 'install_all_deps "$venv_dir"' "$bootstrap_file" | head -1 | cut -d: -f1)

    # Find first 'touch "$sentinel"' line after install_line
    sentinel_line=$(grep -n 'touch "$sentinel"' "$bootstrap_file" | awk -F: -v min="$install_line" '$1 > min { print $1; exit }')
    # Find first 'release_lock' line after install_line
    release_line=$(grep -n 'release_lock' "$bootstrap_file" | awk -F: -v min="$install_line" '$1 > min { print $1; exit }')

    if [[ -n "$sentinel_line" && -n "$release_line" ]]; then
        if [[ "$sentinel_line" -lt "$release_line" ]]; then
            pass "sentinel written (line $sentinel_line) before lock release (line $release_line)"
        else
            fail "sentinel written (line $sentinel_line) AFTER lock release (line $release_line) — waiters may miss it"
        fi
    else
        fail "could not locate sentinel write or release_lock lines"
    fi
) || true

# ============================================================================
# D5-MUT: test_acquire_lock_return_code_distinguishes_leader_from_waiter
# derived_from: dimension:mutation_mindset — return 0 vs 1 drives different paths
# Anticipate: If both paths return 0, waiter would try to re-create venv.
# Challenge: Verify leader path returns 0, waiter (sentinel) path returns 1.
# Verify: Changing "return 1" to "return 0" in sentinel path would fail.
# ============================================================================
echo ""
echo "=== D5-MUT: acquire_lock return codes ==="

(
    source "$SCRIPT_DIR/bootstrap-venv.sh"

    # Test 1: Leader path (no lock exists) -> return 0
    lock_dir="$TMP_DIR/lock_rc_leader.lock"
    sentinel="$TMP_DIR/lock_rc_leader.sentinel"
    rm -rf "$lock_dir" "$sentinel"

    exit_code=0
    acquire_lock "$lock_dir" "$sentinel" "rc-test" 2>/dev/null || exit_code=$?
    assert_exit_code 0 "$exit_code" "leader path returns 0 (lock acquired)"
    rmdir "$lock_dir" 2>/dev/null || true

    # Test 2: Waiter path (lock exists, sentinel appears) -> return 1
    lock_dir="$TMP_DIR/lock_rc_waiter.lock"
    sentinel="$TMP_DIR/lock_rc_waiter.sentinel"
    rm -rf "$lock_dir" "$sentinel"
    mkdir -p "$lock_dir"

    # Background: touch sentinel after 1s
    (sleep 1 && touch "$sentinel") &
    bg_pid=$!

    exit_code=0
    BOOTSTRAP_TIMEOUT=10 acquire_lock "$lock_dir" "$sentinel" "rc-test" 2>/dev/null || exit_code=$?
    wait "$bg_pid" 2>/dev/null || true

    assert_exit_code 1 "$exit_code" "waiter path returns 1 (sentinel appeared, another process completed)"

    rm -f "$sentinel"
    rmdir "$lock_dir" 2>/dev/null || true
) || true

# ============================================================================
# D5-MUT: test_version_comparison_uses_less_than_not_less_than_or_equal
# derived_from: dimension:mutation_mindset — >= 3.12 means -lt 12, not -le 12
# Anticipate: Using -le instead of -lt would reject 3.12.
# Challenge: This is already tested by the BVA 3.12 test above, but we also
#   verify the source code uses -lt (not -le) for the minor version check.
# Verify: Changing -lt to -le in source would fail this test.
# ============================================================================
echo ""
echo "=== D5-MUT: version comparison operator ==="

(
    bootstrap_file="$SCRIPT_DIR/bootstrap-venv.sh"

    # Given the check_python_version function
    # Extract the minor version comparison line
    minor_check=$(grep 'minor.*-l' "$bootstrap_file" 2>/dev/null || echo "")

    if [[ -z "$minor_check" ]]; then
        fail "could not find minor version comparison in check_python_version"
    else
        # Then the comparison must use -lt (less than), not -le (less than or equal)
        if echo "$minor_check" | grep -q '\-lt'; then
            pass "minor version check uses -lt (correct for >= 3.12)"
        else
            fail "minor version check does not use -lt — may use -le which would reject 3.12"
        fi

        if echo "$minor_check" | grep -q '\-le'; then
            fail "minor version check uses -le (would incorrectly reject 3.12)"
        else
            pass "minor version check does not use -le"
        fi
    fi
) || true

# ============================================================================
# Summary (unit + integration + deepening tests)
# ============================================================================
echo ""
PASS=$(cat "$PASS_FILE")
FAIL=$(cat "$FAIL_FILE")
echo "============================================"
echo "  UNIT + INTEGRATION + DEEPENING RESULTS"
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
echo "  TOTAL: $((PASS + FAIL))"
echo "============================================"

if [[ "$FAIL" -gt 0 ]]; then
    exit 1
fi
exit 0
