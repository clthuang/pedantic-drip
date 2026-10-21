# Tasks: SQLite Write Contention Fix

## Phase 1: Database Layer (Steps 1-3)

### Task 1.1: Add _in_transaction flag to EntityDatabase.__init__
- **Action:** Edit `plugins/pd/hooks/lib/entity_registry/database.py`: Add `self._in_transaction = False` as the FIRST line of `__init__()` (before `self._conn = sqlite3.connect(...)`)
- **Done when:** `grep -n "_in_transaction = False" plugins/pd/hooks/lib/entity_registry/database.py` returns 1 match inside `__init__`

### Task 1.2: Add _commit() helper method
- **Action:** Edit `plugins/pd/hooks/lib/entity_registry/database.py`: Add method after `close()`:
  ```python
  def _commit(self):
      """Commit unless inside an explicit transaction()."""
      if not self._in_transaction:
          self._conn.commit()
  ```
- **Depends on:** Task 1.1
- **Done when:** `grep -n "def _commit" plugins/pd/hooks/lib/entity_registry/database.py` returns 1 match

### Task 1.3: Replace self._conn.commit() with self._commit() in instance methods
- **Action:** Edit `plugins/pd/hooks/lib/entity_registry/database.py`: Replace all 19 `self._conn.commit()` calls in instance methods with `self._commit()`. Do NOT change the 6 `conn.commit()` calls in module-level migration functions (they use `conn` parameter, not `self._conn`).
- **Depends on:** Task 1.2
- **Done when:** `grep -c "self._conn.commit()" plugins/pd/hooks/lib/entity_registry/database.py` returns 0. `grep -c "self._commit()" plugins/pd/hooks/lib/entity_registry/database.py` returns >= 19. `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -x --tb=short` passes.

### Task 1.4: Add transaction() context manager
- **Action:** Edit `plugins/pd/hooks/lib/entity_registry/database.py`: Add `transaction()` method after `begin_immediate()` per plan Step 2 code. Includes nested guard (`RuntimeError`), pre-flush `self._conn.commit()`, BEGIN IMMEDIATE, ROLLBACK suppression in except.
- **Depends on:** Task 1.3
- **Done when:** `grep -n "def transaction" plugins/pd/hooks/lib/entity_registry/database.py` returns 1 match. `grep -c "self._conn.commit()" plugins/pd/hooks/lib/entity_registry/database.py` returns 1 (the flush in transaction()). All existing entity registry tests pass.

### Task 1.5: Write tests for _commit() and transaction()
- **Action:** Edit `plugins/pd/hooks/lib/entity_registry/test_database.py`: Add 5 tests: `test_commit_outside_transaction`, `test_commit_suppressed_inside_transaction`, `test_transaction_commits_on_success`, `test_transaction_rolls_back_on_exception`, `test_transaction_nested_raises_runtime_error`
- **Depends on:** Task 1.4
- **Done when:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "transaction or _commit"` — all 5 tests pass

### Task 1.6: Increase busy_timeout to 15000ms
- **Action:** Edit `plugins/pd/hooks/lib/entity_registry/database.py`: In `_set_pragmas()`, change `PRAGMA busy_timeout = 5000` → `PRAGMA busy_timeout = 15000`
- **Done when:** `grep "busy_timeout" plugins/pd/hooks/lib/entity_registry/database.py` shows 15000

## Phase 2: MCP Server Layer (Steps 4-8)

### Task 2.1: Write tests for atomic transaction wrapping (TDD RED)
- **Action:** Edit `plugins/pd/mcp/test_workflow_state_server.py`: Add 4 tests:
  1. `test_transition_phase_atomic_rollback` — mock db.update_workflow_phase to raise OperationalError; assert entity metadata NOT persisted
  2. `test_complete_phase_atomic_rollback` — same for complete_phase
  3. `test_transition_phase_degraded_raises_inside_transaction` — mock engine to return degraded=True; assert OperationalError raised
  4. `test_project_meta_json_called_after_transaction` — verify _project_meta_json called OUTSIDE transaction
- **Done when:** Tests exist and `pytest -k "atomic"` exits with FAILED (not ERROR)

### Task 2.2: Write tests for retry decorator (TDD RED)
- **Action:** Edit `plugins/pd/mcp/test_workflow_state_server.py`: Add 7 tests:
  1. `test_retry_succeeds_after_transient_error`
  2. `test_retry_exhausted_raises`
  3. `test_retry_permanent_error_not_retried`
  4. `test_is_transient_locked` — True
  5. `test_is_transient_table_locked` — True
  6. `test_is_transient_sql_logic_error` — False
  7. `test_retry_logs_to_stderr`
- **Done when:** Tests exist and `pytest -k "retry or transient"` exits with FAILED (not ERROR)

### Task 2.3: Wrap _process_transition_phase in db.transaction() (TDD GREEN)
- **Action:** Edit `plugins/pd/mcp/workflow_state_server.py`: Restructure `_process_transition_phase()`:
  1. When `db is not None`: wrap both engine paths (entity_engine + engine fallback) inside `with db.transaction():`
  2. After engine call, if `response.degraded`: raise `sqlite3.OperationalError("engine returned degraded=True inside transaction")`
  3. Move `db.update_entity()` + `db.update_workflow_phase()` inside transaction
  4. Move `_project_meta_json()` OUTSIDE transaction (after `with` block)
  5. Keep `else` branch (no db) unchanged
- **Depends on:** Tasks 1.4, 2.1
- **Done when:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k "atomic" --tb=short` — all atomic tests pass

### Task 2.4: Wrap _process_complete_phase in db.transaction() (TDD GREEN)
- **Action:** Edit `plugins/pd/mcp/workflow_state_server.py`: Restructure `_process_complete_phase()`:
  1. Keep first `db.get_entity()` (line 540, for UUID resolution) OUTSIDE transaction
  2. Wrap engine call inside `with db.transaction():`
  3. Check degraded flag on completion, raise if True
  4. The second `db.get_entity()` (line 569, reads metadata for timing assembly) goes INSIDE the transaction — it reads state the engine may have modified
  5. Move `db.update_entity()` (line 595) and `db.update_workflow_phase()` (line 601) inside transaction
  6. Move `_project_meta_json()` (line 604) OUTSIDE transaction (after `with` block)
- **Depends on:** Tasks 1.4, 2.1
- **Done when:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k "complete.*atomic" --tb=short` — tests pass

### Task 2.5: Add _is_transient() and _with_retry() (TDD GREEN)
- **Action:** Edit `plugins/pd/mcp/workflow_state_server.py`:
  1. Add `import time, random` at top
  2. Add `_is_transient(exc)`: `return "locked" in str(exc).lower()`
  3. Add `_with_retry(max_attempts=3, backoff=(0.1, 0.5, 2.0))` decorator with safe indexing (`min(attempt, len(backoff)-1)`), jitter, and stderr logging
- **Depends on:** Task 2.2
- **Done when:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k "retry or transient" --tb=short` — all 7 retry tests pass

### Task 2.6: Apply @_with_retry to 9 write-path functions
- **Action:** Edit `plugins/pd/mcp/workflow_state_server.py`: Add `@_with_retry()` to 9 functions with correct stacking:
  - Functions with `@_catch_value_error`: `@_with_error_handling` / `@_with_retry()` / `@_catch_value_error` — applies to: `_process_transition_phase`, `_process_complete_phase`, `_process_init_feature_state`, `_process_init_project_state`, `_process_activate_feature`
  - Functions with `@_catch_entity_value_error`: same stacking — applies to: `_process_init_entity_workflow`, `_process_transition_entity_phase`
  - Functions without value error decorator: `@_with_error_handling` / `@_with_retry()` — applies to: `_process_reconcile_apply`, `_process_reconcile_frontmatter`
- **Depends on:** Task 2.5
- **Done when:** `grep -c "@_with_retry" plugins/pd/mcp/workflow_state_server.py` returns 9. All existing workflow state server tests pass.

## Phase 3: Observability (Step 9)

### Task 3.1: Write PID file tests
- **Action:** Edit `plugins/pd/mcp/test_workflow_state_server.py`: Add 3 tests:
  1. `test_pid_file_written_at_startup`
  2. `test_pid_file_removed_at_shutdown`
  3. `test_stale_pid_file_overwritten`
- **Done when:** Tests exist and `plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k "pid_file" --tb=short` exits with FAILED (not ERROR)

### Task 3.2: Add _write_pid and _remove_pid to workflow_state_server.py
- **Action:** Edit `plugins/pd/mcp/workflow_state_server.py`: Add `_write_pid(server_name)` and `_remove_pid(pid_path)` helper functions. Call in `lifespan()`. PID dir: `~/.claude/pd/run/`
- **Depends on:** Task 3.1
- **Done when:** `grep -c "_write_pid\|_remove_pid" plugins/pd/mcp/workflow_state_server.py` returns >= 2. PID tests pass.

### Task 3.3: Add PID monitoring to entity_server.py
- **Action:** Edit `plugins/pd/mcp/entity_server.py`: Add same `_write_pid`/`_remove_pid` pattern in its `lifespan()`
- **Depends on:** Task 3.2
- **Done when:** `grep -c "_write_pid\|_remove_pid" plugins/pd/mcp/entity_server.py` returns >= 2. Note: entity_server PID uses identical helper functions tested in Task 3.2 — no separate tests needed.

## Phase 4: Verification (Step 10)

### Task 4.1: Run full test suite
- **Action:** Run all test suites:
  ```bash
  plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v --tb=short
  plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ -v --tb=short
  plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v --tb=short
  ```
- **Depends on:** All prior tasks
- **Done when:** All test suites pass

### Task 4.2: Run AC grep verification
- **Action:** Run:
  ```bash
  # AC-1: transaction wrapper
  grep -n "BEGIN IMMEDIATE" plugins/pd/hooks/lib/entity_registry/database.py | grep transaction

  # AC-2: _commit() replacement (1 = intentional flush in transaction())
  grep -c "self._conn.commit()" plugins/pd/hooks/lib/entity_registry/database.py  # expect 1

  # AC-4: retry on 9 functions
  grep -c "@_with_retry" plugins/pd/mcp/workflow_state_server.py  # expect 9

  # AC-8: busy_timeout
  grep "busy_timeout" plugins/pd/hooks/lib/entity_registry/database.py  # expect 15000
  ```
- **Depends on:** Task 4.1
- **Done when:** All checks pass
