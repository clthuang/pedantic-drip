# Plan: Full-Text Entity Search MCP Tool

## Implementation Order

The implementation follows a bottom-up, test-first approach: schema layer → database layer → MCP tool layer. Each phase builds on the previous one.

```
Phase 1: Foundation (flatten_metadata + migration)
  ├── 1.1 flatten_metadata helper + tests
  └── 1.2 Migration 4 (_create_fts_index) + tests
        ↓
Phase 2: FTS Sync (register + update)
  ├── 2.1 FTS sync in register_entity + tests
  └── 2.2 FTS sync in update_entity + tests
        ↓
Phase 3: Search (database method + MCP tool)
  ├── 3.1 _build_fts_query + search_entities method + tests
  └── 3.2 search_entities MCP tool + tests
        ↓
Phase 4: Final Regression
  └── 4.1 Full regression run
```

## Phase 1: Foundation

### 1.1 `flatten_metadata` Helper + Tests

**Design ref:** C1, I1
**Spec ref:** R2 (metadata_text extraction)
**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_search.py`

**Implementation:**
1. Add `flatten_metadata(metadata: dict | None) -> str` as a module-level function in `database.py`, placed before the `EntityDatabase` class definition.
2. Recursive traversal: dicts → take values, lists → take elements, scalars → `str(value)`, None → skip.
3. Return space-joined leaf values, or empty string for None/empty input.

**Tests (TDD — write first):**
- `TestFlattenMetadata::test_none` → `""`
- `TestFlattenMetadata::test_empty_dict` → `""`
- `TestFlattenMetadata::test_simple_dict` → `"State Engine"`
- `TestFlattenMetadata::test_nested_dict` → `"deep"`
- `TestFlattenMetadata::test_list_values` → `"State Engine 001"`
- `TestFlattenMetadata::test_scalar_types` → `"True 42"`
- `TestFlattenMetadata::test_none_values_skipped` → skips None leaves
- `TestFlattenMetadata::test_empty_list` → `""`

**Done when:** All `TestFlattenMetadata` tests pass. Function handles all I1 examples correctly.

### 1.2 Migration 4 (`_create_fts_index`) + Tests

**Design ref:** C2, I2
**Spec ref:** R1, R5
**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_search.py`
**Depends on:** 1.1 (uses `flatten_metadata` for backfill)

**Implementation:**
1. Add `_create_fts_index(conn)` function. Uses BEGIN IMMEDIATE / COMMIT / ROLLBACK for atomicity. The migration runner handles schema_version after the function returns (separate COMMIT). **Crash-window mitigation:** If a crash occurs between the migration's COMMIT and the runner's schema_version COMMIT, migration 4 re-runs on next startup. Step 2 below ensures re-run safety via DROP + CREATE.
2. `DROP TABLE IF EXISTS entities_fts` then `CREATE VIRTUAL TABLE entities_fts ...` (no `IF NOT EXISTS`). This guarantees a clean slate on re-run — avoids FTS5 external content table DML restrictions where plain `DELETE FROM` may not reliably clear an external content FTS table. The DROP+CREATE is also the FTS5 availability check — wrap the CREATE in try/except, check for "no such module: fts5" in OperationalError message.
3. Backfill: iterate all rows from `entities`, call `flatten_metadata` on each row's metadata, insert into `entities_fts`. Clean slate from step 2 guarantees no duplicates on re-run.
4. Add to `MIGRATIONS` dict: `4: _create_fts_index`.
5. **Immediately update** all 5 `test_database.py` schema version assertions to keep existing tests green (found via `grep -n 'schema_version.*"3"' test_database.py`):
   - Line 322 — `TestMigration2` (old schema migration path): assert `'4'`
   - Line 536 — `TestMetadata::test_schema_version_is_3`: assert `'4'`
   - Line 2302 — `TestMigrationIdempotency` (close/reopen persistence): assert `'4'`
   - Line 2500 — `TestMigration3::test_schema_version_is_3`: assert `'4'`
   - Line 2688 — `TestMigration3::test_fresh_db_has_all_migrations`: assert `'4'`

**Tests (TDD — write first):**
- `TestMigration4::test_fts_table_exists` — verify `entities_fts` in `sqlite_master` after migration (AC-1)
- `TestMigration4::test_backfill_populates_index` — insert entities before migration, verify searchable after (AC-3)
- `TestMigration4::test_schema_version_is_4` — verify schema_version = '4' (AC-19)
- `TestMigration4::test_null_metadata_backfill` — entity with NULL metadata → empty string in FTS (AC-18)
- `TestMigration4::test_idempotent_create` — DROP+CREATE guarantees clean slate on re-run; migration runner skips when schema_version >= 4 (AC-16). **Spec deviation note:** AC-16 says "CREATE VIRTUAL TABLE IF NOT EXISTS for additional safety" but plan uses DROP+CREATE instead because IF NOT EXISTS leaves stale FTS data on crash re-run. The spec's intent (idempotent migration) is preserved via DROP+CREATE + migration runner skip.
- `TestMigration4::test_preserves_existing_data` — existing entities table data unchanged (AC-17)

**Known limitation:** The FTS5 `rebuild` command cannot be used with this schema because `metadata_text` is a computed column not present in the `entities` table. Recovery from FTS index drift requires re-running the backfill logic (e.g., via a helper function that calls `_create_fts_index`).

**Done when:** All `TestMigration4` tests pass. FTS table exists with backfilled data. All 545+ existing tests pass (schema version assertions updated).

## Phase 2: FTS Sync

### 2.1 FTS Sync in `register_entity`

**Design ref:** C3, I3
**Spec ref:** R2 (INSERT sync)
**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_search.py`
**Depends on:** 1.2 (FTS table must exist)

**Implementation:**
1. In `register_entity`, change `self._conn.execute(...)` (line 456) to `cursor = self._conn.execute(...)` to capture the cursor return value.
2. Check `cursor.rowcount == 1` — only sync if row was actually inserted. (Python sqlite3 sets rowcount=1 for inserted rows, rowcount=0 for INSERT OR IGNORE that skips a duplicate.)
3. If inserted: SELECT rowid, call `flatten_metadata`, INSERT into `entities_fts`.
4. Move `self._conn.commit()` (currently line 466) to after FTS write. The existing SELECT uuid at line 467 reads from the same connection and sees uncommitted data, so it works before or after commit. Final sequence: INSERT OR IGNORE → rowcount check → FTS sync → commit → SELECT uuid → return.

**Tests (TDD — write first):**
- `TestFTSSync::test_register_makes_searchable` — register entity, verify FTS SELECT returns it (AC-4)
- `TestFTSSync::test_duplicate_register_no_fts_corruption` — INSERT OR IGNORE skip doesn't double-insert FTS
- `TestFTSSync::test_register_with_metadata` — metadata content appears in FTS index
- `TestFTSSync::test_insert_or_ignore_rowcount_zero_on_skip` — verify cursor.rowcount == 0 for duplicate INSERT OR IGNORE

**Done when:** All `TestFTSSync` register tests pass. New entities are immediately searchable.

### 2.2 FTS Sync in `update_entity`

**Design ref:** C4, I4
**Spec ref:** R2 (UPDATE sync)
**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_search.py`
**Depends on:** 2.1 (register sync provides initial FTS rows to update against)

**Implementation:**
1. Before the existing UPDATE, SELECT old values (rowid, name, entity_id, entity_type, status, metadata). Compute `old_metadata_text` via `flatten_metadata`.
2. Execute the existing UPDATE logic (unchanged).
3. After UPDATE, SELECT the row again to get the **actual new values** from the database. This avoids duplicating the metadata merge logic (None/keep, `{}`/clear, dict/merge) in Python — the database is the single source of truth for new values. Compute `new_metadata_text` via `flatten_metadata(json.loads(new_row["metadata"]) if new_row["metadata"] else None)` — `json.loads` is needed because the metadata column stores JSON text, but `flatten_metadata` expects `dict | None`.
4. Issue FTS delete with old values, then FTS insert with new values from step 3.
5. Move `self._conn.commit()` to after FTS writes.
6. Add maintenance comment near FTS sync block: `# FTS sync reads post-UPDATE values from DB. If new FTS-indexed fields are added, update both the old-value SELECT and the FTS insert columns.`

**Tests (TDD — write first):**
- `TestFTSSync::test_update_name_reflected` — update name, search by new name finds it, old name doesn't (AC-5)
- `TestFTSSync::test_update_status_reflected` — update status, search by new status finds it
- `TestFTSSync::test_update_metadata_reflected` — update metadata, search by new metadata content finds it
- `TestFTSSync::test_update_non_fts_field` — update `artifact_path` only, entity still searchable (unconditional sync correctness)

**Done when:** All `TestFTSSync` update tests pass. Updated entities reflect changes in search.

## Phase 3: Search

### 3.1 `search_entities` Database Method + Tests

**Design ref:** C5, I5
**Spec ref:** R3
**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_search.py`
**Depends on:** 2.1 (needs FTS-synced entities to search). Does NOT depend on 2.2 — all test fixtures use `register_entity` for data setup (not `update_entity`), ensuring Phase 3.1 can be tested independently of update sync.

**Implementation:**
1. Add `_build_fts_query(self, query: str) -> str | None` private method per I5 pseudocode, with one plan-level addition not in I5: after tokenizing on whitespace, filter out FTS5 keyword operators (`OR`, `AND`, `NOT`, `NEAR` — case-sensitive uppercase only, so normal lowercase usage is preserved). **Rationale:** I5 sanitizes character-level operators (`*"()+^:-`) but FTS5 also treats uppercase `OR`, `AND`, `NOT`, `NEAR` as syntax. Without filtering these, a user query like `"NOT working"` would produce an FTS5 syntax error. This is a gap in the design pseudocode discovered during planning.
2. Add `search_entities(self, query, entity_type, limit)` method per I5.
3. FTS availability guard: check `entities_fts` in `sqlite_master`, raise `ValueError("fts_not_available: ...")`.
4. Limit clamping: `limit = max(1, min(limit, 100))`.
5. JOIN query: `entities_fts JOIN entities e ON entities_fts.rowid = e.rowid`.
6. Catch `sqlite3.OperationalError` on MATCH, raise `ValueError("invalid_search_query: ...")`.

**Tests (TDD — write first):**
- `TestSearchEntities::test_prefix_match` — "recon" finds "Reconciliation MCP Tool" (AC-7)
- `TestSearchEntities::test_type_filter` — entity_type filter excludes non-matching types (AC-8)
- `TestSearchEntities::test_relevance_ordering` — results ordered by rank (AC-9)
- `TestSearchEntities::test_empty_query` — returns empty list (AC-10)
- `TestSearchEntities::test_limit_caps_results` — limit=2 returns max 2 (AC-11)
- `TestSearchEntities::test_limit_clamped_to_100` — limit=200 treated as 100 (AC-11)
- `TestSearchEntities::test_exact_phrase` — `'"state engine"'` matches phrase
- `TestSearchEntities::test_multi_token_and` — "state engine" matches both tokens
- `TestSearchEntities::test_fts_not_available` — raises ValueError on missing table
- `TestSearchSanitization::test_operators_stripped` — "state(engine" doesn't raise (AC-21)
- `TestSearchSanitization::test_all_operators_stripped` — query of only operators returns empty
- `TestSearchSanitization::test_whitespace_only` — returns empty list
- `TestSearchSanitization::test_keyword_operators_stripped` — "NOT working" becomes "working*", "state OR engine" becomes "state* engine*"

**Done when:** All `TestSearchEntities` and `TestSearchSanitization` tests pass.

### 3.2 `search_entities` MCP Tool + Tests

**Design ref:** C6, I6
**Spec ref:** R4
**File:** `plugins/iflow/mcp/entity_server.py`
**Test file:** `plugins/iflow/mcp/test_search_mcp.py` (**Created** — new Python pytest file). Note: `test_entity_server.py` already exists at `hooks/lib/entity_registry/test_entity_server.py` (tests MCP handler dual-identity messages) and `mcp/test_entity_server.sh` (bash bootstrap test). Using `test_search_mcp.py` avoids naming confusion across directories.
**Depends on:** 3.1 (calls database method)

**Implementation:**
1. Add `search_entities` async function in `entity_server.py` per I6.
2. Follow existing tool pattern: check `_db is None`, call DB method, format results.
3. Catch `ValueError` from DB method, return formatted error string.
4. Output format: numbered list with `type_id — "name" (status)`.

**Tests (TDD — write first):**
- `TestSearchMCPTool::test_tool_registered` — search_entities callable (AC-12)
- `TestSearchMCPTool::test_formatted_output` — returns human-readable numbered list (AC-13)
- `TestSearchMCPTool::test_no_results` — returns "No entities found" message (AC-14)
- `TestSearchMCPTool::test_error_handling` — invalid query returns error string, not exception (AC-15)
- `TestSearchMCPTool::test_db_not_initialized` — returns error when _db is None

**Done when:** All `TestSearchMCPTool` tests pass. MCP tool returns formatted results.

## Phase 4: Final Regression

### 4.1 Full Regression Run

**Spec ref:** AC-20
**Depends on:** All previous phases

**Implementation:**
1. Run full existing test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
2. Verify 545+ existing tests pass (AC-20). Schema version assertions were already updated in Phase 1.2.
3. Run new search test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_search.py -v`
4. Run MCP tool tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_search_mcp.py -v`

**Done when:** All existing and new tests pass. Zero test failures.

## Dependency Graph

```
1.1 (flatten_metadata)
 └──→ 1.2 (migration 4 + schema version assertion updates)
       └──→ 2.1 (register sync)
             ├──→ 2.2 (update sync)
             └──→ 3.1 (search method)
                   └──→ 3.2 (MCP tool)
4.1 (full regression) ← runs after all phases
```

**Parallelism:** Steps within the same phase are sequential due to dependencies. Schema version assertions are updated in Phase 1.2 to keep tests green at every phase boundary.

## Files Changed Summary

| File | Action | Phase |
|------|--------|-------|
| `plugins/iflow/hooks/lib/entity_registry/database.py` | Modified | 1.1, 1.2, 2.1, 2.2, 3.1 |
| `plugins/iflow/hooks/lib/entity_registry/test_search.py` | **Created** | 1.1, 1.2, 2.1, 2.2, 3.1 |
| `plugins/iflow/hooks/lib/entity_registry/test_database.py` | Modified | 1.2 |
| `plugins/iflow/mcp/entity_server.py` | Modified | 3.2 |
| `plugins/iflow/mcp/test_search_mcp.py` | **Created** | 3.2 |

## AC Coverage Matrix

| AC | Phase | Test |
|----|-------|------|
| AC-1 | 1.2 | TestMigration4::test_fts_table_exists |
| AC-2 | 3.1 | TestSearchEntities::test_prefix_match (exercises MATCH on all fields) |
| AC-3 | 1.2 | TestMigration4::test_backfill_populates_index |
| AC-4 | 2.1 | TestFTSSync::test_register_makes_searchable |
| AC-5 | 2.2 | TestFTSSync::test_update_name_reflected |
| AC-6 | — | Future scope (no delete_entity method) |
| AC-7 | 3.1 | TestSearchEntities::test_prefix_match |
| AC-8 | 3.1 | TestSearchEntities::test_type_filter |
| AC-9 | 3.1 | TestSearchEntities::test_relevance_ordering |
| AC-10 | 3.1 | TestSearchEntities::test_empty_query |
| AC-11 | 3.1 | TestSearchEntities::test_limit_caps_results, test_limit_clamped_to_100 |
| AC-12 | 3.2 | TestSearchMCPTool::test_tool_registered |
| AC-13 | 3.2 | TestSearchMCPTool::test_formatted_output |
| AC-14 | 3.2 | TestSearchMCPTool::test_no_results |
| AC-15 | 3.2 | TestSearchMCPTool::test_error_handling |
| AC-16 | 1.2 | TestMigration4::test_idempotent_create |
| AC-17 | 1.2 | TestMigration4::test_preserves_existing_data |
| AC-18 | 1.2 | TestMigration4::test_null_metadata_backfill |
| AC-19 | 1.2 | TestMigration4::test_schema_version_is_4 + test_database.py assertion updates |
| AC-20 | 4.1 | Full regression run |
| AC-21 | 3.1 | TestSearchSanitization::test_operators_stripped |
