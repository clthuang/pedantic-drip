# Spec: MCP Bootstrap Python Discovery and Silent Failure

**Feature:** 042-mcp-bootstrap-python-discovery
**RCA:** [docs/rca/20260318-mcp-bootstrap-python-discovery.md](../../rca/20260318-mcp-bootstrap-python-discovery.md)

## Problem Statement

On fresh iflow installations where PATH ordering places macOS system Python (3.9) before a Homebrew Python (3.12+), all three MCP servers fail to start silently. The agent loses all workflow MCP tools with no diagnostic path. Five root causes compound: no intelligent Python discovery (RC-1), version threshold mismatch between doctor.sh and bootstrap (RC-2), invisible bootstrap failures (RC-3), no MCP health check at session start (RC-4), and setup never enforced (RC-5). A residual stale-sentinel edge case in meta-json-guard (RC-6) can recreate the deadlock.

## Requirements

### R1: Intelligent Python Discovery in Bootstrap

**Addresses:** RC-1 (Primary root cause)
**File:** `plugins/iflow/mcp/bootstrap-venv.sh`

Replace `check_python_version()` with a new `discover_python()` function that searches for a suitable interpreter and exports `PYTHON_FOR_VENV`:

1. Search order (first match wins):
   - `python3.14`, `python3.13`, `python3.12` in `/opt/homebrew/bin` (macOS Apple Silicon)
   - `python3.14`, `python3.13`, `python3.12` in `/usr/local/bin` (macOS Intel / Linux)
   - Bare `python3` from PATH
2. For each candidate, verify version >= 3.12 before accepting
3. On success, export `PYTHON_FOR_VENV` (the discovered interpreter's absolute path)
4. On failure (no interpreter >= 3.12 found), emit a diagnostic listing what was tried and exit 1

All callsites that currently use bare `python3` must be updated to use `$PYTHON_FOR_VENV`:
- `check_python_version()` line 28: `python3 -c "import sys..."` → use `$PYTHON_FOR_VENV` (replaced by `discover_python()`)
- `check_system_python()` line 54: `check_venv_deps python3` → `check_venv_deps "$PYTHON_FOR_VENV"`
- `create_venv()` line 75: `python3 -m venv` → `"$PYTHON_FOR_VENV" -m venv`
- `create_venv()` line 72: `uv venv "$venv_dir"` → `uv venv --python "$PYTHON_FOR_VENV" "$venv_dir"`

**Platform scope:** macOS (Apple Silicon and Intel). The search paths cover Homebrew locations. Linux users typically have correct PATH ordering; adding `/usr/bin/python3.1x` is out of scope but the bare `python3` fallback covers Linux.

**Acceptance Criteria:**
- AC-1.1: On a system where `/usr/bin/python3` is 3.9 and `/opt/homebrew/bin/python3.13` exists, bootstrap discovers and uses 3.13
- AC-1.2: On a system where only bare `python3` >= 3.12 exists, bootstrap uses it (backward compatible)
- AC-1.3: On a system with no Python >= 3.12, bootstrap exits 1 with a diagnostic listing all checked locations
- AC-1.4: `create_venv()` non-uv path uses `$PYTHON_FOR_VENV` instead of bare `python3`
- AC-1.5: `create_venv()` uv path passes `--python "$PYTHON_FOR_VENV"` to `uv venv`
- AC-1.6: `check_system_python()` passes `$PYTHON_FOR_VENV` to `check_venv_deps`

### R2: Align Version Thresholds

**Addresses:** RC-2
**Files:** `plugins/iflow/scripts/doctor.sh`

Update `check_python3()` minimum version from 3.10 to 3.12 to match bootstrap-venv.sh's runtime requirement.

**Acceptance Criteria:**
- AC-2.1: `doctor.sh check_python3()` fails for Python 3.10 and 3.11
- AC-2.2: `doctor.sh check_python3()` passes for Python 3.12+
- AC-2.3: Error message mentions "3.12" as the minimum

### R3: Structured Bootstrap Error Reporting

**Addresses:** RC-3
**Files:** `plugins/iflow/mcp/bootstrap-venv.sh`, `plugins/iflow/mcp/run-*.sh`

When bootstrap fails, write a diagnostic to a well-known log file that session-start can check.

1. On `discover_python()` failure, write a JSON line to `~/.claude/iflow/mcp-bootstrap-errors.log`
2. On other bootstrap failures (venv creation, dep install, lock timeout), write a JSON line similarly
3. Log file is append-only. Session-start truncates entries older than 1 hour after reading (simple rotation).

**Log entry JSON schema:**
- Required fields: `timestamp` (ISO-8601 UTC), `server` (string, e.g. "memory-server"), `error` (string enum: "python_version", "venv_creation", "dep_install", "lock_timeout"), `message` (human-readable string)
- Optional fields by error type:
  - `python_version`: `found` (string), `required` (string), `searched` (array of paths tried)
  - `venv_creation`: `exit_code` (integer), `venv_path` (string)
  - `dep_install`: `exit_code` (integer), `missing_deps` (array)
  - `lock_timeout`: `timeout_seconds` (integer)

**Acceptance Criteria:**
- AC-3.1: When Python discovery fails, `~/.claude/iflow/mcp-bootstrap-errors.log` contains a JSON line with error type "python_version" and the searched paths
- AC-3.2: When venv creation fails, error is logged with type "venv_creation"
- AC-3.3: Log entries include UTC ISO-8601 timestamp and server name
- AC-3.4: Existing stderr output is preserved (not replaced) — the log is additive
- AC-3.5: Session-start truncates entries older than 1 hour after reading

### R4: Session-Start MCP Health Check

**Addresses:** RC-4
**Files:** `plugins/iflow/hooks/session-start.sh`

Add a check that reads `~/.claude/iflow/mcp-bootstrap-errors.log` for recent errors and surfaces them prominently.

1. After existing first-run detection (near the venv existence check in `build_session_context`), check for bootstrap error log entries from the last 10 minutes. Timestamps are UTC ISO-8601; comparison uses `date +%s` epoch arithmetic: `current_epoch - entry_epoch < 600`.
2. If recent errors found, emit a **hard warning** (not buried in additionalContext) — prepend to context so it appears first:
   ```
   WARNING: MCP servers failed to start. Workflow tools (transition_phase, store_memory, etc.) are unavailable.
   Error: Python >= 3.12 required, found 3.9. Run: bash "{PLUGIN_ROOT}/scripts/setup.sh"
   ```
3. Also check for bootstrap sentinel existence as a secondary signal

**Acceptance Criteria:**
- AC-4.1: When bootstrap error log has entries < 10 minutes old, session-start emits a warning
- AC-4.2: Warning includes the specific error and a fix command
- AC-4.3: Warning appears at the top of context output (not buried)
- AC-4.4: When no recent errors, no warning emitted (no false positives)

### R5: Strengthen First-Run Detection

**Addresses:** RC-5
**File:** `plugins/iflow/hooks/session-start.sh`

The current first-run message is a soft note buried in additionalContext. Strengthen it:

1. When `.venv` is missing OR `~/.claude/iflow/memory` is missing, emit the setup prompt **before** other context (not appended at the end)
2. Change wording from informational to actionable: "Setup required for MCP workflow tools. Run: bash \"{PLUGIN_ROOT}/scripts/setup.sh\""

**Acceptance Criteria:**
- AC-5.1: When `.venv` is missing, setup prompt appears before feature status in context output
- AC-5.2: Setup message is clearly actionable (includes the exact command to run)

### R6: Stale Sentinel Handling in meta-json-guard

**Addresses:** RC-6 residual risk
**File:** `plugins/iflow/hooks/meta-json-guard.sh`

Improve `check_mcp_available()` to detect stale sentinels by recording the Python version used.

1. Modify bootstrap-venv.sh: when writing the sentinel (`touch "$sentinel"`), also write the Python interpreter path and version into the sentinel file (e.g., `/opt/homebrew/bin/python3.13:3.13`)
2. In `check_mcp_available()`: after finding a sentinel, read the recorded interpreter path and verify it still exists and still meets the version requirement. If not, treat as MCP unavailable.
3. Fallback: if sentinel exists but has no content (legacy format), check mtime < 24 hours as a heuristic. Stale (> 24h) → treat as unavailable.
4. Log "permit-degraded-stale-sentinel" action for observability

**Acceptance Criteria:**
- AC-6.1: Bootstrap writes interpreter path and version into sentinel file
- AC-6.2: Guard with valid sentinel (interpreter exists, version OK) → blocks direct writes (existing behavior)
- AC-6.3: Guard with invalid sentinel (interpreter moved/removed or version changed) → permits degraded writes
- AC-6.4: Guard with legacy sentinel (no content) + mtime < 24h → blocks (backward compat)
- AC-6.5: Guard with legacy sentinel (no content) + mtime > 24h → permits degraded writes
- AC-6.6: Missing sentinel → permits degraded writes (existing behavior)
- AC-6.7: Stale/invalid sentinel events are logged with distinct action

## Scope Boundaries

**In scope:**
- Python discovery logic in bootstrap-venv.sh (R1)
- Version threshold in doctor.sh (R2)
- Error logging in bootstrap-venv.sh (R3)
- MCP health check in session-start.sh (R4)
- Strengthened first-run detection in session-start.sh (R5)
- Stale sentinel detection in meta-json-guard.sh (R6)

**Platform:** macOS (Apple Silicon and Intel). Linux coverage via bare `python3` fallback only.

**Out of scope:**
- Changing how Claude Code launches MCP servers (plugin.json)
- Adding a `postInstall` hook to plugin.json (would require Claude Code platform changes)
- Changing the MCP protocol error reporting (would require mcp library changes)
- Probing MCP server responsiveness at session start (too complex for this feature; error log is sufficient)
- Linux-specific Python discovery paths (e.g., `/usr/bin/python3.12`)

## Dependencies

- No external dependencies
- All changes are to existing bash scripts
- Backward compatible: systems with working Python >= 3.12 on PATH see no behavior change

## Testing Strategy

**Python discovery tests** (extend `test_bootstrap_venv.sh`):
- Scenario 1: `PATH=/mock/bin` where mock `python3` returns 3.9, mock `python3.13` at `/opt/homebrew/bin/` returns 3.13 → expects discovery of `/opt/homebrew/bin/python3.13`
- Scenario 2: `PATH` contains only bare `python3` >= 3.12 → expects use of bare `python3`
- Scenario 3: No Python >= 3.12 anywhere (mock all candidates) → expects exit 1 with diagnostic listing all checked locations
- PATH mocking uses `PATH=/mock/bin:$PATH` prefix in test functions with stub scripts

**Doctor version threshold test** (extend or add to doctor tests):
- Verify `check_python3()` fails for mocked Python 3.10 and 3.11
- Verify passes for mocked Python 3.12+

**Error log tests:**
- Bootstrap failure writes JSON to `~/.claude/iflow/mcp-bootstrap-errors.log`
- Session-start reads log entries and emits warning for entries < 10min old
- Session-start truncates entries > 1 hour

**Sentinel tests** (extend hook tests):
- Sentinel with valid interpreter → guard blocks
- Sentinel with removed interpreter → guard permits
- Legacy empty sentinel + mtime < 24h → guard blocks
- Legacy empty sentinel + mtime > 24h → guard permits

**Regression:** Existing `test_bootstrap_venv.sh` and `test-hooks.sh` must continue to pass
