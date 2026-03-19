# Spec: Entity Delete API

## Problem Statement

The entity registry (`EntityDatabase`) and knowledge bank (`MemoryDatabase`) both lack delete operations. Users cannot remove stale, incorrect, or test entries without raw SQL. This blocks cleanup workflows and makes the `/iflow:remember` "forget" use case impossible through the standard API surface.

**Motivation:** Required for (1) `/iflow:remember --forget` workflow, (2) test cleanup in entity registry tests, (3) removing stale entities from abandoned features.

## Scope

### In Scope
1. `EntityDatabase.delete_entity(type_id)` — delete entity row, FTS entry, and workflow_phases row
2. `MemoryDatabase.delete_entry(entry_id)` — delete memory row (FTS auto-cleaned by trigger)
3. CLI `--action delete` for `semantic_memory.writer`
4. MCP `delete_entity` tool on entity_server
5. MCP `delete_memory` tool on memory_server

### Out of Scope
- Bulk delete / batch operations
- Soft delete / archival (use status updates for that)
- Cascade delete of child entities (delete is leaf-only; parent with children is rejected)
- UI delete buttons
- Deletion of on-disk artifact files (.meta.json, spec.md, etc.) — DB-only operation. Orphaned file cleanup is a separate concern.

## Requirements

### R1: EntityDatabase.delete_entity(type_id: str) -> None

**Execution order within a single transaction (R1.6):**

1. **R1.4**: Validate existence — `SELECT uuid, rowid, name, entity_id, entity_type, status, metadata FROM entities WHERE type_id = ?`. Raise `ValueError` if not found. Note: `metadata` is needed to compute `metadata_text` via `flatten_metadata(json.loads(metadata))` for the FTS delete in step 3.
2. **R1.5**: Reject if entity has children — `SELECT 1 FROM entities WHERE parent_uuid = ? LIMIT 1` (using `parent_uuid` to match existing codebase pattern at database.py:1136). Raise `ValueError("Cannot delete entity with children: {type_id}")` if children exist.
3. **R1.2**: Delete FTS entry using FTS5 external-content delete syntax: `INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, entity_type, status, metadata_text) VALUES('delete', ?, ?, ?, ?, ?, ?)` with the old row values (follows existing pattern at database.py:936-941).
4. **R1.3**: Delete workflow_phases row if present — inline SQL `DELETE FROM workflow_phases WHERE type_id = ?` (do NOT call `delete_workflow_phase()` method, as it performs its own commit which would break atomicity).
5. **R1.1**: Delete the entity row — `DELETE FROM entities WHERE type_id = ?`.

- **R1.6**: All operations above wrapped in a single transaction with try/except rollback. Use `self._conn.execute("BEGIN IMMEDIATE")` for write lock (intentional departure from existing CRUD patterns — multi-table delete requires stronger isolation to prevent partial writes under concurrent access).

### R2: MemoryDatabase.delete_entry(entry_id: str) -> None

- **R2.1**: Validate existence — `SELECT 1 FROM entries WHERE id = ?`. Raise `ValueError` if not found.
- **R2.2**: Delete the row from `entries` table — `DELETE FROM entries WHERE id = ?`. FTS cleanup is handled automatically by the existing `entries_ad` AFTER DELETE trigger. No manual FTS deletion needed.
- **R2.3**: Wrap in `BEGIN IMMEDIATE` / `commit()` with rollback on exception.

### R3: CLI --action delete for semantic_memory.writer

- **R3.1**: Add `"delete"` to `choices=["upsert"]` → `choices=["upsert", "delete"]`
- **R3.2**: Add `--entry-id` argument. Required when `--action delete`.
- **R3.3**: When `--action delete`: call `db.delete_entry(entry_id)`, print `Deleted memory entry: {entry_id}`
- **R3.4**: Exit 1 with error message to stderr if entry not found (ValueError)
- **R3.5**: If `--action delete` without `--entry-id`: argparse exits with code 2 and prints usage to stderr

### R4: MCP delete_entity tool

- **R4.1**: Add `delete_entity(type_id: str) -> str` to `entity_server.py`
- **R4.2**: Call `db.delete_entity(type_id)`
- **R4.3**: Return `{"result": "Deleted: {type_id}"}` on success
- **R4.4**: Return `{"error": "..."}` if entity not found or has children

### R5: MCP delete_memory tool

- **R5.1**: Add `delete_memory(entry_id: str) -> str` to `memory_server.py`
- **R5.2**: Call `db.delete_entry(entry_id)`
- **R5.3**: Return `{"result": "Deleted memory: {entry_id}"}` on success
- **R5.4**: Return `{"error": "..."}` if entry not found

## Acceptance Criteria

- **AC-1**: `EntityDatabase.delete_entity("feature:999-nonexistent")` raises `ValueError`
- **AC-2**: Given entity `feature:001-test` exists with a workflow_phases row, when `delete_entity("feature:001-test")` is called, then `SELECT FROM entities WHERE type_id = "feature:001-test"` returns no rows, AND `entities_fts` MATCH query returns no results, AND `SELECT FROM workflow_phases WHERE type_id = "feature:001-test"` returns no rows.
- **AC-3**: `EntityDatabase.delete_entity("project:P001")` raises `ValueError` when project has child features
- **AC-4**: After entity delete, `search_entities` no longer returns the deleted entity
- **AC-5**: `MemoryDatabase.delete_entry("nonexistent")` raises `ValueError`
- **AC-6**: `MemoryDatabase.delete_entry("test-entry")` deletes entry row and FTS trigger auto-cleans FTS
- **AC-7**: After memory delete, `search` no longer returns the deleted entry
- **AC-8**: CLI `--action delete --entry-id "test"` deletes and prints confirmation
- **AC-9**: CLI `--action delete` without `--entry-id` exits with code 2 and prints usage to stderr
- **AC-10**: MCP `delete_entity(type_id="feature:001-test")` returns success JSON
- **AC-11**: MCP `delete_memory(entry_id="test")` returns success JSON
- **AC-12**: Given an entity exists, when `delete_entity` is called and an error occurs mid-transaction (e.g., mock `self._conn.execute` to raise after the workflow_phases DELETE but before the entities DELETE), then the entity, FTS entry, and workflow_phases row all remain intact (full rollback).
