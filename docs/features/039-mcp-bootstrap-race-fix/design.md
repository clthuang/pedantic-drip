# Design: MCP Bootstrap Race Fix

## Prior Art Research

### Codebase Patterns
- **Existing bootstrap structure:** All 4 scripts follow a 4-step resolution: fast-path venv → system python3 → uv bootstrap → pip bootstrap. Each script independently handles its own deps.
- **Directory-based locks:** `cleanup-locks.sh` already uses `rmdir ~/.claude/history.jsonl.lock` — mkdir/rmdir lock pattern is established in this codebase.
- **Python version checking:** `doctor.sh:144-154` extracts major.minor via `python3 -c "import sys; print(...)"` and compares with bash arithmetic.
- **Import verification:** `doctor.sh:226-244` iterates `module:package` pairs and runs `"$venv_python" -c "import ${module}"` per dep.
- **Dep import check:** `run-memory-server.sh:23` already checks `import mcp.server.fastmcp; import numpy; import dotenv` for system python3 path.
- **No existing coordination:** Zero locking or serialization exists in bootstrap scripts today.

### External Research
- **mkdir atomicity:** POSIX guarantees `mkdir` fails atomically for all but one concurrent caller — the canonical portable lock primitive (BashFAQ/045).
- **flock unavailability on macOS:** flock(1) is not installed by default on macOS, confirming mkdir as the right choice per DC-4.
- **Stale detection:** `find "$LOCKDIR" -maxdepth 0 -mmin +N` is portable across macOS and Linux without GNU coreutils (per spec AC-1.3).
- **Double-checked locking:** Standard pattern — acquire lock → re-check sentinel → bootstrap if still needed → write sentinel → release lock.
- **Spin-wait for consumers:** Poll sentinel file with bounded retries instead of piling on the lock: `for i in $(seq 1 N); do [ -f "$SENTINEL" ] && break; sleep 1; done`.
- **PID in lockdir:** Write `$$` to `$LOCKDIR/pid` for debuggability — though PID liveness check adds complexity; mtime-based stale detection is simpler and sufficient here since bootstrap is short (<120s).

## Architecture Overview

### Design Approach: Shared Bootstrap Library

Extract all bootstrap logic into a single shared shell library (`bootstrap-venv.sh`) that each server sources. This eliminates code duplication, centralizes the canonical dep list, and ensures all 4 scripts use identical coordination logic.

```
Before (4 independent scripts, each with inline bootstrap):
  run-memory-server.sh   →  inline venv create + install mcp,numpy,dotenv
  run-entity-server.sh   →  inline venv create + install mcp
  run-workflow-server.sh →  inline venv create + install mcp
  run-ui-server.sh       →  inline venv create + install fastapi,uvicorn,jinja2

After (4 thin scripts + 1 shared library):
  run-memory-server.sh   →  source bootstrap-venv.sh; exec python server.py
  run-entity-server.sh   →  source bootstrap-venv.sh; exec python server.py
  run-workflow-server.sh →  source bootstrap-venv.sh; exec python server.py
  run-ui-server.sh       →  source bootstrap-venv.sh; exec python server.py "$@"
  bootstrap-venv.sh      →  version guard + lock + venv create + dep install + dep verify
```

### Bootstrap Flow (Single Process View)

```
┌─────────────────────────────────────────────────┐
│ Server Script (e.g., run-memory-server.sh)      │
│ source bootstrap-venv.sh                        │
└─────────────┬───────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────┐
│ 1. Python Version Guard (FR-3)                  │
│    python3 -c "sys.exit(0 if >= 3.12 else 1)"  │
│    FAIL → stderr error + exit 1                 │
└─────────────┬───────────────────────────────────┘
              │ PASS
              ▼
┌─────────────────────────────────────────────────┐
│ 2. System Python3 Check (existing, preserved)   │
│    python3 -c "import all_canonical_deps"       │
│    PASS → exec python3 $SERVER_SCRIPT; done     │
└─────────────┬───────────────────────────────────┘
              │ FAIL (deps not on system python)
              ▼
┌─────────────────────────────────────────────────┐
│ 3. Fast-Path: Venv + Deps Check (FR-2)          │
│    if bin/python exists AND all deps importable │
│    → set PYTHON=$VENV_DIR/bin/python; return    │
│    if bin/python exists BUT deps missing        │
│    → self-heal: install all deps (AC-2.4)       │
│    → set PYTHON=$VENV_DIR/bin/python; return    │
└─────────────┬───────────────────────────────────┘
              │ No venv yet
              ▼
┌─────────────────────────────────────────────────┐
│ 4. Locked Bootstrap (FR-1)                      │
│    a. acquire_lock (mkdir atomic)               │
│    b. set trap EXIT → release_lock (cleanup)    │
│    c. re-check: if venv appeared while waiting  │
│       → verify deps, self-heal if needed        │
│       → release lock, clear trap, return        │
│    d. create venv (uv venv || python3 -m venv)  │
│    e. install ALL canonical deps                │
│    f. write sentinel (.bootstrap-complete)       │
│    g. release_lock (rmdir), clear trap          │
│    h. set PYTHON=$VENV_DIR/bin/python; return   │
└─────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────┐
│ Back in server script:                          │
│ exec "$PYTHON" "$SERVER_SCRIPT" "$@"            │
└─────────────────────────────────────────────────┘
```

### Concurrent Launch (4 Process View)

```
Time →

Process A (entity-server):     [version guard][sys check][no venv] → LOCK ACQUIRED → create venv → install deps → UNLOCK → exec
Process B (memory-server):     [version guard][sys check][no venv] → lock busy → spin-wait on sentinel ──────────────────────→ [deps ok] → exec
Process C (workflow-server):   [version guard][sys check][no venv] → lock busy → spin-wait on sentinel ──────────────────────→ [deps ok] → exec
Process D (ui-server):         [version guard][sys check][no venv] → lock busy → spin-wait on sentinel ──────────────────────→ [deps ok] → exec
```

## Components

### C1: `bootstrap-venv.sh` (Shared Library)

**Location:** `plugins/iflow/mcp/bootstrap-venv.sh`

**Responsibility:** All bootstrap logic — version guard, dep verification, locking, venv creation, dep installation. Sourced by all 4 server scripts.

**Exports:** Sets `PYTHON` variable to the resolved Python interpreter path. The calling script uses `exec "$PYTHON" "$SERVER_SCRIPT"`.

**Internal functions:**
- `check_python_version` — FR-3 implementation
- `check_system_python` — System python3 fallback: verifies ALL canonical deps are importable on system python3 (not just the calling server's deps). **Spec deviation:** The spec Design Notes say "preserved as-is" for this path, but the current per-server dep subsets are the root cause of RC-2 (entity-server checks only `mcp`, skips `numpy` which memory-server needs). Unifying to check ALL deps is the principled fix. Trade-off: this makes the system python3 path a no-op in practice (no system has all 8 deps globally), but it was already unreliable — dev machines with `uv sync`'d global python are the only case where it triggered, and those machines also have the venv. This is an acceptable behavioral change; the spec should be amended during implementation to replace "preserved as-is" with "unified to check all canonical deps". If all deps are importable, sets `PYTHON=python3` and returns 0; otherwise returns 1 to proceed to venv path.
- `check_venv_deps` — FR-2 fast-path import verification
- `create_venv` — Creates venv at given path. Uses `uv venv` if available, falls back to `python3 -m venv`. Arguments: venv_dir, server_name (for logging). All output to stderr.
- `install_all_deps` — Installs all canonical deps (uv preferred, pip fallback)
- `acquire_lock` — mkdir-based lock with spin-wait + stale detection (FR-1)
- `release_lock` — rmdir + sentinel write
- `bootstrap_venv` — Orchestrates the full flow

**Canonical dependency list:** Defined as two index-aligned bash arrays at the top of the file (see I7). Derived from `pyproject.toml` `[project].dependencies`. All 8 core deps from pyproject.toml are included.

### C2: Server Scripts (Thin Wrappers)

**Files:** `run-memory-server.sh`, `run-entity-server.sh`, `run-workflow-server.sh`, `run-ui-server.sh`

**After refactor:** Each script becomes ~15 lines:
1. `set -euo pipefail`
2. Resolve `SCRIPT_DIR`, `PLUGIN_DIR`, `VENV_DIR`, `SERVER_SCRIPT`
3. Export `PYTHONPATH`, `PYTHONUNBUFFERED`
4. `source "$SCRIPT_DIR/bootstrap-venv.sh"`
5. `bootstrap_venv "$VENV_DIR" "$SERVER_NAME"`
6. `exec "$PYTHON" "$SERVER_SCRIPT" "$@"`

### C3: Lock Directory + Sentinel

**Lock directory:** `$VENV_DIR.bootstrap.lock` (sibling to `.venv`, not inside it)

**Sentinel file:** `$VENV_DIR/.bootstrap-complete` — written after successful dep install, checked by fast-path and spin-wait consumers.

**Why a sentinel separate from `bin/python`:** `bin/python` exists before deps are installed. The sentinel confirms both venv creation AND dep installation completed successfully. This is the fix for RC-2 (fast-path checked only `bin/python`).

## Technical Decisions

### TD-1: Shared Library vs Inline Duplication

**Decision:** Shared library (`bootstrap-venv.sh`), sourced by all 4 scripts.

**Rationale:** The spec requires a single canonical dep list (AC-2.1). Duplicating lock logic and dep lists across 4 scripts would create maintenance drift — the exact problem that caused RC-2. Sourcing a library is idiomatic bash and adds no runtime cost.

**Trade-off:** Slightly harder to read each script in isolation (need to follow the source), but each script is now ~15 lines vs ~40 lines.

### TD-2: Sentinel File for Bootstrap Completion

**Decision:** Use `$VENV_DIR/.bootstrap-complete` as the completion marker, not `$VENV_DIR/bin/python`.

**Rationale:** `bin/python` exists after `uv venv` / `python3 -m venv` but before `pip install`. Checking only `bin/python` is exactly the bug in RC-2. The sentinel is written only after all deps are installed and verified.

**Trade-off:** One extra file in `.venv/`. Negligible.

### TD-3: Spin-Wait on Sentinel (Not Lock Re-acquisition)

**Decision:** Processes that lose the mkdir race spin-wait for the sentinel file (1s interval, 120s timeout) instead of retrying mkdir.

**Rationale:** If 3 processes pile up on mkdir retry, they'd each try to acquire → fail → sleep → retry, creating unnecessary contention. Spin-waiting on the sentinel is simpler: once the leader writes it, all waiters break out immediately. The 120s timeout (AC-1.5) handles the case where the leader crashes.

**Trade-off:** Spin-wait burns CPU on `sleep 1` + `test -f` per iteration. With 3 waiters at 1Hz, this is negligible.

### TD-4: Stale Lock Detection via `find -mmin`

**Decision:** Use `find "$LOCKDIR" -maxdepth 0 -mmin +2` to detect locks older than 120 seconds.

**Rationale:** Portable across macOS (BSD find) and Linux (GNU find) per AC-1.3. No need for `stat` format differences or Python one-liners. `+2` means "modified more than 2 minutes ago" which maps to the 120s threshold.

**Trade-off:** Granularity is 1 minute (find -mmin rounds). A lock at 119s won't be detected until ~180s. Acceptable — the spec says 120s is the threshold, and the extra ~60s worst-case is within the "minimize overhead" guidance (AC-1.4).

**Interaction with spin-wait timeout:** In the concurrent launch scenario, if the leader crashes at T=0, waiters timeout at T=120s (AC-1.5) *before* stale detection would trigger at T≈180s. This is correct: waiters fail fast via timeout, not via stale detection. Stale detection serves a different purpose — cleaning up locks from a *previous* session's crash, discovered by processes in a *new* session.

### TD-5: Indexed Arrays for Dep List (Not Associative)

**Decision:** Two index-aligned bash arrays — `DEP_PIP_NAMES` and `DEP_IMPORT_NAMES` — at the top of `bootstrap-venv.sh`. Derived from `pyproject.toml` `[project].dependencies`.

**Rationale:** Single source of truth (AC-2.1). Both `pip install` (iterates `DEP_PIP_NAMES`) and `import check` (iterates `DEP_IMPORT_NAMES`) derive from the same data structure. Adding a dep = adding one entry to each array at the same index.

**Why not associative arrays:** macOS ships `/bin/bash` 3.2 (Apple will not ship GPLv3 bash 4+). Associative arrays require bash 4+. Since shebangs use `#!/bin/bash`, all scripts run under bash 3.2 on macOS. Indexed arrays work on bash 3.2.

**Why not read pyproject.toml at runtime:** Parsing TOML in bash is fragile. The arrays are the bootstrap-time source of truth. A test verifies they stay aligned with pyproject.toml (see File Changes Summary).

### TD-6: uv-First with pip Fallback (Normalized)

**Decision:** All bootstrap paths use `uv` first, falling back to `pip` only when `uv` is unavailable. This normalizes `run-memory-server.sh` which currently uses pip only (DC-5).

**Rationale:** `uv` is faster (10-100x) and already used by 3 of 4 scripts. The check `command -v uv >/dev/null 2>&1` runs once per bootstrap invocation.

**Trade-off:** `run-ui-server.sh` currently uses `uv sync --no-dev` which respects `uv.lock` for reproducible installs. Switching to `uv pip install` loses lockfile pinning — deps resolve at install time. Accepted because: (1) marketplace installs don't ship `uv.lock` (it's gitignored), so `uv sync` would fail anyway on fresh installs; (2) the version constraints in `DEP_PIP_NAMES` (mirroring pyproject.toml) provide sufficient pinning for bootstrap; (3) dev workspaces already have `.venv` from `uv sync` and take the fast-path, so this change only affects fresh marketplace installs.

### TD-7: Lock Location (Sibling to .venv)

**Decision:** Lock at `$VENV_DIR.bootstrap.lock` (i.e., `$PLUGIN_DIR/.venv.bootstrap.lock`), not in `/tmp`.

**Rationale:** Keeps the lock co-located with the venv it protects. `/tmp` would require a unique name derived from the venv path (hash or encode), adding complexity. Since all 4 scripts resolve the same `$PLUGIN_DIR`, they'll all target the same lock path.

**Trade-off:** If the plugin dir is on a network filesystem, mkdir atomicity might not hold. Acceptable — Claude Code plugins are local.

## Risks

### R1: Bash 3.2 on macOS (Mitigated)

macOS ships bash 3.2 (2007), which lacks associative arrays. **Mitigated** by TD-5: use indexed arrays instead.

### R2: Stale Lock False Positive (Low)

If a legitimate bootstrap takes >120s (very slow network for pip install), a waiter could delete the lock prematurely. **Mitigation:** 120s is generous — typical `uv pip install` of 6 packages takes <10s, pip takes <30s. Even on slow connections, 120s provides ample headroom.

### R3: Sentinel File Deleted by User (Low)

If a user manually deletes `.bootstrap-complete` from the venv, the next server start will re-verify deps (import check) and either find them present (re-write sentinel) or re-install. Self-healing handles this.

### R4: Leader Install Failure (Low)

If the bootstrap leader's `pip install` / `uv pip install` fails (network error, package conflict), the EXIT trap releases the lock but `.bootstrap-complete` is never written. Waiters spin for 120s then timeout (AC-1.5). The partial venv (`bin/python` exists, deps incomplete) is left behind. On next server restart, the fast-path detects missing deps and self-heals (AC-2.4). **The 120s waiter timeout is acceptable** because install failures are rare and the timeout matches the spec-mandated ceiling. A failure sentinel (`.bootstrap-failed`) was considered but rejected as over-engineering — the self-healing fast-path handles recovery on retry.

### R5: SIGKILL During Bootstrap (Low)

If the bootstrap leader is killed with SIGKILL (not trappable), the trap won't fire and the lock persists. **Mitigated** by stale detection: the next server start (or another waiter) detects mtime >120s and cleans up.

## Interfaces

### I1: `bootstrap_venv` Function

```bash
# Main entry point. Called by each server script after sourcing bootstrap-venv.sh.
# Sets PYTHON to the resolved interpreter path.
# Exits with code 1 on fatal errors (Python version, lock timeout).
# All output to stderr (DC-1).
# Sentinel write: After install_all_deps succeeds, writes .bootstrap-complete
# before calling release_lock. This ensures waiters see the sentinel immediately
# after the lock is released.
#
# Arguments:
#   $1 - VENV_DIR: absolute path to the shared venv directory
#   $2 - SERVER_NAME: human-readable name for log messages (e.g., "memory-server")
#
# Exports:
#   PYTHON - path to the Python interpreter to use
#
# Example:
#   source "$SCRIPT_DIR/bootstrap-venv.sh"
#   bootstrap_venv "$VENV_DIR" "memory-server"
#   exec "$PYTHON" "$SERVER_SCRIPT"
bootstrap_venv() {
    local venv_dir="$1"
    local server_name="$2"
    # ... implementation
}
```

### I2: `check_python_version` Function

```bash
# Verifies python3 is >= 3.12. Exits with code 1 if not.
# Error message to stderr includes required and detected versions (AC-3.2).
#
# Arguments: none (uses python3 from PATH)
# Returns: 0 on success, exits 1 on failure
check_python_version() {
    local version
    version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
    local major="${version%%.*}"
    local minor="${version#*.}"
    if (( major < 3 || (major == 3 && minor < 12) )); then
        echo "${SERVER_NAME:-bootstrap}: ERROR: Python >= 3.12 required, found ${version}" >&2
        exit 1
    fi
}
```

### I3: `check_venv_deps` Function

```bash
# Checks if all canonical deps are importable in the given Python interpreter.
# Returns 0 if all deps present, 1 if any missing.
#
# Arguments:
#   $1 - python_path: path to the Python interpreter to check
#
# Uses: DEP_IMPORT_NAMES array (module-level constant)
check_venv_deps() {
    local python_path="$1"
    local imports=""
    for mod in "${DEP_IMPORT_NAMES[@]}"; do
        imports+="import ${mod}; "
    done
    "$python_path" -c "$imports" 2>/dev/null
}
```

### I4: `install_all_deps` Function

```bash
# Installs all canonical deps into the venv. Uses uv if available, pip fallback.
# All output to stderr.
#
# Arguments:
#   $1 - venv_dir: absolute path to the venv
#   $2 - server_name: for log messages
#
# Uses: DEP_PIP_NAMES array (module-level constant)
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
```

### I5: `acquire_lock` / `release_lock` Functions

```bash
# Attempts to acquire the bootstrap lock via mkdir.
# Two-phase behavior:
#   Phase 1: Try mkdir once. If succeeds → lock acquired, return 0.
#   Phase 2: If mkdir fails (lock exists):
#     a. Check stale: find "$lock_dir" -maxdepth 0 -mmin +2
#        If stale → rm -rf "$lock_dir", retry mkdir once.
#        If retry mkdir also fails → fall through to Phase 2b (spin-wait).
#     b. Spin-wait on SENTINEL file (not lock re-acquisition):
#        for i in 1..120: if sentinel exists, return 1 (meaning
#        "another process completed bootstrap, skip to fast-path").
#        sleep 1 between checks.
#     c. If sentinel never appears within 120s → exit 1 (AC-1.5).
#
# Returns: 0 = lock acquired (caller must bootstrap)
#          1 = another process completed (caller should verify deps and proceed)
# Exits:   1 if timeout (120s) with error to stderr
#
# Arguments:
#   $1 - lock_dir: path to the lock directory
#   $2 - sentinel: path to the sentinel file
#   $3 - server_name: for log messages
acquire_lock() {
    local lock_dir="$1"
    local sentinel="$2"
    local server_name="$3"
    # Phase 1: try mkdir
    # Phase 2a: stale detection
    # Phase 2b: sentinel spin-wait
}

# Releases the bootstrap lock. Does NOT write sentinel (that's done
# separately after dep verification succeeds).
#
# Arguments:
#   $1 - lock_dir: path to the lock directory
release_lock() {
    local lock_dir="$1"
    rmdir "$lock_dir" 2>/dev/null || true
}
```

**Trap-based cleanup:** After `acquire_lock` returns 0 (lock acquired), the caller (`bootstrap_venv`) immediately sets a trap:
```bash
trap 'rmdir "$lock_dir" 2>/dev/null' EXIT
```
This ensures the lock is released even if `uv pip install` or `python3 -m venv` fails under `set -euo pipefail`. The trap is cleared (`trap - EXIT`) after `release_lock` completes. This is the standard mkdir lock cleanup pattern (BashFAQ/045).

**Sentinel roles clarified:**
- **For spin-waiters:** Signals "bootstrap leader finished, deps are installed". Waiters break out of spin-wait and proceed to fast-path dep verification.
- **For fast-path (step 3):** NOT used. Fast-path always verifies deps via import check (`check_venv_deps`), regardless of sentinel presence. Sentinel is only for waiter coordination.

### I6: Server Script Interface (Post-Refactor)

Each server script follows this template. **Contract:** `PYTHONPATH` must be exported *before* `source bootstrap-venv.sh`, as `check_system_python` depends on it for import verification.

```bash
#!/bin/bash
# Bootstrap and run the MCP {name} server.
# All bootstrap logic is in bootstrap-venv.sh (shared with other servers).
#
# Called by Claude Code via plugin.json mcpServers — do NOT write to stdout
# (would corrupt MCP stdio protocol). All diagnostics go to stderr.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"
SERVER_SCRIPT="$SCRIPT_DIR/{server_file}.py"

export PYTHONPATH="$PLUGIN_DIR/hooks/lib${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

source "$SCRIPT_DIR/bootstrap-venv.sh"
bootstrap_venv "$VENV_DIR" "{server-name}"
exec "$PYTHON" "$SERVER_SCRIPT" "$@"
```

Note: `run-ui-server.sh` has a slightly different PYTHONPATH (adds `$PLUGIN_DIR` for the `ui` module) and SERVER_SCRIPT path (`$PLUGIN_DIR/ui/__main__.py`).

### I7: Canonical Dependency Arrays

```bash
# Single source of truth for all server dependencies (AC-2.1).
# Index-aligned: DEP_PIP_NAMES[i] installs as DEP_IMPORT_NAMES[i].
# To add a dep: append to both arrays at the same index.
DEP_PIP_NAMES=("fastapi>=0.128.3" "jinja2>=3.1.6" "mcp>=1.0,<2" "numpy>=1.24,<3" "pydantic>=2.11,<3" "pydantic-settings>=2.5,<3" "python-dotenv>=1.0,<2" "uvicorn>=0.34")
DEP_IMPORT_NAMES=(fastapi jinja2 mcp numpy pydantic pydantic_settings dotenv uvicorn)
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `plugins/iflow/mcp/bootstrap-venv.sh` | **Create** | Shared bootstrap library with all coordination logic |
| `plugins/iflow/mcp/run-memory-server.sh` | **Modify** | Replace inline bootstrap with `source bootstrap-venv.sh` |
| `plugins/iflow/mcp/run-entity-server.sh` | **Modify** | Replace inline bootstrap with `source bootstrap-venv.sh` |
| `plugins/iflow/mcp/run-workflow-server.sh` | **Modify** | Replace inline bootstrap with `source bootstrap-venv.sh` |
| `plugins/iflow/mcp/run-ui-server.sh` | **Modify** | Replace inline bootstrap with `source bootstrap-venv.sh` |
| `plugins/iflow/mcp/test_bootstrap_venv.sh` | **Create** | Test: concurrent launch, stale lock, missing dep self-heal, Python version guard, uv-absent fallback, dep array alignment with pyproject.toml |
