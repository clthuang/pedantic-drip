# Design: Entity Delete API

## Prior Art Research

**Codebase patterns:**
- `delete_workflow_phase` (database.py:1476): SELECT-validate-raise, DELETE, commit. No FTS. Own transaction.
- `update_entity` FTS sync (database.py:878-950): SELECT old values, execute UPDATE, FTS 'delete' sentinel with old values, FTS INSERT with new values, commit.
- `upsert_entry` (semantic_memory): BEGIN IMMEDIATE + try/commit/except rollback pattern for write isolation.
- `entries_ad` trigger (semantic_memory:90-95): AFTER DELETE trigger auto-cleans FTS — no manual FTS work needed for memory deletes.
- MCP error convention: return error strings (never raise), guard with `_db is None` check.

**External research:**
- FTS5 external-content delete: must issue 'delete' sentinel BEFORE content row deletion, with exact old values.
- MCP spec supports `destructiveHint` annotation on tools — consider for future but not required for this feature.

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                  MCP Layer (thin)                │
│  delete_entity()          delete_memory()        │
│  (entity_server.py)       (memory_server.py)     │
└──────────┬──────────────────────┬────────────────┘
           │                      │
           ▼                      ▼
┌──────────────────┐   ┌──────────────────────────┐
│ EntityDatabase   │   │ MemoryDatabase           │
│ .delete_entity() │   │ .delete_entry()          │
│                  │   │                          │
│ 1. Validate      │   │ 1. Validate              │
│ 2. Child check   │   │ 2. DELETE (trigger FTS)  │
│ 3. FTS delete    │   │                          │
│ 4. WF delete     │   └──────────────────────────┘
│ 5. Entity delete │            ▲
└──────────────────┘            │
                     ┌──────────┴─────────────────┐
                     │ CLI (writer.py)             │
                     │ --action delete --entry-id  │
                     └────────────────────────────┘
```

**Key design decision:** Two different FTS cleanup strategies:
- Entity registry: manual FTS5 'delete' sentinel (no trigger exists)
- Semantic memory: rely on existing `entries_ad` AFTER DELETE trigger

This is intentional — the entity registry was built without triggers, and adding one now would be a schema migration out of scope.

## Components

### C1: EntityDatabase.delete_entity(type_id: str) -> None

**Location:** `plugins/iflow/hooks/lib/entity_registry/database.py`

**Transaction strategy:** `BEGIN IMMEDIATE` with try/commit/except rollback. This is an intentional departure from the simple commit-only pattern used by `register_entity` and `update_entity` — multi-table delete (entities + entities_fts + workflow_phases) needs stronger isolation to prevent partial writes.

**Implementation pseudocode:**
```python
def delete_entity(self, type_id: str) -> None:
    self._conn.execute("BEGIN IMMEDIATE")
    try:
        # 1. Validate + fetch old values for FTS cleanup
        row = self._conn.execute(
            "SELECT uuid, rowid, name, entity_id, entity_type, status, metadata "
            "FROM entities WHERE type_id = ?", (type_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Entity not found: {type_id}")

        # 2. Reject if has children
        child = self._conn.execute(
            "SELECT 1 FROM entities WHERE parent_uuid = ? LIMIT 1",
            (row["uuid"],)
        ).fetchone()
        if child is not None:
            raise ValueError(f"Cannot delete entity with children: {type_id}")

        # 3. FTS5 external-content delete (before row deletion)
        try:
            metadata_text = flatten_metadata(
                json.loads(row["metadata"]) if row["metadata"] else None
            )
        except (json.JSONDecodeError, TypeError):
            metadata_text = ""  # corrupted metadata — use empty for FTS delete
        self._conn.execute(
            "INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, "
            "entity_type, status, metadata_text) "
            "VALUES('delete', ?, ?, ?, ?, ?, ?)",
            (row["rowid"], row["name"], row["entity_id"],
             row["entity_type"], row["status"] or "", metadata_text),
        )

        # 4. Delete workflow_phases (FK: must precede entity delete)
        self._conn.execute(
            "DELETE FROM workflow_phases WHERE type_id = ?", (type_id,)
        )

        # 5. Delete entity row
        self._conn.execute(
            "DELETE FROM entities WHERE type_id = ?", (type_id,)
        )

        self._conn.commit()
    except Exception:
        self._conn.rollback()
        raise
```

### C2: MemoryDatabase.delete_entry(entry_id: str) -> None

**Location:** `plugins/iflow/hooks/lib/semantic_memory/database.py`

**Transaction strategy:** `BEGIN IMMEDIATE` matching `upsert_entry` pattern.

```python
def delete_entry(self, entry_id: str) -> None:
    self._conn.execute("BEGIN IMMEDIATE")
    try:
        row = self._conn.execute(
            "SELECT 1 FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Memory entry not found: {entry_id}")

        self._conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        # FTS cleanup handled by entries_ad AFTER DELETE trigger
        self._conn.commit()
    except Exception:
        self._conn.rollback()
        raise
```

### C3: CLI extension — writer.py

**Location:** `plugins/iflow/hooks/lib/semantic_memory/writer.py`

Changes:
1. Extend `choices=["upsert"]` → `choices=["upsert", "delete"]`
2. Add `--entry-id` argument (optional, validated post-parse)
3. Add post-parse validation: `if args.action == "delete" and not args.entry_id: parser.error(...)`
4. Add delete handler in main():

```python
if args.action == "delete":
    try:
        db.delete_entry(args.entry_id)
        print(f"Deleted memory entry: {args.entry_id}")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
```

### C4: MCP delete_entity tool

**Location:** `plugins/iflow/mcp/entity_server.py`

```python
async def delete_entity(type_id: str) -> str:
    if _db is None:
        return "Error: database not initialized"
    try:
        _db.delete_entity(type_id)
        return json.dumps({"result": f"Deleted: {type_id}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})
```

### C5: MCP delete_memory tool

**Location:** `plugins/iflow/mcp/memory_server.py`

```python
async def delete_memory(entry_id: str) -> str:
    if _db is None:
        return "Error: database not initialized"
    try:
        _db.delete_entry(entry_id)
        return json.dumps({"result": f"Deleted memory: {entry_id}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})
```

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Transaction pattern for entity delete | BEGIN IMMEDIATE | Multi-table delete needs write lock to prevent partial state |
| FTS cleanup for entity | Manual sentinel | No trigger exists; adding one is a migration out of scope |
| FTS cleanup for memory | Rely on trigger | `entries_ad` trigger already handles this correctly |
| Child check column | `parent_uuid` | Matches existing pattern at database.py:1136 |
| Inline workflow_phases DELETE | Yes | Existing `delete_workflow_phase()` does own commit, breaking atomicity |
| MCP error handling | Return JSON error string | Matches existing convention (never raise from MCP tools) |
| CLI validation | parser.error() | Exits code 2, prints usage — idiomatic argparse |

## Risks

| Risk | Mitigation |
|------|------------|
| FTS index corruption if old values don't match | Fetch values in same transaction before delete; BEGIN IMMEDIATE prevents concurrent modification |
| Orphaned .meta.json files after DB delete | Explicitly out of scope per spec; future cleanup feature can address |
| Concurrent delete + read race | BEGIN IMMEDIATE serializes writes; reads are non-blocking |

## Interfaces

### EntityDatabase.delete_entity

```python
def delete_entity(self, type_id: str) -> None:
    """Delete an entity and all associated data (FTS, workflow_phases).

    Parameters
    ----------
    type_id : str
        Entity type_id in format "{entity_type}:{entity_id}".

    Raises
    ------
    ValueError
        If entity does not exist.
    ValueError
        If entity has child entities (must delete children first).
    """
```

### MemoryDatabase.delete_entry

```python
def delete_entry(self, entry_id: str) -> None:
    """Delete a memory entry. FTS cleaned by trigger.

    Parameters
    ----------
    entry_id : str
        The entry's unique identifier.

    Raises
    ------
    ValueError
        If entry does not exist.
    """
```

### MCP: delete_entity(type_id: str) -> str

- **Input:** `type_id` — entity type_id string
- **Output:** JSON string `{"result": "Deleted: {type_id}"}` or `{"error": "..."}`

### MCP: delete_memory(entry_id: str) -> str

- **Input:** `entry_id` — memory entry identifier
- **Output:** JSON string `{"result": "Deleted memory: {entry_id}"}` or `{"error": "..."}`

### CLI: writer.py --action delete

- **Args:** `--action delete --entry-id <id> --global-store <path>`
- **Stdout:** `Deleted memory entry: {entry_id}`
- **Stderr:** error message if not found
- **Exit codes:** 0 success, 1 not found, 2 missing args

## Dependencies

- `flatten_metadata` from `entity_registry/database.py` (already imported)
- `json` stdlib (already imported in both modules)
- No new dependencies required
