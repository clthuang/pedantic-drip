# Plan: MCP Bootstrap Python Discovery and Silent Failure

**Feature:** 042-mcp-bootstrap-python-discovery
**Design:** [design.md](design.md) | **Spec:** [spec.md](spec.md)

## Implementation Order

Tasks are ordered by dependency — each task builds on the previous. Tests are written alongside each change (TDD where practical).

```
T0: Baseline test run (green check before changes)
 ↓
T1: discover_python() + write_sentinel() + log_bootstrap_error()
 ↓
T2: Update callsites (check_system_python, create_venv, sentinel recovery)
 ↓
T3: Update doctor.sh threshold
 ↓
T4: check_mcp_health() in session-start.sh
 ↓
T5: Enhanced check_mcp_available() in meta-json-guard.sh
 ↓
T6: Strengthen first-run detection in session-start.sh
 ↓
T7: Extend test suites + regression verification
```

## Tasks

### T0: Baseline test run

**Dependencies:** None (must run first)

Run existing test suites to establish a green baseline before any code changes:
1. `bash plugins/iflow/mcp/test_bootstrap_venv.sh`
2. `bash plugins/iflow/hooks/tests/test-hooks.sh`

Record any pre-existing failures to distinguish from regressions introduced by this feature.

### T1: Add discover_python(), write_sentinel(), log_bootstrap_error() to bootstrap-venv.sh

**Addresses:** R1 (core), R3, R6 (sentinel format)
**File:** `plugins/iflow/mcp/bootstrap-venv.sh`
**Dependencies:** None (foundation task)

**Changes:**
1. Add `log_bootstrap_error()` function:
   - Arguments: `$1` server_name, `$2` error_type, `$3` message, `$4` extra_json (optional)
   - Writes JSONL to `~/.claude/iflow/mcp-bootstrap-errors.log`
   - Creates `~/.claude/iflow/` directory if missing (`mkdir -p`)
   - Timestamp: `date -u +%Y-%m-%dT%H:%M:%SZ`
   - Server name values: "memory-server", "entity-registry", "workflow-engine", "ui-server"

2. Add `write_sentinel()` function:
   - Arguments: `$1` sentinel_path, `$2` python_path
   - Writes `<absolute_path>:<major.minor>` to sentinel file
   - Gets version via: `"$python_path" -c "import sys; print('{0}.{1}'.format(sys.version_info.major, sys.version_info.minor))" 2>/dev/null`
   - Parse sentinel: `IFS=: read -r interp_path interp_version < sentinel`

3. Add `discover_python()` function (replaces `check_python_version()`):
   - Tier 1: `uv python find --system '>=3.12' 2>/dev/null` — if uv available and returns valid path
   - Tier 2: Loop `python3.14`, `python3.13`, `python3.12` in `/opt/homebrew/bin` — check `-x` then verify version
   - Tier 3: Same loop in `/usr/local/bin`
   - Tier 4: Bare `python3` from PATH — verify version >= 3.12
   - On success: set `PYTHON_FOR_VENV=<absolute path>`
   - On failure: call `log_bootstrap_error "$SERVER_NAME" "python_version" "..." '"found":"...","required":"3.12","searched":["..."]"'` then `exit 1`
   - For "searched" array: build comma-separated quoted list from the hardcoded candidate paths

4. Delete `check_python_version()` function

**Tests:** Add to `test_bootstrap_venv.sh`:
- `test_discover_python_uv_path`: mock uv returning valid path → expects PYTHON_FOR_VENV set
- `test_discover_python_manual_fallback`: no uv, mock python3.13 in /opt/homebrew/bin → expects discovery
- `test_discover_python_bare_fallback`: no uv, no versioned, bare python3 >= 3.12 → expects use
- `test_discover_python_failure`: all candidates < 3.12 → expects exit 1 + error log written
- `test_write_sentinel_format`: verify sentinel file content matches `path:version` format
- `test_log_bootstrap_error_format`: verify JSONL line has required fields

**Verification:** `bash plugins/iflow/mcp/test_bootstrap_venv.sh`

### T2: Update bootstrap-venv.sh callsites to use PYTHON_FOR_VENV

**Addresses:** R1 (AC-1.4, AC-1.5, AC-1.6)
**File:** `plugins/iflow/mcp/bootstrap-venv.sh`
**Dependencies:** T1

**Changes:**
1. `check_system_python()`:
   - `check_venv_deps python3` → `check_venv_deps "$PYTHON_FOR_VENV"`
   - `export PYTHON=python3` → `export PYTHON="$PYTHON_FOR_VENV"`
   - Add: `write_sentinel "$sentinel" "$PYTHON_FOR_VENV"` on success (needs sentinel path passed or derived)
   - Approach: set sentinel path as module-level variable `SENTINEL_PATH` at the top of `bootstrap_venv()` (alongside `PYTHON_FOR_VENV`), so `check_system_python()` can read it without a signature change.

2. `create_venv()`:
   - `python3 -m venv "$venv_dir"` → `"$PYTHON_FOR_VENV" -m venv "$venv_dir"`
   - `uv venv "$venv_dir"` → `uv venv --python "$PYTHON_FOR_VENV" "$venv_dir"`

3. `bootstrap_venv()` flow reorder:
   - Move `discover_python()` call to Step 1 (before system python check)
   - Step 2: `check_system_python()` — now uses PYTHON_FOR_VENV
   - Step 3: venv fast-path — replace `touch "$sentinel"` with `write_sentinel "$sentinel" "$PYTHON_FOR_VENV"`
   - Step 4: locked bootstrap — replace both `touch "$sentinel"` calls (line 236, 259) with `write_sentinel`

**Tests:** Extend existing tests:
- `test_system_python_uses_discovered`: verify check_system_python passes PYTHON_FOR_VENV to check_venv_deps
- `test_create_venv_uv_uses_python_flag`: verify uv venv receives --python
- `test_sentinel_written_on_system_python`: verify sentinel exists after system python fast-path

**Verification:** `bash plugins/iflow/mcp/test_bootstrap_venv.sh`

### T3: Update doctor.sh version threshold

**Addresses:** R2 (AC-2.1, AC-2.2, AC-2.3)
**File:** `plugins/iflow/scripts/doctor.sh`
**Dependencies:** None (independent)

**Changes:**
1. `check_python3()`: Change `(( major < 3 || (major == 3 && minor < 10) ))` → `(( major < 3 || (major == 3 && minor < 12) ))`
2. Update error message: `"python3 version ${version} < 3.10 required"` → `"python3 version ${version} < 3.12 required"`

**Tests:** Add concrete test script (reuse mock pattern from test_bootstrap_venv.sh):
- Create mock python3 returning version 3.10 in `$MOCK_DIR`, source doctor.sh, assert `check_python3` returns 1
- Create mock python3 returning version 3.12, assert `check_python3` returns 0
- Create mock python3 returning version 3.11, assert `check_python3` returns 1
- Add these tests to `test_bootstrap_venv.sh` (since doctor.sh has no own test file and the mock pattern exists there)

**Verification:** `bash plugins/iflow/mcp/test_bootstrap_venv.sh` and `bash plugins/iflow/scripts/doctor.sh` (on current system)

### T4: Add check_mcp_health() to session-start.sh

**Addresses:** R4 (AC-4.1 through AC-4.4)
**File:** `plugins/iflow/hooks/session-start.sh`
**Dependencies:** T1 (error log format must exist)

**Changes:**
1. Add `check_mcp_health()` function:
   - Early return if log file doesn't exist → empty string
   - Read log file line by line
   - Parse timestamp from each JSONL line (extract value after `"timestamp":"`)
   - Convert to epoch: `date -jf '%Y-%m-%dT%H:%M:%SZ' "$ts" +%s 2>/dev/null` (BSD macOS). Python fallback uses `datetime.strptime(ts, '%Y-%m-%dT%H:%M:%SZ')` (3.9+ compatible — NOT `fromisoformat` which doesn't support timezone suffixes until 3.11).
   - Compare: `current_epoch - entry_epoch < 600` (10 minutes)
   - Collect recent error messages
   - Truncation: write entries < 1 hour to temp file in `~/.claude/iflow/` (same filesystem for atomic mv), then `mv` to replace log. If mv fails, silently skip.
   - **Error resilience:** Wrap entire function body so failures don't crash session-start (which has `set -euo pipefail`). Pattern: `local result; result=$( ... ) 2>/dev/null || result=""`. Session-start must never fail — a missing health warning is acceptable, a broken hook is not.
   - Return formatted warning text or empty string

2. Update `main()`:
   - Call `check_mcp_health()` before `build_context()` and `build_memory_context()`
   - Prepend result to `full_context` if non-empty

**Tests:** Add to hook tests:
- Create mock error log with recent entry → verify warning emitted
- Create mock error log with old entry → verify no warning, entry truncated
- No log file → verify no warning, no error

**Verification:** `bash plugins/iflow/hooks/tests/test-hooks.sh`

### T5: Enhance check_mcp_available() in meta-json-guard.sh

**Addresses:** R6 (AC-6.1 through AC-6.7)
**File:** `plugins/iflow/hooks/meta-json-guard.sh`
**Dependencies:** T1 (sentinel format must exist)

**Changes:**
1. Enhance `check_mcp_available()`:
   - Find sentinel via existing glob pattern
   - Read content: `IFS=: read -r interp_path interp_version < "$sentinel_file"`
   - If content present (non-empty interp_path):
     - Check `[ -x "$interp_path" ]`
     - Parse version: `major="${interp_version%%.*}"; minor="${interp_version#*.}"`
     - Check version too low: `[ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 12 ]; }` (doctor.sh pattern, Bash 3.2 compatible). This correctly accepts Python 4.0+ (major > 3).
     - Version OK → return 0; version too low → return 1
   - If content empty (legacy sentinel):
     - Check mtime < 24h: `find "$sentinel_file" -mmin -1440 -print 2>/dev/null`
     - Recent → return 0; stale → return 1
   - If no sentinel → return 1

2. Update `log_guard_event()`: add "permit-degraded-stale-sentinel" action for stale/invalid sentinel cases

**Tests:** Add to hook tests or create dedicated test:
- Sentinel with valid content (existing python, version OK) → guard blocks
- Sentinel with invalid content (removed python) → guard permits
- Sentinel with invalid content (version 3.9) → guard permits
- Empty sentinel, mtime < 24h → guard blocks
- Empty sentinel, mtime > 24h → guard permits
- No sentinel → guard permits

**Verification:** `bash plugins/iflow/hooks/tests/test-hooks.sh`

### T6: Strengthen first-run detection in session-start.sh

**Addresses:** R5 (AC-5.1, AC-5.2)
**File:** `plugins/iflow/hooks/session-start.sh`
**Dependencies:** T4 (ordering in main() must be established)

**Changes:**
1. Move first-run detection from `build_session_context()` (line 272) to `main()` — evaluate before `build_context()`
2. Update wording: "First run detected..." → "Setup required for MCP workflow tools. Run: bash \"{PLUGIN_ROOT}/scripts/setup.sh\""
3. Prepend to `full_context` (same pattern as check_mcp_health result)

**Tests:** Verify in hook test:
- Missing .venv → setup message appears before feature context
- .venv exists → no setup message

**Verification:** `bash plugins/iflow/hooks/tests/test-hooks.sh`

### T7: Regression verification and test cleanup

**Addresses:** All requirements (regression safety)
**Dependencies:** T1-T6 all complete

**Changes:**
1. Run full existing test suites:
   - `bash plugins/iflow/mcp/test_bootstrap_venv.sh`
   - `bash plugins/iflow/hooks/tests/test-hooks.sh`
   - `bash plugins/iflow/mcp/test_run_memory_server.sh`
2. Fix any regressions
3. Verify on current system: MCP servers start correctly after changes
4. Verify doctor.sh passes on current system

**Verification:** All test commands above pass with zero failures.

## Dependency Graph

```
T0 (baseline) → must run first
 ↓
T1 (discover_python + write_sentinel + log_error)
├── T2 (callsite updates) → depends on T1
├── T4 (session-start health check) → depends on T1 (log format)
└── T5 (meta-json-guard sentinel) → depends on T1 (sentinel format)

T3 (doctor.sh threshold) → independent, can run after T0

T6 (first-run detection) → depends on T4 (same file, ordering dependency)

T7 (regression) → depends on T1-T6
```

## Parallelization Opportunities

- T3 can run in parallel with T1/T2 (independent file)
- T4 and T5 can run in parallel after T1 (different files, both depend only on T1's formats)
- T4 and T6 must be sequential (both modify session-start.sh, T6 depends on T4's main() ordering)
