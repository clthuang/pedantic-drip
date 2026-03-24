# Design: SQLite Write Contention Fix

## Prior Art Research

### Codebase Patterns
- **`begin_immediate()` already exists** on `EntityDatabase` (line 1125) — yields `self._conn` for raw SQL within `BEGIN IMMEDIATE ... COMMIT/ROLLBACK`. Used by `delete_entity()` and `register_entities_batch()`. Does NOT suppress internal `commit()` calls in high-level methods.
- **19 `self._conn.commit()` sites** in database.py — all bare autocommit per-statement.
- **`_with_error_handling`** catches all `sqlite3.Error` and returns structured JSON error. No retry.
- **WAL mode + busy_timeout=5000ms** already enabled in `_set_pragmas()`.
- **WorkflowStateEngine** holds a reference to `EntityDatabase` (not its own connection) — all writes go through the shared `EntityDatabase` instance.
- **entity_server.py** and **workflow_state_server.py** each open independent `sqlite3.connect()` to the same `entities.db` file — two concurrent writer connections from separate MCP processes.

### External Research
- **BEGIN IMMEDIATE vs DEFERRED:** IMMEDIATE acquires the write lock at BEGIN time (respects busy_timeout). DEFERRED delays to first write — upgrade failures bypass busy_timeout entirely. This is critical: our current implicit transactions use DEFERRED.
- **Python 3.12+ `autocommit` attribute** supersedes `isolation_level` (removal planned for 3.16). For now, use `isolation_level=None` + manual BEGIN for explicit control.
- **Retry with jitter:** Standard pattern is `initial_delay * (2 ** attempt) + random.uniform(0, jitter)` to prevent thundering-herd.
- **PID files:** `fcntl.flock()` is preferred over PID-only validation (auto-releases on crash). But our use case is monitoring-only, so PID + liveness check suffices.

## Architecture Overview

Four changes, ordered by dependency:

```
C1: _commit() helper + _in_transaction flag (database.py)
  ↓
C2: transaction() context manager (database.py, extends begin_immediate pattern)
  ↓
C3: Atomic writes in workflow_state_server.py (uses C2)
  ↓
C4: _with_retry decorator (workflow_state_server.py)

C5: busy_timeout increase (database.py, independent)
C6: PID file monitoring (workflow_state_server.py + entity_server.py, independent)
```

### Component Interaction

```
Before (split-commit):
  _process_transition_phase()
    → engine.transition_phase()     [calls db.update_workflow_phase → commit 1]
    → db.update_entity()            [commit 2 — may fail under contention]
    → db.update_workflow_phase()    [commit 3 — may fail, state inconsistent]
    → _project_meta_json()          [filesystem write]

After (atomic — ALL writes in one transaction):
  _process_transition_phase()
    → with db.transaction():        [BEGIN IMMEDIATE]
        engine.transition_phase()   [_commit() suppressed — engine uses same db]
        db.update_entity()          [_commit() suppressed]
        db.update_workflow_phase()  [_commit() suppressed]
                                    [COMMIT — all 3 writes atomic]
    → _project_meta_json()          [filesystem, after DB committed]
```

**Critical correction:** `WorkflowStateEngine` holds a reference to the SAME `EntityDatabase` instance (`self.db = db` at engine.py:48). It does NOT have its own connection. Therefore `engine.transition_phase()` writes go through the same `_commit()` path and MUST be inside the `db.transaction()` block for true atomicity.

## Components

### C1: _commit() helper with _in_transaction flag

Add to `EntityDatabase`:

```python
def __init__(self, db_path: str, *, check_same_thread: bool = True) -> None:
    self._in_transaction = False  # Must be set BEFORE _set_pragmas/_migrate
    self._conn = sqlite3.connect(db_path, timeout=5.0, check_same_thread=check_same_thread)
    self._conn.row_factory = sqlite3.Row
    self._set_pragmas()
    self._migrate()

def _commit(self):
    """Commit unless inside an explicit transaction().

    Inside a transaction() block, commits are deferred to the
    context manager's COMMIT. Outside, behaves identically to
    self._conn.commit().
    """
    if not self._in_transaction:
        self._conn.commit()
```

Replace all 19 `self._conn.commit()` in instance methods with `self._commit()`. The 6 `conn.commit()` sites in module-level migration functions (which receive `conn` as parameter, not `self._conn`) are NOT changed — they use their own connection and are not affected by `_in_transaction`.

### C2: transaction() context manager

Extend the existing `begin_immediate()` pattern with commit suppression:

```python
@contextmanager
def transaction(self):
    """Context manager for atomic multi-step writes.

    Uses BEGIN IMMEDIATE to acquire write lock upfront.
    Suppresses _commit() calls inside the block so all writes
    commit atomically at the end.

    Unlike begin_immediate() which yields the raw connection,
    this method is designed for use with high-level methods
    (update_entity, update_workflow_phase, etc.) that call
    _commit() internally.
    """
    if self._in_transaction:
        raise RuntimeError("Nested transactions not supported")
    # Flush any pending implicit transaction (Python sqlite3 default
    # isolation_level='' starts implicit DML transactions).
    # This is a no-op when no implicit transaction is pending.
    self._conn.commit()
    self._conn.execute("BEGIN IMMEDIATE")
    self._in_transaction = True
    try:
        yield
        self._conn.execute("COMMIT")
    except Exception:
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass  # Suppress ROLLBACK failures; Python will implicit-rollback on close
        raise
    finally:
        self._in_transaction = False
```

**Relationship to begin_immediate():** Both use BEGIN IMMEDIATE. `begin_immediate()` yields the raw connection for SQL; `transaction()` suppresses `_commit()` for high-level methods. They are complementary — `begin_immediate()` stays for raw SQL use cases.

### C3: Atomic writes in workflow_state_server.py

Wrap entity DB writes in `_process_transition_phase` and `_process_complete_phase`:

**_process_transition_phase:**
```python
# Move engine call + entity writes into one transaction
# engine.transition_phase() uses the same db instance (engine.db = db)
if db is not None:
    with db.transaction():
        response = engine.transition_phase(feature_type_id, target_phase, yolo_active)
        # ... metadata assembly (reads from response, no separate writes) ...
        if transitioned:
            db.update_entity(feature_type_id, metadata=metadata)
            if feature_type_id.startswith("feature:"):
                kanban = derive_kanban("active", target_phase)
                db.update_workflow_phase(feature_type_id, kanban_column=kanban)
else:
    response = engine.transition_phase(feature_type_id, target_phase, yolo_active)
# Filesystem write AFTER transaction committed
if transitioned and db is not None:
    warning = _project_meta_json(db, engine, feature_type_id)
```

**_process_complete_phase:**
```python
# Reads (outside transaction — no write lock needed)
entity = db.get_entity(feature_type_id) if db else None
# ... early return if entity is None ...

# All writes in one transaction
if db is not None:
    with db.transaction():
        completion = engine.complete_phase(feature_type_id, phase)
        # ... metadata assembly from completion ...
        db.update_entity(feature_type_id, metadata=metadata)
        if feature_type_id.startswith("feature:"):
            kanban = derive_kanban(status, phase)
            db.update_workflow_phase(feature_type_id, kanban_column=kanban)
else:
    completion = engine.complete_phase(feature_type_id, phase)
# Filesystem after commit
if db is not None:
    _project_meta_json(db, engine, feature_type_id)
```

**entity_server.py exclusion note:** entity_server.py writes (register_entity, update_entity, set_parent, etc.) are single-statement operations that are already atomic via individual `_commit()`. They don't have the multi-step split-commit problem. Retry (FR-2) is not applied to entity_server because it uses a different MCP server process with its own `_with_error_handling` implementation.

### C4: _with_retry decorator

```python
import time
import random

def _is_transient(exc: sqlite3.Error) -> bool:
    """Return True if the error is a transient lock contention error."""
    msg = str(exc).lower()
    return "locked" in msg  # Matches "database is locked" and "database table is locked"

def _with_retry(max_attempts=3, backoff=(0.1, 0.5, 2.0)):
    """Retry decorator for transient SQLite write errors.

    Applied INSIDE _with_error_handling so retries happen before
    the error is converted to a terminal MCP response.

    Decorator stacking order:
      @_with_error_handling    ← outer: catches final exception, returns JSON error
      @_with_retry()           ← inner: retries transient errors before they reach outer
      def _process_foo(...)

    Uses time.sleep() for backoff. This is acceptable because:
    - MCP servers process one request at a time per connection
    - Claude sends requests sequentially, not concurrently
    - The async handlers call _process_* synchronously (no await)
    - Worst case 2.6s blocking affects only the current request
    If concurrent MCP request handling is needed in the future,
    wrap _process_* calls in run_in_executor().
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as exc:
                    if not _is_transient(exc):
                        raise
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        delay = backoff[min(attempt, len(backoff) - 1)]
                        jitter = random.uniform(0, 0.05)
                        print(
                            f"workflow-state: retry {attempt+1}/{max_attempts} "
                            f"after {exc} (sleeping {delay:.1f}s)",
                            file=sys.stderr,
                        )
                        time.sleep(delay + jitter)
            raise last_exc  # Exhausted — propagates to _with_error_handling
        return wrapper
    return decorator
```

**Decorator stacking:** `_with_error_handling` stays as the OUTER decorator on all 15 functions. `_with_retry()` is added as an INNER decorator on the 9 write-path functions only. This means retries happen first; if all retries exhaust, the exception reaches `_with_error_handling` which converts it to a structured MCP error response.

**Applied to (9 write-path):**
`_process_transition_phase`, `_process_complete_phase`, `_process_init_feature_state`, `_process_init_project_state`, `_process_activate_feature`, `_process_init_entity_workflow`, `_process_transition_entity_phase`, `_process_reconcile_apply`, `_process_reconcile_frontmatter`

### C5: busy_timeout increase

In `_set_pragmas()`: change `busy_timeout = 5000` → `busy_timeout = 15000`.

### C6: PID file monitoring

In `lifespan()` of both `workflow_state_server.py` and `entity_server.py`:

```python
import os

_PID_DIR = os.path.expanduser("~/.claude/pd/run")

def _write_pid(server_name: str) -> str:
    os.makedirs(_PID_DIR, exist_ok=True)
    pid_path = os.path.join(_PID_DIR, f"{server_name}.pid")
    # Check for existing instance
    if os.path.isfile(pid_path):
        try:
            old_pid = int(open(pid_path).read().strip())
            os.kill(old_pid, 0)  # Check if alive
            print(f"Another {server_name} instance running (PID {old_pid})", file=sys.stderr)
        except (ProcessLookupError, ValueError, OSError):
            pass  # Stale or unreadable — overwrite
    with open(pid_path, "w") as f:
        f.write(str(os.getpid()))
    return pid_path

def _remove_pid(pid_path: str) -> None:
    try:
        os.remove(pid_path)
    except OSError:
        pass
```

Usage in lifespan:
```python
pid_path = _write_pid("workflow_state_server")
try:
    yield
finally:
    _remove_pid(pid_path)
```

## Technical Decisions

### TD-1: transaction() vs extending begin_immediate()

**Decision:** New `transaction()` method alongside existing `begin_immediate()`.

**Rationale:** `begin_immediate()` yields `self._conn` for raw SQL — callers execute SQL directly. `transaction()` is for high-level methods that call `_commit()` internally. Different use cases, different ergonomics. Merging them would require `begin_immediate()` callers to change behavior.

### TD-2: _with_retry stacking order (inside _with_error_handling)

**Decision:** `_with_retry` is the INNER decorator, `_with_error_handling` is the OUTER.

**Rationale:** Retries should happen before the error is converted to a terminal response. If `_with_retry` were outer, it would retry the already-formatted JSON error string, not the actual function call.

### TD-3: Only "locked" errors are transient

**Decision:** Only `OperationalError` messages containing "locked" are retried. "SQL logic error" is NOT retried.

**Rationale:** "SQL logic error" (SQLITE_ERROR=1) is a broad category including permanent errors. The RCA's observation of this error was likely caused by stale implicit transactions, which FR-1's pre-BEGIN `commit()` flush addresses. After the fix, lock contention should produce "database is locked" cleanly.

### TD-4: ROLLBACK failure suppression

**Decision:** Wrap ROLLBACK in `try/except sqlite3.Error: pass`.

**Rationale:** If ROLLBACK fails (e.g., I/O error), the original exception is more important. Python's sqlite3 will implicit-rollback when the connection is closed. Suppressing the secondary error preserves the original exception's traceback.

### TD-5: _project_meta_json outside transaction

**Decision:** Filesystem writes happen AFTER the DB transaction commits.

**Rationale:** `.meta.json` is a projection of DB state. If the transaction rolls back, the file shouldn't be written (it would reflect a state that doesn't exist). Writing after commit means there's a brief window where DB is updated but file isn't — this is strictly better than current behavior (partial DB commit + no file update).

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| _commit() suppression breaks methods relying on immediate commit visibility | Medium | Medium | Only suppressed inside transaction(). 940+ existing tests verify normal behavior. |
| Pre-BEGIN commit() races with other writers | Low | Low | The commit flushes pending DML; BEGIN IMMEDIATE then acquires lock atomically |
| Retry+jitter adds 2.6s worst-case latency | Low | Low | Only on transient errors. Normal operations unaffected. |
| ROLLBACK suppression hides secondary errors | Low | Low | Original exception preserved. Connection auto-rollback on close. |

## Interfaces

### I1: EntityDatabase.transaction()

```python
@contextmanager
def transaction(self) -> Generator[None, None, None]:
    """Atomic write block for high-level methods.

    Suppresses _commit() calls inside the block.
    Uses BEGIN IMMEDIATE for eager lock acquisition.
    Commits on clean exit, rolls back on exception.
    """
```

### I2: EntityDatabase._commit()

```python
def _commit(self) -> None:
    """Commit unless inside transaction(). Replaces self._conn.commit()."""
```

### I3: _with_retry decorator

```python
def _with_retry(max_attempts=3, backoff=(0.1, 0.5, 2.0)):
    """Retry transient SQLite errors with exponential backoff + jitter.

    Applied as inner decorator (inside _with_error_handling).
    Only retries OperationalError with "locked" in message.
    """
```

### I4: _is_transient classifier

```python
def _is_transient(exc: sqlite3.Error) -> bool:
    """True if error is transient lock contention (retryable)."""
```
