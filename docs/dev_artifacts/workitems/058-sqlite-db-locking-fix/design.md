# Design: SQLite DB Locking Fixes

## Prior Art Research

### Codebase Patterns
- `semantic_memory/database.py` `_migrate()` (line ~780): no outer transaction, individual commits per migration, 4 `executescript` calls across migrations 1-3
- `entity_registry/database.py` `_in_transaction` flag + `_commit()` helper + `transaction()` context manager: well-designed transaction architecture, but `begin_immediate()` doesn't participate
- `entity_registry/database.py` migration 5: `SELECT * FROM workflow_phases` — fragile; migration 6 already uses explicit column lists (good pattern to follow)
- Migration 2 in entity_registry (line 152): also uses `SELECT *` from entities table for UUID migration — noted but lower risk since entities table structure is stable

### External Research
- SQLite `executescript()` issues implicit COMMIT — incompatible with outer `BEGIN IMMEDIATE`
- SQLite `in_transaction` property on Connection reflects actual transaction state
- `BEGIN IMMEDIATE` acquires write lock upfront — prevents concurrent migration race

---

## Architecture Overview

Three independent fixes, no shared state between them:

```
Fix 1: semantic_memory/database.py
  _migrate() → wrap in BEGIN IMMEDIATE
  Migrations 1-3 → convert executescript to execute

Fix 2: entity_registry/database.py
  begin_immediate() → set _in_transaction = True

Fix 3: entity_registry/database.py
  Migration 5 → explicit column lists in INSERT/SELECT
```

---

## Components

### C1: MemoryDatabase Migration Lock (FR-1)

**File:** `plugins/pd/hooks/lib/semantic_memory/database.py`

Two changes:
1. **`_migrate()` method**: Wrap the migration loop in `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`
2. **Migrations 1-3**: Convert all `executescript()` calls to sequential `execute()` calls

### C2: EntityDatabase begin_immediate Fix (FR-2)

**File:** `plugins/pd/hooks/lib/entity_registry/database.py`

Single change to `begin_immediate()`: set `self._in_transaction = True` before yield, reset in `finally`. Add nesting guard matching `transaction()`.

### C3: EntityDatabase Migration 5 Column Lists (FR-3)

**File:** `plugins/pd/hooks/lib/entity_registry/database.py`

Single change to `_expand_workflow_phase_check()`: replace `SELECT *` with explicit 7-column list. Migration 6 audited — already uses explicit column lists (lines 682-686), no change required.

---

## Technical Decisions

### TD-1: executescript conversion scope — ALL calls including _create_fts5_objects

**Decision:** Convert ALL `executescript` calls to `execute()`, including `_create_fts5_objects`. This is required because `_create_fts5_objects` is called from BOTH migration 1 (line 93) AND migration 3 (line 234) — both run inside the outer `BEGIN IMMEDIATE` transaction.

**Rationale:** `_create_fts5_objects` has a single `executescript` call (line 120) containing 3 CREATE TRIGGER statements with f-string interpolation. Convert to 3 separate `execute()` calls, each with its f-string intact. The function already uses `execute()` for the CREATE VIRTUAL TABLE (line 112), so this is consistent.

**Migration 3 also has `INSERT INTO entries_new SELECT * FROM entries` (line 222)** — same `SELECT *` fragility as entity_registry migration 5. Convert to explicit column list (16 columns at migration 3's schema point: the original 16 columns before migration 2 added source_hash and created_timestamp_utc — but migration 3 runs AFTER migration 2, so the table has 18 columns). Use explicit 18-column list.

### TD-2: begin_immediate nesting guard

**Decision:** Add `RuntimeError` on nesting, matching `transaction()` pattern.
**Rationale:** `transaction()` already raises on nesting (line 1157). `begin_immediate()` should be consistent.

### TD-3: Migration 2 SELECT * in entity_registry

**Decision:** Leave migration 2's `SELECT * FROM entities` (line 152) unchanged.
**Rationale:** Migration 2 reads rows into Python, generates UUIDs per row, then inserts into a new table with explicit column mapping. The `SELECT *` is used to read data into `Row` objects accessed by column name, not as a bulk INSERT. The pattern is safe — the Python code adapts to whatever columns exist.

---

## Interfaces

### I1: Updated `_migrate()` — semantic_memory/database.py

```python
def _migrate(self) -> None:
    # Bootstrap _metadata (idempotent, outside transaction).
    # SQLite serializes DDL; CREATE IF NOT EXISTS is safe under concurrency.
    self._conn.execute(
        "CREATE TABLE IF NOT EXISTS _metadata "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    self._conn.commit()

    # Acquire write lock for entire migration chain.
    # If BEGIN IMMEDIATE times out (busy_timeout=5s), OperationalError
    # propagates to caller — acceptable, caller should retry.
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

No post-transaction FTS5 block needed — `_create_fts5_objects` is converted to `execute()` (TD-1) and runs safely inside the transaction.

### I2: Updated `_create_initial_schema()` — line 66

Convert `executescript` to sequential `execute()`. FTS5 creation stays inside (now uses `execute()` too):
```python
def _create_initial_schema(conn, *, fts5_available=False, **_kwargs):
    conn.execute("""CREATE TABLE IF NOT EXISTS entries (...)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS _metadata (...)""")
    if fts5_available:
        _create_fts5_objects(conn)  # now uses execute(), safe inside transaction
```

### I3: Updated `_add_source_hash_and_created_timestamp()` — line 153

```python
def _add_source_hash_and_created_timestamp(conn, **_kwargs):
    conn.execute("ALTER TABLE entries ADD COLUMN source_hash TEXT")
    conn.execute("ALTER TABLE entries ADD COLUMN created_timestamp_utc REAL")
    conn.execute(
        "UPDATE entries SET created_timestamp_utc = CAST(strftime('%s', created_at) AS REAL)"
    )
```

### I4: Updated `_enforce_not_null_columns()` — line 201

Convert the `executescript` (table rebuild DDL) to sequential `execute()` calls. Each statement becomes a separate `execute()` call. Additionally, replace `INSERT INTO entries_new SELECT * FROM entries` with explicit 18-column list (all columns at this migration point: id, name, description, reasoning, category, keywords, source, source_project, "references", observation_count, confidence, recall_count, last_recalled_at, embedding, created_at, updated_at, source_hash, created_timestamp_utc).

### I5: Updated `begin_immediate()` — entity_registry/database.py

```python
@contextmanager
def begin_immediate(self):
    if self._in_transaction:
        raise RuntimeError("Nested transactions not supported")
    self._conn.commit()  # flush pending implicit transactions (matches transaction() pattern)
    self._conn.execute("BEGIN IMMEDIATE")
    self._in_transaction = True
    try:
        yield self._conn
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

### I6: Updated `_expand_workflow_phase_check()` — migration 5

```sql
-- Replace line 466:
INSERT INTO workflow_phases_new (type_id, workflow_phase, kanban_column,
    last_completed_phase, mode, backward_transition_reason, updated_at)
SELECT type_id, workflow_phase, kanban_column,
    last_completed_phase, mode, backward_transition_reason, updated_at
FROM workflow_phases
```

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| executescript → execute changes migration DDL behavior | Low | Medium | Test schema matches after migration via PRAGMA table_info |
| _create_fts5_objects execute() conversion breaks trigger creation | Low | Medium | 3 triggers become 3 execute() calls with same SQL — mechanical split. Test by verifying FTS5 triggers exist after migration. |
| begin_immediate nesting guard breaks callers | Low | Low | Only `transaction()` callers nest — they already check. `begin_immediate` callers use raw SQL. |

---

## File Change Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `plugins/pd/hooks/lib/semantic_memory/database.py` | Modify | `_migrate()` wrapped in BEGIN IMMEDIATE; migrations 1-3 and `_create_fts5_objects` converted from executescript to execute(); migration 3 SELECT * replaced with explicit 18-column list |
| `plugins/pd/hooks/lib/entity_registry/database.py` | Modify | `begin_immediate()` sets `_in_transaction` flag; migration 5 uses explicit column lists |
| `plugins/pd/hooks/lib/semantic_memory/test_database.py` | Modify | Add concurrent init test, migration atomicity test |
| `plugins/pd/hooks/lib/entity_registry/test_database.py` | Modify | Add begin_immediate + register_entity test |
