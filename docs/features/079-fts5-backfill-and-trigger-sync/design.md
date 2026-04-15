---
last-updated: 2026-04-15
feature: 079-fts5-backfill-and-trigger-sync
---
# Design: FTS5 Backfill and Trigger Sync

## Approach

Add **migration 5** to `plugins/pd/hooks/lib/semantic_memory/database.py` — a lightweight, idempotent rebuild that re-issues the FTS5 `rebuild` command on any DB that reached v4 with an empty `entries_fts`. This is the cleanest fix because:

- **Triggers already exist** (`entries_ai`, `entries_au`, `entries_ad` created in `_create_fts5_objects`). Ongoing sync is not the gap.
- **External-content mode** (`content='entries'`) means `INSERT INTO entries_fts(entries_fts) VALUES('rebuild')` is a single-statement, transactional, idempotent repopulate.
- **No schema changes** — additive migration only, no new columns or tables. NFR-2 satisfied.

## Architecture

```
MIGRATIONS dict
├── 1 _create_initial_schema (existing)
├── 2 _add_source_hash_and_created_timestamp (existing)
├── 3 _enforce_not_null_columns (existing, rebuilds fts5 too)
├── 4 _add_influence_tracking (existing)
└── 5 _rebuild_fts5_index (new) ← THIS FEATURE
```

Migration 5 calls `_create_fts5_objects(conn)` (idempotent — uses `CREATE VIRTUAL TABLE IF NOT EXISTS` and `CREATE TRIGGER IF NOT EXISTS`) then issues the `rebuild` command. On DBs where fts5 is already populated, rebuild rewrites the same rows — no harm, cheap.

Gated by `fts5_available` kwarg: no-op on SQLite builds without FTS5.

## Technical Decisions

**TD-1 (rebuild over per-row backfill):** The FTS5 `rebuild` command repopulates in native SQLite code; a Python-side loop would be 2–3 orders of magnitude slower and would need manual `REPLACE`/JSON-strip to match trigger semantics. Using `rebuild` guarantees parity with trigger behavior.

**TD-2 (run at migration time, not SessionStart):** The migration bumps `schema_version` from 4→5, so subsequent SessionStart runs detect v5 and skip. One-time cost per DB, no ongoing overhead.

**TD-3 (in-session test suite update):** The existing test assertions `assert db.get_schema_version() == 4` are updated to `5` in the same change. No backwards-compat shim — per CLAUDE.md "No backward compatibility" principle.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Migration called on a DB where fts5 is unavailable | `fts5_available=False` early return; no crash |
| Previous fts5 table corrupted / half-populated | `rebuild` clears and repopulates from source-of-truth `entries` |
| Migration runs on empty DB (no entries) | rebuild yields empty fts5, count equality holds trivially |
