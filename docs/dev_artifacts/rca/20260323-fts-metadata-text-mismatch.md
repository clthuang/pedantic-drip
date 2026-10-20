# RCA: FTS5 entities_fts metadata_text Column Mismatch

**Date:** 2026-03-23
**Severity:** Medium (search works, rebuild/integrity broken)
**Status:** Root causes identified, fix not yet applied

---

## Problem Statement

The `entities_fts` FTS5 virtual table is defined with `content='entities', content_rowid='rowid'` and includes a column named `metadata_text`. However, the `entities` table has a column named `metadata` (not `metadata_text`). This mismatch causes any operation that reads from the content table to fail with `Runtime error: no such column: T.metadata_text`.

## Root Causes

### Cause 1: Intentional Design Choice Became a Latent Defect

The `metadata_text` column was a deliberate design decision from Feature 012 (Full-Text Entity Search). The column holds flattened text extracted from the JSON `metadata` column via `flatten_metadata()`. The Feature 012 plan (line 79) explicitly documented this as a **known limitation**:

> "The FTS5 `rebuild` command cannot be used with this schema because `metadata_text` is a computed column not present in the `entities` table."

The FTS table was always created with `content='entities'` (external content mode), which tells SQLite to read column values from the `entities` table by name during `rebuild` and `integrity-check` operations. Since `metadata_text` does not exist in `entities`, these operations fail.

**Evidence:** Commit `92661ec` (first FTS implementation) already contains the mismatch. Every subsequent migration that recreates `entities_fts` (migrations 4 and 6) perpetuates it.

**Locations in code:**
- `database.py:369-371` (_create_fts_index, migration 4)
- `database.py:728-730` (_expand_entity_type_check, migration 6)

### Cause 2: Migration Tool Uses rebuild Despite Known Limitation

`scripts/migrate_db.py:347` calls `INSERT INTO entities_fts(entities_fts) VALUES('rebuild')` after `merge_entities`. This always fails due to Cause 1, but the error is silently caught:

```python
try:
    dst.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
except sqlite3.OperationalError:
    pass
```

This means entities imported via the migration tool are **not indexed in FTS** and will not appear in search results. The silent `except` masks the failure entirely.

**Evidence:** Reproduction script confirmed rebuild fails on both live DB and in-memory DBs.

### Cause 3: Test Helpers Use Different FTS Schema Than Production

The test helper `create_entity_db` in `scripts/test_migrate_db.py:327-329` creates FTS with:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    name, entity_type, entity_id, status, content=entities, content_rowid=rowid
);
```

This schema omits `metadata_text` entirely and uses only columns that exist in `entities`. The helper's `rebuild` call at line 373 succeeds, making `test_merge_entities_fts_rebuild` pass despite the production code being broken. The bash test helper at `test_migrate_bash.sh:878-880` has the same divergent schema.

A second test helper (used by deepened tests, line 1133) does use the production schema with `metadata_text` but avoids `rebuild` by manually inserting FTS rows.

**Evidence:** Test at line 719-739 (`test_merge_entities_fts_rebuild`) passes because it uses the corrected test schema, not the production schema.

## Impact Analysis

### What Works (No User-Visible Impact)

| Operation | Pattern | Why It Works |
|-----------|---------|-------------|
| `search_entities()` | `SELECT e.* FROM entities_fts JOIN entities e ON entities_fts.rowid = e.rowid WHERE entities_fts MATCH ?` | JOIN queries do not trigger content-table column resolution |
| `register_entity()` | Manual `INSERT INTO entities_fts(rowid, ..., metadata_text) VALUES(...)` | Manual DML does not read from content table |
| `update_entity()` | Manual delete + insert | Same as above |
| `delete_entity()` | Manual FTS delete with old values | Same as above |

### What Is Broken

| Operation | Error | Impact |
|-----------|-------|--------|
| FTS rebuild | `no such column: T.metadata_text` | Cannot reconstruct FTS index from entities table |
| Direct FTS query (`SELECT * FROM entities_fts WHERE MATCH`) | `no such column: T.metadata_text` | Cannot query FTS table directly (minor, not used by search_entities) |
| FTS integrity-check | `SQL logic error` | Cannot verify FTS index consistency |
| `merge_entities` FTS rebuild | Silently caught OperationalError | **Imported entities are not searchable** |

### Severity Assessment

**Medium.** Day-to-day entity operations (register, update, delete, search) work correctly because they use manual FTS DML and JOIN queries. The primary user-facing impact is that entities imported via the migration tool's `merge_entities` are not searchable until the database is re-migrated or the FTS index is manually rebuilt using the backfill pattern.

## Hypotheses Considered

1. **metadata was renamed from metadata_text at some point** -- REJECTED. Git history shows `entities` table always had `metadata`. The FTS column `metadata_text` was always a computed derivative.

2. **A migration changed the entities schema without updating FTS** -- REJECTED. The mismatch was present from the initial implementation. No rename occurred.

3. **FTS5 external-content tables tolerate column name mismatches for some operations** -- CONFIRMED. SQLite's FTS5 only resolves content-table columns for operations that need to read from the content table (rebuild, integrity-check, and direct SELECT from the FTS table). Manual DML and JOIN queries work regardless of column name alignment.

## Affected Files

| File | Line(s) | Issue |
|------|---------|-------|
| `plugins/pd/hooks/lib/entity_registry/database.py` | 369-371, 728-730 | FTS CREATE with mismatched `metadata_text` |
| `scripts/migrate_db.py` | 347 | Rebuild call that silently fails |
| `scripts/test_migrate_db.py` | 327-329 | Test helper uses different FTS schema, masking the bug |
| `scripts/test_migrate_bash.sh` | 878-880 | Same divergent test schema |

## Reproduction

Reproduction and verification scripts are at:
- `agent_sandbox/20260323/rca-fts-metadata-text/reproduction/reproduce_fts_mismatch.py`
- `agent_sandbox/20260323/rca-fts-metadata-text/experiments/verify_all_impacts.py`
- `agent_sandbox/20260323/rca-fts-metadata-text/experiments/test_fts_behavior.py`

## Fix Direction (Not Prescriptive)

The core tension: `metadata_text` is a computed/flattened column that adds search value (human-readable text instead of raw JSON), but FTS5 `content=` mode requires column names to match the content table. Two approaches exist:

1. **Remove `content='entities'`** -- Make the FTS table standalone (no external content). Enables rebuild via manual backfill function (already exists as `_create_fts_index`). Increases storage (FTS stores its own copy of data). Loses nothing functionally since manual DML is already the only working path.

2. **Rename FTS column to `metadata`** -- Aligns names so `rebuild` works, but `rebuild` would index raw JSON instead of flattened text, reducing search quality for metadata fields. Would require removing `flatten_metadata` from the backfill/sync paths or accepting the quality tradeoff.

Either approach requires updating: the two CREATE statements in `database.py`, the migrate tool's rebuild call, and the test helpers' FTS schemas.
