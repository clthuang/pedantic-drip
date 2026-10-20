---
last-updated: 2026-04-15
feature: 079-fts5-backfill-and-trigger-sync
project: P002-memory-flywheel
---

# Spec: FTS5 Backfill and Trigger Sync

## Problem

The `entries_fts` FTS5 virtual table in `~/.claude/pd/memory/memory.db` exists but contains 0 rows while `entries` has 964 rows (verified: SessionStart hook output 2026-04-15 shows `vector=964, fts5=0`). As a result, the hybrid retrieval pipeline in `plugins/pd/hooks/lib/semantic_memory/retrieval.py` runs vector-only — the keyword/BM25 leg returns empty and its weight (0.2 per `memory_keyword_weight` config) collapses unused into the vector weight.

Queries for rare technical terms (file names like `session-start.sh`, error codes, MCP tool names like `record_influence_by_content`) that vector search misses cannot be recovered by keyword search.

## Success Criteria

- [ ] `sqlite3 ~/.claude/pd/memory/memory.db "SELECT COUNT(*) FROM entries_fts"` returns within 1 of `SELECT COUNT(*) FROM entries` (within tolerance for any edge-case entries lacking indexable fields).
- [ ] Insert/update triggers on `entries` keep `entries_fts` in sync for all future writes (verified via a test that inserts a new entry and confirms it appears in an FTS5 MATCH query without a manual backfill).
- [ ] SessionStart hook memory injection diagnostic reports `vector=N, fts5=N` where both values equal the `entries` row count (within tolerance).
- [ ] `plugins/pd/hooks/lib/semantic_memory/retrieval.py` hybrid search returns non-empty FTS5 results for a test query that keyword-matches an indexed entry (e.g., query `"record_influence_by_content"` returns at least one entry).
- [ ] BM25 score component is visible in `rank()` weighted output in unit tests.

## Functional Requirements

### FR-1: Backfill migration
Implement a one-time backfill that populates `entries_fts` from the current `entries` table. Must be:
- **Idempotent:** safe to re-run; re-running when fts5 is already populated is a no-op (or warns and exits without corrupting data).
- **Resumable:** crash mid-flight leaves partial state that the next run completes correctly (per-row inserts are acceptable).
- **Measured:** reports row-count before/after and wall-clock duration.
- **Invoked once** during migration, not on every SessionStart. The migration is bookkept in `entries` DB's schema_version or a `_migrations` table so re-runs of SessionStart don't re-trigger it.

### FR-2: Insert/update triggers for ongoing sync
Add or verify SQL triggers on `entries`:
- `AFTER INSERT ON entries` → inserts corresponding row into `entries_fts`.
- `AFTER UPDATE ON entries` → updates corresponding row in `entries_fts` when any indexed field changes.
- `AFTER DELETE ON entries` → removes corresponding row from `entries_fts`.

Indexed fields (must match the FTS5 table's virtual columns): at minimum `description`, `name`, `reasoning`. Use the existing schema as source of truth — do not redefine which fields are indexed in this feature.

### FR-3: Retrieval integration
Existing `retrieval.py` `hybrid_search()` already issues an FTS5 MATCH query alongside vector search. No code changes expected there — the function gracefully handles empty FTS5 results today, so once FTS5 is populated it naturally begins contributing BM25 scores. Verify no retrieval changes are needed by running the existing unit tests unchanged.

## Happy Paths

### HP-1: First-time backfill on a 964-entry DB
**Given** `entries_fts` is empty and `entries` has 964 rows
**When** the backfill migration runs
**Then** `entries_fts` has 964 rows and the migration is marked complete in `_migrations` (or schema_version bumped)
**And** total wall-clock time is < 30 seconds

### HP-2: Re-run is a no-op
**Given** backfill has already run and `entries_fts` is populated
**When** the migration re-runs (e.g., due to environment recreation)
**Then** it detects the completion marker, reports "already backfilled", exits with status 0, does not rewrite `entries_fts`

### HP-3: New entry via `store_memory` syncs automatically
**Given** backfill is complete
**When** a new entry is inserted via `semantic_memory.writer.store_entry()` (the production path)
**Then** the `entries_fts` table automatically contains a matching row (trigger fires)
**And** an FTS5 MATCH query against the new entry's keywords returns it

## Error & Boundary Cases

| Scenario | Expected Behavior | Rationale |
|---|---|---|
| `entries_fts` virtual table missing | Backfill errors out with a clear message citing the schema file; does not silently create a wrong schema | Schema is authoritative; feature does not own creation |
| Partial previous backfill (some rows in fts5, some missing) | Backfill detects mismatch count, backfills only missing rows based on `entries.id NOT IN fts5.rowid` | Resumability |
| Entry has NULL in an indexed field | Insert row with empty string for that field; FTS5 accepts | Avoid index holes |
| DB is write-locked during backfill | Use WAL busy_timeout already configured (15s); retry on BUSY; do not hold write lock across many rows | Coexist with concurrent session-start readers |
| `entries_fts` build lacks FTS5 extension | Skip backfill with warning; log `FTS5 unavailable — feature disabled`; do not crash migration chain | Graceful degradation (NFR3) |
| Trigger creation fails (e.g., already exists) | Use `CREATE TRIGGER IF NOT EXISTS`; verify existence after creation | Idempotent |

## Non-Functional Requirements

### NFR-1: Performance
Backfill must complete in < 30 seconds for 964 entries on a developer-class laptop (Apple Silicon or equivalent). Measured via wall-clock timing in migration logs.

### NFR-2: Additive-only
No breaking changes to `semantic_memory` module signatures. Existing `search_memory` call sites, `store_memory` MCP tool, and `retrieval.hybrid_search()` continue to work without caller changes. Only new migration code + triggers are added.

### NFR-3: No disruption to existing sessions
SessionStart continues to function identically before, during, and after migration. Backfill runs synchronously (not in a background thread) to avoid coordination complexity — a 30-second one-time cost is acceptable vs. concurrency risks.

## Out of Scope

- Re-ranking algorithm changes (covered by feature 080 influence wiring and 082 recall tracking).
- Embedding regeneration (separate concern).
- Cross-project FTS5 scoping (follow-up item in backlog).
- Adding new searchable fields to the FTS5 table (schema evolution, separate feature).

## Acceptance Evidence

Before marking the feature complete:
1. Run the migration manually against a clean copy of `memory.db`; confirm row-count equality.
2. Run the existing semantic_memory test suite (`plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/semantic_memory/`) — all existing tests pass unchanged.
3. Run new tests verifying trigger sync on insert/update/delete.
4. Run a live hybrid search against a fresh session (`SessionStart` emits `vector=N, fts5=N` with both non-zero) and confirm a keyword-heavy query returns non-empty results.
