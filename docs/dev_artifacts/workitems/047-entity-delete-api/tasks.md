# Tasks: Entity Delete API

## Phase 1: Database Methods (parallel)

### Task 1.1: Write EntityDatabase.delete_entity tests
- **File:** `plugins/iflow/hooks/lib/entity_registry/test_database.py`
- **Fixture:** Use existing `db` fixture from conftest.py (`EntityDatabase(":memory:")`). Register test entities with `db.register_entity()` before each delete test. For FTS verification: `db._conn.execute("SELECT * FROM entities_fts WHERE entities_fts MATCH ?", (name,))`.
- **Tests:** test_delete_entity_not_found (AC-1), test_delete_entity_success (AC-2), test_delete_entity_with_children_rejected (AC-3), test_delete_entity_fts_cleaned (AC-4), test_delete_entity_no_workflow_phases (AC-13), test_delete_entity_rollback_on_error (AC-12), test_delete_entity_corrupted_metadata_still_deletes
- **Done when:** All 7 tests exist and fail (RED phase)
- **Depends on:** nothing

### Task 1.2: Implement EntityDatabase.delete_entity
- **File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
- **Placement:** After `update_entity` (~line 950), before Search section
- **Implementation:** Follow design.md C1 pseudocode — BEGIN IMMEDIATE, validate existence (SELECT with metadata), child check via parent_uuid, FTS5 'delete' sentinel (defensive metadata parsing), DELETE workflow_phases, DELETE entity, commit/rollback
- **Done when:** All 7 tests from Task 1.1 pass (GREEN phase)
- **Depends on:** Task 1.1

### Task 1.3: Write MemoryDatabase.delete_entry tests
- **File:** `plugins/iflow/hooks/lib/semantic_memory/test_database.py`
- **Fixture:** Use existing `db` fixture (`MemoryDatabase(":memory:")`). Insert test entries with `db.upsert_entry()` before delete. For FTS verification: `db._conn.execute("SELECT * FROM entries_fts WHERE entries_fts MATCH ?", (name,))` — assert zero results after delete.
- **Tests:** test_delete_entry_not_found (AC-5), test_delete_entry_success (AC-6), test_delete_entry_fts_cleaned (AC-7)
- **Done when:** All 3 tests exist and fail (RED phase)
- **Depends on:** nothing

### Task 1.4: Implement MemoryDatabase.delete_entry
- **File:** `plugins/iflow/hooks/lib/semantic_memory/database.py`
- **Placement:** After `get_entry` (~line 343)
- **Implementation:** Follow design.md C2 pseudocode — BEGIN IMMEDIATE, validate existence, DELETE FROM entries (trigger handles FTS), commit/rollback
- **Done when:** All 3 tests from Task 1.3 pass (GREEN phase)
- **Depends on:** Task 1.3

## Phase 2: CLI Extension

### Task 2.1: Write CLI delete tests
- **File:** `plugins/iflow/hooks/lib/semantic_memory/test_writer.py`
- **Tests:** test_cli_delete_success (AC-8), test_cli_delete_missing_entry_id (AC-9), test_cli_delete_not_found_exits_1
- **Done when:** All 3 tests exist and fail (RED phase)
- **Depends on:** Task 1.4

### Task 2.2: Implement CLI --action delete
- **File:** `plugins/iflow/hooks/lib/semantic_memory/writer.py`
- **Implementation:** Add "delete" to choices, add --entry-id arg, post-parse validation via parser.error(), delete handler branch calling db.delete_entry()
- **Done when:** All 3 tests from Task 2.1 pass (GREEN phase)
- **Depends on:** Task 2.1

## Phase 3: MCP Tools (two parallel tracks: 3.1→3.2 and 3.3→3.4)

### Task 3.1: Write MCP delete_entity tests
- **File:** `plugins/iflow/mcp/test_search_mcp.py`
- **Tests:** test_mcp_delete_entity_success (AC-10), test_mcp_delete_entity_not_found, test_mcp_delete_entity_has_children
- **Done when:** All 3 tests exist and fail (RED phase)
- **Depends on:** Task 1.2

### Task 3.2: Implement MCP delete_entity tool
- **File:** `plugins/iflow/mcp/entity_server.py`
- **Implementation:** Add `async def delete_entity(type_id: str) -> str` with `@mcp.tool()` decorator, _db None guard, broad except Exception, return JSON strings
- **Done when:** All 3 tests from Task 3.1 pass (GREEN phase)
- **Depends on:** Task 3.1

### Task 3.3: Write MCP delete_memory tests
- **File:** `plugins/iflow/mcp/test_memory_server.py`
- **Tests:** test_mcp_delete_memory_success (AC-11), test_mcp_delete_memory_not_found
- **Done when:** All 2 tests exist and fail (RED phase)
- **Depends on:** Task 1.4

### Task 3.4: Implement MCP delete_memory tool
- **File:** `plugins/iflow/mcp/memory_server.py`
- **Implementation:** Add `async def delete_memory(entry_id: str) -> str` with `@mcp.tool()` decorator, _db None guard, broad except Exception, return JSON strings
- **Done when:** All 2 tests from Task 3.3 pass (GREEN phase)
- **Depends on:** Task 3.3

## Phase 4: Verification

### Task 4.1: Run full test suites and validate
- **Commands:**
  - `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
  - `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/semantic_memory/ -v`
  - `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_search_mcp.py -v`
  - `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_memory_server.py -v`
  - `./validate.sh`
- **Done when:** All suites pass, validate.sh reports 0 errors
- **Depends on:** Tasks 2.2, 3.2, 3.4
