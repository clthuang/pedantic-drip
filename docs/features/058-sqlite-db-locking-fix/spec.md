# Spec: SQLite DB Locking Fixes

## Problem Statement

Three SQLite concurrency/locking bugs in the pd plugin's database layer cause session-level failures. Bug 1 was directly responsible for the `.meta.json` state corruption observed during Feature 057 (stop hook fired 10+ times on stale state because workflow DB writes failed with "database is locked" throughout the session).

RCA source: `/Users/terry/projects/parameter-golf/docs/rca-pd-db-locking.md`

## Scope

Three bugs, two database modules:

1. **Bug 1: MemoryDatabase migration race condition** (`semantic_memory/database.py`)
2. **Bug 2: EntityDatabase `begin_immediate()` doesn't set `_in_transaction` flag** (`entity_registry/database.py`)
3. **Bug 3: EntityDatabase migration 5 `SELECT *` fragility** (`entity_registry/database.py`)

## Requirements

### FR-1: Wrap MemoryDatabase migration chain in BEGIN IMMEDIATE

The `_migrate()` method in `semantic_memory/database.py` (line ~780) currently runs each migration with individual commits but no overarching write lock. When multiple connections open the same DB file concurrently (e.g., multiple hooks firing at session start), two connections can race through migrations simultaneously, causing `duplicate column name` or `database is locked` errors.

**Fix:** Wrap the entire migration loop in `BEGIN IMMEDIATE` / `COMMIT` with rollback on failure. This acquires the write lock before checking schema_version, preventing concurrent migration execution.

```python
def _migrate(self):
    # Bootstrap _metadata table — idempotent CREATE IF NOT EXISTS.
    # Intentionally OUTSIDE the transaction: SQLite serializes DDL,
    # and CREATE IF NOT EXISTS is safe under concurrency.
    self._conn.execute("CREATE TABLE IF NOT EXISTS _metadata ...")
    self._conn.commit()

    self._conn.execute("BEGIN IMMEDIATE")
    try:
        current = self.get_schema_version()
        target = max(MIGRATIONS) if MIGRATIONS else 0
        for version in range(current + 1, target + 1):
            migration_fn = MIGRATIONS[version]
            migration_fn(self._conn, fts5_available=self._fts5_available)
            self._conn.execute(
                "INSERT INTO _metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("schema_version", str(version)),
            )
        self._conn.commit()
    except Exception:
        self._conn.rollback()
        raise
```

**`executescript` conversion required:** `executescript()` issues an implicit COMMIT that would break the outer `BEGIN IMMEDIATE` transaction. ALL migrations using `executescript` must be converted to sequential `execute()` calls:

| Migration | Function | Lines with `executescript` |
|-----------|----------|--------------------------|
| 1 | `_create_initial_schema` | line 66 (DDL), line 120 (`_create_fts5_objects`) |
| 2 | `_add_source_hash_and_created_timestamp` | line 153 (2 ALTER TABLE + 1 UPDATE) |
| 3 | `_enforce_not_null_columns` | line 201 (table rebuild) |

Each `executescript("""...""")` call should be split into individual `execute()` calls for each SQL statement. This is a mechanical transformation — the SQL statements themselves don't change, only the Python call method. Note: `_create_fts5_objects` (line 120) contains 3 CREATE TRIGGER statements in a single executescript, each using f-string interpolation with `_KEYWORDS_STRIP` — these become 3 separate `execute()` calls, each with its f-string intact.

**Note:** Migrations 4+ (including the new migration 4 from Feature 057) already use `execute()` and are compatible with the outer transaction.

### FR-2: Make `begin_immediate()` set `_in_transaction` flag

The EntityDatabase already has a well-designed transaction architecture:
- `_in_transaction: bool` flag (initialized `False` in `__init__`, line 965)
- `_commit()` helper (line 979) that skips commit when `_in_transaction` is `True`
- `transaction()` context manager (line 1150) that sets `_in_transaction = True`, suppressing `_commit()` calls inside the block

The bug: `begin_immediate()` (line 1132) does NOT set `_in_transaction = True`. When `register_entity()` or other high-level methods call `_commit()` inside a `begin_immediate()` block, `_commit()` fires because the flag is `False`, prematurely ending the outer transaction.

**Fix:** Make `begin_immediate()` set `self._in_transaction = True` (and reset in `finally` block), matching the `transaction()` pattern:

```python
@contextmanager
def begin_immediate(self):
    """Context manager that wraps a block in BEGIN IMMEDIATE."""
    if self._in_transaction:
        raise RuntimeError("Nested transactions not supported")
    self._conn.execute("BEGIN IMMEDIATE")
    self._in_transaction = True
    try:
        yield self._conn
        self._conn.execute("COMMIT")
    except Exception:
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass  # connection may be in bad state
        raise
    finally:
        self._in_transaction = False
```

**No per-method changes needed.** All high-level methods (`register_entity`, `update_entity`, `add_dependency`, etc.) already call `_commit()` which already checks `_in_transaction`. Setting the flag in `begin_immediate()` is the only change required.

### FR-3: Use explicit column lists in EntityDatabase migrations

Migration 5 (`_expand_workflow_phase_check`) uses `INSERT INTO workflow_phases_new SELECT * FROM workflow_phases`. This is fragile — if a later migration adds a column to `workflow_phases` (e.g., migration 6 adds `uuid`), and migration 5 re-runs on a DB with the extra column present (due to version tracking inconsistency or cross-version plugin access), the column counts mismatch.

**Specific column mismatch:** Migration 5 creates `workflow_phases_new` with 7 columns (type_id, workflow_phase, kanban_column, last_completed_phase, mode, backward_transition_reason, updated_at). If the source `workflow_phases` already has an 8th column (`uuid`, added by migration 6), `SELECT *` produces 8 values for a 7-column target.

**Fix:** Replace `SELECT *` with explicit column lists in migration 5:
```sql
INSERT INTO workflow_phases_new (type_id, workflow_phase, kanban_column,
    last_completed_phase, mode, backward_transition_reason, updated_at)
SELECT type_id, workflow_phase, kanban_column,
    last_completed_phase, mode, backward_transition_reason, updated_at
FROM workflow_phases
```

Also audit migration 6 (`_schema_expansion_v6`) for any `SELECT *` usage and apply the same fix with explicit column lists.

## Non-Requirements (Out of Scope)

- **NR-1:** Changing SQLite isolation_level to manual mode globally — too invasive, affects all existing code
- **NR-2:** Adding file-level locking (fcntl.flock) — WAL mode + BEGIN IMMEDIATE is sufficient
- **NR-3:** Fixing the pre-existing `TestSysPathIdempotency` test failure (test ordering artifact, unrelated)
- **NR-4:** Restructuring EntityDatabase's transaction model wholesale — the existing `_in_transaction` + `_commit()` pattern is sound, just needs `begin_immediate()` to participate
- **NR-5:** Deprecating `begin_immediate()` in favor of `transaction()` — both serve valid use cases (raw SQL vs. high-level methods)
- **NR-6:** EntityDatabase `_migrate()` race condition — entity_registry migrations 3-6 each use self-managed `BEGIN IMMEDIATE` internally, so the race window is limited to the migration loop's schema_version check. This is a lower-priority concern since entity DB init is less concurrent than memory DB init (entity DB is opened once per MCP server, not per-hook). Defer to a follow-up if observed in practice.

## Acceptance Criteria

### AC-1: MemoryDatabase concurrent init succeeds
6 threads concurrently creating `MemoryDatabase(same_path)` on a new DB file all succeed without errors. Post-condition: schema_version equals target AND all expected columns exist in the entries table. Verified by concurrent init test.

### AC-2: MemoryDatabase migration is atomic
If a migration fails mid-way, schema_version is not incremented. The next connection retries the failed migration. Verified by test that simulates migration failure.

### AC-3: register_entity inside begin_immediate works
`db.register_entity()` called inside `db.begin_immediate()` completes without error. The entire block is atomic (rollback on exception reverts all changes). Verified by test.

### AC-4: register_entity outside transaction still works
`db.register_entity()` called normally (not inside a transaction) continues to work as before. Verified by existing tests passing.

### AC-5: transaction() still works
`db.transaction()` context manager continues to work correctly (regression guard). Verified by existing tests passing.

### AC-6: Migration 5 uses explicit column lists
`_expand_workflow_phase_check` uses explicit column names in both INSERT and SELECT. No `SELECT *` in any migration function. Verified by grep.

### AC-7: Existing tests pass
All semantic_memory tests (435+), entity_registry tests (940+), and MCP server tests pass without regressions.

## Dependencies

- Feature 056 (sqlite-write-contention-fix) — merged to main, provides WAL mode + busy_timeout foundation
- Feature 057 (memory-phase2-quality) — merged to main, added migration 4 to semantic_memory (already uses `execute()`, compatible with outer transaction)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `executescript` → `execute` conversion changes migration behavior | Low | Medium | Each conversion is mechanical (split multi-statement string into individual calls). Verify schema matches by comparing PRAGMA table_info before/after. |
| `_in_transaction` flag in `begin_immediate()` breaks callers that relied on `_commit()` firing | Low | Low | The whole point is to suppress `_commit()` inside `begin_immediate()`. Any caller that needed the commit to fire was already broken (Bug 2). |
| Concurrent migration test is flaky (thread timing) | Medium | Low | Use 6+ threads with barrier synchronization to maximize collision probability. Run multiple times. |
| Migration 6 also has `SELECT *` that needs fixing | Low | Medium | FR-3 explicitly calls for auditing migration 6. |
