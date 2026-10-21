# Tasks: Fix FTS5 entities_fts metadata_text Column Mismatch

## Phase A: Core Migration & DML Updates

### Task 1.1: Add migration 7 function to database.py
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Plan Step:** 1
**Depends on:** None

Add `_fix_fts_content_mode(conn)` after migration 6. Function body:
```python
def _fix_fts_content_mode(conn: sqlite3.Connection) -> None:
    """Migration 7: Remove external-content mode from entities_fts."""
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("DROP TABLE IF EXISTS entities_fts")
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE entities_fts USING fts5("
            "name, entity_id, entity_type, status, metadata_text)"
        )
    except sqlite3.OperationalError as exc:
        if "no such module: fts5" in str(exc):
            raise RuntimeError("FTS5 extension not available") from exc
        raise
    rows = conn.execute(
        "SELECT rowid, name, entity_id, entity_type, status, metadata FROM entities"
    ).fetchall()
    for row in rows:
        metadata_text = flatten_metadata(
            json.loads(row[5]) if row[5] else None
        )
        conn.execute(
            "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
            "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
            (row[0], row[1], row[2], row[3], row[4] or "", metadata_text),
        )
    conn.commit()
```

Register in MIGRATIONS dict: `MIGRATIONS[7] = _fix_fts_content_mode` (add after the existing entry for key 6).

**Done-when:** Function exists, registered in MIGRATIONS dict. `grep -c '_fix_fts_content_mode' database.py` returns 2 (definition + registration).

### Task 1.2: Update FTS DELETE in update_entity
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Plan Step:** 2
**Depends on:** 1.1

Replace the FTS delete+insert block in `update_entity`. Find:
```python
        old_meta_text = flatten_metadata(
            json.loads(old_row["metadata"]) if old_row["metadata"] else None
        )
        new_meta_text = flatten_metadata(
            json.loads(new_row["metadata"]) if new_row["metadata"] else None
        )
        self._conn.execute(
            "INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, "
            "entity_type, status, metadata_text) "
            "VALUES('delete', ?, ?, ?, ?, ?, ?)",
            (old_row["rowid"], old_row["name"], old_row["entity_id"],
             old_row["entity_type"], old_row["status"] or "",
             old_meta_text),
        )
        self._conn.execute(
            "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
            "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
            (old_row["rowid"], new_row["name"], new_row["entity_id"],
             new_row["entity_type"], new_row["status"] or "",
             new_meta_text),
        )
```

Replace with:
```python
        new_meta_text = flatten_metadata(
            json.loads(new_row["metadata"]) if new_row["metadata"] else None
        )
        # Standalone FTS: use DELETE FROM (not external-content VALUES('delete',...))
        # INVARIANT: rowid must match entities table rowid
        self._conn.execute(
            "DELETE FROM entities_fts WHERE rowid = ?", (old_row["rowid"],)
        )
        self._conn.execute(
            "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
            "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
            (old_row["rowid"], new_row["name"], new_row["entity_id"],
             new_row["entity_type"], new_row["status"] or "",
             new_meta_text),
        )
```

**Done-when:** `grep "DELETE FROM entities_fts WHERE rowid" database.py` matches. No `VALUES('delete'` in update_entity.

### Task 1.3: Update FTS DELETE in delete_entity
**File:** `plugins/pd/hooks/lib/entity_registry/database.py`
**Plan Step:** 3
**Depends on:** 1.1

Replace the FTS delete block in `delete_entity`. Find:
```python
            # 3. FTS5 external-content delete (before row deletion)
            try:
                metadata_text = flatten_metadata(
                    json.loads(row["metadata"]) if row["metadata"] else None
                )
            except (json.JSONDecodeError, TypeError):
                metadata_text = ""  # corrupted metadata — use empty for FTS delete
            self._conn.execute(
                "INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, "
                "entity_type, status, metadata_text) "
                "VALUES('delete', ?, ?, ?, ?, ?, ?)",
                (row["rowid"], row["name"], row["entity_id"],
                 row["entity_type"], row["status"] or "", metadata_text),
            )
```

Replace with:
```python
            # Standalone FTS: delete by rowid (no old values needed)
            # INVARIANT: rowid must match entities table rowid
            self._conn.execute(
                "DELETE FROM entities_fts WHERE rowid = ?", (row["rowid"],)
            )
```

**Done-when:** `grep -c "VALUES('delete'" database.py` returns 0. delete_entity uses `DELETE FROM entities_fts WHERE rowid`.

## Phase B: Test Helper Alignment

### Task 2.1: Update create_entity_db FTS schema in test_migrate_db.py
**File:** `scripts/test_migrate_db.py`
**Plan Step:** 4a
**Depends on:** None

Find the FTS CREATE in `create_entity_db` (near line 327):
```sql
        CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
            name, entity_type, entity_id, status, content=entities, content_rowid=rowid
        );
```

Replace with:
```sql
        CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
            name, entity_id, entity_type, status, metadata_text
        );
```

Then replace the FTS rebuild (near line 371-374):
```python
    if entities:
        conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
        conn.commit()
```

With explicit FTS INSERTs:
```python
    if entities:
        for row in conn.execute(
            "SELECT rowid, name, entity_id, entity_type, status, metadata FROM entities"
        ).fetchall():
            conn.execute(
                "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
                "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3], row[4] or "", row[5] or ""),
            )
        conn.commit()
```

**Done-when:** `create_entity_db` creates standalone FTS with `metadata_text`. No `content=entities` in the helper. No `VALUES('rebuild')` in the helper.

### Task 2.2: Update deepened test helper FTS schema in test_migrate_db.py
**File:** `scripts/test_migrate_db.py`
**Plan Step:** 4b
**Depends on:** None

Find the deepened helper FTS CREATE (near line 1133):
```sql
        CREATE VIRTUAL TABLE entities_fts USING fts5(
            name, entity_id, entity_type, status, metadata_text,
            content='entities', content_rowid='rowid'
        );
```

Replace with:
```sql
        CREATE VIRTUAL TABLE entities_fts USING fts5(
            name, entity_id, entity_type, status, metadata_text
        );
```

**Done-when:** Deepened helper FTS CREATE has no `content='entities'`. `grep "content='entities'" test_migrate_db.py` returns no matches.

### Task 2.3: Update bash test helper FTS schema
**File:** `scripts/test_migrate_bash.sh`
**Plan Step:** 4c
**Depends on:** None

Find the FTS CREATE (near line 878):
```sql
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    name, entity_type, entity_id, status, content=entities, content_rowid=rowid
);
```

Replace with:
```sql
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    name, entity_id, entity_type, status, metadata_text
);
```

Note: column order changes from `name, entity_type, entity_id` to `name, entity_id, entity_type` to match production.

**Done-when:** Bash helper creates FTS matching production schema. `grep "metadata_text" test_migrate_bash.sh` returns a match. No `content=entities` in the FTS CREATE.

## Phase C: migrate_db.py Backfill Fix

### Task 3.1: Add _flatten_metadata to migrate_db.py
**File:** `scripts/migrate_db.py`
**Plan Step:** 5a
**Depends on:** None

Add after imports (near top of file):
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

**Done-when:** `grep -c "_flatten_metadata" migrate_db.py` returns >= 2 (definition + usage).

### Task 3.2: Replace silent FTS rebuild with proper backfill in merge_entities
**File:** `scripts/migrate_db.py`
**Plan Step:** 5b
**Depends on:** 3.1

Find in `merge_entities` (near line 344):
```python
        # Phase 5: FTS5 rebuild
        try:
            dst.execute(
                "INSERT INTO entities_fts(entities_fts) VALUES('rebuild')"
            )
        except sqlite3.OperationalError:
            pass
```

Replace with (note: this runs inside the existing BEGIN/COMMIT block — no nested transaction):
```python
        # Phase 5: FTS5 backfill (clear + re-index all entities)
        dst.execute("DELETE FROM entities_fts")
        fts_rows = dst.execute(
            "SELECT rowid, name, entity_id, entity_type, status, metadata "
            "FROM entities"
        ).fetchall()
        for fts_row in fts_rows:
            try:
                meta_text = _flatten_metadata(
                    json.loads(fts_row[5]) if fts_row[5] else None
                )
                dst.execute(
                    "INSERT INTO entities_fts(rowid, name, entity_id, "
                    "entity_type, status, metadata_text) "
                    "VALUES(?, ?, ?, ?, ?, ?)",
                    (fts_row[0], fts_row[1], fts_row[2], fts_row[3],
                     fts_row[4] or "", meta_text),
                )
            except (sqlite3.OperationalError, json.JSONDecodeError) as exc:
                print(
                    f"WARNING: FTS index failed for rowid={fts_row[0]}: {exc}",
                    file=sys.stderr,
                )
```

Ensure `import sys` is present at the top of the file (check first — likely already imported).

**Done-when:** No `VALUES('rebuild')` in `merge_entities`. `grep "DELETE FROM entities_fts" migrate_db.py` matches. `grep "_flatten_metadata" migrate_db.py` shows usage in the backfill.

## Phase D: New Tests

### Task 4.1: Add FTS rebuild regression test
**File:** `plugins/pd/hooks/lib/entity_registry/test_search.py`
**Plan Step:** 6
**Depends on:** 1.1

```python
def test_fts_rebuild_succeeds_on_production_schema(tmp_path):
    """AC-7: Verify FTS rebuild works on standalone content-bearing table."""
    db = EntityDB(str(tmp_path / "test.db"))
    db.register_entity(
        entity_type="feature", entity_id="test-rebuild",
        name="Rebuild Test Feature", metadata={"key": "value"},
    )
    # Rebuild should succeed (was broken before this fix)
    db._conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
    # Integrity check should pass
    db._conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('integrity-check')")
    # Search should still find the entity after rebuild
    results = db.search_entities("Rebuild")
    assert len(results) == 1
    assert results[0]["entity_id"] == "test-rebuild"
```

**Done-when:** Test passes: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_search.py::test_fts_rebuild_succeeds_on_production_schema -v`

### Task 4.2: Add migration 7 upgrade test
**File:** `plugins/pd/hooks/lib/entity_registry/test_search.py`
**Plan Step:** 7
**Depends on:** 1.1, 2.1

```python
def test_migration_7_upgrades_v6_database(tmp_path):
    """AC-4: Migration 7 upgrades v6 DB with working FTS index."""
    db_path = tmp_path / "v6.db"
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
            'active', NULL, NULL, NULL, '2026-01-01T00:00:00Z',
            '2026-01-01T00:00:00Z', NULL
        );
    """)
    conn.execute(
        "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
        "status, metadata_text) VALUES(1, 'V6 Test Entity', 'test-v6', "
        "'feature', 'active', '')"
    )
    conn.commit()
    conn.close()
    # Open with EntityDB — triggers migration 7
    # Ensure import sqlite3 is at top of test_search.py (add if missing)
    db = EntityDB(str(db_path))
    assert db.get_schema_version() == 7
    # Pre-existing entity is searchable
    results = db.search_entities("V6")
    assert len(results) == 1
    assert results[0]["entity_id"] == "test-v6"
    # Rebuild succeeds
    db._conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
    # Integrity check passes
    db._conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('integrity-check')")
```

**Done-when:** Test passes: `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_search.py::test_migration_7_upgrades_v6_database -v`

### Task 4.3: Add merge_entities FTS searchability test
**File:** `scripts/test_migrate_db.py`
**Plan Step:** 8
**Depends on:** 2.1, 3.2

Add to class `TestMergeEntities` (near line 545 in `test_migrate_db.py`):
```python
def test_merge_entities_fts_searchable(self, tmp_path):
    """AC-5: Imported entities appear in search results after merge."""
    src_path = str(tmp_path / "src.db")
    dst_path = str(tmp_path / "dst.db")
    create_entity_db(src_path, entities=[{
        "type_id": "feature:import-test",
        "entity_type": "feature",
        "entity_id": "import-test",
        "name": "TestImport",
        "status": "active",
    }])
    create_entity_db(dst_path, entities=[])
    merge_entities(src_path, dst_path)
    dst = sqlite3.connect(dst_path)
    dst.row_factory = sqlite3.Row
    results = dst.execute(
        "SELECT e.* FROM entities_fts "
        "JOIN entities e ON entities_fts.rowid = e.rowid "
        "WHERE entities_fts MATCH 'TestImport'",
    ).fetchall()
    dst.close()
    assert len(results) == 1
    assert results[0]["entity_id"] == "import-test"
```

**Done-when:** Test passes: `python3 -m pytest scripts/test_migrate_db.py -k test_merge_entities_fts_searchable -v`

## Phase E: Verification

### Task 5.1: Run full entity registry test suite
**Command:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v`
**Plan Step:** 9
**Depends on:** 1.1, 1.2, 1.3, 2.1, 2.2, 4.1, 4.2

**Done-when:** All 710+ tests pass. Zero failures.

### Task 5.2: Run full migration test suite
**Command:** `python3 -m pytest scripts/test_migrate_db.py -v`
**Plan Step:** 9
**Depends on:** 2.1, 2.2, 3.1, 3.2, 4.3

**Done-when:** All 128+ tests pass. Zero failures.

### Task 5.3: Run bash migration tests
**Command:** `bash scripts/test_migrate_bash.sh`
**Plan Step:** 9
**Depends on:** 2.3

**Done-when:** All bash tests pass. Exit code 0.
