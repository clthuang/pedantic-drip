# Tasks: MCP Stale Lock Prevention

## Phase 1: Shared Infrastructure

### Task 1.1: Create server_lifecycle.py with TDD tests

**Status:** pending
**Files:** `plugins/pd/mcp/server_lifecycle.py` (CREATE), `plugins/pd/mcp/test_server_lifecycle.py` (CREATE)
**Dependencies:** none
**Parallel group:** A

**Steps:**
1. Create `test_server_lifecycle.py` with all test cases (RED phase):
   - `test_write_pid_creates_file` — write PID, read file, assert contains `str(os.getpid())`
   - `test_write_pid_creates_directory` — use tmp dir, verify `os.makedirs` called
   - `test_write_pid_overwrites_stale` — write fake PID, call write_pid, verify overwritten
   - `test_remove_pid_deletes_file` — write PID file, call remove_pid, verify file gone
   - `test_remove_pid_noop_missing` — call remove_pid on non-existent file, no exception
   - `test_read_pid_returns_value` — write PID file, call read_pid, verify int returned
   - `test_read_pid_returns_none_missing` — call read_pid on non-existent, verify None
   - `test_read_pid_returns_none_invalid` — write "abc" to PID file, verify None
   - `test_parent_watchdog_calls_exit_on_ppid_change` — use `poll_interval=0.05`, mock `os.getppid` to return changed value after first call, use `threading.Event` with 2s timeout to wait for `_exit_fn` call
   - `test_parent_watchdog_noop_same_ppid` — mock `os.getppid` to return same value, sleep 0.2s, verify `_exit_fn` NOT called
   - `test_lifetime_watchdog_calls_exit_after_timeout` — use `max_seconds=0.1`, `threading.Event` with 2s timeout, verify `_exit_fn` called
   - `test_watchdog_threads_are_daemon` — start both watchdogs, assert `thread.daemon is True`
2. Create `server_lifecycle.py` implementing all functions (GREEN phase):
   - `PID_DIR = Path(os.path.expanduser("~/.claude/pd/run"))`
   - `write_pid(server_name)` — makedirs, write `os.getpid()`, return Path
   - `remove_pid(server_name)` — unlink with `missing_ok=True`
   - `read_pid(server_name)` — read file, return `int(content)` or None
   - `start_parent_watchdog(poll_interval=10.0, _exit_fn=os._exit)` — record `os.getppid()`, poll in daemon thread, call `_exit_fn(0)` on change
   - `start_lifetime_watchdog(max_seconds=86400, _exit_fn=os._exit)` — sleep in daemon thread, call `_exit_fn(0)` after timeout
3. Run tests: `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_server_lifecycle.py -v`
4. All 12 tests pass

**Done when:** All 12 tests pass, zero failures

---

### Task 1.2: Refactor backfill.py — replace run_backfill raw SQL

**Status:** pending
**Files:** `plugins/pd/hooks/lib/entity_registry/backfill.py` (MODIFY)
**Dependencies:** none
**Parallel group:** A

**Steps:**
1. Read `backfill.py` lines 140-155 (run_backfill tail)
2. Replace lines 145-149 with:
   ```python
   with db.transaction():
       all_phases = db.list_workflow_phases()
       for row in all_phases:
           if row["workflow_phase"] is None:
               try:
                   db.update_workflow_phase(row["type_id"], workflow_phase="finish")
               except ValueError:
                   pass  # TOCTOU: row deleted between list and update
   ```
3. Run existing tests: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v`
4. All tests pass

Note: run_backfill operates on a small set (only rows with workflow_phase IS NULL), so a single transaction is acceptable. The 20-entity batching in `_chunked` applies only to `backfill_workflow_phases` (Task 1.4).

**Done when:** Lines 145-149 use `db.list_workflow_phases()` + `db.update_workflow_phase()`, no `db._conn.execute` or `db._conn.commit` in this section

---

### Task 1.3: Refactor backfill.py — replace backfill_workflow_phases reads

**Status:** pending
**Files:** `plugins/pd/hooks/lib/entity_registry/backfill.py` (MODIFY)
**Dependencies:** Task 1.2
**Parallel group:** A

**Steps:**
1. Read `backfill.py` lines 220-230 (SELECT query)
2. Read `database.py:2145` — verify `get_workflow_phase(type_id)` returns a dict with key `"workflow_phase"` (same key name as the raw fetchone Row access at line 229)
3. Replace line 224 `db._conn.execute("SELECT ...")` with `existing_row = db.get_workflow_phase(type_id)` — returns dict or None, same access pattern (`existing_row["workflow_phase"]`)
4. Run tests: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v`
5. All tests pass

**Done when:** Line 224 uses `db.get_workflow_phase(type_id)` instead of raw SQL, access pattern `existing_row["workflow_phase"]` confirmed working, tests pass

---

### Task 1.4: Refactor backfill.py — replace backfill_workflow_phases writes with batching

**Status:** pending
**Files:** `plugins/pd/hooks/lib/entity_registry/backfill.py` (MODIFY)
**Dependencies:** Task 1.3
**Parallel group:** A

**Steps:**
1. Add `_chunked(iterable, size)` helper at module level
2. Read lines 234-347 (the entity processing loop + commit)
3. Replace Case 3 (line 247, existing row with NULL phase) `db._conn.execute("UPDATE ...")` with `db.update_workflow_phase(type_id, workflow_phase=..., kanban_column=...)`
4. Replace Case 1 brainstorm/backlog (line 256) `db._conn.execute("INSERT OR IGNORE ...")` with `db.upsert_workflow_phase(type_id, workflow_phase=..., kanban_column=...)`
5. Preserve the feature-specific derivation logic (lines 270-335: status derivation from meta/entity/default, workflow_phase from `_derive_next_phase`, completed status override, mode from meta, kanban_column from `derive_kanban`) — this business logic stays inline, only the final SQL execution changes
6. Replace feature INSERT OR IGNORE (line 336) `db._conn.execute(insert_sql, params)` with `db.upsert_workflow_phase(type_id, workflow_phase=workflow_phase, kanban_column=kanban_column, last_completed_phase=last_completed_phase, mode=mode)`
7. Remove `db._now_iso()` calls (public API sets timestamps internally)
8. Remove `db._conn.commit()` at line 347
9. Wrap entity loop in `for batch in _chunked(entities, 20): with db.transaction():`
10. Run tests: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v`
11. Verify: `grep -n 'db._conn.execute\|db._conn.commit\|db._now_iso' plugins/pd/hooks/lib/entity_registry/backfill.py` returns zero matches

**Done when:** Zero `db._conn` references in backfill.py, all entity registry tests pass

---

### Task 1.5: Add backfill batch verification test

**Status:** pending
**Files:** `plugins/pd/hooks/lib/entity_registry/backfill.py` test file (MODIFY)
**Dependencies:** Task 1.4
**Parallel group:** A

**Steps:**
1. Add `test_backfill_no_raw_conn_execute` — grep backfill.py source for `db._conn.execute`, assert zero matches
2. Add `test_backfill_batched_transactions` — create 25 mock entities, instrument `db.transaction()` call count, verify 2 batches (ceil(25/20))
3. Run: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v -k "batch or raw_conn"`

**Done when:** Both new tests pass

---

## Phase 2: Server Integration

### Task 2.1: Migrate entity_server to server_lifecycle + add watchdog

**Status:** pending
**Files:** `plugins/pd/mcp/entity_server.py` (MODIFY)
**Dependencies:** Task 1.1
**Parallel group:** B

**Steps:**
1. Read `entity_server.py` — locate `_write_pid()`, `_remove_pid()`, `_PID_DIR`, and their usage in `lifespan()`
2. Delete `_write_pid()`, `_remove_pid()`, `_PID_DIR` constant
3. Add import: `from server_lifecycle import write_pid, remove_pid, start_parent_watchdog`
4. In `lifespan()`, insert after `os.makedirs` (line ~83) but BEFORE `EntityDatabase()` call (line ~85): add `write_pid("entity_server")` and `start_parent_watchdog()`. This ensures orphan protection even if DB init hangs
5. In `lifespan()` finally block: replace `_remove_pid()` with `remove_pid("entity_server")`
6. Run: `bash plugins/pd/mcp/test_entity_server.sh`
7. Verify: `grep -n '_write_pid\|_remove_pid\|_PID_DIR' plugins/pd/mcp/entity_server.py` returns zero matches

**Done when:** Local PID functions removed, server_lifecycle imports used, watchdog starts before DB init (verify by reading lifespan code order), bootstrap test passes

---

### Task 2.2: Migrate workflow_state_server to server_lifecycle + add watchdog

**Status:** pending
**Files:** `plugins/pd/mcp/workflow_state_server.py` (MODIFY)
**Dependencies:** Task 1.1
**Parallel group:** B

**Steps:**
1. Read `workflow_state_server.py` — locate `_write_pid()`, `_remove_pid()`, `_PID_DIR`
2. Delete local PID functions and constant
3. Add import: `from server_lifecycle import write_pid, remove_pid, start_parent_watchdog`
4. In `lifespan()`, add as FIRST operations: `write_pid("workflow_state_server")` and `start_parent_watchdog()`
5. In `lifespan()` finally: replace with `remove_pid("workflow_state_server")`
6. Update `TestPIDFileLifecycle` tests to use `server_lifecycle` imports
7. Run: `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k PID`

**Done when:** Local PID functions removed, server_lifecycle used, PID tests updated and passing

---

### Task 2.3: Add PID management + watchdog to memory_server

**Status:** pending
**Files:** `plugins/pd/mcp/memory_server.py` (MODIFY)
**Dependencies:** Task 1.1
**Parallel group:** B

**Steps:**
1. Read `memory_server.py` — locate `lifespan()` function
2. Add import: `from server_lifecycle import write_pid, remove_pid, start_parent_watchdog`
3. In `lifespan()`, add as FIRST operations: `write_pid("memory_server")` and `start_parent_watchdog()`
4. In `lifespan()` finally: add `remove_pid("memory_server")`
5. Run: `bash plugins/pd/mcp/test_run_memory_server.sh`

**Done when:** PID file written on startup, watchdog running, bootstrap test passes

---

### Task 2.4: Add PID management + lifetime watchdog to UI server

**Status:** pending
**Files:** `plugins/pd/ui/__main__.py` (MODIFY)
**Dependencies:** Task 1.1
**Parallel group:** B

**Steps:**
1. Read `plugins/pd/ui/__main__.py`
2. Add `import os` to imports (currently missing — file only imports argparse, socket, sys, uvicorn)
3. Add sys.path manipulation: `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcp'))`
4. Add import: `from server_lifecycle import write_pid, remove_pid, start_lifetime_watchdog`
5. Add `import atexit`
6. In `main()` before `uvicorn.run()`: add `write_pid("ui_server")`, `start_lifetime_watchdog(86400)`, `atexit.register(remove_pid, "ui_server")`
7. Verify import works from actual launch context: `cd plugins/pd && python -c "import sys; sys.path.insert(0, 'mcp'); from server_lifecycle import write_pid; print('OK')"`
8. Run: `PYTHONPATH="plugins/pd/hooks/lib:plugins/pd" plugins/pd/.venv/bin/python -m pytest plugins/pd/ui/tests/ -v`

**Done when:** PID file written before uvicorn starts, lifetime watchdog running, import verified, tests pass

---

## Phase 3: Degraded Mode

### Task 3.1: Add degraded mode to entity_server — tests first

**Status:** pending
**Files:** `plugins/pd/mcp/test_entity_server_degraded.py` (CREATE)
**Dependencies:** Task 2.1
**Parallel group:** C

**Steps:**
1. Create `test_entity_server_degraded.py` with tests:
   - `test_degraded_mode_on_db_lock` — mock EntityDatabase constructor to raise `sqlite3.OperationalError("database is locked")`, verify `_db_unavailable is True` after `_init_db_with_retry()`
   - `test_degraded_tool_returns_error` — set `_db_unavailable = True`, call a tool handler, verify returns `{"error": "database temporarily unavailable"}`
   - `test_recovery_thread_recovers` — mock EntityDatabase to fail once then succeed, use `poll_interval=0.1`, verify `_db_unavailable` becomes False within 1s
   - `test_retry_backoff_is_flat` — mock `time.sleep`, call `_init_db_with_retry`, verify sleep called with 2.0 each time (not exponential)
   - `test_recovery_logs_backfill_skipped` — verify recovery thread logs "backfill skipped" message
2. Run tests (should fail — RED): `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_entity_server_degraded.py -v`

**Done when:** Test file created with 5 test cases, all fail (RED phase)

---

### Task 3.2: Implement degraded mode in entity_server

**Status:** pending
**Files:** `plugins/pd/mcp/entity_server.py` (MODIFY)
**Dependencies:** Task 3.1
**Parallel group:** C

**Steps:**
1. Add module-level: `_db_unavailable: bool = False`
2. Implement `_init_db_with_retry(db_path, max_retries=3, backoff_seconds=2.0)`:
   - Loop max_retries times, catch OperationalError, sleep backoff_seconds (flat), return None on exhaustion
3. Implement `_start_recovery_thread(db_path, poll_interval=30.0)`:
   - Daemon thread, retry EntityDatabase() every poll_interval
   - On success: set global `_db`, clear `_db_unavailable`, log "DB recovered — backfill skipped", exit thread
4. Implement `_check_db_available()` helper — returns error dict if `_db_unavailable`
5. Add `_check_db_available()` guard at top of ALL tool handlers (enumerate: register_entity, update_entity, get_entity, search_entities, get_lineage, export_entities, add_dependency, query_dependencies, delete_entity, etc.)
6. Modify `lifespan()`: replace `EntityDatabase()` with `_init_db_with_retry()`, start recovery thread on failure
7. Run tests: `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_entity_server_degraded.py -v`
8. All 5 tests pass (GREEN)

**Done when:** All degraded mode tests pass, every tool handler has `_check_db_available()` guard

---

### Task 3.3: Add degraded mode to workflow_state_server

**Status:** pending
**Files:** `plugins/pd/mcp/workflow_state_server.py` (MODIFY)
**Dependencies:** Task 2.2
**Parallel group:** C

**Steps:**
1. Read `workflow_state_server.py` — locate the existing module-level `degraded` variable (used for meta_json_fallback). Confirm it uses the name `degraded`, not `_db_unavailable`. Verify no existing `_db_unavailable` in the file via grep
2. Add module-level: `_db_unavailable: bool = False` (distinct from existing `degraded` flag)
3. Implement same `_init_db_with_retry`, `_start_recovery_thread`, `_check_db_available` pattern
4. Add `_check_db_available()` guard to all EntityDatabase-dependent tool handlers
5. Modify `lifespan()` DB init to use retry pattern
6. Add `TestDegradedMode` class to existing `test_workflow_state_server.py`:
   - `test_degraded_mode_on_db_lock`
   - `test_degraded_tool_returns_error`
   - `test_recovery_thread_recovers`
7. Run: `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k degraded`

**Done when:** Degraded mode tests pass, `_db_unavailable` flag distinct from existing `degraded`

---

## Phase 4: Session-Start Cleanup + Doctor

### Task 4.1: Add cleanup_stale_mcp_servers to session-start.sh

**Status:** pending
**Files:** `plugins/pd/hooks/session-start.sh` (MODIFY)
**Dependencies:** Task 1.1
**Parallel group:** D

**Steps:**
1. Read `session-start.sh` — locate where `run_doctor_autofix()` and `check_mcp_health()` are called
2. Implement `cleanup_stale_mcp_servers()` function:
   ```bash
   cleanup_stale_mcp_servers() {
     local pid_dir="$HOME/.claude/pd/run"
     [[ -d "$pid_dir" ]] || return 0
     for pid_file in "$pid_dir"/*.pid; do
       [[ -f "$pid_file" ]] || continue
       local pid=$(cat "$pid_file" 2>/dev/null)
       [[ -n "$pid" ]] || { rm -f "$pid_file"; continue; }
       if ! kill -0 "$pid" 2>/dev/null; then
         rm -f "$pid_file"; continue
       fi
       # Verify it's a Python process
       local comm=$(ps -o comm= -p "$pid" 2>/dev/null)
       echo "$comm" | grep -iq python || continue
       # Check if orphaned (PPID=1)
       local ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
       [[ "$ppid" == "1" ]] || continue
       # Kill orphan: SIGTERM, wait 5s, SIGKILL
       kill -TERM "$pid" 2>/dev/null
       sleep 5
       kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
       rm -f "$pid_file"
     done
     # lsof fallback
     if command -v lsof >/dev/null 2>&1; then
       # Find Python processes with PPID=1 holding DB files
       lsof "$HOME/.claude/pd/entities/entities.db" "$HOME/.claude/pd/memory/memory.db" 2>/dev/null | \
         awk 'NR>1{print $2}' | sort -u | while read -r pid; do
           local ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
           [[ "$ppid" == "1" ]] || continue
           local comm=$(ps -o comm= -p "$pid" 2>/dev/null)
           echo "$comm" | grep -iq python || continue
           kill -TERM "$pid" 2>/dev/null
           sleep 5
           kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
         done
     fi
   }
   ```
3. Call `cleanup_stale_mcp_servers` BEFORE `run_doctor_autofix` and `check_mcp_health`
4. Ensure all subcommands have stderr suppressed (2>/dev/null)
5. Run hook test: `bash plugins/pd/hooks/tests/test-hooks.sh`

**Done when:** Function added, called before doctor/health, hook tests pass

---

### Task 4.2: Create session-start cleanup integration test

**Status:** pending
**Files:** `plugins/pd/hooks/tests/test_session_start_cleanup.sh` (CREATE)
**Dependencies:** Task 4.1
**Parallel group:** D

**Steps:**
1. Create test script with cases:
   - Test 1: Write stale PID file (non-running PID), source cleanup function, verify file removed
   - Test 2: Missing PID directory → function returns 0 (no error)
   - Test 3: PID file with invalid content → file removed
   - Test 4: PID file with running non-orphaned process → file NOT removed
2. Run: `bash plugins/pd/hooks/tests/test_session_start_cleanup.sh`

**Done when:** All 4 test cases pass

---

### Task 4.3: Enhance doctor lock diagnostic with holder identification

**Status:** pending
**Files:** `plugins/pd/hooks/lib/doctor/checks.py` (MODIFY)
**Dependencies:** none
**Parallel group:** D

**Steps:**
1. Read `checks.py` — locate `_test_db_lock()` function
2. Add `_identify_lock_holders(db_path: str) -> list[str]` (see design.md lines 459-476 for exact interface):
   - Scan `~/.claude/pd/run/*.pid` for running processes: for each file, read PID, check alive via `os.kill(pid, 0)`, get PPID via `subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)])`, extract server_name from filename (e.g., `entity_server.pid` → `entity_server`)
   - Format each as `"PID {pid} ({server_name}, PPID={ppid})"`
   - Try `lsof` via `subprocess.run(["lsof", db_path])` as fallback — parse output for additional PIDs not covered by PID files
   - Return list of holder descriptions, empty list if none found
3. Modify `_test_db_lock()`: on lock detected, call `_identify_lock_holders()`, include results in Issue message. Format: `"entities.db write lock held by PID 1234 (entity_server, orphaned)"` or fallback `"entities.db write lock held — lock holder unknown, check ~/.claude/pd/run/"`
4. Add tests to doctor test suite:
   - `test_lock_holder_identified_via_pid_file` — create mock PID file in tmp dir, mock `os.kill` to succeed, verify holder description contains PID and server_name
   - `test_lock_holder_identified_via_lsof` — mock `subprocess.run` to return lsof output with PID, verify holder found
   - `test_lock_holder_unknown_fallback` — empty PID dir, mock lsof unavailable (`FileNotFoundError`), verify empty list returned
5. Run: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v -k lock_holder`

**Done when:** Lock diagnostic shows holder PID info, 3 new tests pass, existing doctor tests still pass

---

## Phase 5: Verification

### Task 5.1: End-to-end acceptance verification

**Status:** pending
**Files:** none (verification only)
**Dependencies:** all previous tasks
**Parallel group:** E

**Steps:**
1. `grep -n 'db._conn.execute\|db._conn.commit' plugins/pd/hooks/lib/entity_registry/backfill.py` → zero matches
2. Run all test suites (9 commands):
   - `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_server_lifecycle.py -v`
   - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v`
   - `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_entity_server_degraded.py -v`
   - `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v`
   - `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v`
   - `bash plugins/pd/hooks/tests/test_session_start_cleanup.sh`
   - `bash plugins/pd/mcp/test_entity_server.sh`
   - `bash plugins/pd/mcp/test_run_memory_server.sh`
   - `PYTHONPATH="plugins/pd/hooks/lib:plugins/pd" plugins/pd/.venv/bin/python -m pytest plugins/pd/ui/tests/ -v`
3. Verify all pass with zero failures

**Done when:** All test suites pass, grep verification confirms zero raw SQL in backfill.py

---

## Summary

- **15 tasks** across **5 phases**
- **5 parallel groups** (A, B, C, D, E)
- Group A: Tasks 1.1-1.5 (sequential within group)
- Group B: Tasks 2.1-2.4 (all parallel, depend on 1.1)
- Group C: Tasks 3.1-3.3 (3.1→3.2 sequential, 3.3 parallel with 3.1-3.2)
- Group D: Tasks 4.1-4.3 (4.1→4.2 sequential, 4.3 parallel)
- Group E: Task 5.1 (depends on all)
