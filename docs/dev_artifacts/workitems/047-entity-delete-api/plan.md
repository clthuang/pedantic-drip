# Plan: Entity Delete API

## Build Order

Five steps, ordered by dependency. Database methods first (no dependencies), then CLI (depends on memory DB method), then MCP tools (depend on DB methods).

```
Step 1: EntityDatabase.delete_entity    ← no deps
Step 2: MemoryDatabase.delete_entry     ← no deps
Step 3: CLI --action delete             ← depends on Step 2
Step 4: MCP delete_entity tool          ← depends on Step 1
Step 5: MCP delete_memory tool          ← depends on Step 2
```

Steps 1 and 2 are independent and can be implemented in parallel.
Steps 4 and 5 are independent and can be implemented in parallel.

## Step 1: EntityDatabase.delete_entity

**Why this item:** Implements C1 from design — core database delete with FTS5 sentinel, child guard, and workflow_phases cleanup.
**Why this order:** No dependencies; must exist before MCP layer (Step 4) can call it.

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
**Test file:** `plugins/iflow/hooks/lib/entity_registry/test_database.py`
**Placement:** After `update_entity` (~line 950) to group CRUD operations logically.

**Tests (write first — TDD):**
- test_delete_entity_not_found → AC-1
- test_delete_entity_success → AC-2
- test_delete_entity_with_children_rejected → AC-3
- test_delete_entity_fts_cleaned → AC-4
- test_delete_entity_no_workflow_phases → AC-13
- test_delete_entity_rollback_on_error → AC-12
- test_delete_entity_corrupted_metadata_still_deletes

**Implementation:**
1. Add `delete_entity(self, type_id: str) -> None` method
2. Follow pseudocode from design.md C1:
   - BEGIN IMMEDIATE (note: existing connection has busy_timeout via `_conn.execute("PRAGMA busy_timeout = 5000")` — contention returns SQLITE_BUSY after 5s)
   - SELECT entity row (uuid, rowid, name, entity_id, entity_type, status, metadata)
   - ValueError if not found (rollback is harmless after read-only ops)
   - Check children via parent_uuid; ValueError if any
   - FTS5 'delete' sentinel with old values (defensive try/except on metadata parsing)
   - DELETE FROM workflow_phases WHERE type_id = ?
   - DELETE FROM entities WHERE type_id = ?
   - commit / rollback

**Run:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/test_database.py -v -k delete`

## Step 2: MemoryDatabase.delete_entry

**Why this item:** Implements C2 from design — memory delete with trigger-based FTS cleanup.
**Why this order:** No dependencies; must exist before CLI (Step 3) and MCP (Step 5) can call it.

**File:** `plugins/iflow/hooks/lib/semantic_memory/database.py`
**Test file:** `plugins/iflow/hooks/lib/semantic_memory/test_database.py`
**Placement:** After `get_entry` (~line 343).

**Tests (write first — TDD):**
- test_delete_entry_not_found → AC-5
- test_delete_entry_success → AC-6
- test_delete_entry_fts_cleaned → AC-7

**Implementation:**
1. Add `delete_entry(self, entry_id: str) -> None` method
2. Follow pseudocode from design.md C2:
   - BEGIN IMMEDIATE
   - SELECT 1 to validate existence; ValueError if not found
   - DELETE FROM entries WHERE id = ?
   - FTS auto-cleaned by entries_ad trigger
   - commit / rollback

**Run:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/semantic_memory/test_database.py -v -k delete`

## Step 3: CLI --action delete

**Why this item:** Implements C3 from design — extends writer CLI for memory deletion.
**Why this order:** Depends on Step 2 (MemoryDatabase.delete_entry).

**File:** `plugins/iflow/hooks/lib/semantic_memory/writer.py`
**Test file:** `plugins/iflow/hooks/lib/semantic_memory/test_writer.py`

**Tests (write first — TDD):**
- test_cli_delete_success → AC-8
- test_cli_delete_missing_entry_id → AC-9
- test_cli_delete_not_found_exits_1

**Implementation:**
1. Extend `choices=["upsert"]` → `choices=["upsert", "delete"]`
2. Add `--entry-id` argument (optional)
3. Add post-parse validation: `if args.action == "delete" and not args.entry_id: parser.error("--entry-id required for delete")`
4. Add delete handler branch in main()

**Run:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/semantic_memory/test_writer.py -v -k delete`

## Step 4: MCP delete_entity tool

**Why this item:** Implements C4 from design — exposes entity delete via MCP protocol.
**Why this order:** Depends on Step 1 (EntityDatabase.delete_entity).

**File:** `plugins/iflow/mcp/entity_server.py`
**Test file:** `plugins/iflow/mcp/test_search_mcp.py`
**Decorator:** Use `@mcp.tool()` matching existing pattern at entity_server.py line 109+.

**Tests (write first — TDD):**
- test_mcp_delete_entity_success → AC-10
- test_mcp_delete_entity_not_found
- test_mcp_delete_entity_has_children

**Implementation:**
1. Add `async def delete_entity(type_id: str) -> str` with `@mcp.tool()` decorator
2. Guard: `if _db is None: return "Error: database not initialized"`
3. Try/except Exception → return JSON error string
4. Return `json.dumps({"result": f"Deleted: {type_id}"})` on success

**Run:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_search_mcp.py -v -k delete`

## Step 5: MCP delete_memory tool

**Why this item:** Implements C5 from design — exposes memory delete via MCP protocol.
**Why this order:** Depends on Step 2 (MemoryDatabase.delete_entry).

**File:** `plugins/iflow/mcp/memory_server.py`
**Test file:** `plugins/iflow/mcp/test_memory_server.py`
**Decorator:** Use `@mcp.tool()` matching existing pattern at memory_server.py line 290+.

**Tests (write first — TDD):**
- test_mcp_delete_memory_success → AC-11
- test_mcp_delete_memory_not_found

**Implementation:**
1. Add `async def delete_memory(entry_id: str) -> str` with `@mcp.tool()` decorator
2. Guard: `if _db is None: return "Error: database not initialized"`
3. Try/except Exception → return JSON error string
4. Return `json.dumps({"result": f"Deleted memory: {entry_id}"})` on success

**Run:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_memory_server.py -v -k delete`

## Verification

After all steps:
1. Run full entity registry test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
2. Run full semantic memory test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/semantic_memory/ -v`
3. Run entity server MCP tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_search_mcp.py -v`
4. Run memory server MCP tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_memory_server.py -v`
5. Run `./validate.sh` — 0 errors
