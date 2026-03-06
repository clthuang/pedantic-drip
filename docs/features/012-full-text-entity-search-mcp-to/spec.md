# Spec: Full-Text Entity Search MCP Tool

## Overview

Add full-text search to the entity registry using SQLite FTS5 and expose it as an MCP tool (`search_entities`). Enables agents and users to find entities by name, ID fragments, or metadata content without knowing exact identifiers.

## Background

The entity registry currently supports only exact-match lookups (`get_entity` by type_id/UUID) and filtered listing (`list_entities` by entity_type). There is no way to search by partial name, ID fragment, or metadata content. As the entity count grows (currently ~80+ entities across backlog, brainstorm, project, feature types), finding entities requires knowing the exact type_id.

**Dependency:** Feature 001-entity-uuid-primary-key-migrat (completed) — UUID primary keys are in place.

## Requirements

### R1: FTS5 Virtual Table

Create an FTS5 virtual table that indexes searchable entity fields.

**Indexed fields:**
- `name` — entity display name
- `entity_id` — the ID portion of type_id (e.g., "012-full-text-entity-search")
- `entity_type` — backlog, brainstorm, project, feature
- `status` — entity status value
- `metadata_text` — flattened text representation of metadata JSON values

**Schema:**
```sql
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    name,
    entity_id,
    entity_type,
    status,
    metadata_text,
    content='entities',
    content_rowid='rowid'
);
```

**rowid decision:** The `entities` table uses `uuid TEXT PRIMARY KEY` and is NOT declared `WITHOUT ROWID`, so SQLite maintains an implicit integer rowid. This implicit rowid is stable across VACUUM for non-WITHOUT-ROWID tables. The `content='entities', content_rowid='rowid'` configuration is valid and safe. No schema change needed.

**AC-1:** FTS5 virtual table `entities_fts` exists after migration runs.
**AC-2:** All 5 indexed fields are searchable via FTS5 MATCH syntax.
**AC-3:** Existing entities are backfilled into the FTS index on migration.

### R2: Application-Level FTS Sync

Keep the FTS index synchronized with the entities table.

**Sync approach:** Application-level sync in Python, not SQLite triggers. Reason: metadata JSON flattening requires recursive traversal of arbitrarily nested structures, which cannot be expressed reliably in a SQLite trigger expression. Instead, `EntityDatabase` methods (`register_entity`, `update_entity`, and any delete method) perform FTS writes after the main table write, within the same transaction.

**FTS write operations:**
- **On INSERT (register_entity):** After the INSERT OR IGNORE into `entities`, check `cursor.rowcount == 1` to confirm a row was actually inserted (not skipped as duplicate). Only if a row was inserted, insert into `entities_fts` with flattened metadata. When INSERT OR IGNORE skips a duplicate, no FTS write occurs.
- **On UPDATE (update_entity):** Before executing the UPDATE on `entities`, SELECT the current row to capture old values for all FTS-indexed fields (name, entity_id, entity_type, status, metadata). Then execute the UPDATE. Then use old values in the FTS5 delete command, followed by an FTS insert with new values. All four operations (old-value read, entities UPDATE, FTS delete, FTS insert) occur within the same transaction.
  ```sql
  -- Step 1: Read old values
  SELECT rowid, name, entity_id, entity_type, status, metadata FROM entities WHERE uuid = :uuid;
  -- Step 1b: Compute old_metadata_text = flatten_metadata(old_metadata) using the Python helper
  -- Step 2: UPDATE entities (existing logic)
  -- Step 3: FTS delete with old values (using old_metadata_text from Step 1b)
  INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, entity_type, status, metadata_text)
  VALUES('delete', :old_rowid, :old_name, :old_entity_id, :old_entity_type, :old_status, :old_metadata_text);
  -- Step 4: FTS insert with new values
  INSERT INTO entities_fts(rowid, name, entity_id, entity_type, status, metadata_text)
  VALUES(:rowid, :name, :entity_id, :entity_type, :status, :metadata_text);
  ```
- **On DELETE:** DELETE sync is documented for completeness. Currently no `delete_entity` method exists in `EntityDatabase`. When a delete method is added in the future, it must include FTS cleanup per this pattern:
  ```sql
  INSERT INTO entities_fts(entities_fts, rowid, name, entity_id, entity_type, status, metadata_text)
  VALUES('delete', :rowid, :name, :entity_id, :entity_type, :status, :metadata_text);
  ```

**metadata_text extraction (Python helper):** Flatten metadata JSON to a space-separated string of all leaf values. If metadata is NULL, return empty string. Recursively traverse dicts (take values) and lists (take elements), collecting all scalar string representations.

Example: `{"module": "State Engine", "depends_on": ["001"]}` → `"State Engine 001"`.

**Implementation note:** Existing `register_entity` and `update_entity` commit eagerly after the main table write. The implementation must defer commit until after FTS writes to maintain transactional consistency.

**Edge cases:** Scalar values are converted via `str(value)`. `None`/`null` values are skipped. Booleans become `"True"`/`"False"`. Numeric values become their string form (e.g., `42` → `"42"`). Empty dicts/lists contribute nothing.

**AC-4:** Inserting an entity via `register_entity` makes it immediately searchable.
**AC-5:** Updating an entity via `update_entity` reflects changes in search results.
**AC-6:** The DELETE FTS sync pattern is specified for future use. When a `delete_entity` method is added, it must remove the entity from search results per the documented pattern. (Not testable in current scope — no `delete_entity` method exists.)

### R3: Database search_entities Method

Add a `search_entities` method to `EntityDatabase`.

**Signature:**
```python
def search_entities(
    self,
    query: str,
    entity_type: str | None = None,
    limit: int = 20,
) -> list[dict]:
```

**Behavior:**
1. If `query` is empty or whitespace-only, return empty list.
2. Sanitize `query`: strip leading/trailing whitespace.
3. Build FTS5 MATCH query (order of operations matters):
   a. **Exact phrase detection** (first): If the query starts and ends with double quotes, extract the inner content, strip FTS5 operators from the inner content per step 3b, and wrap the sanitized inner content back in double quotes for FTS5 phrase matching. Return this as the MATCH expression. Skip steps 3b-3d.
   b. **Sanitize special characters:** Strip FTS5 operators (`*`, `"`, `(`, `)`, `+`, `-`, `^`, `:`) from the query. This prevents `sqlite3.OperationalError` from malformed FTS syntax.
   c. **Tokenize:** Split sanitized query on whitespace into individual tokens. If no tokens remain after sanitization, return empty list.
   d. **Multi-token combination:** Multiple tokens are combined with implicit AND (FTS5 default). Example: query `"state engine"` matches entities containing both "state" AND "engine".
   e. **Prefix match:** Append `*` to each token for prefix matching. Example: query `"recon"` becomes `"recon*"` to match "reconciliation". Multi-token: `"state eng"` becomes `"state* eng*"`.
4. If `entity_type` provided, filter results to that type.
5. Order results by FTS5 `rank` (relevance score, lower is better).
6. Clamp `limit` to range [1, 100] — if `limit > 100`, set `limit = 100`. Apply clamped limit to query.
7. Return list of entity dicts with same shape as `get_entity` output plus a `rank` field.

**JOIN strategy:** Query joins `entities_fts` with `entities` using rowid: `SELECT e.*, entities_fts.rank FROM entities_fts JOIN entities e ON entities_fts.rowid = e.rowid WHERE entities_fts MATCH :query ORDER BY entities_fts.rank`. The `entity_type` filter and `limit` are applied as additional WHERE/LIMIT clauses.

**Status filtering:** No dedicated `status` parameter is provided. Status is FTS-indexed, so searching `"completed"` will match entities with that status. This satisfies PRD FR-9's status search requirement through the general FTS query mechanism rather than a dedicated filter parameter.

**Rank in output:** Rank (FTS5 relevance score) is used for ordering only and is not displayed in the MCP tool formatted output (R4). It is included in the raw dict returned by the database method for programmatic consumers.

**Error handling:**
- If FTS5 table doesn't exist (pre-migration DB), raise `ValueError("fts_not_available: search requires migration 4")`.
- If MATCH syntax is invalid (malformed query), catch `sqlite3.OperationalError` and raise `ValueError("invalid_search_query: {detail}")`.

**AC-7:** Given entities including `feature:011-reconciliation-mcp-tool` (name: "Reconciliation MCP Tool"), `search_entities("recon")` returns results including that entity (prefix match on name).
**AC-8:** Given entities of type `feature` containing the word "feature" in metadata, `search_entities("feature", entity_type="brainstorm")` returns empty list (type filter excludes non-brainstorm entities).
**AC-9:** Results are ordered by relevance (best match first).
**AC-10:** Empty query returns empty list, not all entities.
**AC-11:** `limit` parameter caps result count; values > 100 are clamped to 100.

### R4: MCP Tool — search_entities

Expose search as an MCP tool in the entity server.

**Tool definition:**
```
Tool: search_entities
Description: Search entities by name, ID, type, or metadata using full-text search.

Parameters:
  query (str, required): Search query. Supports prefix matching by default.
      Examples: "recon" matches "reconciliation", "kanban" matches "kanban-board-view".
  entity_type (str, optional): Filter to specific entity type (backlog, brainstorm, project, feature).
  limit (int, optional, default=20): Maximum results to return (max 100).

Returns: Formatted text listing matching entities with type_id, name (display name), and status.
```

**Output format:** Each result shows `type_id`, `name` (display name), and `status`.
```
Found {n} entities matching "{query}":

1. feature:011-reconciliation-mcp-tool — "Reconciliation MCP Tool" (completed)
2. feature:009-state-engine-mcp-tools — "State Engine MCP Tools" (completed)

{n} results shown (limit: {limit}).
```

If no results: `No entities found matching "{query}".`

**Error handling:** If `search_entities` raises `ValueError`, catch it in the MCP handler and return a formatted error string (e.g., `"Search error: {error message}"`) as the tool result. Do not propagate as an unhandled exception.

**AC-12:** MCP tool `search_entities` is registered and callable.
**AC-13:** Tool returns human-readable formatted results.
**AC-14:** Tool returns "No entities found" for queries with no matches.
**AC-15:** Invalid query syntax returns a clear error message, not a stack trace.

### R5: Schema Migration (Migration 4)

Add as migration 4 in the entity registry migration chain.

**Migration steps:**
1. Create `entities_fts` FTS5 virtual table.
2. Backfill existing entities: read all rows from `entities`, flatten each row's metadata JSON via the Python helper (R2), and insert into `entities_fts`. NULL metadata becomes empty string.
3. Update `schema_version` to 4.

Note: No SQLite triggers are created — FTS sync is handled at the application level per R2.

**AC-16:** Migration is idempotent at the framework level — the migration runner skips it when `schema_version >= 4`. The migration function uses `CREATE VIRTUAL TABLE IF NOT EXISTS` for additional safety.
**AC-17:** Migration preserves all existing data.
**AC-18:** Migration handles NULL metadata gracefully (empty string in FTS).
**AC-19:** Schema version is 4 after migration.

## Scope Boundaries

**In scope:**
- FTS5 virtual table and application-level sync
- search_entities database method
- search_entities MCP tool
- Migration 4 with backfill
- Prefix matching and exact phrase search

**Out of scope:**
- Search UI (future: feature 020 entity list views)
- Faceted search / aggregations
- Fuzzy / typo-tolerant matching (FTS5 doesn't support this natively)
- Search over artifact file contents (only metadata, not file bodies)
- Search history or saved queries
- Weighted field boosting (use default FTS5 ranking)
- Indexing `phase` field (PRD FR-9 mentions search by phase; however, phase data lives in the `workflow_phases` table, not in `entities`. Adding phase to FTS would require a cross-table join at index time. Deferred to a future enhancement if needed.)

## Success Criteria

1. An agent can find entities by partial name without knowing exact type_id.
2. Search results appear within 50ms for a registry with 100+ entities. (Non-functional target — verified by manual profiling during implementation, not by automated AC.)
3. FTS index stays in sync automatically — no manual rebuild needed.
4. Zero impact on existing entity registry operations (register, get, update, delete, lineage).

**AC-20:** All existing entity registry tests (545+) pass after migration and FTS integration (regression gate for Success Criterion 4).
**AC-21:** `search_entities` with FTS5 special characters in query (e.g., `"state(engine"`) does not raise an exception — returns results or empty list.
