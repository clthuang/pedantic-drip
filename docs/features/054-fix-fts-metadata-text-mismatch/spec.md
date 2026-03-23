# Spec: Fix FTS5 entities_fts metadata_text Column Mismatch

## Problem Statement

The `entities_fts` FTS5 virtual table is defined with `content='entities'` (external content mode) and includes a column named `metadata_text`. The `entities` table has a column named `metadata` — not `metadata_text`. This mismatch causes `rebuild`, `integrity-check`, and direct FTS `SELECT` operations to fail with `no such column: T.metadata_text`.

**RCA report:** `docs/rca/20260323-fts-metadata-text-mismatch.md`

### Root Causes (from RCA)

1. Feature 012 deliberately used `metadata_text` as a computed FTS column while declaring `content='entities'`, documenting rebuild as a known limitation but never fixing it.
2. `scripts/migrate_db.py:347` calls FTS rebuild after merge, silently catching the failure — imported entities are not indexed.
3. Test helpers in `scripts/test_migrate_db.py` and `scripts/test_migrate_bash.sh` use a divergent FTS schema (without `metadata_text`), masking the production bug.

## Requirements

### FR-1: Remove external content mode from entities_fts

Remove `content='entities', content_rowid='rowid'` from the FTS5 CREATE statement, making `entities_fts` a standalone (contentless or content-bearing) FTS table. This enables `rebuild` to work without requiring column name alignment with the `entities` table.

**Rationale:** The `content=` directive provides no functional benefit — all production code paths already use manual DML (INSERT/DELETE) to sync FTS rows. Removing it eliminates the column name constraint while preserving `metadata_text` as a computed column with flattened text for better search quality.

**Affected locations:**
- `database.py:369-371` (`_create_fts_index`, migration 4)
- `database.py:728-730` (`_expand_entity_type_check`, migration 6)

### FR-2: Add a new database migration to fix existing databases

Create migration 7 (or the next available migration number) that:
1. Drops the existing `entities_fts` table
2. Recreates it without `content='entities', content_rowid='rowid'`
3. Backfills all existing entities using `flatten_metadata()` for the `metadata_text` column

This must follow the existing migration pattern in `database.py` (version check, `_metadata` table update).

### FR-3: Fix migrate_db.py merge_entities FTS rebuild

Replace the silent `try/except pass` FTS rebuild in `scripts/migrate_db.py:344-350` with a proper backfill that:
1. Iterates over all entities in the destination DB
2. Inserts each into `entities_fts` using `flatten_metadata()` for `metadata_text`
3. Logs a warning if individual inserts fail rather than silently swallowing errors

### FR-4: Align test helper FTS schemas with production

Update the test helper `create_entity_db` in `scripts/test_migrate_db.py` and the bash test helper in `scripts/test_migrate_bash.sh` to use the same FTS schema as production code (including `metadata_text`, without `content='entities'`).

### FR-5: Add rebuild verification test

Add a test that creates a production-schema database, populates entities, runs FTS `rebuild`, and verifies it succeeds. This prevents future regressions where the FTS schema diverges from what `rebuild` expects.

## Non-Requirements (Out of Scope)

- **NR-1:** Changing the `entities` table schema (no column additions/renames).
- **NR-2:** Changing the `search_entities()` query pattern (JOIN-based queries are correct).
- **NR-3:** Changing the `flatten_metadata()` function behavior.
- **NR-4:** Adding `metadata_text` as a generated column on `entities` table.
- **NR-5:** Migrating to contentless-delete FTS5 mode.

## Acceptance Criteria

### AC-1: FTS rebuild succeeds on production schema
```
INSERT INTO entities_fts(entities_fts) VALUES('rebuild')
```
executes without error on a database created or migrated by the updated code.

### AC-2: FTS integrity-check passes
```
INSERT INTO entities_fts(entities_fts) VALUES('integrity-check')
```
returns no errors on a database with entities.

### AC-3: Existing search_entities() behavior unchanged
`search_entities("query")` returns matching entities with rank ordering, identical to current behavior. Existing entity registry tests pass without modification (beyond test helper schema fixes).

### AC-4: Migration 7 upgrades existing databases
A database at schema version 6 is upgraded to version 7 with a working FTS index after running `EntityDB()` initialization.

### AC-5: merge_entities indexes imported entities
After `merge_entities` in `migrate_db.py`, imported entities appear in `search_entities()` results.

### AC-6: Test helpers use production FTS schema
The `create_entity_db` helper in `test_migrate_db.py` and the bash helper in `test_migrate_bash.sh` create FTS tables matching the production schema (including `metadata_text`, without `content='entities'`).

### AC-7: Rebuild regression test exists
A test verifies that FTS `rebuild` succeeds on a production-schema database with populated entities.

## Dependencies

- No external dependencies. All changes are within the existing entity registry and migration tool.

## Risks

- **Risk:** Existing databases with corrupt FTS indexes may have stale entries that become visible after rebuild.
  **Mitigation:** Migration 7 drops and recreates the FTS table, ensuring a clean index.

- **Risk:** Standalone FTS table increases storage (FTS stores its own copy of indexed text).
  **Mitigation:** Entity count is small (< 1000 typically). Storage overhead is negligible.
