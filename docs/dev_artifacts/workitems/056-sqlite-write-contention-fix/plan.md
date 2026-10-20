# Plan: SQLite Write Contention Fix

## Execution Order

```
Phase 1: Database Layer (C1 + C2 + C5)
  Step 1: Add _commit() helper and _in_transaction flag
  Step 2: Add transaction() context manager
  Step 3: Increase busy_timeout to 15s

Phase 2: MCP Server Layer (C3 + C4)
  Step 4: Write tests for atomic transactions (TDD RED)
  Step 5: Write tests for retry decorator (TDD RED)
  Step 6: Wrap _process_transition_phase in db.transaction()
  Step 7: Wrap _process_complete_phase in db.transaction()
  Step 8: Add _with_retry decorator to 9 write-path functions

Phase 3: Observability (C6)
  Step 9: Add PID file monitoring to MCP server lifespans

Phase 4: Verification
  Step 10: Run full test suite + AC verification
```

## Dependency Graph

```
Step 1 (_commit) → Step 2 (transaction) → Steps 4-7 (atomic writes)
                                        → Step 8 (retry)
Step 3 (busy_timeout) — independent
Step 9 (PID files) — independent
Steps 4-9 → Step 10 (verification)
```

## Steps

### Step 1: Add _commit() helper and _in_transaction flag (C1)

**Files:**
- EDIT `plugins/pd/hooks/lib/entity_registry/database.py`

**Edits:**
1. In `__init__()`: add `self._in_transaction = False` as the FIRST line (before `self._conn = sqlite3.connect(...)`)
2. Add `_commit()` method after `close()`:
   ```python
   def _commit(self):
       if not self._in_transaction:
           self._conn.commit()
   ```
3. Replace all 19 `self._conn.commit()` calls in instance methods with `self._commit()`. Do NOT change the 6 `conn.commit()` calls in module-level migration functions (they receive `conn` as parameter).

**Verification:**
```bash
grep -c "self._conn.commit()" plugins/pd/hooks/lib/entity_registry/database.py  # expect 0 (becomes 1 after Step 2 adds transaction())
grep -c "self._commit()" plugins/pd/hooks/lib/entity_registry/database.py  # expect >= 19
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v --tb=short -x 2>&1 | tail -5
```

### Step 2: Add transaction() context manager (C2)

> Depends on: Step 1

**Files:**
- EDIT `plugins/pd/hooks/lib/entity_registry/database.py`

**Edits:**
1. Add `transaction()` method after `begin_immediate()`:
   ```python
   @contextmanager
   def transaction(self):
       if self._in_transaction:
           raise RuntimeError("Nested transactions not supported")
       self._conn.commit()  # flush implicit transactions
       self._conn.execute("BEGIN IMMEDIATE")
       self._in_transaction = True
       try:
           yield
           self._conn.execute("COMMIT")
       except Exception:
           try:
               self._conn.execute("ROLLBACK")
           except sqlite3.Error:
               pass
           raise
       finally:
           self._in_transaction = False
   ```

**Verification:**
```bash
grep -n "def transaction" plugins/pd/hooks/lib/entity_registry/database.py  # expect 1 match
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v --tb=short -x 2>&1 | tail -5
```

### Step 2b: Write tests for _commit() and transaction() (TDD RED)

> Depends on: Steps 1-2

**Files:**
- EDIT `plugins/pd/hooks/lib/entity_registry/test_database.py`

**Tests to add:**
1. `test_commit_outside_transaction` — `_commit()` calls `self._conn.commit()` normally
2. `test_commit_suppressed_inside_transaction` — inside `transaction()`, `_commit()` is a no-op
3. `test_transaction_commits_on_success` — data written inside transaction() is persisted after context exits
4. `test_transaction_rolls_back_on_exception` — data written inside transaction() is NOT persisted when exception raised
5. `test_transaction_nested_raises_runtime_error` — calling transaction() inside transaction() raises RuntimeError

**Done when:** All 5 tests pass (Steps 1-2 already implemented the code)

### Step 3: Increase busy_timeout (C5)

**Files:**
- EDIT `plugins/pd/hooks/lib/entity_registry/database.py`

**Edits:**
1. In `_set_pragmas()`: change `self._conn.execute("PRAGMA busy_timeout = 5000")` → `self._conn.execute("PRAGMA busy_timeout = 15000")`

**Verification:**
```bash
grep "busy_timeout" plugins/pd/hooks/lib/entity_registry/database.py  # expect 15000
```

### Step 4: Write tests for atomic transactions (TDD RED)

> Depends on: Steps 1-2

**Files:**
- EDIT `plugins/pd/mcp/test_workflow_state_server.py`

**Tests to add:**
1. `test_transition_phase_atomic_rollback` — mock `db.update_workflow_phase` to raise OperationalError after `db.update_entity` succeeds; assert entity metadata is NOT persisted (rolled back)
2. `test_complete_phase_atomic_rollback` — same pattern for complete_phase
3. `test_transition_phase_degraded_raises_inside_transaction` — mock engine to return degraded=True; assert OperationalError raised, transaction rolled back
4. `test_project_meta_json_called_after_transaction` — verify _project_meta_json called OUTSIDE the transaction (after COMMIT)
5. `test_transaction_nested_raises_runtime_error` — call db.transaction() inside db.transaction(); assert RuntimeError

**Done when:** Tests exist and FAIL (atomic wrapping not yet implemented)

### Step 5: Write tests for retry decorator (TDD RED)

> No dependencies (independent test writing step)

**Files:**
- EDIT `plugins/pd/mcp/test_workflow_state_server.py`

**Tests to add:**
1. `test_retry_succeeds_after_transient_error` — function fails with OperationalError("database is locked") on first call, succeeds on second; assert returns success
2. `test_retry_exhausted_raises` — function fails 3 times with "database is locked"; assert OperationalError propagates
3. `test_retry_permanent_error_not_retried` — function fails with IntegrityError; assert raised immediately (no retry)
4. `test_is_transient_locked` — "database is locked" → True
5. `test_is_transient_table_locked` — "database table is locked" → True
6. `test_is_transient_sql_logic_error` — "SQL logic error" → False
7. `test_retry_logs_to_stderr` — on retry, stderr contains "retry 1/3"

**Done when:** Tests exist and FAIL (retry not yet implemented)

### Step 6: Wrap _process_transition_phase in db.transaction() (TDD GREEN)

> Depends on: Steps 2, 4

**Files:**
- EDIT `plugins/pd/mcp/workflow_state_server.py`

**Edits:**
Restructure `_process_transition_phase()` per design C3:
1. Move both engine paths (entity_engine + engine fallback) inside `with db.transaction():`
2. After engine call, check `response.degraded` — if True, raise `sqlite3.OperationalError("engine returned degraded=True inside transaction")`
3. Move `db.update_entity()` and `db.update_workflow_phase()` inside the transaction
4. Move `_project_meta_json()` OUTSIDE the transaction (after the `with` block)

**Verification:**
```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k "atomic" --tb=short 2>&1 | tail -10
```

### Step 7: Wrap _process_complete_phase in db.transaction() (TDD GREEN)

> Depends on: Steps 2, 4

**Files:**
- EDIT `plugins/pd/mcp/workflow_state_server.py`

**Edits:**
Same pattern as Step 6 for `_process_complete_phase()`:
1. Keep reads (db.get_entity) OUTSIDE transaction
2. Move engine call + entity writes inside `with db.transaction():`
3. Check degraded flag
4. Move `_project_meta_json()` outside

**Verification:**
```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k "complete.*atomic" --tb=short 2>&1 | tail -10
```

### Step 8: Add _with_retry decorator (TDD GREEN)

> Depends on: Step 5

**Files:**
- EDIT `plugins/pd/mcp/workflow_state_server.py`

**Edits:**
1. Add `import time, random` at top
2. Add `_is_transient(exc)` function: returns True if "locked" in str(exc).lower()
3. Add `_with_retry()` decorator per design C4 (with safe backoff indexing, jitter, stderr logging)
4. Add `@_with_retry()` decorator to 9 write-path functions. **Three-decorator stacking order** (for functions that have `@_catch_value_error`):
   ```python
   @_with_error_handling    # outer: catches final sqlite3.Error → JSON error
   @_with_retry()           # middle: retries transient OperationalError
   @_catch_value_error      # inner: catches ValueError → JSON error (not retried)
   def _process_foo(...)
   ```
   This ensures: (1) ValueError is caught by `_catch_value_error` and converted to JSON before reaching `_with_retry`, so it's not retried. (2) `sqlite3.OperationalError` propagates through `_catch_value_error` to `_with_retry` for retry. (3) After retries exhaust, `_with_error_handling` catches the final exception.

   For functions WITHOUT `@_catch_value_error`, the order is:
   ```python
   @_with_error_handling    # outer
   @_with_retry()           # inner
   def _process_foo(...)
   ```

   Apply to:
   - `_process_transition_phase` (has @_catch_value_error)
   - `_process_complete_phase` (has @_catch_value_error)
   - `_process_init_feature_state` (has @_catch_value_error)
   - `_process_init_project_state` (has @_catch_value_error)
   - `_process_activate_feature` (has @_catch_value_error)
   - `_process_init_entity_workflow` (has @_catch_entity_value_error — same stacking position)
   - `_process_transition_entity_phase` (has @_catch_entity_value_error — same stacking position)
   - `_process_reconcile_apply` (verify if has @_catch_value_error)
   - `_process_reconcile_frontmatter` (verify if has @_catch_value_error)

**Verification:**
```bash
grep -c "@_with_retry" plugins/pd/mcp/workflow_state_server.py  # expect 9
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v -k "retry" --tb=short 2>&1 | tail -10
```

### Step 9: Add PID file monitoring (C6)

**Files:**
- EDIT `plugins/pd/mcp/workflow_state_server.py` — add `_write_pid`, `_remove_pid`, usage in `lifespan()`
- EDIT `plugins/pd/mcp/entity_server.py` — same pattern in its `lifespan()`
- EDIT `plugins/pd/mcp/test_workflow_state_server.py` — add PID file tests

**Tests (write before implementation):**
1. `test_pid_file_written_at_startup` — mock lifespan, assert PID file exists with correct PID
2. `test_pid_file_removed_at_shutdown` — mock lifespan exit, assert PID file removed
3. `test_stale_pid_file_overwritten` — write PID file with non-existent PID, start server, assert overwritten

**Edits per design C6:**
1. Add `_write_pid(server_name)` and `_remove_pid(pid_path)` helper functions
2. In `lifespan()`: call `_write_pid()` at startup, `_remove_pid()` in finally block
3. PID files written to `~/.claude/pd/run/`

**Verification:**
```bash
grep -c "_write_pid\|_remove_pid" plugins/pd/mcp/workflow_state_server.py  # expect >= 2
grep -c "_write_pid\|_remove_pid" plugins/pd/mcp/entity_server.py  # expect >= 2
```

### Step 10: Final Verification

> Depends on: Steps 1-9

**Full test suite:**
```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v --tb=short 2>&1 | tail -5
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ -v --tb=short 2>&1 | tail -5
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v --tb=short 2>&1 | tail -5
```

**AC verification:**
```bash
# AC-1: transaction wrapper exists
grep -n "BEGIN IMMEDIATE" plugins/pd/hooks/lib/entity_registry/database.py | grep transaction

# AC-2: all commits use _commit() (except 1 intentional flush in transaction())
echo "self._conn.commit() count: $(grep -c 'self._conn.commit()' plugins/pd/hooks/lib/entity_registry/database.py)"  # expect 1

# AC-4: retry applied to 9 functions
echo "retry count: $(grep -c '@_with_retry' plugins/pd/mcp/workflow_state_server.py)"  # expect 9

# AC-8: busy_timeout
grep "busy_timeout" plugins/pd/hooks/lib/entity_registry/database.py  # expect 15000
```

## Risk Mitigations

| Step | Risk | Mitigation |
|------|------|------------|
| 1 | _commit() replacement breaks existing tests | Run 940+ entity registry tests after Step 1 |
| 2 | transaction() conflicts with implicit transactions | Pre-flush commit() + nested guard |
| 6-7 | Engine error-swallowing defeats atomicity | degraded=True check raises explicit exception |
| 8 | time.sleep blocks event loop | Acceptable: MCP processes one request at a time |
