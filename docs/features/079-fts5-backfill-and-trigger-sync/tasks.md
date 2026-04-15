# Tasks: FTS5 Backfill and Trigger Sync

## Stage 1: Migration + Tests

### Task 1.1: Add _rebuild_fts5_index migration
**File:** `plugins/pd/hooks/lib/semantic_memory/database.py`
**Change:** Add function after `_add_influence_tracking`; register as migration 5 in `MIGRATIONS` dict.
**Done:** `MIGRATIONS[5]` resolves to the new function; `fts5_available=False` kwarg returns early.
**Depends on:** none

### Task 1.2: Update schema_version assertions
**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
**Change:** Replace `get_schema_version() == 4` → `== 5` (6 sites).
**Done:** All 149 existing tests pass at schema version 5.
**Depends on:** Task 1.1

### Task 1.3: Add migration-5 tests
**File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
**Change:** Append `TestMigration5FTS5Rebuild` (3 tests) + `TestFTS5TriggerSync` (3 tests).
**Done:** 6 new tests pass. Full suite 411/411.
**Depends on:** Task 1.2

### Task 1.4: Run migration on live DB
**File:** (no new file)
**Change:** Open `~/.claude/pd/memory/memory.db` via `MemoryDatabase(...)` to trigger migration.
**Done:** `sqlite3 memory.db "SELECT COUNT(*) FROM entries, entries_fts"` shows equal counts; `schema_version == 5`.
**Depends on:** Task 1.3
