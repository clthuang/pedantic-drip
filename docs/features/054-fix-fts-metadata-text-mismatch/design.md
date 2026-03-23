# Design: Fix FTS5 entities_fts metadata_text Column Mismatch

## Prior Art Research

### Codebase Patterns
- **Migration pattern:** `MIGRATIONS` dict maps version → function. Each function uses `BEGIN IMMEDIATE` / `COMMIT` with `_metadata` table upsert for version tracking. DDL migrations use `PRAGMA foreign_keys = OFF` guard.
- **FTS backfill:** Both migration 4 and 6 use identical pattern: DROP IF EXISTS → CREATE VIRTUAL TABLE → SELECT all entities → INSERT each with `flatten_metadata()`.
- **FTS sync (DML):** `register_entity`, `update_entity`, `delete_entity` all use manual FTS INSERT/DELETE with the external-content `VALUES('delete', ...)` pattern.

### External Research (SQLite FTS5 docs)
- **`VALUES('delete', ...)` is external-content only.** It does NOT work on standalone content-bearing FTS5 tables. For standalone tables, use `DELETE FROM entities_fts WHERE rowid = ?`.
- **Standalone tables support `rebuild`.** The `INSERT INTO fts(fts) VALUES('rebuild')` command works for both standalone and external-content tables.
- **Standalone `DELETE FROM` is simpler.** Only needs rowid — no need to supply original text values, eliminating the risk of silent index corruption from mismatched delete values.
- **`integrity-check` for standalone tables** verifies internal b-tree/segment consistency.

## Architecture Overview

### Component: Migration 7 (`_fix_fts_content_mode`)

A new migration function added to the `MIGRATIONS` dict at key `7`. Follows the established pattern:

1. `BEGIN IMMEDIATE`
2. `DROP TABLE IF EXISTS entities_fts`
3. `CREATE VIRTUAL TABLE entities_fts USING fts5(name, entity_id, entity_type, status, metadata_text)` — no `content=` or `content_rowid=`
4. Backfill all entities (same pattern as migration 4/6)
5. Update `_metadata` schema_version to `7`
6. `COMMIT`

### Component: FTS DML Pattern Update

All FTS delete operations change from external-content syntax to standard SQL:

| Operation | Before (external-content) | After (standalone) |
|-----------|--------------------------|-------------------|
| Delete | `INSERT INTO entities_fts(entities_fts, rowid, ...) VALUES('delete', ?, ...)` | `DELETE FROM entities_fts WHERE rowid = ?` |
| Insert | `INSERT INTO entities_fts(rowid, ...) VALUES(?, ...)` | No change |
| Rebuild | Fails (schema mismatch) | `INSERT INTO entities_fts(entities_fts) VALUES('rebuild')` — now works |

**Affected functions:**
- `update_entity()` at database.py:1513-1519 — replace 7-column VALUES('delete',...) with `DELETE FROM entities_fts WHERE rowid = ?`
- `delete_entity()` at database.py:1574-1579 — same replacement

**Simplification benefit:** The new delete pattern no longer requires fetching old column values or calling `flatten_metadata()` on old metadata. `update_entity` still needs the old metadata for the old FTS insert pattern — but actually, only the INSERT of new values is needed after DELETE. `delete_entity` no longer needs to compute `metadata_text` before deletion.

### Component: migrate_db.py FTS Backfill

Replace the silent `try/except pass` rebuild with a proper backfill function:

```python
def _backfill_fts(conn):
    """Backfill entities_fts after merge. Imports flatten_metadata from entity_registry."""
    rows = conn.execute(
        "SELECT rowid, name, entity_id, entity_type, status, metadata FROM entities"
    ).fetchall()
    for row in rows:
        metadata_text = flatten_metadata(json.loads(row[5]) if row[5] else None)
        conn.execute(
            "INSERT OR REPLACE INTO entities_fts(rowid, name, entity_id, entity_type, "
            "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
            (row[0], row[1], row[2], row[3], row[4] or "", metadata_text),
        )
```

**Import path:** `migrate_db.py` needs `flatten_metadata`. Two options:

### TD-1: How migrate_db.py imports flatten_metadata

**Option A (chosen): Inline the function.**
Copy the ~15-line `flatten_metadata` function into `migrate_db.py`. The function is stable (unchanged since Feature 012), simple (recursive dict/list flattener), and has no dependencies beyond stdlib.

**Option B (rejected): sys.path import from entity_registry.**
Would create a cross-layer dependency between `scripts/` and `plugins/pd/hooks/lib/`. The import path is fragile — depends on relative directory structure. Not worth the coupling for a 15-line pure function.

**Rationale:** The spec suggested sys.path import, but inlining is simpler and avoids coupling. The function has zero external dependencies and is unlikely to change. If it ever does, the migration tool's copy only needs to handle the frozen schema at migration time.

### Component: Test Helper Alignment

Three test helpers need FTS schema updates:

| Helper | File:Line | Current Schema | Change |
|--------|-----------|---------------|--------|
| `create_entity_db` | test_migrate_db.py:327-329 | Missing `metadata_text`, no `content=` | Add `metadata_text` |
| Deepened helper | test_migrate_db.py:1133 | Has `metadata_text`, has `content='entities'` | Remove `content='entities', content_rowid='rowid'` |
| Bash helper | test_migrate_bash.sh:878-880 | Missing `metadata_text`, no `content=` | Add `metadata_text` |

After updating schemas, the FTS `rebuild` calls in these helpers will work correctly.

**Test assertion impact:** The `VALUES('delete', ...)` pattern is NOT used in any test helper or test assertion. Tests only use `INSERT INTO entities_fts(...)` and `INSERT INTO entities_fts(entities_fts) VALUES('rebuild')`. No test assertion changes are needed.

## Technical Decisions

### TD-2: Historical migration CREATE statements

**Decision:** Do NOT modify the FTS CREATE statements in migrations 4 and 6.

**Rationale:** These migrations run on databases at version 3→4 and 5→6 respectively. Migration 7 will drop and recreate the FTS table regardless, so the intermediate state created by migrations 4/6 is overwritten. Modifying historical migrations risks breaking upgrade paths for databases stuck at intermediate versions. The migration chain 4→5→6→7 must work — and it does, because migration 7 unconditionally drops and recreates.

### TD-3: FTS INSERT pattern in update_entity

**Decision:** Keep the delete-then-insert pattern but simplify the delete.

Before:
```python
# Fetch old values for FTS delete
old_meta_text = flatten_metadata(json.loads(old_row["metadata"]) ...)
conn.execute("INSERT INTO entities_fts(entities_fts, rowid, ...) VALUES('delete', ?, ...)",
             (old_row["rowid"], old_row["name"], ..., old_meta_text))
# Insert new values
conn.execute("INSERT INTO entities_fts(rowid, ...) VALUES(?, ...)",
             (old_row["rowid"], new_row["name"], ..., new_meta_text))
```

After:
```python
# Delete old FTS entry by rowid (no need for old column values)
conn.execute("DELETE FROM entities_fts WHERE rowid = ?", (old_row["rowid"],))
# Insert new values
conn.execute("INSERT INTO entities_fts(rowid, ...) VALUES(?, ...)",
             (old_row["rowid"], new_row["name"], ..., new_meta_text))
```

The `old_meta_text` computation in `update_entity` becomes unnecessary and can be removed.

### TD-4: Error handling in migrate_db.py backfill

**Decision:** Log per-entity warnings to stderr, do not abort the merge.

```python
import sys
for row in rows:
    try:
        # ... insert into FTS
    except sqlite3.OperationalError as exc:
        print(f"WARNING: FTS index failed for entity rowid={row[0]}: {exc}", file=sys.stderr)
```

This matches the existing error-handling posture in `migrate_db.py` (warn, don't crash).

## Interfaces

### Migration 7 Function Signature

```python
def _fix_fts_content_mode(conn: sqlite3.Connection) -> None:
    """Migration 7: Remove external-content mode from entities_fts.

    Drops and recreates entities_fts as a standalone content-bearing
    FTS5 table, then backfills from all existing entities.
    """
```

Registration: `MIGRATIONS[7] = _fix_fts_content_mode`

### Updated update_entity FTS Block

```python
# In update_entity(), replace lines 1507-1527:
new_meta_text = flatten_metadata(
    json.loads(new_row["metadata"]) if new_row["metadata"] else None
)
self._conn.execute(
    "DELETE FROM entities_fts WHERE rowid = ?",
    (old_row["rowid"],),
)
self._conn.execute(
    "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, "
    "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
    (old_row["rowid"], new_row["name"], new_row["entity_id"],
     new_row["entity_type"], new_row["status"] or "", new_meta_text),
)
```

### Updated delete_entity FTS Block

```python
# In delete_entity(), replace lines 1567-1580:
self._conn.execute(
    "DELETE FROM entities_fts WHERE rowid = ?",
    (row["rowid"],),
)
```

The `metadata_text` computation (lines 1568-1573) and the 7-column VALUES('delete',...) statement are both removed.

### migrate_db.py Backfill Function

```python
def _flatten_metadata(metadata: dict | None) -> str:
    """Flatten metadata JSON to space-separated leaf values (inlined from entity_registry)."""
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


def _backfill_entity_fts(dst: sqlite3.Connection) -> int:
    """Backfill entities_fts from all entities. Returns count of indexed entities."""
    rows = dst.execute(
        "SELECT rowid, name, entity_id, entity_type, status, metadata FROM entities"
    ).fetchall()
    indexed = 0
    for row in rows:
        try:
            meta_text = _flatten_metadata(json.loads(row[5]) if row[5] else None)
            dst.execute(
                "INSERT OR REPLACE INTO entities_fts(rowid, name, entity_id, entity_type, "
                "status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)",
                (row[0], row[1], row[2], row[3], row[4] or "", meta_text),
            )
            indexed += 1
        except (sqlite3.OperationalError, json.JSONDecodeError) as exc:
            print(f"WARNING: FTS index failed for rowid={row[0]}: {exc}", file=sys.stderr)
    return indexed
```

### Test: FTS Rebuild Regression

```python
def test_fts_rebuild_succeeds_on_production_schema(tmp_path):
    """AC-7: Verify rebuild works on production schema."""
    db_path = tmp_path / "test.db"
    db = EntityDB(str(db_path))
    db.register_entity(entity_type="feature", entity_id="test-1",
                       name="Test Feature", metadata={"key": "value"})
    # Rebuild should succeed (was broken before this fix)
    db._conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
    # Integrity check should pass
    db._conn.execute("INSERT INTO entities_fts(entities_fts) VALUES('integrity-check')")
    # Search should find the entity
    results = db.search_entities("Test")
    assert len(results) == 1
    assert results[0]["entity_id"] == "test-1"
```

## Risks

| Risk | Mitigation |
|------|-----------|
| Standalone FTS increases disk usage | Entity count < 1000; overhead ~500KB max — negligible |
| Old databases at version < 6 upgrading | Migration chain 4→5→6→7 works; migration 7 drops/recreates FTS regardless of prior state |
| `flatten_metadata` diverges between database.py and migrate_db.py | Function is 15 lines, stable since Feature 012. Comment in migrate_db.py copy notes the source |

## Test Strategy

1. **Existing entity registry tests** (710+) — must pass with only FTS CREATE schema changes in helpers
2. **Existing migration tests** (128) — must pass with updated test helper schemas
3. **New: FTS rebuild regression test** (AC-7) — verifies rebuild + integrity-check + search
4. **New: Migration 7 test** (AC-4) — creates v6 DB, runs migration, verifies FTS works
5. **New: merge_entities FTS test** (AC-5) — verifies imported entities are searchable
