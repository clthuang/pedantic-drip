# Tasks: 042-mcp-bootstrap-python-discovery

## Dependency Graph

```
T0 (baseline)
 ↓
T1.1 → T1.2 → T1.3 → T1.4  (bootstrap-venv.sh new functions)
 ├── T2.1 → T2.2 → T2.3     (bootstrap-venv.sh callsite updates)
 │
 ├── T4.1 → T4.2             (session-start.sh health check)
 │    ↓
 │   T6.1                    (session-start.sh first-run)
 │
 └── T5.1 → T5.2             (meta-json-guard.sh sentinel)

T3.1                          (doctor.sh — independent, after T0)

T7.1                          (regression — depends on all above)
```

## Parallel Groups

- **Group A** (after T0): T1.1 and T3.1 can start in parallel
- **Group B** (after T1.4): T2.1, T4.1, and T5.1 can start in parallel (different files; T4/T5 only need T1's log/sentinel formats)
- **Sequential**: T4 → T6 (same file)

---

## T0: Baseline

### T0.1: Run baseline test suites
- [ ] Run `bash plugins/iflow/mcp/test_bootstrap_venv.sh` — record pass/fail count
- [ ] Run `bash plugins/iflow/hooks/tests/test-hooks.sh` — record pass/fail count
- **Done when:** Both suites run, pre-existing failures (if any) documented

---

## T1: New functions in bootstrap-venv.sh

### T1.1: Add log_bootstrap_error()
- [ ] Add function after the Constants section in `plugins/iflow/mcp/bootstrap-venv.sh`
- [ ] Arguments: `$1` server_name, `$2` error_type, `$3` message, `$4` extra_json (optional)
- [ ] Create log dir: `mkdir -p "$HOME/.claude/iflow"`
- [ ] Timestamp: `date -u +%Y-%m-%dT%H:%M:%SZ`
- [ ] Write JSONL line: `echo "{\"timestamp\":\"$ts\",\"server\":\"$server_name\",\"error\":\"$error_type\",\"message\":\"$msg\"${extra_json:+,$extra_json}}" >> "$LOG_FILE"`
- [ ] Add `BOOTSTRAP_ERROR_LOG="$HOME/.claude/iflow/mcp-bootstrap-errors.log"` constant
- [ ] Add test `test_log_bootstrap_error_format`: call function, verify JSONL has required fields (timestamp, server, error, message)
- **Done when:** Test passes, JSONL line is valid JSON with all required fields

### T1.2: Add write_sentinel()
- [ ] Add function in `plugins/iflow/mcp/bootstrap-venv.sh`
- [ ] Arguments: `$1` sentinel_path, `$2` python_path
- [ ] Get version: `"$2" -c "import sys; print('{0}.{1}'.format(sys.version_info.major, sys.version_info.minor))" 2>/dev/null`
- [ ] Write: `echo "$2:$version" > "$1"`
- [ ] Add test `test_write_sentinel_format`: call with known python path, verify content matches `<path>:<version>` pattern
- **Done when:** Test passes, sentinel file contains `<abs_path>:<major.minor>`

### T1.3: Add discover_python()
- [ ] Add function replacing `check_python_version()` in `plugins/iflow/mcp/bootstrap-venv.sh`
- [ ] Tier 1: `if command -v uv >/dev/null 2>&1; then candidate=$(uv python find --system '>=3.12' 2>/dev/null); if [ -n "$candidate" ] && [ -x "$candidate" ]; then PYTHON_FOR_VENV="$candidate"; return 0; fi; fi`
- [ ] Tier 2: Loop `for ver in python3.14 python3.13 python3.12; do candidate="/opt/homebrew/bin/$ver"; ...verify...; done`
- [ ] Tier 3: Same loop for `/usr/local/bin`
- [ ] Tier 4: `candidate=$(command -v python3 2>/dev/null || true)` — verify version >= 3.12
- [ ] Version verification for tiers 2-4: get version string, parse major/minor, check `[ "$major" -lt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -lt 12 ]; }`
- [ ] On failure: build searched array from hardcoded paths (all safe characters), call `log_bootstrap_error "$SERVER_NAME" "python_version" "Python >= 3.12 required, found $found_version" "\"found\":\"$found_version\",\"required\":\"3.12\",\"searched\":[$searched_json]"` then `exit 1`
- [ ] Set `PYTHON_FOR_VENV` as module-level variable (not exported)
- [ ] Add test `test_discover_python_uv_path`: mock uv → expects PYTHON_FOR_VENV set
- [ ] Add test `test_discover_python_manual_fallback`: no uv, mock python3.13 in /opt/homebrew/bin → expects discovery
- [ ] Add test `test_discover_python_bare_fallback`: no versioned binaries, bare python3 >= 3.12 → expects use
- [ ] Add test `test_discover_python_failure`: all < 3.12 → expects exit 1 + error log written
- **Done when:** All 4 tests pass

### T1.4: Delete check_python_version()
- [ ] Remove the `check_python_version()` function from bootstrap-venv.sh
- [ ] Verify no remaining references to `check_python_version` in the file
- [ ] Run `bash plugins/iflow/mcp/test_bootstrap_venv.sh` — all tests pass
- **Done when:** Function removed, no references, tests green

---

## T2: Update callsites in bootstrap-venv.sh

### T2.1: Reorder bootstrap_venv() flow and establish module-level variables
- [ ] Set `SENTINEL_PATH="${venv_dir}/.bootstrap-complete"` at top of bootstrap_venv() (module-level, available to all functions)
- [ ] Ensure `SERVER_NAME="$server_name"` is set BEFORE `discover_python()` call (existing line 186, must stay first)
- [ ] Move `discover_python` to Step 1 (before system python check)
- [ ] Step 3 (venv fast-path): replace `touch "$sentinel"` with `write_sentinel "$sentinel" "$PYTHON_FOR_VENV"` (sentinel recovery)
- [ ] Step 4 (locked bootstrap): replace `touch "$sentinel"` at leader path with `write_sentinel "$sentinel" "$PYTHON_FOR_VENV"`
- [ ] Step 4 (waiter self-heal): replace `touch "$sentinel"` with `write_sentinel "$sentinel" "$PYTHON_FOR_VENV"`
- [ ] Run full `bash plugins/iflow/mcp/test_bootstrap_venv.sh` — all tests pass
- **Done when:** All 3 `touch "$sentinel"` calls replaced, SENTINEL_PATH available, full test suite green

### T2.2: Update check_system_python()
- [ ] Change `check_venv_deps python3` → `check_venv_deps "$PYTHON_FOR_VENV"`
- [ ] Change `export PYTHON=python3` → `export PYTHON="$PYTHON_FOR_VENV"`
- [ ] Add `write_sentinel "$SENTINEL_PATH" "$PYTHON_FOR_VENV"` before `return 0` (SENTINEL_PATH is now set from T2.1)
- [ ] Add test `test_system_python_uses_discovered`: verify PYTHON_FOR_VENV passed to check_venv_deps
- [ ] Add test `test_sentinel_written_on_system_python`: verify sentinel exists after system python fast-path
- **Done when:** Both tests pass

### T2.3: Update create_venv()
- [ ] Change `python3 -m venv "$venv_dir"` → `"$PYTHON_FOR_VENV" -m venv "$venv_dir"`
- [ ] Change `uv venv "$venv_dir"` → `uv venv --python "$PYTHON_FOR_VENV" "$venv_dir"`
- [ ] Add test `test_create_venv_uv_uses_python_flag`: verify uv receives --python arg
- **Done when:** Test passes

---

## T3: Doctor threshold

### T3.1: Update check_python3() minimum version
- [ ] In `plugins/iflow/scripts/doctor.sh`, change `(( major < 3 || (major == 3 && minor < 10) ))` → `(( major < 3 || (major == 3 && minor < 12) ))`
- [ ] Change error message: `"python3 version ${version} < 3.10 required"` → `"python3 version ${version} < 3.12 required"`
- [ ] Add tests in `test_bootstrap_venv.sh` (co-located — doctor.sh has no dedicated test file):
  - `test_doctor_rejects_python_310`: mock python3 returning 3.10, source doctor.sh, assert `check_python3` returns 1
  - `test_doctor_rejects_python_311`: mock 3.11, assert returns 1
  - `test_doctor_accepts_python_312`: mock 3.12, assert returns 0
- [ ] Run `bash plugins/iflow/scripts/doctor.sh` on current system — verify passes
- **Done when:** 3 mock tests pass, doctor.sh passes on current system

---

## T4: Session-start health check

### T4.1: Add check_mcp_health() function
- [ ] Add to `plugins/iflow/hooks/session-start.sh`
- [ ] Early return empty string if `~/.claude/iflow/mcp-bootstrap-errors.log` doesn't exist
- [ ] Wrap body in subshell with `set +e` for error resilience: `check_mcp_health() { ( set +e; ... ) 2>/dev/null || echo ''; }`
- [ ] Parse timestamps: `date -jf '%Y-%m-%dT%H:%M:%SZ' "$ts" +%s 2>/dev/null` (BSD); fallback `python3 -c "import calendar,time; print(calendar.timegm(time.strptime('$ts','%Y-%m-%dT%H:%M:%SZ')))"` (3.9+ compatible, treats as UTC without timezone objects)
- [ ] Collect entries < 10 min old (epoch diff < 600), extract error messages
- [ ] Truncation: write entries < 1 hour to temp file in `~/.claude/iflow/`, `mv` to replace. Silently skip if mv fails.
- [ ] Format warning: `"WARNING: MCP servers failed to start. Workflow tools unavailable.\nError: {message}. Run: bash \"${PLUGIN_ROOT}/scripts/setup.sh\""`
- [ ] Add tests:
  - Mock log with recent entry → warning emitted
  - Mock log with old entry only → no warning, entry truncated
  - No log file → no warning, no error
- **Done when:** 3 tests pass, function returns warning or empty string without crashing

### T4.2: Wire check_mcp_health() into main()
- [ ] Call `check_mcp_health()` in `main()` before `build_context()` and `build_memory_context()`
- [ ] Prepend result to `full_context` if non-empty
- [ ] Run `bash plugins/iflow/hooks/tests/test-hooks.sh` — verify no regressions
- **Done when:** Warning appears first in context output when error log has recent entries

---

## T5: Enhanced sentinel in meta-json-guard

### T5.1: Enhance check_mcp_available()
- [ ] In `plugins/iflow/hooks/meta-json-guard.sh`, replace the `ls` glob with enhanced logic
- [ ] Find sentinel via existing glob, capture path: `sentinel_file=$(ls ... 2>/dev/null | head -1)`
- [ ] Read content: `IFS=: read -r interp_path interp_version < "$sentinel_file" 2>/dev/null || true`
- [ ] If content present (non-empty interp_path):
  - Guard: `[ -n "$minor" ] && [ "$minor" -eq "$minor" ] 2>/dev/null || return 1` (reject non-numeric)
  - Check `[ -x "$interp_path" ]`
  - Parse: `major="${interp_version%%.*}"; minor="${interp_version#*.}"`
  - Version check: `if [ "$major" -lt 3 ] 2>/dev/null || { [ "$major" -eq 3 ] && [ "$minor" -lt 12 ]; } 2>/dev/null; then return 1; fi`
  - Both OK → return 0
- [ ] If content empty (legacy): `find "$sentinel_file" -mmin -1440 -print 2>/dev/null | grep -q .` → return 0 (recent) or return 1 (stale)
- [ ] If no sentinel → return 1
- [ ] Add tests:
  - Valid sentinel (real python path, version OK) → returns 0
  - Invalid sentinel (removed interpreter) → returns 1
  - Invalid sentinel (version 3.9) → returns 1
  - Empty sentinel, mtime < 24h → returns 0
  - Empty sentinel, mtime > 24h → returns 1
  - No sentinel → returns 1
- **Done when:** All 6 tests pass

### T5.2: Add log_guard_event() calls for stale sentinel paths
- [ ] In `check_mcp_available()`, add `log_guard_event "$FILE_PATH" "$TOOL_NAME" "permit-degraded-stale-sentinel"` before `return 1` in these branches:
  - (a) After `[ ! -x "$interp_path" ]` — interpreter removed
  - (b) After version-too-low check — version changed
  - (c) After legacy mtime > 24h check — legacy stale sentinel
- [ ] Do NOT add to the no-sentinel branch (existing "permit-degraded" behavior unchanged)
- [ ] Verify in existing guard test that the new action appears in the log
- **Done when:** Log entries with "permit-degraded-stale-sentinel" action verified for all 3 branches

---

## T6: First-run detection

### T6.1: Move and strengthen first-run detection
- [ ] Move the first-run check from `build_session_context()` to `main()` — evaluate before `build_context()`
- [ ] Remove old check from `build_session_context()` — locate with `grep -n "First run\|iflow/memory" plugins/iflow/hooks/session-start.sh` (the block checking `! -d "$HOME/.claude/iflow/memory"` or `! -x .venv/bin/python`)
- [ ] New check in `main()`: `if [[ ! -d "$HOME/.claude/iflow/memory" ]] || [[ ! -x "${PLUGIN_ROOT}/.venv/bin/python" ]]; then ...`
- [ ] Update wording: `"Setup required for MCP workflow tools. Run: bash \"${PLUGIN_ROOT}/scripts/setup.sh\""`
- [ ] Prepend to `full_context` (same pattern as check_mcp_health)
- [ ] Add tests:
  - Missing .venv → setup message appears before feature context
  - .venv exists → no setup message
- [ ] Run `bash plugins/iflow/hooks/tests/test-hooks.sh` — no regressions
- **Done when:** 2 tests pass, setup message appears first when .venv missing

---

## T7: Regression

### T7.1: Full regression verification
- [ ] Run `bash plugins/iflow/mcp/test_bootstrap_venv.sh` — all pass
- [ ] Run `bash plugins/iflow/hooks/tests/test-hooks.sh` — all pass
- [ ] Run `bash plugins/iflow/mcp/test_run_memory_server.sh` — passes
- [ ] Run `bash plugins/iflow/mcp/test_run_workflow_server.sh` — passes
- [ ] Run `bash plugins/iflow/mcp/test_entity_server.sh` — passes
- [ ] Run `bash plugins/iflow/scripts/doctor.sh` — passes on current system
- [ ] Compare pass/fail counts with T0 baseline — no new failures
- **Done when:** All suites pass with zero new failures vs baseline
