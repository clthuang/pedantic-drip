# Spec: SQLite Write Contention Fix

## Problem Statement

Multiple MCP server processes (workflow_state_server, entity_server, UI server) share a single SQLite database (`~/.claude/pd/entities/entities.db`). Write operations fail under contention while reads succeed, causing partial state advancement and confusing error responses. RCA report: `docs/rca/20260324-workflow-sql-error.md`.

Three confirmed root causes:
1. **Multi-process write lock contention** — 7-9 processes compete for SQLite's single writer lock; 5s busy_timeout insufficient
2. **Split-commit architecture** — `_process_transition_phase` and `_process_complete_phase` perform 3 sequential auto-commits; if commit 1 succeeds but 2-3 fail, state is partially advanced
3. **No retry logic** — `_with_error_handling` converts all `sqlite3.Error` to terminal responses with no distinction between transient (lock contention) and permanent (corruption) errors

## Scope

This spec covers all three root causes:
1. Atomic transactions for multi-step DB writes
2. Application-level retry with exponential backoff for transient errors
3. MCP server instance monitoring (PID-based observability)
4. Increased busy_timeout

## Requirements

### FR-1: Atomic transactions for multi-step write handlers

Wrap all DB writes within `_process_transition_phase` and `_process_complete_phase` in a single transaction so they atomically succeed or roll back.

**Affected functions in `workflow_state_server.py`:**
- `_process_transition_phase()` — currently does: `engine.transition_phase()` → `db.update_entity()` → `db.update_workflow_phase()` → `_project_meta_json()` as 3+ independent auto-commits
- `_process_complete_phase()` — similar pattern

**Critical design constraint — internal commit suppression:**

`EntityDatabase` methods (`update_entity`, `update_workflow_phase`, etc.) call `self._conn.commit()` internally (25 call sites in database.py). The `transaction()` context manager MUST suppress these internal commits during an explicit transaction, otherwise the first internal `commit()` will finalize a partial transaction, defeating atomicity.

**Mechanism:** Add a `transaction()` context manager to `EntityDatabase` with an `_in_transaction` flag:

```python
@contextmanager
def transaction(self):
    """Context manager for explicit write transactions.

    Uses BEGIN IMMEDIATE to acquire write lock upfront.
    Sets _in_transaction flag to suppress internal commit() calls
    within update_entity, update_workflow_phase, etc.
    """
    # Commit any implicit transaction first (Python sqlite3 default
    # isolation_level='' starts implicit transactions on DML).
    # This is a no-op when no implicit transaction is pending.
    # If it fails due to contention, the exception propagates —
    # correct since the transaction hasn't started yet (eligible for FR-2 retry).
    self._conn.commit()
    self._conn.execute("BEGIN IMMEDIATE")
    self._in_transaction = True
    try:
        yield
        self._conn.execute("COMMIT")
    except Exception:
        self._conn.execute("ROLLBACK")
        raise
    finally:
        self._in_transaction = False
```

**Internal commit suppression:** Add a `_commit()` helper method that checks the flag:

```python
def _commit(self):
    """Commit unless inside an explicit transaction()."""
    if not self._in_transaction:
        self._conn.commit()
```

Replace all 19 `self._conn.commit()` call sites in database.py with `self._commit()`. Initialize `self._in_transaction = False` in `__init__` BEFORE `_set_pragmas()` and `_migrate()` are called (so commits during initialization still execute normally since `_in_transaction` is False).

**Usage in workflow_state_server.py:**
```python
if transitioned and db is not None:
    with db.transaction():
        db.update_entity(feature_type_id, metadata=metadata)
        db.update_workflow_phase(feature_type_id, kanban_column=kanban)
    # _project_meta_json writes to filesystem, NOT SQLite —
    # must be OUTSIDE transaction to avoid inconsistency on rollback
    _project_meta_json(db, engine, feature_type_id)
```

**Note:** `WorkflowStateEngine` holds a reference to the SAME `EntityDatabase` instance (`self.db = db` at engine.py:48). It does NOT have its own DB connection. Therefore `engine.transition_phase()` and `engine.complete_phase()` writes go through the same `_commit()` path and MUST be included inside the `db.transaction()` block for true atomicity.

### FR-2: Retry with exponential backoff for transient errors

Replace the terminal `_with_error_handling` decorator with a retry-aware version that distinguishes transient errors from permanent errors.

**Transient errors (retry):**
- `sqlite3.OperationalError` with message containing "database is locked" or "database table is locked"

**Not retried** (removed from transient list per reviewer feedback):
- "SQL logic error" — this is SQLITE_ERROR (code 1), a broad category that includes permanent errors like malformed SQL. The RCA's "SQL logic error" observation was likely caused by stale implicit transactions (addressed by FR-1's explicit `self._conn.commit()` before BEGIN IMMEDIATE) rather than contention.

**Permanent errors (no retry):**
- `sqlite3.IntegrityError` (constraint violation)
- `sqlite3.DatabaseError` with message containing "malformed", "corrupt", "not a database"
- `sqlite3.OperationalError` without "locked" in message
- Any non-sqlite3 exception

**Retry parameters:**
- Max attempts: 3
- Backoff schedule: 100ms, 500ms, 2000ms
- Total max wait: 2.6 seconds

**Applied to these 9 write-path `_process_*` functions** (verified by grep for db.update/engine.transition/engine.complete/delegate-to-lib calls):
- `_process_transition_phase` — engine.transition_phase + db.update_entity + db.update_workflow_phase
- `_process_complete_phase` — engine.complete_phase + db.update_entity + db.update_workflow_phase
- `_process_init_feature_state` — delegates to _lib_init_feature_state (writes)
- `_process_init_project_state` — delegates to _lib_init_project_state (writes)
- `_process_activate_feature` — delegates to _lib_activate_feature (writes)
- `_process_init_entity_workflow` — delegates to _lib_init_entity_workflow (writes)
- `_process_transition_entity_phase` — entity_engine.transition_phase (writes)
- `_process_reconcile_apply` — applies drift fixes (writes)
- `_process_reconcile_frontmatter` — syncs frontmatter (writes)

**NOT applied to these 6 read-only functions:**
- `_process_get_phase` — read-only, uses engine fallback
- `_process_validate_prerequisites` — read-only checks
- `_process_list_features_by_phase` — read-only query
- `_process_list_features_by_status` — read-only query
- `_process_reconcile_check` — read-only drift detection
- `_process_reconcile_status` — read-only status report

### FR-3: MCP server instance monitoring

Write a PID file at MCP server startup for observability. Log the count of running instances.

**PID file location:** `~/.claude/pd/run/{server_name}.pid`

**Startup sequence:**
1. Create `~/.claude/pd/run/` directory if needed
2. Check if PID file exists; if so, check if process is alive
3. If alive: log "Another {server_name} instance running (PID {pid}), proceeding anyway"
4. If stale: remove PID file
5. Write current PID to file
6. On shutdown (lifespan exit): remove PID file

This is monitoring-only — the real contention fix is FR-1 + FR-2. Multiple instances are legitimate (one per Claude session).

### FR-4: Increase busy_timeout

Change `busy_timeout` from 5000ms to 15000ms in `EntityDatabase.__init__()` (`_set_pragmas` method). This gives the retry decorator more room to work.

## Non-Requirements (Out of Scope)

- **NR-1:** Migrating from SQLite to a client-server database
- **NR-2:** Implementing a single-writer daemon process with IPC
- **NR-3:** Connection pooling within individual MCP servers
- **NR-4:** Fixing the 22 orphaned foreign key references found during RCA
- **NR-5:** Changing the frozen engine's internal DB connection management
- **NR-6:** Changing Python sqlite3's isolation_level from default — the `transaction()` context manager handles this by committing implicit transactions before BEGIN IMMEDIATE

## Acceptance Criteria

### AC-1: Atomic transaction wrapper exists
`EntityDatabase` has a `transaction()` context manager using `BEGIN IMMEDIATE ... COMMIT/ROLLBACK` with `_in_transaction` flag. Verified by unit test: transaction commits on success, rolls back on exception, internal `_commit()` is suppressed inside transaction.

### AC-2: Internal commits use _commit() helper
All `self._conn.commit()` calls in database.py (19 sites) replaced with `self._commit()`. One intentional `self._conn.commit()` remains in `transaction()` (the pre-BEGIN flush). Verified by: `grep -c "self._conn.commit()" plugins/pd/hooks/lib/entity_registry/database.py` returns 1; `grep -c "self._commit()" plugins/pd/hooks/lib/entity_registry/database.py` returns >= 19.

### AC-3: Transition and complete phase use atomic transactions
`_process_transition_phase` and `_process_complete_phase` wrap entity DB writes in `db.transaction()`. `_project_meta_json` is called AFTER the transaction block. Verified by unit test: mock `db.update_workflow_phase` to raise OperationalError after `db.update_entity` succeeds; assert entity metadata is NOT persisted (rolled back).

### AC-4: Retry decorator applied to write handlers
`_with_retry` decorator exists. Applied to the 9 write-path functions listed in FR-2. NOT applied to the 6 read-only functions. Verified by: `grep -c "@_with_retry" plugins/pd/mcp/workflow_state_server.py` returns 9.

### AC-5: Transient error classification works
`_is_transient(exc)` returns True for "database is locked" and "database table is locked", False for "SQL logic error", "malformed", and IntegrityError. Verified by unit tests.

### AC-6: Retry actually retries on transient errors
Given a function that fails with `OperationalError("database is locked")` on first call and succeeds on second, the retry decorator calls it twice and returns success. Verified by unit test.

### AC-7: PID file written at startup, removed at shutdown
MCP server lifespan writes PID file at startup and removes at shutdown. Verified by unit test: mock lifespan context, assert PID file exists with correct PID after startup, assert PID file removed after shutdown context exit.

### AC-8: busy_timeout increased
`PRAGMA busy_timeout` set to 15000. Verified by: `grep "busy_timeout" plugins/pd/hooks/lib/entity_registry/database.py` shows 15000.

### AC-9: Existing tests pass
All entity registry tests (940+), workflow engine tests (309), and workflow state MCP server tests (272) pass.

## Dependencies

- No external dependencies. All changes within the pd plugin.
- `EntityDatabase` class in `plugins/pd/hooks/lib/entity_registry/database.py`
- `_with_error_handling` decorator in `plugins/pd/mcp/workflow_state_server.py`

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BEGIN IMMEDIATE causes more lock contention (eager lock acquisition) | Medium | Low | Combined with retry+backoff, brief lock holds are retried |
| Retry masks permanent errors misclassified as transient | Low | Medium | Conservative: only "locked" substring matches. All others are permanent. |
| _commit() helper breaks methods that rely on immediate commit visibility | Medium | Medium | Only suppressed inside `transaction()` context. Outside, `_commit()` behaves identically to `self._conn.commit()`. Test all 940+ existing tests. |
| Implicit transaction commit before BEGIN IMMEDIATE races with other writers | Low | Low | The commit() flushes any pending implicit DML; the subsequent BEGIN IMMEDIATE acquires the lock atomically. |
| _project_meta_json outside transaction creates window where DB committed but .meta.json not yet written | Low | Low | This is strictly better than current state (partial DB commit + no .meta.json). And .meta.json projection failure was already non-fatal. |
