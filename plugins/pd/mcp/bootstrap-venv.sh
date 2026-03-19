#!/bin/bash
# Shared bootstrap library for MCP server venv management.
# Sourced by all server scripts (run-*.sh) to coordinate venv creation,
# dependency installation, and locking.
#
# Exports: PYTHON — path to the resolved Python interpreter.
# All output to stderr (DC-1: no stdout to avoid corrupting MCP stdio protocol).
# Bash 3.2 compatible (TD-5: no associative arrays).

# --- Constants ---

BOOTSTRAP_TIMEOUT=${BOOTSTRAP_TIMEOUT:-120}
BOOTSTRAP_ERROR_LOG="$HOME/.claude/pd/mcp-bootstrap-errors.log"

# Single source of truth for all server dependencies (AC-2.1).
# Index-aligned: DEP_PIP_NAMES[i] installs as DEP_IMPORT_NAMES[i].
# To add a dep: append to both arrays at the same index.
# Derived from pyproject.toml [project].dependencies.
DEP_PIP_NAMES=("fastapi>=0.128.3" "jinja2>=3.1.6" "mcp>=1.0,<2" "numpy>=1.24,<3" "pydantic>=2.11,<3" "pydantic-settings>=2.5,<3" "python-dotenv>=1.0,<2" "uvicorn>=0.34")
DEP_IMPORT_NAMES=(fastapi jinja2 mcp numpy pydantic pydantic_settings dotenv uvicorn)

# Module-level variables set during bootstrap_venv():
#   PYTHON_FOR_VENV - absolute path to the discovered Python >= 3.12 interpreter (for venv creation)
#   SENTINEL_PATH   - path to the bootstrap-complete sentinel file
#   SERVER_NAME     - human-readable server name for logging

# --- Functions ---

# Writes a JSONL error entry to ~/.claude/pd/mcp-bootstrap-errors.log.
# Called before exit 1 on any fatal bootstrap error.
# All output to stderr (MCP stdio safety).
#
# Arguments:
#   $1 - server_name: which server failed (e.g., "memory-server")
#   $2 - error_type: one of "python_version", "venv_creation", "dep_install", "lock_timeout"
#   $3 - message: human-readable error description
#   $4 - extra_json: optional additional JSON fields (e.g., '"found":"3.9","required":"3.12"')
log_bootstrap_error() {
    local server_name="$1"
    local error_type="$2"
    local msg="$3"
    local extra_json="${4:-}"
    local ts

    mkdir -p "$HOME/.claude/pd" 2>/dev/null || true
    ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    echo "{\"timestamp\":\"$ts\",\"server\":\"$server_name\",\"error\":\"$error_type\",\"message\":\"$msg\"${extra_json:+,$extra_json}}" >> "$BOOTSTRAP_ERROR_LOG"
}

# Writes the sentinel file with interpreter metadata.
# Format: <absolute_path>:<major.minor>
# Example: /opt/homebrew/bin/python3.13:3.13
#
# Arguments:
#   $1 - sentinel_path: path to the sentinel file
#   $2 - python_path: absolute path to the Python interpreter used
write_sentinel() {
    local sentinel_path="$1"
    local python_path="$2"
    local version

    version=$("$python_path" -c "import sys; print('{0}.{1}'.format(sys.version_info.major, sys.version_info.minor))" 2>/dev/null || echo "")
    if [ -n "$version" ]; then
        echo "$python_path:$version" > "$sentinel_path"
    else
        # Fallback: write sentinel without version info (better than no sentinel)
        echo "$python_path:" > "$sentinel_path"
    fi
}

# Discovers a Python >= 3.12 interpreter and sets PYTHON_FOR_VENV.
# Search order:
#   1. uv python find --system '>=3.12' (if uv available)
#   2. python3.14, python3.13, python3.12 in /opt/homebrew/bin
#   3. python3.14, python3.13, python3.12 in /usr/local/bin
#   4. Bare python3 from PATH
# For each candidate (tiers 2-4), verify version >= 3.12.
# On failure: calls log_bootstrap_error() and exits 1.
# On success: sets PYTHON_FOR_VENV=<absolute path>
#
# Arguments: none
# Sets: PYTHON_FOR_VENV (module-level, NOT exported)
# Requires: SERVER_NAME must be set before calling
discover_python() {
    local candidate version major minor

    # Tier 1: uv python find (if uv available)
    if command -v uv >/dev/null 2>&1; then
        candidate=$(uv python find --system '>=3.12' 2>/dev/null) || true
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            PYTHON_FOR_VENV="$candidate"
            echo "${SERVER_NAME:-bootstrap}: discovered Python via uv: $PYTHON_FOR_VENV" >&2
            return 0
        fi
    fi

    # Tier 2-3: Manual search in well-known directories
    local search_dirs="/opt/homebrew/bin /usr/local/bin"
    local search_versions="python3.14 python3.13 python3.12"
    for dir in $search_dirs; do
        for ver in $search_versions; do
            candidate="$dir/$ver"
            if [ -x "$candidate" ]; then
                version=$("$candidate" -c "import sys; print('{0}.{1}'.format(sys.version_info.major, sys.version_info.minor))" 2>/dev/null || echo "0.0")
                major="${version%%.*}"
                minor="${version#*.}"
                # Validate: accept if >= 3.12
                if [ -n "$minor" ] && [ "$minor" -eq "$minor" ] 2>/dev/null; then
                    if [ "$major" -gt 3 ] 2>/dev/null || { [ "$major" -eq 3 ] && [ "$minor" -ge 12 ]; } 2>/dev/null; then
                        PYTHON_FOR_VENV="$candidate"
                        echo "${SERVER_NAME:-bootstrap}: discovered Python at $PYTHON_FOR_VENV ($version)" >&2
                        return 0
                    fi
                fi
            fi
        done
    done

    # Tier 4: Bare python3 from PATH
    candidate=$(command -v python3 2>/dev/null || true)
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        version=$("$candidate" -c "import sys; print('{0}.{1}'.format(sys.version_info.major, sys.version_info.minor))" 2>/dev/null || echo "0.0")
        major="${version%%.*}"
        minor="${version#*.}"
        if [ -n "$minor" ] && [ "$minor" -eq "$minor" ] 2>/dev/null; then
            if [ "$major" -gt 3 ] 2>/dev/null || { [ "$major" -eq 3 ] && [ "$minor" -ge 12 ]; } 2>/dev/null; then
                PYTHON_FOR_VENV="$candidate"
                echo "${SERVER_NAME:-bootstrap}: using python3 from PATH: $PYTHON_FOR_VENV ($version)" >&2
                return 0
            fi
        fi
    fi

    # Record what we found (or didn't) for the error message
    local found_version="${version:-none}"

    # All tiers exhausted — failure
    local searched_json="\"/opt/homebrew/bin/python3.{14,13,12}\",\"/usr/local/bin/python3.{14,13,12}\",\"python3 (PATH)\""
    echo "${SERVER_NAME:-bootstrap}: ERROR: Python >= 3.12 required, found ${found_version:-none}" >&2
    echo "${SERVER_NAME:-bootstrap}: Searched: /opt/homebrew/bin, /usr/local/bin, PATH" >&2
    log_bootstrap_error "${SERVER_NAME:-bootstrap}" "python_version" "Python >= 3.12 required, found ${found_version:-none}" "\"found\":\"${found_version:-none}\",\"required\":\"3.12\",\"searched\":[$searched_json]"
    exit 1
}

# Checks if all canonical deps are importable in the given Python interpreter.
# Returns 0 if all deps present, 1 if any missing (I3, FR-2).
#
# Arguments:
#   $1 - python_path: path to the Python interpreter to check
check_venv_deps() {
    local python_path="$1"
    local imports=""
    for mod in "${DEP_IMPORT_NAMES[@]}"; do
        imports+="import ${mod}; "
    done
    "$python_path" -c "$imports" 2>/dev/null
}

# System python check — uses check_venv_deps with PYTHON_FOR_VENV.
# If all canonical deps are importable globally, we can skip venv bootstrap entirely.
check_system_python() {
    if check_venv_deps "$PYTHON_FOR_VENV"; then
        export PYTHON="$PYTHON_FOR_VENV"
        write_sentinel "$SENTINEL_PATH" "$PYTHON_FOR_VENV"
        return 0
    fi
    return 1
}

# Creates a venv at the given path. Uses uv if available, pip fallback (DC-5).
# All output to stderr (DC-1).
#
# Arguments:
#   $1 - venv_dir: absolute path to the venv directory
#   $2 - server_name: for log messages
create_venv() {
    local venv_dir="$1"
    local server_name="$2"
    if command -v uv >/dev/null 2>&1; then
        echo "${server_name}: creating venv with uv..." >&2
        uv venv --python "$PYTHON_FOR_VENV" "$venv_dir" >&2
    else
        echo "${server_name}: creating venv with $PYTHON_FOR_VENV -m venv..." >&2
        "$PYTHON_FOR_VENV" -m venv "$venv_dir" >&2
    fi
}

# Installs all canonical deps into the venv. Uses uv if available, pip fallback (I4, DC-5).
# All output to stderr (DC-1).
#
# Arguments:
#   $1 - venv_dir: absolute path to the venv
#   $2 - server_name: for log messages
install_all_deps() {
    local venv_dir="$1"
    local server_name="$2"
    if command -v uv >/dev/null 2>&1; then
        echo "${server_name}: installing deps with uv..." >&2
        uv pip install --python "$venv_dir/bin/python" "${DEP_PIP_NAMES[@]}" >&2
    else
        echo "${server_name}: installing deps with pip..." >&2
        "$venv_dir/bin/pip" install -q "${DEP_PIP_NAMES[@]}" >&2
    fi
}

# Attempts to acquire the bootstrap lock via mkdir (I5, FR-1, DC-4).
# Two-phase behavior:
#   Phase 1: Try mkdir once. If succeeds -> lock acquired, return 0.
#   Phase 2: If mkdir fails (lock exists):
#     a. Check stale: find "$lock_dir" -maxdepth 0 -mmin +2
#        If stale -> rmdir (NOT rm -rf, preserves empty-dir invariant) + retry mkdir once.
#        If retry fails -> fall through to Phase 2b.
#     b. Spin-wait on sentinel file (1s intervals, $BOOTSTRAP_TIMEOUT iterations).
#        Return 1 if sentinel appears (another process completed).
#        Exit 1 if timeout (AC-1.5).
#
# Returns: 0 = lock acquired (caller must bootstrap)
#          1 = another process completed (caller should verify deps and proceed)
# Exits:   1 if timeout with error to stderr
#
# Arguments:
#   $1 - lock_dir: path to the lock directory
#   $2 - sentinel: path to the sentinel file
#   $3 - server_name: for log messages
acquire_lock() {
    local lock_dir="$1"
    local sentinel="$2"
    local server_name="$3"

    # Phase 1: try mkdir (atomic on POSIX)
    if mkdir "$lock_dir" 2>/dev/null; then
        return 0
    fi

    # Phase 2a: stale detection
    # If the lock dir's mtime is >2 minutes old, it's from a crashed previous bootstrap.
    if [ -d "$lock_dir" ] && [ -n "$(find "$lock_dir" -maxdepth 0 -mmin +2 2>/dev/null)" ]; then
        echo "${server_name}: detected stale lock, removing..." >&2
        # rmdir (not rm -rf): preserves empty-dir invariant; falls through to spin-wait if non-empty
        if rmdir "$lock_dir" 2>/dev/null; then
            # Retry mkdir once after stale cleanup
            if mkdir "$lock_dir" 2>/dev/null; then
                return 0
            fi
            # Another process grabbed it between rmdir and mkdir — fall through to spin-wait
        else
            echo "${server_name}: WARNING: stale lock dir is non-empty, waiting for timeout..." >&2
        fi
    fi

    # Phase 2b: spin-wait on sentinel file
    echo "${server_name}: waiting for another process to complete bootstrap..." >&2
    local i=0
    while [ "$i" -lt "$BOOTSTRAP_TIMEOUT" ]; do
        if [ -f "$sentinel" ]; then
            return 1
        fi
        sleep 1
        i=$((i + 1))
    done

    # Timeout — no sentinel appeared within BOOTSTRAP_TIMEOUT seconds
    echo "${server_name}: ERROR: bootstrap lock timeout after ${BOOTSTRAP_TIMEOUT}s" >&2
    log_bootstrap_error "$server_name" "lock_timeout" "Bootstrap lock timeout after ${BOOTSTRAP_TIMEOUT}s" "\"timeout_seconds\":$BOOTSTRAP_TIMEOUT"
    exit 1
}

# Releases the bootstrap lock. Uses rmdir exclusively (not rm -rf)
# to enforce the empty-dir invariant.
#
# Arguments:
#   $1 - lock_dir: path to the lock directory
release_lock() {
    local lock_dir="$1"
    rmdir "$lock_dir" 2>/dev/null || true
}

# Main entry point. Called by each server script after sourcing bootstrap-venv.sh.
# Sets PYTHON to the resolved interpreter path (I1).
# Exits with code 1 on fatal errors (Python version, lock timeout).
# All output to stderr (DC-1).
#
# Arguments:
#   $1 - venv_dir: absolute path to the shared venv directory
#   $2 - server_name: human-readable name for log messages
#
# Exports:
#   PYTHON - path to the Python interpreter to use
bootstrap_venv() {
    local venv_dir="$1"
    local server_name="$2"
    local lock_dir="${venv_dir}.bootstrap.lock"
    local sentinel="${venv_dir}/.bootstrap-complete"

    # Set module-level variables before discover_python()
    SERVER_NAME="$server_name"
    SENTINEL_PATH="$sentinel"

    # Step 1: Python discovery — find a suitable interpreter >= 3.12
    discover_python

    # Step 2: System python check — if all deps importable, use system python
    if check_system_python; then
        echo "${server_name}: using system python (all deps available)" >&2
        return 0
    fi

    # Step 3: Fast-path — if venv exists and all deps importable, use it.
    # Handles both normal fast-path (sentinel present) and sentinel recovery
    # (sentinel missing but deps present — previous leader crashed before writing sentinel).
    if [ -x "$venv_dir/bin/python" ] && check_venv_deps "$venv_dir/bin/python"; then
        # Re-write sentinel if missing (sentinel recovery, safe without locking — idempotent)
        [ -f "$sentinel" ] || { write_sentinel "$sentinel" "$PYTHON_FOR_VENV"; echo "${server_name}: sentinel recovered (deps already present)" >&2; }
        export PYTHON="$venv_dir/bin/python"
        return 0
    fi
    # If venv exists but deps incomplete (with or without sentinel), fall through to Step 4.
    # Do NOT delete sentinel — it's harmless and deleting could cause
    # spin-waiters to miss the signal and timeout unnecessarily.
    if [ -x "$venv_dir/bin/python" ] && [ -f "$sentinel" ]; then
        echo "${server_name}: deps incomplete despite sentinel, entering locked bootstrap..." >&2
    fi

    # Step 4: Locked bootstrap
    if acquire_lock "$lock_dir" "$sentinel" "$server_name"; then
        # Lock acquired — we are the leader
        # Set trap to release lock on any exit (crash safety under set -euo pipefail)
        trap 'rmdir "'"$lock_dir"'" 2>/dev/null || true' EXIT

        # Double-checked locking: re-check sentinel after acquiring lock
        if [ -f "$sentinel" ] && check_venv_deps "$venv_dir/bin/python" 2>/dev/null; then
            release_lock "$lock_dir"
            trap - EXIT
            export PYTHON="$venv_dir/bin/python"
            return 0
        fi

        # Create venv if needed (may already exist as partial from crashed previous attempt)
        if [ ! -x "$venv_dir/bin/python" ]; then
            create_venv "$venv_dir" "$server_name"
        fi

        # Install all canonical deps
        install_all_deps "$venv_dir" "$server_name"

        # Write sentinel (before releasing lock so waiters see it immediately)
        write_sentinel "$sentinel" "$PYTHON_FOR_VENV"

        # Release lock and clear trap
        release_lock "$lock_dir"
        trap - EXIT

        export PYTHON="$venv_dir/bin/python"
        return 0
    else
        # acquire_lock returned 1 — another process completed bootstrap
        # Re-check deps (waiter path)
        if [ -x "$venv_dir/bin/python" ] && check_venv_deps "$venv_dir/bin/python"; then
            export PYTHON="$venv_dir/bin/python"
            return 0
        fi

        # Self-heal: deps missing after another process supposedly finished.
        # Race is acceptable: concurrent pip/uv installs of identical packages are idempotent
        echo "${server_name}: WARNING: deps incomplete after peer bootstrap, self-healing..." >&2
        if [ ! -x "$venv_dir/bin/python" ]; then
            create_venv "$venv_dir" "$server_name"
        fi
        install_all_deps "$venv_dir" "$server_name"
        write_sentinel "$sentinel" "$PYTHON_FOR_VENV"
        export PYTHON="$venv_dir/bin/python"
        return 0
    fi
}
