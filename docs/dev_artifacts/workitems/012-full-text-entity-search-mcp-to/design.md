# Design: Full-Text Entity Search MCP Tool

## Prior Art Research

### Codebase Patterns
- **EntityDatabase** (`plugins/iflow/hooks/lib/entity_registry/database.py:340-713`): Core class with `register_entity`, `update_entity`, `get_entity`, `list_entities`. All write methods commit eagerly after the main table write.
- **Migration chain** (`database.py:329-334`): `MIGRATIONS = {1: _create_initial_schema, 2: _migrate_to_uuid_pk, 3: _create_workflow_phases_table}`. Each migration uses `BEGIN IMMEDIATE / COMMIT / ROLLBACK` in a try/except/finally pattern.
- **MCP entity server** (`plugins/iflow/mcp/entity_server.py:88-274`): FastMCP with async tool functions. Error pattern: `except Exception as exc: return f'Error ...: {exc}'`.
- **Test patterns** (`test_database.py`, `test_entity_server.py`): pytest fixtures with `tmp_path`, direct SQL introspection for schema assertions, monkeypatched DB for MCP tool tests.
- **No existing FTS code** — entirely greenfield addition.

### External Research
- FTS5 external content tables use `content='entities', content_rowid='rowid'` to link index to source table.
- Application-level sync is explicitly supported by FTS5. The delete command format `INSERT INTO fts(fts, rowid, ...) VALUES('delete', ...)` requires exact old values matching indexed tokens.
- The `rebuild` command (`INSERT INTO fts(fts) VALUES('rebuild')`) reconstructs the entire index from the content table — serves as the recovery mechanism for any FTS/content table drift.
- Double-quote wrapping with internal quote escaping neutralizes all FTS5 special characters for safe user input handling.
- At ~100 rows, FTS5 value is feature richness (ranking, tokenization, prefix) rather than performance — query latency is negligible.

## Architecture Overview

The feature adds full-text search as a vertical slice through three existing layers:

```
MCP Tool Layer        →  search_entities tool in entity_server.py
Database Layer        →  search_entities method + FTS sync in database.py
Schema Layer          →  entities_fts FTS5 virtual table via migration 4
```

All changes are additive — no existing method signatures change, no existing SQL schema changes, no existing tests break (AC-20).

### Component Map

```
plugins/iflow/hooks/lib/entity_registry/
├── database.py              ← Modified: migration 4, FTS sync in register/update, search_entities method, flatten_metadata helper
├── test_database.py         ← Modified: new FTS test class, update schema_version assertion
├── test_search.py           ← NEW: dedicated search tests (AC-7 through AC-11, AC-20, AC-21)
plugins/iflow/mcp/
├── entity_server.py         ← Modified: search_entities MCP tool
├── test_entity_server.py    ← Modified: search_entities MCP tool test
```

## Components

### C1: `flatten_metadata` Helper Function

**Location:** `database.py`, module-level function (not a method — used by both EntityDatabase and migration).

**Purpose:** Convert metadata JSON (dict/list/None) to a space-separated string of all leaf scalar values for FTS indexing.

**Why module-level:** The migration backfill needs this function to populate FTS for existing entities. Making it a method would require instantiating EntityDatabase during migration, creating a circular dependency. A simple pure function is the right abstraction.

### C2: Migration 4 — `_create_fts_index`

**Location:** `database.py`, added to `MIGRATIONS` dict as key `4`.

**Purpose:** Create `entities_fts` FTS5 virtual table and backfill from existing entities.

**Pattern:** Follows existing migration pattern — `BEGIN IMMEDIATE`, DDL, data operations, `COMMIT` in try/except/finally. `BEGIN IMMEDIATE` acquires a write lock upfront, preventing concurrent writers from corrupting the migration mid-flight. This is consistent with migrations 2 and 3. No FK changes needed, no PRAGMA manipulation.

**FTS5 availability check:** The `CREATE VIRTUAL TABLE ... USING fts5(...)` itself serves as the availability check — wrap it in try/except and if `OperationalError` contains "no such module: fts5", raise `RuntimeError("FTS5 extension not available")`. See I2 step 1 for the definitive approach.

**Backfill strategy:** `INSERT INTO entities_fts(rowid, name, entity_id, entity_type, status, metadata_text) SELECT rowid, name, entity_id, entity_type, status, '' FROM entities` for the base columns, then iterate rows in Python to flatten metadata JSON per-row. This avoids loading all metadata into memory at once for large registries.

**Revised backfill strategy:** Actually, since we have ~80 rows, a single Python loop reading all rows and inserting per-row is simpler and sufficient. No need for batch optimization.

### C3: FTS Sync in `register_entity`

**Location:** `database.py`, within `register_entity` method.

**Change:** After the existing `INSERT OR IGNORE INTO entities ...`, check `cursor.rowcount == 1`. If row was inserted, insert into `entities_fts` with flattened metadata. Defer `self._conn.commit()` until after FTS write.

**Transaction boundary change:** Move `self._conn.commit()` to after FTS insert. If FTS insert fails, the entire transaction (entities insert + FTS insert) rolls back together.

### C4: FTS Sync in `update_entity`

**Location:** `database.py`, within `update_entity` method.

**Change:** Before the existing UPDATE, SELECT current row to capture old values (rowid, name, entity_id, entity_type, status, metadata). After UPDATE, issue FTS delete with old values then FTS insert with new values. All within one transaction.

**Unconditional sync:** FTS sync fires on every `update_entity` call, regardless of which fields changed. Even if only non-FTS fields are updated (e.g., `artifact_path`), the delete+insert cycle runs. This is correct because: (1) `update_entity` accepts any combination of fields including FTS-indexed ones, (2) checking which fields changed adds complexity for negligible savings at ~100 rows, (3) the delete+insert with identical values is a no-op to FTS5.

**`set_parent` exclusion:** The `set_parent` method modifies only the `parent_uuid` column, which is not FTS-indexed. Since `set_parent` doesn't go through `update_entity`, no FTS sync is needed. If `set_parent` ever modifies FTS-indexed fields, it must be updated to include FTS sync.

**Critical ordering note:** The spec captures old values before UPDATE (Step 1), then does UPDATE (Step 2), then FTS delete with explicit old values (Step 3), then FTS insert (Step 4). This is safe because we pass explicit old values to the FTS delete command, not relying on FTS5 to read the content table. External research confirmed: the delete command uses the values you provide, not what's in the content table.

### C5: `search_entities` Database Method

**Location:** `database.py`, new method on `EntityDatabase`.

**Purpose:** Execute FTS5 MATCH queries with sanitization, type filtering, limit clamping, and relevance ranking. Includes a private helper method `_build_fts_query` for query sanitization.

**Query sanitization pipeline (in `_build_fts_query` private method):**
1. Empty/whitespace → return `[]`
2. Exact phrase detection: `"..."` → strip operators from inner content, wrap back in quotes
3. Strip FTS5 operators: `* " ( ) + - ^ :`
4. Tokenize on whitespace, return `[]` if empty
5. Append `*` to each token for prefix matching
6. Join tokens with spaces (FTS5 implicit AND)

**FTS availability guard:** Check if `entities_fts` exists in `sqlite_master` before querying. Raise `ValueError("fts_not_available: ...")` if missing.

### C6: `search_entities` MCP Tool

**Location:** `entity_server.py`, new async function registered with FastMCP.

**Pattern:** Follows existing tool pattern — check `_db is None`, call DB method, format results, catch `ValueError` and return error string.

**Output formatting:** Numbered list with `type_id — "name" (status)` per result line.

## Technical Decisions

### TD-1: Application-Level Sync vs Triggers
**Decision:** Application-level sync (per spec R2).
**Rationale:** metadata JSON flattening requires recursive Python traversal. SQLite triggers cannot express this. Application-level sync also provides better error handling and testability.
**Trade-off:** If a future code path writes to `entities` table without going through `EntityDatabase` methods, FTS will drift. Mitigated by the `rebuild` command and by the convention that all writes go through `EntityDatabase`.

### TD-2: Module-Level `flatten_metadata` vs Method
**Decision:** Module-level pure function.
**Rationale:** Needed by both `EntityDatabase` methods and migration backfill. A pure function with no state is simpler and avoids circular dependencies.

### TD-3: FTS Availability Check via sqlite_master
**Decision:** Check `entities_fts` in `sqlite_master` rather than try/except on query.
**Rationale:** Explicit check gives a clear error message (`fts_not_available`) vs a generic `OperationalError`. The check is O(1) and cacheable.

### TD-4: Separate Test File for Search
**Decision:** New `test_search.py` alongside `test_database.py`.
**Rationale:** Search tests need multi-entity fixtures and test all sanitization paths. Keeping them separate avoids bloating `test_database.py` (already 545+ tests) and makes the search test suite independently runnable.

### TD-5: Backfill in Migration vs On-Demand Rebuild
**Decision:** Backfill during migration (per spec R5).
**Rationale:** Ensures FTS index is immediately available after migration. On-demand rebuild would require checking index state on every search, adding latency and complexity.

## Risks

### Risk 1: Rowid Stability Across VACUUM
**Impact:** Medium — if VACUUM reassigns implicit rowids, FTS index becomes stale.
**Likelihood:** Low — implicit rowids are NOT guaranteed stable across VACUUM (contrary to the spec's original claim). However, VACUUM is never called in the codebase, and the entity DB uses WAL mode which does not auto-vacuum by default.
**Mitigation:** The `rebuild` command can reconstruct the index. If needed, a future enhancement could add an explicit integer rowid column. Not needed now given VACUUM is never invoked.
**Note:** The spec R1 (line 39) claims implicit rowids are stable across VACUUM — this is incorrect per SQLite docs. The design treats rowids as NOT guaranteed stable. This discrepancy is acknowledged and the design's position is authoritative.

### Risk 2: FTS Index Drift from Direct DB Writes
**Impact:** Medium — searches return stale results.
**Likelihood:** Low — all entity writes go through `EntityDatabase` methods.
**Mitigation:** Convention enforcement (all writes via `EntityDatabase`) + `rebuild` command for recovery. Could add a periodic health check in the future.

### Risk 3: FTS5 Extension Not Available
**Impact:** High — feature completely broken.
**Likelihood:** Very low — FTS5 is compiled into Python's bundled SQLite by default on all major platforms.
**Mitigation:** Migration checks for FTS5 availability and raises a clear error if missing. `search_entities` method checks for table existence.

## Interfaces

### I1: `flatten_metadata(metadata: dict | None) -> str`

```python
def flatten_metadata(metadata: dict | None) -> str:
    """Flatten metadata JSON to space-separated string of all leaf scalar values.

    Recursively traverses dicts (values only) and lists (elements).
    None/null values are skipped. Scalars are converted via str().
    Returns empty string for None input or empty structures.
    """
```

**Examples:**
- `None` → `""`
- `{}` → `""`
- `{"module": "State Engine"}` → `"State Engine"`
- `{"module": "State Engine", "depends_on": ["001"]}` → `"State Engine 001"`
- `{"a": {"b": "deep"}}` → `"deep"`
- `{"flag": True, "count": 42}` → `"True 42"`

### I2: `_create_fts_index(conn: sqlite3.Connection)`

```python
def _create_fts_index(conn: sqlite3.Connection):
    """Migration 4: Create FTS5 virtual table and backfill from existing entities."""
```

**Operations:**
1. **FTS5 availability check via CREATE:** The `CREATE VIRTUAL TABLE ... USING fts5(...)` itself is the check. Wrap it in try/except — if `OperationalError` message contains "no such module: fts5", raise `RuntimeError("FTS5 extension not available")`. Note: `SELECT fts5()` is NOT valid — FTS5 is a virtual table module, not a standalone function.
2. `CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(name, entity_id, entity_type, status, metadata_text, content='entities', content_rowid='rowid')`
3. For each row in `SELECT rowid, name, entity_id, entity_type, status, metadata FROM entities`:
   - `metadata_text = flatten_metadata(json.loads(metadata) if metadata else None)`
   - `INSERT INTO entities_fts(rowid, name, entity_id, entity_type, status, metadata_text) VALUES(?, ?, ?, ?, ?, ?)`
4. Schema version update to `'4'` — handled by the migration runner (`_run_migrations`), not inside this function. This is consistent with migrations 2 and 3 which also don't set schema_version themselves.

### I3: FTS Sync in `register_entity`

**After existing INSERT OR IGNORE (cursor must be captured from execute):**
```python
cursor = self._conn.execute(
    "INSERT OR IGNORE INTO entities ...", (...)
)
if cursor.rowcount == 1:
    # Row was actually inserted (not duplicate skip)
    rowid = self._conn.execute(
        "SELECT rowid FROM entities WHERE uuid = ?", (entity_uuid,)
    ).fetchone()[0]
    metadata_text = flatten_metadata(metadata)
    self._conn.execute(
        "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, status, metadata_text) "
        "VALUES(?, ?, ?, ?, ?, ?)",
        (rowid, name, entity_id, entity_type, status or "", metadata_text),
    )
self._conn.commit()  # Moved to after FTS write
```

### I4: FTS Sync in `update_entity`

**Execution order:** The existing `_resolve_identifier` call (which raises `ValueError` for missing entities) precedes the FTS sync code, so `old_row` is guaranteed non-None.

**Before existing UPDATE, within same transaction:**
```python
# Step 1: Read old values (entity_uuid is from existing _resolve_identifier call)
old_row = self._conn.execute(
    "SELECT rowid, name, entity_id, entity_type, status, metadata FROM entities WHERE uuid = ?",
    (entity_uuid,)
).fetchone()
old_rowid, old_name, old_entity_id, old_entity_type, old_status, old_metadata_raw = old_row
old_metadata_text = flatten_metadata(json.loads(old_metadata_raw) if old_metadata_raw else None)

# Step 2: UPDATE entities (existing logic — unchanged)
# ...

# Step 3: FTS delete with old values
self._conn.execute(
    "INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, entity_type, status, metadata_text) "
    "VALUES('delete', ?, ?, ?, ?, ?, ?)",
    (old_rowid, old_name, old_entity_id, old_entity_type, old_status or "", old_metadata_text),
)

# Step 4: FTS insert with new values (computed from Python, no re-read needed)
# Derive final_metadata from the three metadata code paths:
#   (a) metadata is None (not provided) => final_metadata = old metadata (unchanged)
#   (b) metadata == {} (clear) => final_metadata = None (will produce "")
#   (c) metadata has keys => final_metadata = shallow-merged result
if metadata is None:
    final_metadata = json.loads(old_metadata_raw) if old_metadata_raw else None
elif metadata == {}:
    final_metadata = None
else:
    existing = json.loads(old_metadata_raw) if old_metadata_raw else {}
    existing.update(metadata)
    final_metadata = existing

new_metadata_text = flatten_metadata(final_metadata)
# entity_id and entity_type never change; rowid is stable within transaction
self._conn.execute(
    "INSERT INTO entities_fts(rowid, name, entity_id, entity_type, status, metadata_text) "
    "VALUES(?, ?, ?, ?, ?, ?)",
    (old_rowid, name if name is not None else old_name, old_entity_id, old_entity_type,
     (status if status is not None else old_status) or "", new_metadata_text),
)

self._conn.commit()  # Moved to after FTS writes
```

### I5: `search_entities` Database Method

```python
def search_entities(
    self,
    query: str,
    entity_type: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Search entities using FTS5 full-text search.

    Args:
        query: Search string. Supports prefix matching by default.
            Wrap in double quotes for exact phrase matching.
        entity_type: Optional filter to specific entity type.
        limit: Max results (1-100, default 20).

    Returns:
        List of entity dicts with same shape as get_entity() plus 'rank' field.

    Raises:
        ValueError: If FTS5 table not available or query syntax invalid.
    """
```

**Query building implementation:**
```python
def _build_fts_query(self, query: str) -> str | None:
    """Build FTS5 MATCH expression from user query. Returns None if query is empty after sanitization."""
    query = query.strip()
    if not query:
        return None

    FTS5_OPERATORS = set('*"()+-^:')

    # Exact phrase detection
    if query.startswith('"') and query.endswith('"') and len(query) > 2:
        inner = query[1:-1]
        sanitized_inner = "".join(c for c in inner if c not in FTS5_OPERATORS)
        sanitized_inner = sanitized_inner.strip()
        if not sanitized_inner:
            return None
        return f'"{sanitized_inner}"'

    # Strip FTS5 operators
    sanitized = "".join(c for c in query if c not in FTS5_OPERATORS)
    tokens = sanitized.split()
    if not tokens:
        return None

    # Prefix match on each token
    return " ".join(f"{token}*" for token in tokens)
```

**SQL query:**
```sql
SELECT e.*, entities_fts.rank
FROM entities_fts
JOIN entities e ON entities_fts.rowid = e.rowid
WHERE entities_fts MATCH :query
  [AND e.entity_type = :entity_type]  -- optional
ORDER BY entities_fts.rank
LIMIT :limit
```

### I6: `search_entities` MCP Tool

```python
@mcp.tool()
async def search_entities(
    query: str,
    entity_type: str | None = None,
    limit: int = 20,
) -> str:
    """Search entities by name, ID, type, or metadata using full-text search.

    Args:
        query: Search query. Supports prefix matching by default.
            Examples: "recon" matches "reconciliation", "kanban" matches "kanban-board-view".
        entity_type: Filter to specific entity type (backlog, brainstorm, project, feature).
        limit: Maximum results to return (max 100).
    """
    if _db is None:
        return "Error: database not initialized"
    try:
        results = _db.search_entities(query, entity_type=entity_type, limit=limit)
    except ValueError as exc:
        return f"Search error: {exc}"

    if not results:
        return f'No entities found matching "{query}".'

    lines = [f'Found {len(results)} entities matching "{query}":\n']
    for i, entity in enumerate(results, 1):
        type_id = entity.get("type_id", "unknown")
        name = entity.get("name", "")
        status = entity.get("status", "")
        lines.append(f'{i}. {type_id} — "{name}" ({status})')

    lines.append(f"\n{len(results)} results shown (limit: {limit}).")
    return "\n".join(lines)
```

## Test Strategy

### Existing Test Updates
- `test_database.py::TestMetadata::test_schema_version_is_3` (function name: `test_schema_version_is_3` in class `TestMetadata`, line ~535) → assert `'4'`
- `test_database.py::TestMigration3::test_schema_version_is_3` (function name: `test_schema_version_is_3` in class `TestMigration3`, line ~2498) → assert `'4'`

Both are locatable via: `grep -n 'test_schema_version_is_3' test_database.py`

### New Test File: `test_search.py`

**Fixture:** `search_db` — creates EntityDatabase with 5+ entities of various types, names, and metadata to exercise all search paths.

**Test classes:**
- `TestFlattenMetadata` — unit tests for the helper (None, empty, nested, scalars, edge cases)
- `TestMigration4` — FTS table exists, backfill correct, schema version 4, idempotent `IF NOT EXISTS`
- `TestFTSSync` — insert makes entity searchable, update reflects changes, duplicate skip doesn't corrupt
- `TestSearchEntities` — prefix match, type filter, limit clamping, empty query, relevance ordering, exact phrase
- `TestSearchSanitization` — FTS5 operators stripped, special chars don't raise, empty-after-sanitization returns `[]`
- `TestSearchMCPTool` — tool registered, formatted output, no results message, error handling

### Regression Gate (AC-20)
All 545+ existing tests must pass. No existing test should require modification except `test_schema_version_is_3`.
