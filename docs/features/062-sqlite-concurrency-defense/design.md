# Design: SQLite Concurrency Defense

## Prior Art Research

### Codebase Patterns
- `_with_retry` decorator in `workflow_state_server.py:429-463` — parameterized factory with `max_attempts`, `backoff` tuple, jitter `random.uniform(0, 0.05)`. Uses `_is_transient(exc)` predicate checking `'locked' in str(exc).lower()`.
- Decorator stacking: `@_with_error_handling` (outermost) → `@_with_retry()` (middle) → `@_catch_value_error` (innermost). Read-only handlers have no retry.
- `EntityDatabase.transaction()` at `database.py:1136-1187` — `BEGIN IMMEDIATE`, sets `_in_transaction=True` to suppress `_commit()`, commits on success, rolls back on exception.
- `_commit()` at `database.py:984-987` — no-op when `_in_transaction=True`.
- `_run_cascade()` at `entity_engine.py:571-604` — two separate auto-committing calls (`cascade_unblock`, `rollup_parent`), no enclosing transaction.
- `_recover_pending_cascades()` at `reconciliation.py:521-624` — detects missed cascades by comparing computed vs stored parent progress, re-runs rollup for mismatches.

### External Research
- SQLite transient errors: SQLITE_BUSY (5), SQLITE_BUSY_RECOVERY (261), SQLITE_BUSY_SNAPSHOT (517), SQLITE_LOCKED (6). In Python, all surface as `OperationalError` — classify via message string.
- Jitter: Full jitter (`random(0, base * 2^attempt)`) is recommended for SQLite scenarios to maximize collision spread.
- Testing: `multiprocessing.Event()` as a barrier for synchronized stress tests — all workers wait, then main process releases simultaneously.
- `time.sleep` can be monkeypatched in tests to eliminate real delays; use `side_effect` lists to simulate N failures then success.

## Architecture Overview

### Component Map

```
┌─────────────────────────────────────────────────────────────┐
│                    Shared Library Layer                       │
│                                                               │
│  plugins/pd/hooks/lib/sqlite_retry.py                        │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  with_retry(server_name, max_attempts, backoff)     │     │
│  │  is_transient(exc) → bool                           │     │
│  └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│ entity_server.py│ │ memory_server.py│ │workflow_state_server │
│                 │ │                 │ │ .py                  │
│ @with_retry(    │ │ @with_retry(    │ │ @with_retry(         │
│  "entity")      │ │  "memory")      │ │  "workflow-state")   │
│                 │ │                 │ │ (refactored import)  │
└────────┬────────┘ └────────┬────────┘ └──────────┬──────────┘
         │                    │                     │
         ▼                    ▼                     ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│ EntityDatabase   │ │ MemoryDatabase  │ │ EntityWorkflowEngine│
│ busy_timeout=15s │ │ busy_timeout=15s│ │ + EntityDatabase     │
│ transaction()    │ │ BEGIN IMMEDIATE │ │   transaction()      │
│ _in_transaction  │ │                 │ │   _run_cascade()     │
└─────────────────┘ └─────────────────┘ └─────────────────────┘
```

### Change Summary

| Component | Change | Risk |
|-----------|--------|------|
| `sqlite_retry.py` (NEW) | Extract `with_retry` + `is_transient` from workflow_state_server | Low — proven code, just moved |
| `workflow_state_server.py` | Replace local `_with_retry`/`_is_transient` with imports | Low — functional no-op |
| `entity_server.py` | Add `@with_retry("entity")` to 10 write handlers | Low — additive decorator |
| `memory_server.py` | Add `@with_retry("memory")` to 3 write handlers | Low — additive decorator |
| `entity_engine.py` | Wrap `_run_cascade()` body in `db.transaction()` | Medium — changes commit semantics |
| `database.py` | Wrap multi-step `_commit()` methods in `transaction()` | Medium — changes commit semantics |
| `semantic_memory/database.py` | Change `busy_timeout` 5000→15000 | Low — only extends wait time |
| `engine.py:287` | Fix stale comment (5s→15s) | Low — documentation only |
| `memory_server.py:128` | Fix misleading comment | Low — documentation only |
| `test_sqlite_retry.py` (NEW) | Unit tests for shared module | N/A |
| `test_concurrent_writes.py` (NEW) | Integration tests with multiprocessing | N/A |

## Technical Decisions

### TD-1: Shared Module Location
**Decision:** `plugins/pd/hooks/lib/sqlite_retry.py`
**Rationale:** All three MCP servers already import from `hooks/lib/` (entity_registry, semantic_memory, workflow_engine). Placing the retry module here follows the established pattern and avoids a new import path.

### TD-2: Public API (No Underscore Prefix)
**Decision:** Export as `with_retry` and `is_transient` (no underscore)
**Rationale:** The module is a shared library, not a private implementation detail. Public names signal reusability. The workflow_state_server's `_with_retry` was private because it was module-local.

### TD-3: Decorator Factory Signature
**Decision:** `with_retry(server_name: str, max_attempts: int = 3, backoff: tuple = (0.1, 0.5, 2.0)) -> Callable`
**Rationale:** Matches the existing proven signature. `server_name` parameterizes the log prefix (currently hardcoded as `"workflow-state:"`). Defaults match production values.

### TD-4: Jitter Strategy
**Decision:** Additive jitter: `backoff[i] + random.uniform(0, 0.05)`
**Rationale:** Matches existing production implementation. Full jitter (random over entire interval) would be more theoretically optimal but deviates from proven behavior. 50ms max jitter is sufficient for 3-10 concurrent processes.

### TD-5: is_transient Classification
**Decision:** `'locked' in str(exc).lower()` — same as existing implementation
**Rationale:** This catches both `"database is locked"` and `"database table is locked"` messages. SQLITE_BUSY_SNAPSHOT surfaces as a different error path but handler-level retry restarts the full transaction (fresh snapshot), so explicit BUSY_SNAPSHOT detection is unnecessary.

### TD-6: Phase B Cascade Atomicity
**Decision:** Wrap `_run_cascade()` body in `self._db.transaction()`. Phase A/B separation preserved.
**Rationale:** `cascade_unblock` calls `remove_dependencies_by_blocker` → `_commit()` and `update_entity` → `_commit()`. `rollup_parent` calls `update_entity` → `_commit()`. All internal `_commit()` calls are suppressed by `_in_transaction=True`. No nested transaction conflict — verified that neither method calls `begin_immediate()` or `transaction()` internally.

### TD-7: Multi-Step Write Wrapping Strategy
**Decision:** Wrap only methods with 2+ `_commit()` calls in non-transactional context. Do NOT wrap single-statement writes.
**Rationale:** Per spec behavioral constraint — `busy_timeout` handles single-statement contention natively. Wrapping adds unnecessary lock-acquisition overhead.

### TD-8: Workflow State Server Refactoring Approach
**Decision:** Import `from sqlite_retry import with_retry, is_transient`, create local aliases `_with_retry = with_retry("workflow-state")` and `_is_transient = is_transient`, preserve decorator stacking order.
**Rationale:** Minimizes diff size. Local aliases preserve the `_` prefix convention used throughout the file without renaming every decorator application. `_is_transient` alias enables callers that call it directly (if any).

### TD-9: No External Dependencies
**Decision:** Pure stdlib implementation (time, random, functools, sqlite3, logging)
**Rationale:** Plugin portability constraint from spec. The existing `_with_retry` is already stdlib-only. Tenacity would add a dependency for minimal benefit given the simple retry pattern.

## Risks

### R-1: Cascade Transaction Changes Commit Semantics (Medium)
**Impact:** If `_run_cascade()` is wrapped in `transaction()`, a failure in `rollup_parent` now rolls back `cascade_unblock` changes too (previously, `cascade_unblock` would have committed independently).
**Mitigation:** This is the intended behavior per spec (Phase B atomicity). Reconciliation already handles complete Phase B failure recovery via `_recover_pending_cascades()`.

### R-2: Multi-Step Write Audit May Find Unexpected Patterns (Low)
**Impact:** The `_commit()` audit may reveal methods that are difficult to wrap in `transaction()` due to side effects or complex control flow.
**Mitigation:** Spec includes circuit breaker: if >8 multi-step sequences found, stop and re-evaluate scope.

### R-3: Retry Masking Logic Errors (Low)
**Impact:** `is_transient` checks for "locked" substring. A logic error that produces an error message coincidentally containing "locked" could be retried instead of failing fast.
**Mitigation:** Only `sqlite3.OperationalError` is caught. Error messages containing "locked" in non-contention contexts are extremely unlikely in SQLite's error repertoire.

## Components

### C1: sqlite_retry.py (Shared Library)

**File:** `plugins/pd/hooks/lib/sqlite_retry.py`
**Responsibility:** Provide reusable retry decorator and transient-error classifier for SQLite operations.
**Dependencies:** `time`, `random`, `functools`, `sqlite3`, `sys` (for `print(file=sys.stderr)` — matches existing workflow_state_server pattern; uses `print` not `logging` per hook subprocess safety rules)

### C2: Entity Server Retry Integration

**File:** `plugins/pd/mcp/entity_server.py` and `plugins/pd/hooks/lib/entity_registry/server_helpers.py`
**Responsibility:** Add retry coverage to all write paths in entity server.
**Dependencies:** C1 (sqlite_retry)

**Architecture note:** Entity server uses `async def` MCP handlers that delegate to sync helpers. The retry decorator is synchronous. Two handler types exist:

**Type A — Handlers using server_helpers (sync `_process_*` functions):**
Apply `@with_retry("entity")` to the sync `_process_*` functions in `server_helpers.py`:
1. `_process_register_entity` in `server_helpers.py` — called from `register_entity` (line 224)
2. `_process_set_parent` in `server_helpers.py` — called from `set_parent` (line 264)

**Type B — Handlers with inline DB logic in async handlers:**
Extract DB logic into sync helper functions, then apply `@with_retry("entity")`:
3. `update_entity` (line 332) — inline `_db.update_entity()` call
4. `delete_entity` (line 441) — inline `_db.delete_entity()` call
5. `add_entity_tag` (line 466) — inline `_db.get_entity()` + `_db.add_tag()` calls
6. `add_dependency` (line 526) — inline `mgr.add_dependency()` call
7. `remove_dependency` (line 562) — inline `mgr.remove_dependency()` call
8. `add_okr_alignment` (line 643) — inline `_db.add_okr_alignment()` call
9. `create_key_result` (line 690) — inline `_db.register_entity()` call
10. `update_kr_score` (line 737) — inline `_db.update_entity()` call

For Type B handlers, the pattern is: extract the try-block DB logic into a sync `_process_*` function (matching the convention of server_helpers.py), then wrap with `@with_retry("entity")`. The async handler becomes a thin wrapper that checks `_db is None` and calls the sync helper.

**Error conversion for exhausted retries:** Not all async handlers have `except Exception`. Handlers 8 (`add_okr_alignment` — catches `ValueError` only), 9 (`create_key_result` — catches `ValueError, KeyError`), and 10 (`update_kr_score` — catches `ValueError, KeyError`) use narrow exception clauses. These must be broadened to `except Exception` to catch exhausted-retry `OperationalError` and convert to structured JSON error. Handlers 3-7 already have `except Exception`.

**Implementation-time verification:** Grep `entity_server.py` for all `@mcp.tool()` handlers that call `_db` write methods (`register`, `update`, `delete`, `add_*`, `remove_*`, `set_*`) and confirm coverage matches this list.

### C3: Memory Server Retry Integration

**File:** `plugins/pd/mcp/memory_server.py`
**Responsibility:** Apply `with_retry("memory")` to write handlers. Fix misleading comment at line 128.
**Dependencies:** C1 (sqlite_retry)

**Handlers to decorate** (already sync `_process_*` functions — same pattern as workflow_state_server):
1. `_process_store_memory` (line 38) — sync helper, no existing decorators, apply `@with_retry("memory")` directly
2. `_process_record_influence` (line 237) — sync helper, no existing decorators, apply `@with_retry("memory")` directly
3. `delete_memory` handler (line 410) — has inline `_db.delete_entry()`, extract to sync `_process_delete_memory` then wrap

**Error conversion:** NOT all memory server async handlers have try/except. `store_memory` (line 314) and `record_influence` (line 451) call their sync helpers directly with NO try/except — only `delete_memory` (line 422) has `except Exception`. Implementation must add `try/except Exception` wrappers to `store_memory` and `record_influence` async handlers to catch exhausted-retry `OperationalError` and return structured error strings.

**Embedding idempotency:** `_process_store_memory` computes embeddings via `provider.embed()` before the DB write. Embedding computation is stateless (HTTP call or local model) and safe to re-invoke on retry. The 3-retry window (~2.6s) is well within typical API rate limits.

### C4: Workflow State Server Refactor

**File:** `plugins/pd/mcp/workflow_state_server.py`
**Responsibility:** Replace local `_with_retry`/`_is_transient` with imports from C1.
**Dependencies:** C1 (sqlite_retry)

### C5: Cascade Atomicity Fix

**File:** `plugins/pd/hooks/lib/workflow_engine/entity_engine.py`
**Responsibility:** Wrap `_run_cascade()` body in `self._db.transaction()`.
**Dependencies:** Existing `EntityDatabase.transaction()` infrastructure.

### C6: Multi-Step Write Atomicity

**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Responsibility:** Audit and wrap multi-step `_commit()` methods in `transaction()`.
**Dependencies:** Existing `transaction()` infrastructure.

**Preliminary audit (to be confirmed during implementation):**
- `set_parent()` — parent update + depth recalculation
- `register_entity()` — insert + FTS sync
- `update_entity()` — update + FTS sync

### C7: Timeout Standardization

**Files:** `plugins/pd/hooks/lib/semantic_memory/database.py`, `plugins/pd/hooks/lib/workflow_engine/engine.py`
**Responsibility:** Change `MemoryDatabase` busy_timeout from 5000 to 15000. Fix stale comment in engine.py.

### C8: Tests

**Unit tests:** `plugins/pd/hooks/lib/test_sqlite_retry.py` — test `with_retry` and `is_transient` in isolation (mock OperationalError, verify backoff sequence, test transient classification).
**Integration tests:** `plugins/pd/hooks/lib/test_sqlite_retry_integration.py` — concurrent-write tests using `multiprocessing` with real file-backed SQLite.
**CLAUDE.md entries to add:**
```bash
# Run sqlite retry unit tests
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/test_sqlite_retry.py -v

# Run sqlite retry concurrent-write integration tests
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/test_sqlite_retry_integration.py -v --timeout=60
```

## Interfaces

### I1: sqlite_retry.with_retry

```python
def with_retry(
    server_name: str,
    max_attempts: int = 3,
    backoff: tuple[float, ...] = (0.1, 0.5, 2.0),
) -> Callable:
    """Decorator factory for retrying SQLite operations on transient errors.

    Catches sqlite3.OperationalError, checks is_transient(). If transient,
    retries with exponential backoff + jitter. If not transient or retries
    exhausted, re-raises the exception.

    Args:
        server_name: Prefix for log messages (e.g., "entity", "memory").
        max_attempts: Maximum number of attempts (default 3).
        backoff: Tuple of sleep durations in seconds for each retry.
            Index clamped to last element for attempts beyond tuple length.

    Returns:
        Decorator that wraps a function with retry logic.
    """
```

**Behavior:**
1. Call wrapped function
2. On `sqlite3.OperationalError`:
   a. Call `is_transient(exc)` — if False, re-raise immediately
   b. If attempt < max_attempts: log warning with `server_name` prefix, sleep `backoff[min(attempt, len(backoff)-1)] + random.uniform(0, 0.05)`, retry
   c. If attempt == max_attempts: re-raise last exception
3. On success: return result

### I2: sqlite_retry.is_transient

```python
def is_transient(exc: Exception) -> bool:
    """Classify whether a SQLite error is transient (retryable).

    Returns True for OperationalError containing 'locked' (case-insensitive).
    Returns False for all other errors.
    """
```

### I3: Entity Engine Cascade Transaction

```python
# In EntityWorkflowEngine._run_cascade()
def _run_cascade(self, entity_uuid: str) -> tuple[list[str], float | None]:
    """Run cascade operations atomically within Phase B."""
    unblocked: list[str] = []
    parent_progress: float | None = None

    # Transaction scope: only the two write operations
    with self._db.transaction():
        unblocked = self._dep_manager.cascade_unblock(self._db, entity_uuid)
        rollup_parent(self._db, entity_uuid)

    # Read-only operations OUTSIDE transaction (no write lock held).
    # Note: compute_progress may read slightly stale data if another writer
    # commits between transaction end and this read. This is acceptable —
    # stale progress self-corrects on the next reconciliation cycle.
    entity = self._db.get_entity_by_uuid(entity_uuid)
    if entity is not None:
        parent_uuid = entity.get("parent_uuid")
        if parent_uuid is not None:
            parent_progress = compute_progress(self._db, parent_uuid)

    # Notifications after DB operations
    if self._notification_queue is not None:
        self._push_notifications(entity_uuid, unblocked)

    return unblocked, parent_progress
```

### I4: Entity Server Decorator Application Pattern

**Type A (existing server_helpers functions):**
```python
# In server_helpers.py — add decorator to existing functions
from sqlite_retry import with_retry

@with_retry("entity")
def _process_register_entity(db, entity_type, entity_id, name, ...):
    ...  # existing logic unchanged
```

**Type B (inline handlers → extract + decorate):**
```python
# In entity_server.py — extract inline DB logic to sync helper
from sqlite_retry import with_retry

@with_retry("entity")
def _process_delete_entity(db, resolved_type_id):
    db.delete_entity(resolved_type_id)
    return json.dumps({"result": f"Deleted: {resolved_type_id}"})

@mcp.tool()
async def delete_entity(type_id=None, ref=None) -> str:
    if _db is None:
        return "Error: database not initialized"
    try:
        resolved = _resolve_ref_param(_db, type_id, ref, is_mutation=True)
        return _process_delete_entity(_db, resolved)
    except Exception as exc:
        # Catches exhausted-retry OperationalError → structured error
        return json.dumps({"error": str(exc)})
```

**Error conversion:** The existing `except Exception` in async handlers already converts any exception (including exhausted-retry OperationalError) to a structured JSON error response. No additional error handling wrapper needed.

### I5: Memory Server Decorator Application Pattern

```python
# In memory_server.py — apply to existing sync helpers
from sqlite_retry import with_retry

@with_retry("memory")
def _process_store_memory(db, provider, name, description, reasoning,
                          category, references, confidence="medium",
                          source_project="", config=None) -> str:
    ...  # existing logic unchanged
```

### I6: Workflow State Server Refactor Pattern

```python
# Replace local definitions with imports
from sqlite_retry import with_retry as _make_retry, is_transient as _is_transient

# Create server-specific decorator instance
_with_retry = _make_retry("workflow-state")

# All existing @_with_retry() decorator calls remain unchanged
# except _with_retry is now a pre-configured instance, not a factory call
```

**Wait — this changes semantics.** The existing `_with_retry()` is called WITH parentheses as a decorator factory. If we replace it with a pre-configured decorator, the call sites need adjustment. Two options:

**Approach:** Import and alias the factory with `**kwargs` passthrough (no duplicated defaults):
```python
from sqlite_retry import with_retry, is_transient

def _with_retry(**kwargs):
    return with_retry("workflow-state", **kwargs)

_is_transient = is_transient
```
This preserves all `@_with_retry()` call sites unchanged. Defaults are maintained only in `with_retry` — no dual-defaults maintenance burden.

## Dependency Graph

```
C1 (sqlite_retry.py)
├── C2 (entity_server.py) — imports from C1
├── C3 (memory_server.py) — imports from C1
├── C4 (workflow_state_server.py) — imports from C1, replaces locals
└── C8 (test_concurrent.py) — tests C1

C5 (entity_engine.py cascade fix) — independent of C1
C6 (database.py multi-step wrapping) — independent of C1
C7 (timeout standardization) — independent of C1
```

**Implementation order:**
1. C1 (shared module) — prerequisite for C2, C3, C4
2. C7 (timeout) — no dependencies, quick win
3. C5 (cascade atomicity) — independent, medium risk
4. C6 (multi-step writes) — requires audit
5. C4 (workflow refactor) — depends on C1
6. C2 (entity server) — depends on C1
7. C3 (memory server) — depends on C1
8. C8 (integration tests) — depends on all above
