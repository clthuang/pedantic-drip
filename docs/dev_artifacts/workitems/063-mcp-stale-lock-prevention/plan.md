# Plan: MCP Stale Lock Prevention

## Implementation Order

The plan follows a bottom-up dependency order: shared library first, then consumers, then integration points. Each phase is independently testable.

## Phase 1: Shared Infrastructure

### 1.1 Create `server_lifecycle.py` + tests

**Files:** `plugins/pd/mcp/server_lifecycle.py` (CREATE), `plugins/pd/mcp/test_server_lifecycle.py` (CREATE)

**Work:**
- Implement `write_pid()`, `remove_pid()`, `read_pid()` — PID file management in `~/.claude/pd/run/`
- Implement `start_parent_watchdog()` — daemon thread polling `os.getppid()`, calls `_exit_fn(0)` on change
- Implement `start_lifetime_watchdog()` — daemon thread that calls `_exit_fn(0)` after `max_seconds`
- Both watchdog functions accept injectable `_exit_fn` for testing

**Tests (TDD — write first):**
- `test_write_pid_creates_file` — verify file contains current PID
- `test_write_pid_creates_directory` — verify `~/.claude/pd/run/` created if missing
- `test_write_pid_overwrites_stale` — verify stale PID file is overwritten
- `test_remove_pid_deletes_file` — verify file removed
- `test_remove_pid_noop_missing` — verify no error when file doesn't exist
- `test_read_pid_returns_value` — verify correct PID returned
- `test_read_pid_returns_none_missing` — verify None for missing file
- `test_read_pid_returns_none_invalid` — verify None for non-numeric content
- `test_parent_watchdog_calls_exit_on_ppid_change` — use `poll_interval=0.05`, mock `os.getppid()` to return changed value after first call, use `threading.Event` with timeout to wait for `_exit_fn` call (avoids timing flakiness)
- `test_parent_watchdog_noop_same_ppid` — verify no exit when PPID unchanged
- `test_lifetime_watchdog_calls_exit_after_timeout` — use short timeout (0.1s), verify `_exit_fn` called
- `test_watchdog_threads_are_daemon` — verify `thread.daemon is True`

**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_server_lifecycle.py -v`

**Dependencies:** None (leaf node)

### 1.2 Refactor `backfill.py` to use public API + batched transactions

**Files:** `plugins/pd/hooks/lib/entity_registry/backfill.py` (MODIFY)

**Work:**
- `run_backfill()` lines 145-149: Replace bulk `db._conn.execute("UPDATE ...")` + `db._conn.commit()` with `db.list_workflow_phases()` → client-side filter for `workflow_phase is None` → `db.update_workflow_phase()` per row inside `db.transaction()`. Wrap each `update_workflow_phase()` in `try/except ValueError` to handle TOCTOU race where a row is deleted between list and update (acceptable given typical entity counts of 50-200)
- `backfill_workflow_phases()` line 224: Replace `db._conn.execute("SELECT ...")` with `db.get_workflow_phase(type_id)`
- `backfill_workflow_phases()` lines 247-336: Replace all `db._conn.execute()` write calls with `db.upsert_workflow_phase()` (for inserts) and `db.update_workflow_phase()` (for NULL-phase updates). Note: `upsert_workflow_phase()` auto-sets `updated_at` internally (verified in database.py:2276). Omitting `backward_transition_reason` from kwargs leaves column unchanged on UPDATE or uses column default (NULL) on INSERT — both match current behavior
- `backfill_workflow_phases()` line 347: Remove `db._conn.commit()` — transactions handle commits
- Add `_chunked()` helper function for batching
- Wrap entity processing in batches of 20 inside `db.transaction()` blocks
- Remove all `db._now_iso()` calls (public API methods set timestamps internally)

**Tests:** Existing tests in `plugins/pd/hooks/lib/entity_registry/` cover backfill behavior. Run full suite to verify no regressions. Add targeted tests:
- `test_backfill_no_raw_conn_execute` — grep-based verification that `db._conn.execute` does not appear in `backfill.py`
- `test_backfill_batched_transactions` — mock/instrument `db.transaction()` to count invocations, verify 25 entities produce 2 transaction batches (ceil(25/20) = 2)

**Verification:**
- `grep -n 'db._conn.execute\|db._conn.commit' plugins/pd/hooks/lib/entity_registry/backfill.py` returns zero matches
- `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v` — full regression suite

**Dependencies:** None (uses existing public API methods)

## Phase 2: Server Integration

### 2.1 Migrate entity_server PID management + add watchdog

**Files:** `plugins/pd/mcp/entity_server.py` (MODIFY)

**Work:**
- Remove local `_write_pid()`, `_remove_pid()` functions
- Import from `server_lifecycle`: `write_pid`, `remove_pid`, `start_parent_watchdog`
- In `lifespan()`: call `write_pid("entity_server")` and `start_parent_watchdog()` as the FIRST operations, BEFORE any DB initialization — ensures orphan protection even if DB init hangs
- In `lifespan()` finally: call `remove_pid("entity_server")`

**Tests:** Existing entity_server tests + verify PID functions no longer defined locally

**Verification:** `bash plugins/pd/mcp/test_entity_server.sh`

**Dependencies:** Phase 1.1

### 2.2 Migrate workflow_state_server PID management + add watchdog

**Files:** `plugins/pd/mcp/workflow_state_server.py` (MODIFY)

**Work:**
- Remove local `_write_pid()`, `_remove_pid()` functions
- Import from `server_lifecycle`: `write_pid`, `remove_pid`, `start_parent_watchdog`
- In `lifespan()`: call `write_pid("workflow_state_server")` and `start_parent_watchdog()` as the FIRST operations, BEFORE any DB initialization
- In `lifespan()` finally: call `remove_pid("workflow_state_server")`

**Tests:** Existing workflow_state_server tests (PID lifecycle tests in `TestPIDFileLifecycle` class) — these need updating to use `server_lifecycle` imports

**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v`

**Dependencies:** Phase 1.1

### 2.3 Add PID management + watchdog to memory_server

**Files:** `plugins/pd/mcp/memory_server.py` (MODIFY)

**Work:**
- Import from `server_lifecycle`: `write_pid`, `remove_pid`, `start_parent_watchdog`
- In `lifespan()`: call `write_pid("memory_server")` and `start_parent_watchdog()` as the FIRST operations, BEFORE any DB initialization
- In `lifespan()` finally: call `remove_pid("memory_server")`

**Tests:** Verify PID file created on startup, removed on shutdown

**Verification:** `bash plugins/pd/mcp/test_run_memory_server.sh`

**Dependencies:** Phase 1.1

### 2.4 Add PID management + lifetime watchdog to UI server

**Files:** `plugins/pd/ui/__main__.py` (MODIFY)

**Work:**
- Import `server_lifecycle` using sys.path manipulation: `sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'mcp'))` then `from server_lifecycle import write_pid, remove_pid, start_lifetime_watchdog`. Verify the import works from the UI server's actual launch context (run-ui-server.sh) — if the relative path `../mcp` doesn't resolve, adjust to absolute path resolution via `__file__`
- In `main()` before `uvicorn.run()`: call `write_pid("ui_server")`, `start_lifetime_watchdog(86400)`
- Register `atexit.register(remove_pid, "ui_server")` for best-effort cleanup
- Note: no parent watchdog (UI server is intentionally detached via `nohup ... & disown`)

**Tests:** Verify PID file created on startup

**Verification:** `PYTHONPATH="plugins/pd/hooks/lib:plugins/pd" plugins/pd/.venv/bin/python -m pytest plugins/pd/ui/tests/ -v`

**Dependencies:** Phase 1.1

## Phase 3: Degraded Mode

### 3.1 Add degraded mode to entity_server

**Files:** `plugins/pd/mcp/entity_server.py` (MODIFY), `plugins/pd/mcp/test_entity_server_degraded.py` (CREATE)

**Work:**
- Add module-level `_db_unavailable: bool = False` flag
- Implement `_init_db_with_retry(db_path, max_retries=3, backoff_seconds=2.0)` — returns `EntityDatabase | None`
- Implement `_start_recovery_thread(db_path, poll_interval=30.0)` — daemon thread retrying DB init every 30s
- Modify `lifespan()` to use `_init_db_with_retry()` instead of direct `EntityDatabase()` call
- On init failure: set `_db = None`, `_db_unavailable = True`, start recovery thread
- Add `_db_unavailable` guard to ALL tool handlers — implement as a helper function `_check_db_available()` that raises/returns error, called at the top of each handler. This reduces risk of missing a handler. Enumerate all handlers that need the guard (register_entity, update_entity, get_entity, search_entities, get_lineage, export_entities, add_dependency, etc.)
- Recovery thread: on success, set `_db = new_db`, `_db_unavailable = False`, log "DB recovered — backfill skipped, will run on next restart", thread exits. Recovery initializes DB only (no backfill) — backfill runs on next full server restart. This avoids re-introducing the hang risk that degraded mode mitigates

**Tests (TDD) in `test_entity_server_degraded.py`:**
- `test_degraded_mode_on_db_lock` — mock EntityDatabase to raise OperationalError, verify server starts with `_db_unavailable = True`
- `test_degraded_tool_returns_error` — verify tool handler returns structured error when degraded
- `test_recovery_thread_recovers` — mock DB init to fail then succeed, verify `_db_unavailable` becomes False
- `test_retry_backoff_is_flat` — verify 2s intervals, not exponential

**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_entity_server_degraded.py -v`

**Dependencies:** Phase 2.1 (entity_server already modified with watchdog)

### 3.2 Add degraded mode to workflow_state_server

**Files:** `plugins/pd/mcp/workflow_state_server.py` (MODIFY)

**Work:**
- Same pattern as 3.1 but for workflow_state_server
- Use `_db_unavailable` flag (distinct from existing `degraded` flag for meta_json_fallback)
- Add `_check_db_available()` guard to all EntityDatabase-dependent tool handlers
- Recovery thread with same 30s interval

**Tests:** Add degraded mode tests to existing `test_workflow_state_server.py` (it already has 7000+ lines of tests, so adding a new class `TestDegradedMode` is appropriate)

**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k degraded`

**Dependencies:** Phase 2.2 (workflow_state_server already modified with watchdog)

## Phase 4: Session-Start Cleanup + Doctor

### 4.1 Add `cleanup_stale_mcp_servers()` to session-start.sh

**Files:** `plugins/pd/hooks/session-start.sh` (MODIFY)

**Work:**
- Implement `cleanup_stale_mcp_servers()` function:
  - Early return if `~/.claude/pd/run/` doesn't exist
  - PID file scan: read PID, check `kill -0`, verify process is Python via `ps -o comm= -p $pid 2>/dev/null | grep -iq python` (handles Python, python3, python3.12 etc.), check PPID via `ps -o ppid=`. If comm doesn't match Python, skip — lsof fallback will catch it
  - Orphaned (PPID=1 + Python process): `kill -TERM`, `sleep 5`, `kill -9` if needed, `rm` PID file
  - Not running: `rm` stale PID file
  - Alive with real parent: skip
  - On EPERM from kill (wrong user): log warning, remove PID file (stale from our perspective)
  - lsof fallback: find Python processes with PPID=1 holding entities.db/memory.db
  - lsof unavailable: skip with stderr warning
- Call `cleanup_stale_mcp_servers` BEFORE `run_doctor_autofix()` and `check_mcp_health()`
- All stderr suppressed for hook JSON output safety

**Tests:** `plugins/pd/hooks/tests/test_session_start_cleanup.sh` (CREATE)
- Test stale PID file removal (process not running)
- Test orphaned process detection and termination
- Test non-orphaned process is not killed
- Test missing PID directory handled gracefully

**Verification:** `bash plugins/pd/hooks/tests/test_session_start_cleanup.sh`

**Dependencies:** Phase 1.1 (PID files must exist for cleanup to operate on)

### 4.2 Enhance doctor lock diagnostic

**Files:** `plugins/pd/hooks/lib/doctor/checks.py` (MODIFY)

**Work:**
- Add `_identify_lock_holders(db_path: str) -> list[str]` helper
  - Scan `~/.claude/pd/run/*.pid` for running processes
  - Attempt `lsof` on db_path for holder discovery
  - Return descriptions: `["PID 1234 (entity_server, PPID=1)", ...]`
- Modify `_test_db_lock()` to call `_identify_lock_holders()` when lock detected
- Include holder info in Issue message, or fallback message if unknown

**Tests:** Add to existing doctor test suite:
- `test_lock_holder_identified_via_pid_file` — mock PID file + running process
- `test_lock_holder_identified_via_lsof` — mock lsof output
- `test_lock_holder_unknown_fallback` — no PID files, no lsof

**Verification:** `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v`

**Dependencies:** None (reads PID files but doesn't require servers running)

## Phase 5: Verification

### 5.1 End-to-end acceptance verification

**Work:**
- Run spec acceptance criteria verification:
  - `grep -n 'db._conn.execute' plugins/pd/hooks/lib/entity_registry/backfill.py` → zero matches
  - Verify PID files written to `~/.claude/pd/run/` for all 4 servers
  - Verify parent watchdog exits within 15s of parent death (manual test)
  - Verify UI server lifetime watchdog (manual — set short timeout for testing)
  - Verify session-start cleanup kills orphaned processes
  - Verify degraded mode returns structured error
  - Verify doctor shows PID holder info on lock
- Integration check: verify batched backfill behavior under degraded recovery (backfill changes from 1.2 work correctly when entity_server recovers from degraded mode in 3.1)
- Run full test suites:
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_server_lifecycle.py -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v`
  - `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v`
  - `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/doctor/ -v`
  - `bash plugins/pd/hooks/tests/test_session_start_cleanup.sh`

**Dependencies:** All previous phases

## Dependency Graph

```
Phase 1.1 (server_lifecycle) ──┬──→ Phase 2.1 (entity_server) ──→ Phase 3.1 (entity degraded)
                               ├──→ Phase 2.2 (workflow_state) ──→ Phase 3.2 (workflow degraded)
                               ├──→ Phase 2.3 (memory_server)
                               ├──→ Phase 2.4 (UI server)
                               └──→ Phase 4.1 (session-start)

Phase 1.2 (backfill) ─────────────────────────────────────────────→ Phase 5.1 (verification)

Phase 4.2 (doctor) ───────────────────────────────────────────────→ Phase 5.1 (verification)

Parallelizable:
- Phase 1.1 and 1.2 (no shared dependencies)
- Phase 2.1, 2.2, 2.3, 2.4 (all depend only on 1.1, independent of each other)
- Phase 3.1 and 3.2 (independent, but each depends on its Phase 2 counterpart)
- Phase 4.1 and 4.2 (independent)
```

## Estimated Scope

| Phase | Tasks | Files Modified |
|-------|-------|----------------|
| 1.1 | 1 | 2 (CREATE) |
| 1.2 | 1 | 1 (MODIFY) |
| 2.1-2.4 | 4 | 4 (MODIFY) |
| 3.1-3.2 | 2 | 3 (2 MODIFY + 1 CREATE: test_entity_server_degraded.py) |
| 4.1 | 1 | 2 (MODIFY + CREATE) |
| 4.2 | 1 | 1 (MODIFY) |
| 5.1 | 1 | 0 (verification only) |
| **Total** | **11** | **13** |
