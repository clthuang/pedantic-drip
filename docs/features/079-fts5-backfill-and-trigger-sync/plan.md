---
last-updated: 2026-04-15
feature: 079-fts5-backfill-and-trigger-sync
---
# Plan: FTS5 Backfill and Trigger Sync

Single-phase implementation. No cross-file coordination.

## Phase 1: Migration + Tests

1. Add `_rebuild_fts5_index` function to `database.py`.
2. Register as migration 5 in `MIGRATIONS` dict.
3. Bump test assertions `get_schema_version() == 4` → `== 5` (6 test sites).
4. Add `TestMigration5FTS5Rebuild` class (3 tests: repopulate after drop, idempotent re-run, fts5_unavailable no-op).
5. Add `TestFTS5TriggerSync` class (3 tests: insert trigger populates, update trigger reindexes, delete trigger removes).
6. Run full `semantic_memory/` test suite — confirm 411/411 pass.
7. Apply migration to live `~/.claude/pd/memory/memory.db` — verify `entries_fts` row count equals `entries` row count.

**Done when:** Full suite green; live DB fts5 count equals entries count; schema_version == 5.
