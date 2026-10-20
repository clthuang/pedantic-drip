# Tasks: Full-Text Entity Search MCP Tool

## Phase 1: Foundation

### Task 1.1.1: Write `flatten_metadata` tests (RED)
- [ ] Create `plugins/iflow/hooks/lib/entity_registry/test_search.py`
- [ ] Write `TestFlattenMetadata` class with 8 test cases:
  - `test_none` → returns `""`
  - `test_empty_dict` → returns `""`
  - `test_simple_dict` → `{"module": "State Engine"}` returns `"State Engine"`
  - `test_nested_dict` → `{"a": {"b": "deep"}}` returns `"deep"`
  - `test_list_values` → `{"module": "State Engine", "deps": ["001"]}` returns `"State Engine 001"`
  - `test_scalar_types` → booleans/ints converted via `str()`: `"True 42"`
  - `test_none_values_skipped` → `{"a": None, "b": "val"}` returns `"val"`
  - `test_empty_list` → `{"a": []}` returns `""`
- [ ] Import `flatten_metadata` from `database` module (will fail — function doesn't exist yet)
- [ ] Run tests, verify all 8 fail with ImportError

**File:** `plugins/iflow/hooks/lib/entity_registry/test_search.py` (Created)
**Depends on:** None
**Done when:** 8 failing tests exist in `TestFlattenMetadata`

### Task 1.1.2: Implement `flatten_metadata` (GREEN)
- [ ] Add `flatten_metadata(metadata: dict | None) -> str` as module-level function in `database.py`, before `EntityDatabase` class
- [ ] Implement recursive traversal: dicts → values, lists → elements, scalars → `str(value)`, None → skip
- [ ] Return space-joined leaf values, empty string for None/empty input
- [ ] Run `TestFlattenMetadata` tests, verify all 8 pass

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py` (Modified)
**Depends on:** 1.1.1
**Done when:** All 8 `TestFlattenMetadata` tests pass

### Task 1.2.1: Write Migration 4 tests (RED)
- [ ] Add `TestMigration4` class to `test_search.py` with 7 test cases:
  - `test_fts_table_exists` — `entities_fts` in `sqlite_master` after migration (AC-1)
  - `test_backfill_populates_index` — pre-existing entities searchable after migration (AC-3)
  - `test_all_five_fields_indexed` — unique value per FTS column, MATCH verified per field (AC-2)
  - `test_schema_version_is_4` — schema_version = '4' (AC-19)
  - `test_null_metadata_backfill` — NULL metadata → empty string in FTS (AC-18)
  - `test_idempotent_create` — DROP+CREATE clean slate on re-run; migration runner skips when schema_version >= 4 (AC-16)
  - `test_preserves_existing_data` — entities table data unchanged (AC-17)
- [ ] Tests create a fresh DB, insert entities via raw SQL (pre-migration), then trigger migration
- [ ] Run tests, verify all 7 fail

**File:** `plugins/iflow/hooks/lib/entity_registry/test_search.py` (Modified)
**Depends on:** 1.1.2
**Done when:** 7 failing tests exist in `TestMigration4`

### Task 1.2.2: Implement Migration 4 (`_create_fts_index`)
- [ ] Add `_create_fts_index(conn)` function in `database.py`
- [ ] BEGIN IMMEDIATE transaction
- [ ] `DROP TABLE IF EXISTS entities_fts` for clean slate
- [ ] `CREATE VIRTUAL TABLE entities_fts USING fts5(name, entity_id, entity_type, status, metadata_text, content='entities', content_rowid='rowid')` — wrap in try/except for FTS5 availability check ("no such module: fts5")
- [ ] Backfill: iterate `entities` rows, call `flatten_metadata`, insert into `entities_fts`
- [ ] COMMIT (ROLLBACK on error)
- [ ] Add `4: _create_fts_index` to `MIGRATIONS` dict
- [ ] Run `TestMigration4` tests, verify all 7 pass

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py` (Modified)
**Depends on:** 1.2.1
**Done when:** All 7 `TestMigration4` tests pass. NOTE: `test_database.py` assertions will fail until Task 1.2.3 completes — do not run full suite regression until after 1.2.3.

### Task 1.2.3: Update schema version assertions in test_database.py
- [ ] Locate assertions with `grep -n 'schema_version.*"3"' plugins/iflow/hooks/lib/entity_registry/test_database.py` — expect 5 matches in these test classes:
  - `TestMigration2`
  - `TestMetadata::test_schema_version_is_3`
  - `TestMigrationIdempotency`
  - `TestMigration3::test_schema_version_is_3`
  - `TestMigration3::test_fresh_db_has_all_migrations`
- [ ] Update all 5 assertions from `'3'` to `'4'` using grep output line numbers (not hardcoded)
- [ ] Run full existing test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_database.py -v`
- [ ] Verify all 545+ existing tests pass

**File:** `plugins/iflow/hooks/lib/entity_registry/test_database.py` (Modified)
**Depends on:** 1.2.2
**Done when:** All existing tests pass with schema version 4

## Phase 2: FTS Sync

### Task 2.1.1: Write register_entity FTS sync tests (RED)
- [ ] Add `TestFTSSync` class to `test_search.py` with 4 register tests:
  - `test_register_makes_searchable` — register entity, FTS SELECT returns it (AC-4)
  - `test_duplicate_register_no_fts_corruption` — INSERT OR IGNORE skip doesn't double-insert FTS
  - `test_register_with_metadata` — metadata content appears in FTS index
  - `test_insert_or_ignore_rowcount_zero_on_skip` — cursor.rowcount == 0 for duplicate
- [ ] Tests use `EntityDatabase` API (not raw SQL) to register entities
- [ ] Run tests, verify all 4 fail (no FTS sync yet)

**File:** `plugins/iflow/hooks/lib/entity_registry/test_search.py` (Modified)
**Depends on:** 1.2.3
**Done when:** 4 failing tests exist in `TestFTSSync` (register)

### Task 2.1.2: Implement FTS sync in `register_entity`
- [ ] Change `self._conn.execute(...)` (line 456) to `cursor = self._conn.execute(...)` to capture cursor
- [ ] After INSERT, check `cursor.rowcount == 1` — only sync if row actually inserted
- [ ] If inserted: `SELECT rowid FROM entities WHERE uuid = :uuid`, call `flatten_metadata`, INSERT into `entities_fts`
- [ ] Move `self._conn.commit()` to after FTS write (defer commit for transactional consistency)
- [ ] Run `TestFTSSync` register tests, verify all 4 pass

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py` (Modified)
**Depends on:** 2.1.1
**Done when:** All 4 `TestFTSSync` register tests pass

### Task 2.2.1: Write update_entity FTS sync tests (RED)
- [ ] Add 4 update tests to `TestFTSSync`:
  - `test_update_name_reflected` — update name, new name searchable, old name not (AC-5)
  - `test_update_status_reflected` — update status, new status searchable
  - `test_update_metadata_reflected` — update metadata, new content searchable
  - `test_update_non_fts_field` — update `artifact_path` only, entity still searchable
- [ ] Tests use `register_entity` then `update_entity`
- [ ] Run tests, verify all 4 fail

**File:** `plugins/iflow/hooks/lib/entity_registry/test_search.py` (Modified)
**Depends on:** 2.1.2
**Done when:** 4 failing tests exist in `TestFTSSync` (update)

### Task 2.2.2: Implement FTS sync in `update_entity`
- [ ] Before existing UPDATE: SELECT old values (rowid, name, entity_id, entity_type, status, metadata), compute `old_metadata_text = flatten_metadata(json.loads(old_row["metadata"]) if old_row["metadata"] else None)`
- [ ] Execute existing UPDATE logic (unchanged)
- [ ] After UPDATE: `SELECT name, entity_id, entity_type, status, metadata FROM entities WHERE uuid = :uuid` for actual new values from DB (plan-level deviation from design I4 — reads post-UPDATE DB values instead of Python-derived values; see plan.md §2.2 for rationale), compute `new_metadata_text = flatten_metadata(json.loads(new_row["metadata"]) if new_row["metadata"] else None)`
- [ ] FTS delete with old values, FTS insert with new values
- [ ] Move `self._conn.commit()` to after FTS writes
- [ ] Add maintenance comment: `# FTS sync reads post-UPDATE values from DB. If new FTS-indexed fields are added, update both the old-value SELECT and the FTS insert columns.`
- [ ] Run `TestFTSSync` update tests, verify all 4 pass

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py` (Modified)
**Depends on:** 2.2.1
**Done when:** All 4 `TestFTSSync` update tests pass

## Phase 3: Search

### Task 3.1.1: Write `_build_fts_query` and `search_entities` tests (RED)
- [ ] Add `TestSearchEntities` class to `test_search.py` with 9 tests:
  - `test_prefix_match` — "recon" finds "Reconciliation MCP Tool" (AC-7)
  - `test_type_filter` — entity_type filter excludes non-matching types (AC-8)
  - `test_relevance_ordering` — results ordered by rank (AC-9)
  - `test_empty_query` — returns empty list (AC-10)
  - `test_limit_caps_results` — limit=2 returns max 2 (AC-11)
  - `test_limit_clamped_to_100` — limit=200 treated as 100 (AC-11)
  - `test_exact_phrase` — `'"state engine"'` matches phrase
  - `test_multi_token_and` — "state engine" matches both tokens
  - `test_fts_not_available` — raises ValueError on missing table (use raw `sqlite3` connection or pre-migration DB fixture, NOT `EntityDatabase` which auto-migrates; this test may pass at RED phase if fixture creates FTS table)
- [ ] Add `TestSearchSanitization` class with 4 tests:
  - `test_operators_stripped` — "state(engine" doesn't raise (AC-21)
  - `test_all_operators_stripped` — query of only operators returns empty
  - `test_whitespace_only` — returns empty list
  - `test_keyword_operators_stripped` — "NOT working" → "working*", "state OR engine" → "state* engine*"
- [ ] Tests use `register_entity` for fixture setup (not update_entity)
- [ ] Run tests, verify all 13 fail

**File:** `plugins/iflow/hooks/lib/entity_registry/test_search.py` (Modified)
**Depends on:** 2.1.2
**Done when:** 12-13 failing tests exist (test_fts_not_available may pass at RED since FTS table is created by migration; remaining 12 tests confirm search method not yet implemented)

### Task 3.1.2: Implement `_build_fts_query` and `search_entities`
- [ ] Add `_build_fts_query(self, query: str) -> str | None` private method:
  - Strip whitespace, return None if empty
  - Exact phrase detection: if starts/ends with `"`, extract inner, sanitize, re-wrap
  - Sanitize FTS5 character operators: strip `* " ( ) + - ^ :`
  - Tokenize on whitespace
  - Filter FTS5 keyword operators: remove `OR`, `AND`, `NOT`, `NEAR` (case-sensitive uppercase)
  - Return None if no tokens remain
  - Append `*` to each token for prefix matching, join with spaces
- [ ] Add `search_entities(self, query, entity_type=None, limit=20)` method:
  - FTS availability guard: check `entities_fts` in `sqlite_master`
  - Empty/whitespace query → return `[]`
  - Limit clamping: `max(1, min(limit, 100))`
  - Build MATCH query via `_build_fts_query`
  - JOIN: `entities_fts JOIN entities e ON entities_fts.rowid = e.rowid WHERE entities_fts MATCH :query`
  - Optional `entity_type` filter, ORDER BY `entities_fts.rank`, LIMIT
  - Catch `sqlite3.OperationalError`, raise `ValueError("invalid_search_query: ...")`
- [ ] Run all search tests, verify all 13 pass

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py` (Modified)
**Depends on:** 3.1.1
**Done when:** All 13 `TestSearchEntities` and `TestSearchSanitization` tests pass

### Task 3.2.1: Write MCP tool tests (RED)
- [ ] Create `plugins/iflow/mcp/test_search_mcp.py`
- [ ] Add `TestSearchMCPTool` class with 5 tests:
  - `test_tool_registered` — search_entities callable (AC-12)
  - `test_formatted_output` — returns human-readable numbered list (AC-13)
  - `test_no_results` — returns "No entities found" message (AC-14)
  - `test_error_handling` — invalid query returns error string, not exception (AC-15)
  - `test_db_not_initialized` — returns `"Error: database not initialized"` when `_db is None` (per design I6)
- [ ] Run tests, verify all 5 fail

**File:** `plugins/iflow/mcp/test_search_mcp.py` (Created)
**Depends on:** 3.1.2
**Done when:** 5 failing tests exist in `TestSearchMCPTool`

### Task 3.2.2: Implement `search_entities` MCP tool
- [ ] Add `search_entities` async function in `entity_server.py` following existing tool pattern
- [ ] Check `_db is None` → return `"Error: database not initialized"`
- [ ] Call `db.search_entities(query, entity_type, limit)`
- [ ] Format results using `"\n".join(lines)` pattern per design I6: header line `f'Found {n} entities matching "{query}":\n'`, numbered entries `f'{i}. {type_id} — "{name}" ({status})'`, footer `f'\n{n} results shown (limit: {limit}).'` — footer string includes leading `\n` to produce blank separator line when joined
- [ ] No results: `"No entities found matching \"{query}\"."`
- [ ] Catch `ValueError` → return `"Search error: {message}"`
- [ ] Run `TestSearchMCPTool` tests, verify all 5 pass

**File:** `plugins/iflow/mcp/entity_server.py` (Modified)
**Depends on:** 3.2.1
**Done when:** All 5 `TestSearchMCPTool` tests pass

## Phase 4: Final Regression

### Task 4.1.1: Run full regression suite
- [ ] Run existing entity registry tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- [ ] Verify 545+ existing tests pass (AC-20)
- [ ] Run new search tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_search.py -v`
- [ ] Run MCP tool tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_search_mcp.py -v`
- [ ] Verify zero test failures across all suites

**Depends on:** All previous tasks
**Done when:** All existing and new tests pass with zero failures
