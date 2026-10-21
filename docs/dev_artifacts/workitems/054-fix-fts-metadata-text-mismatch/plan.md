# Plan: Fix FTS5 entities_fts metadata_text Column Mismatch

## Overview

Fix the FTS5 `entities_fts` virtual table by removing external-content mode (`content='entities'`), switching to standalone content-bearing mode, updating all FTS DML patterns, adding a database migration, and aligning test helpers.

## Step Sequence

### Step 1: Add migration 7 to database.py (FR-2)

**File:** `plugins/pd/hooks/lib/entity_registry/database.py`

Add function `_fix_fts_content_mode(conn)` that:
1. `BEGIN IMMEDIATE`
2. `DROP TABLE IF EXISTS entities_fts`
3. `CREATE VIRTUAL TABLE entities_fts USING fts5(name, entity_id, entity_type, status, metadata_text)` — no `content=` or `content_rowid=`
4. Backfill all entities using `flatten_metadata()` (same pattern as migration 4/6)
5. `COMMIT`

No `PRAGMA foreign_keys` guard needed — virtual tables have no FK constraints.
No schema_version upsert inside the function — the `_migrate()` loop handles it.

Register: `MIGRATIONS[7] = _fix_fts_content_mode`

**Done-when:** `EntityDB()` on a v6 database upgrades to v7. `get_schema_version()` returns `7`.

**Depends on:** Nothing.

### Step 2: Update FTS DELETE pattern in update_entity (FR-1)

**File:** `plugins/pd/hooks/lib/entity_registry/database.py`

Replace lines 1507-1527 (the FTS delete+insert block in `update_entity`):

Before:
```python
old_meta_text = flatten_metadata(json.loads(old_row["metadata"]) if old_row["metadata"] else None)
new_meta_text = flatten_metadata(json.loads(new_row["metadata"]) if new_row["metadata"] else None)
self._conn.execute(
    "INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, "
    "entity_type, status, metadata_text) "
    "VALUES('delete', ?, ?, ?, ?, ?, ?)",
    (old_row["rowid"], old_row["name"], old_row["entity_id"],
     old_row["entity_type"], old_row["status"] or "", old_meta_text),
)
self._conn.execute(
    "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
    "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
    (old_row["rowid"], new_row["name"], new_row["entity_id"],
     new_row["entity_type"], new_row["status"] or "", new_meta_text),
)
```

After:
```python
new_meta_text = flatten_metadata(
    json.loads(new_row["metadata"]) if new_row["metadata"] else None
)
# Standalone FTS: use DELETE FROM (not external-content VALUES('delete',...))
# INVARIANT: rowid must match entities table rowid
self._conn.execute("DELETE FROM entities_fts WHERE rowid = ?", (old_row["rowid"],))
self._conn.execute(
    "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
    "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
    (old_row["rowid"], new_row["name"], new_row["entity_id"],
     new_row["entity_type"], new_row["status"] or "", new_meta_text),
)
```

Remove the `old_meta_text` computation — no longer needed.

**Done-when:** `update_entity()` uses `DELETE FROM entities_fts WHERE rowid = ?`. Existing update tests pass.

**Depends on:** Step 1 (migration creates standalone FTS table).

### Step 3: Update FTS DELETE pattern in delete_entity (FR-1)

**File:** `plugins/pd/hooks/lib/entity_registry/database.py`

Replace lines 1567-1580 (FTS delete block in `delete_entity`):

Before:
```python
# 3. FTS5 external-content delete (before row deletion)
try:
    metadata_text = flatten_metadata(
        json.loads(row["metadata"]) if row["metadata"] else None
    )
except (json.JSONDecodeError, TypeError):
    metadata_text = ""
self._conn.execute(
    "INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, "
    "entity_type, status, metadata_text) "
    "VALUES('delete', ?, ?, ?, ?, ?, ?)",
    (row["rowid"], row["name"], row["entity_id"],
     row["entity_type"], row["status"] or "", metadata_text),
)
```

After:
```python
# Standalone FTS: delete by rowid (no old values needed)
# INVARIANT: rowid must match entities table rowid
self._conn.execute("DELETE FROM entities_fts WHERE rowid = ?", (row["rowid"],))
```

Remove the `metadata_text` computation and try/except block — no longer needed.

**Done-when:** `delete_entity()` uses `DELETE FROM entities_fts WHERE rowid = ?`. Existing delete tests pass.

**Depends on:** Step 1 (migration creates standalone FTS table).

### Step 4: Update test helper FTS schemas (FR-4)

**Files:**
- `scripts/test_migrate_db.py` — two locations
- `scripts/test_migrate_bash.sh` — one location

#### 4a: test_migrate_db.py `create_entity_db` (line ~327)

Change FTS CREATE from:
```sql
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    name, entity_type, entity_id, status, content=entities, content_rowid=rowid
);
```
To:
```sql
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    name, entity_id, entity_type, status, metadata_text
);
```

**Critical:** With standalone FTS (no `content=`), the existing `rebuild` at line 373 no longer populates FTS from the entities table. Replace the `rebuild` call with explicit FTS INSERTs:

Before (line 371-374):
```python
if entities:
    conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
    conn.commit()
```

After:
```python
if entities:
    for row in conn.execute("SELECT rowid, name, entity_id, entity_type, status, metadata FROM entities").fetchall():
        conn.execute(
            "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, status, metadata_text) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (row[0], row[1], row[2], row[3], row[4] or "", row[5] or ""),
        )
    conn.commit()
```

Note: test entities typically have no metadata, so `row[5] or ""` suffices (no need for `flatten_metadata`).

#### 4b: test_migrate_db.py deepened helper (line ~1133)

Change FTS CREATE from:
```sql
CREATE VIRTUAL TABLE entities_fts USING fts5(
    name, entity_id, entity_type, status, metadata_text,
    content='entities', content_rowid='rowid'
);
```
To:
```sql
CREATE VIRTUAL TABLE entities_fts USING fts5(
    name, entity_id, entity_type, status, metadata_text
);
```

**Deepened test callers investigated:** The deepened helper at line 1133 creates the schema but FTS rows are populated via manual INSERT (not rebuild). The `test_migration_fts_works` test at line 1443 runs `migrate` CLI which triggers `EntityDB()` auto-migration including migration 7's backfill — so it will work correctly. No deepened tests rely on rebuild for initial FTS population. Safe to change.

#### 4c: test_migrate_bash.sh (line ~878)

Update the bash test helper's FTS CREATE to match production schema (add `metadata_text`, remove `content=`).

**Done-when:** All three helpers create FTS tables matching production schema. FTS `rebuild` calls in helpers succeed.

**Depends on:** Nothing (test-only changes, but logically paired with Step 1 — the helpers should match the production schema that migration 7 creates).

### Step 5: Fix migrate_db.py FTS backfill (FR-3)

**File:** `scripts/migrate_db.py`

#### 5a: Add inline `_flatten_metadata` function

Add near the top of the file (after imports):
```python
def _flatten_metadata(metadata: dict | None) -> str:
    """Flatten metadata JSON to space-separated leaf values.

    Inlined from entity_registry.database.flatten_metadata (Spec Deviation FR-3).
    """
    if metadata is None:
        return ""
    parts: list[str] = []
    def _walk(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for v in obj:
                _walk(v)
        elif obj is not None:
            parts.append(str(obj))
    _walk(metadata)
    return " ".join(parts)
```

#### 5b: Replace silent rebuild with proper backfill

Replace lines 344-350 in `merge_entities`:
```python
# Phase 5: FTS5 rebuild
try:
    dst.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
except sqlite3.OperationalError:
    pass
```

With (note: this runs inside the existing BEGIN/COMMIT block at lines ~291/352 — do not add a nested transaction):
```python
# Phase 5: FTS5 backfill (clear + re-index all entities)
dst.execute("DELETE FROM entities_fts")
rows = dst.execute(
    "SELECT rowid, name, entity_id, entity_type, status, metadata FROM entities"
).fetchall()
for row in rows:
    try:
        meta_text = _flatten_metadata(json.loads(row[5]) if row[5] else None)
        dst.execute(
            "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
            "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
            (row[0], row[1], row[2], row[3], row[4] or "", meta_text),
        )
    except (sqlite3.OperationalError, json.JSONDecodeError) as exc:
        print(f"WARNING: FTS index failed for rowid={row[0]}: {exc}", file=sys.stderr)
```

**Done-when:** `merge_entities` indexes all entities into FTS. No silent `except pass`.

**Depends on:** Step 4 (test helpers must match for tests to pass).

### Step 6: Add FTS rebuild regression test (FR-5, AC-7)

**File:** `plugins/pd/hooks/lib/entity_registry/test_search.py` (or appropriate test file in that directory)

```python
def test_fts_rebuild_succeeds_on_production_schema(tmp_path):
    """AC-7: Verify FTS rebuild works on standalone content-bearing table."""
    db = EntityDB(str(tmp_path / "test.db"))
    db.register_entity(entity_type="feature", entity_id="test-rebuild",
                       name="Rebuild Test Feature", metadata={"key": "value"})
    # Rebuild should succeed (was broken before this fix)
    db._conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
    # Integrity check should pass
    db._conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('integrity-check')")
    # Search should still find the entity after rebuild
    results = db.search_entities("Rebuild")
    assert len(results) == 1
    assert results[0]["entity_id"] == "test-rebuild"
```

**Done-when:** Test passes. Rebuild and integrity-check succeed on production schema.

**Depends on:** Step 1.

### Step 7: Add migration 7 test (AC-4)

**File:** `plugins/pd/hooks/lib/entity_registry/test_search.py` (or test_database.py)

Create a v6 database manually, then instantiate `EntityDB()` which will auto-run only migration 7, and verify:

**V6 fixture setup:**
```python
conn = sqlite3.connect(str(db_path))
conn.executescript("""
    CREATE TABLE _metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    INSERT INTO _metadata VALUES ('schema_version', '6');
    CREATE TABLE entities (
        uuid TEXT NOT NULL PRIMARY KEY, type_id TEXT NOT NULL UNIQUE,
        entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, name TEXT NOT NULL,
        status TEXT, parent_type_id TEXT, parent_uuid TEXT, artifact_path TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, metadata TEXT
    );
    CREATE VIRTUAL TABLE entities_fts USING fts5(
        name, entity_id, entity_type, status, metadata_text,
        content='entities', content_rowid='rowid'
    );
    CREATE TABLE workflow_phases (
        type_id TEXT NOT NULL, workflow_phase TEXT, kanban_column TEXT,
        last_completed_phase TEXT, mode TEXT, backward_transition_reason TEXT,
        updated_at TEXT NOT NULL
    );
    INSERT INTO entities VALUES (
        'uuid-1', 'feature:test-v6', 'feature', 'test-v6', 'V6 Test Entity',
        'active', NULL, NULL, NULL, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', NULL
    );
""")
# Manually add FTS entry (external-content mode)
conn.execute(
    "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, status, metadata_text) "
    "VALUES(1, 'V6 Test Entity', 'test-v6', 'feature', 'active', '')"
)
conn.commit()
conn.close()
# Now open with EntityDB — triggers migration 7
db = EntityDB(str(db_path))
```

Verify:
1. `get_schema_version() == 7`
2. Pre-existing entities are searchable via `search_entities()`
3. FTS `rebuild` succeeds
4. FTS `integrity-check` passes

**Done-when:** Test passes. Migration 7 correctly upgrades v6 databases.

**Depends on:** Step 1, Step 4 (needs updated test helpers).

### Step 8: Add merge_entities FTS test (AC-5)

**File:** `scripts/test_migrate_db.py`

```python
def test_merge_entities_fts_searchable(tmp_path):
    """AC-5: Imported entities appear in search results after merge."""
    src_path = tmp_path / "src.db"
    dst_path = tmp_path / "dst.db"
    create_entity_db(str(src_path), entities=[
        {"entity_type": "feature", "entity_id": "import-test",
         "name": "TestImport", ...}
    ])
    create_entity_db(str(dst_path), entities=[])
    merge_entities(str(src_path), str(dst_path))
    # Verify imported entity is FTS-searchable
    dst = sqlite3.connect(str(dst_path))
    dst.row_factory = sqlite3.Row
    results = dst.execute(
        "SELECT e.* FROM entities_fts JOIN entities e ON entities_fts.rowid = e.rowid "
        "WHERE entities_fts MATCH 'TestImport'",
    ).fetchall()
    assert len(results) == 1
    assert results[0]["entity_id"] == "import-test"
```

**Done-when:** Test passes. Imported entities are searchable.

**Depends on:** Step 4, Step 5.

### Step 9: Run full test suite and verify (AC-3)

Run all test suites to verify no regressions:

```bash
# Entity registry tests (710+)
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v

# Migration tests (128)
python3 -m pytest scripts/test_migrate_db.py -v

# Bash migration tests
bash scripts/test_migrate_bash.sh
```

**Done-when:** All existing tests pass. No assertion changes needed (only CREATE VIRTUAL TABLE changes in helpers).

**Depends on:** Steps 1-8.

## Dependency Graph

```
Step 1 (migration 7) ──┬── Step 2 (update_entity DML)
                        ├── Step 3 (delete_entity DML)
                        ├── Step 6 (rebuild regression test)
                        └── Step 7 (migration 7 test)

Step 4 (test helpers) ──┬── Step 5 (migrate_db.py backfill)
                        ├── Step 7 (migration 7 test)
                        └── Step 8 (merge_entities test)

Step 5 (backfill) ──────── Step 8 (merge_entities test)

Steps 1-8 ─────────────── Step 9 (full test suite)
```

## Verification Strategy

| AC | Verified By |
|----|------------|
| AC-1: FTS rebuild succeeds | Step 6 test |
| AC-2: integrity-check passes | Step 6 test |
| AC-3: search_entities unchanged | Step 9 full suite |
| AC-4: Migration 7 upgrades v6 | Step 7 test |
| AC-5: merge_entities indexes | Step 8 test |
| AC-6: Test helpers match production | Step 4 + Step 9 |
| AC-7: Rebuild regression test | Step 6 test |
