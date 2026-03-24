# Spec: SQLite DB Locking Fixes

## Problem Statement

Three SQLite concurrency/locking bugs in the pd plugin's database layer cause session-level failures. Bug 1 was directly responsible for the `.meta.json` state corruption observed during Feature 057 (stop hook fired 10+ times on stale state because workflow DB writes failed with "database is locked" throughout the session).

RCA source: `/Users/terry/projects/parameter-golf/docs/rca-pd-db-locking.md`

## Scope

Three bugs, two database modules:

1. **Bug 1: MemoryDatabase migration race condition** (`semantic_memory/database.py`)
2. **Bug 2: EntityDatabase `begin_immediate()` + high-level method incompatibility** (`entity_registry/database.py`)
3. **Bug 3: EntityDatabase migration 5 `SELECT *` fragility** (`entity_registry/database.py`)

## Requirements

### FR-1: Wrap MemoryDatabase migration chain in BEGIN IMMEDIATE

The `_migrate()` method in `semantic_memory/database.py` (line ~780) currently runs each migration with individual commits but no overarching write lock. When multiple connections open the same DB file concurrently (e.g., multiple hooks firing at session start), two connections can race through migrations simultaneously, causing `duplicate column name` or `database is locked` errors.

**Fix:** Wrap the entire migration loop in `BEGIN IMMEDIATE` / `COMMIT` with rollback on failure. This acquires the write lock before checking schema_version, preventing concurrent migration execution.

```python
def _migrate(self):
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

**Note:** Individual migration functions that use `executescript()` (which auto-commits) need to be changed to use `execute()` calls instead, since `executescript` issues an implicit COMMIT that would break the outer transaction. Migration 2 (`_add_source_hash_and_created_timestamp`) currently uses `executescript` — change to sequential `execute()` calls.

### FR-2: Make EntityDatabase high-level methods transaction-aware

`register_entity()` and other high-level methods on `EntityDatabase` use Python's SQLite autocommit mode (implicit `BEGIN`/`COMMIT` around each `execute()`). When called inside a `begin_immediate()` context manager, the autocommit `COMMIT` prematurely ends the outer transaction. Subsequent `ROLLBACK` from the context manager fails with `cannot rollback - no transaction is active`.

**Fix:** Check `self._conn.in_transaction` before committing in high-level methods. If already in a caller's transaction, skip the internal commit — let the caller manage the transaction boundary.

**Affected methods:** All high-level write methods that do their own `COMMIT`. At minimum: `register_entity()`. Audit other methods that write and commit: `update_entity()`, `add_dependency()`, `remove_dependency()`, `set_parent()`, etc. Apply the same `in_transaction` guard pattern to each.

**Alternative considered:** Adding a runtime guard to `begin_immediate()` that raises on nesting. Rejected because the goal is to allow composing high-level methods inside transactions, not to prevent it.

### FR-3: Use explicit column lists in EntityDatabase migration 5

Migration 5 (`_expand_workflow_phase_check`) uses `INSERT INTO workflow_phases_new SELECT * FROM workflow_phases`. This is fragile — if a later migration adds a column to `workflow_phases` before migration 5 runs (due to version tracking inconsistency or partial migration), the column counts mismatch and the INSERT fails.

**Fix:** Replace `SELECT *` with explicit column list:
```sql
INSERT INTO workflow_phases_new (type_id, workflow_phase, kanban_column,
    last_completed_phase, mode, backward_transition_reason, updated_at)
SELECT type_id, workflow_phase, kanban_column,
    last_completed_phase, mode, backward_transition_reason, updated_at
FROM workflow_phases
```

Also audit migration 6 (`_schema_expansion_v6`) for any `SELECT *` usage and apply the same fix.

## Non-Requirements (Out of Scope)

- **NR-1:** Changing SQLite isolation_level to manual mode globally — too invasive, affects all existing code
- **NR-2:** Adding file-level locking (fcntl.flock) — WAL mode + BEGIN IMMEDIATE is sufficient
- **NR-3:** Fixing the pre-existing `TestSysPathIdempotency` test failure (test ordering artifact, unrelated)
- **NR-4:** Restructuring EntityDatabase's transaction model wholesale — targeted `in_transaction` guard is sufficient

## Acceptance Criteria

### AC-1: MemoryDatabase concurrent init succeeds
6 threads concurrently creating `MemoryDatabase(same_path)` on a new DB file all succeed without errors. Verified by concurrent init test.

### AC-2: MemoryDatabase migration is atomic
If a migration fails mid-way, schema_version is not incremented. The next connection retries the failed migration. Verified by test that simulates migration failure.

### AC-3: register_entity inside begin_immediate works
`db.register_entity()` called inside `db.begin_immediate()` completes without error. The entire block is atomic (rollback works). Verified by test.

### AC-4: register_entity outside transaction still works
`db.register_entity()` called normally (not inside a transaction) continues to work as before. Verified by existing tests passing.

### AC-5: Migration 5 uses explicit column lists
`_expand_workflow_phase_check` uses explicit column names in both INSERT and SELECT. No `SELECT *` in any migration function. Verified by grep.

### AC-6: Existing tests pass
All semantic_memory tests (435+), entity_registry tests (940+), and MCP server tests pass without regressions.

## Dependencies

- Feature 056 (sqlite-write-contention-fix) — already merged, provides WAL mode + busy_timeout foundation
- Feature 057 (memory-phase2-quality) — already merged, added migration 4 to semantic_memory

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Migration 2 `executescript` → `execute` changes behavior | Low | Medium | Migration 2 is simple (2 ALTER TABLE + 1 UPDATE). Test that schema matches after migration. |
| `in_transaction` guard breaks existing EntityDatabase behavior | Low | Medium | Only skip commit when already in transaction. Normal (non-nested) calls are unchanged. |
| Concurrent migration test is flaky (thread timing) | Medium | Low | Use 6+ threads with barrier synchronization to maximize collision probability. Run 3 times in CI. |
