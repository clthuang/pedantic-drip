# Specification: Entity Export MCP Tool

## Overview

Add an `export_entities` MCP tool to the entity registry server that exports all entities (or a filtered subset) as structured JSON with schema version metadata. This enables backup, restore, migration verification, and cross-project entity transfer.

The existing `export_lineage_markdown` tool provides human-readable markdown trees but lacks machine-readable structure, schema versioning, and relationship preservation needed for backup/restore workflows.

> **Note:** The feature directory name contains "context" for historical reasons (from PRD UC-3 naming). The tool itself is named `export_entities` to accurately reflect its behavior.

## Requirements

### FR-1: export_entities MCP Tool

A new `export_entities` tool on the entity-registry MCP server with the following signature:

```
export_entities(
    entity_type: str | None = None,   # Filter by type (backlog, brainstorm, project, feature)
    status: str | None = None,        # Filter by status
    output_path: str | None = None,   # Write to file; if None, return as string
    include_lineage: bool = True       # Include parent/child relationships
) -> str
```

**Returns:** JSON string containing all matching entities with schema version, or confirmation message if `output_path` is provided.

### FR-2: Export JSON Schema

Each entity in the export includes all database columns needed for faithful backup/restore. The `uuid` field is the database primary key and is required for identity preservation across exports. The `parent_type_id` is included (rather than `parent_uuid`) because it is the human-readable relationship identifier used by all other MCP tools; `parent_uuid` is an internal FK that can be resolved from `parent_type_id` during import.

The export format is:

```json
{
  "schema_version": 1,
  "exported_at": "2026-03-07T03:00:00+08:00",
  "entity_count": 42,
  "filters_applied": {
    "entity_type": null,
    "status": null
  },
  "entities": [
    {
      "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "type_id": "feature:012-full-text-entity-search-mcp-to",
      "entity_type": "feature",
      "entity_id": "012-full-text-entity-search-mcp-to",
      "name": "full-text-entity-search-mcp-to",
      "status": "completed",
      "artifact_path": "docs/features/012-full-text-entity-search-mcp-to/",
      "parent_type_id": "project:P001-iflow-arch-evolution",
      "created_at": "2026-03-01T16:27:59+08:00",
      "updated_at": "2026-03-07T03:05:00+08:00",
      "metadata": {}
    }
  ]
}
```

**Column selection rationale:**
- `uuid`: Included — primary key, required for identity preservation in backup/restore
- `type_id`, `entity_type`, `entity_id`: Included — core identity fields
- `name`, `status`, `artifact_path`: Included — mutable fields needed for restore
- `parent_type_id`: Included when `include_lineage=True` — human-readable relationship key
- `parent_uuid`: Excluded — internal FK derivable from `parent_type_id`; including both would create redundancy and sync risk
- `created_at`, `updated_at`: Included — temporal audit fields
- `metadata`: Included — always serialized as `{}` when NULL in database (never omitted, never `null`). The NULL-to-`{}` normalization is performed in `export_entities_json` (database layer), not the MCP tool layer

**Timestamps:** The `exported_at` field uses ISO 8601 format with timezone offset (local timezone of the server). Entity timestamps (`created_at`, `updated_at`) are preserved as stored in the database.

**Entity ordering:** Entities are ordered by `created_at` ASC, then `type_id` ASC for deterministic output.

### FR-3: File Output

When `output_path` is provided:
- Relative paths resolved against `artifacts_root` (consistent with `export_lineage_markdown`)
- **Path containment:** The resolved path must be within `artifacts_root`. Paths that escape via `..` traversal are rejected with error: `"Error: output path escapes artifacts root"` (uses existing `resolve_output_path` helper which enforces this)
- Parent directories created automatically (`os.makedirs`)
- File written with UTF-8 encoding and 2-space JSON indentation
- Returns confirmation message: `"Exported {n} entities to {resolved_path}"`

**Error handling for file I/O:**
- Catch `OSError` (covers `PermissionError`, disk full, etc.) and return `"Error writing export: {error message}"`
- Do not catch broader `Exception` — let unexpected errors (e.g., serialization bugs) propagate as unhandled for debugging
- This intentionally differs from the existing `export_lineage_markdown` pattern (which catches all `Exception`); narrower error handling is preferred here to surface implementation bugs early

When `output_path` is None:
- Returns the JSON string directly (for programmatic consumption)

### FR-4: Filtering

- `entity_type` filter: exact match on entity_type column (backlog, brainstorm, project, feature)
- `status` filter: exact match on status column (free-form string, no validation — matches whatever is stored)
- Both filters can be combined (AND logic)
- Invalid `entity_type` returns error: `"Invalid entity_type: {value}. Must be one of: backlog, brainstorm, project, feature"`
- **Status is not validated** because status values are free-form strings (e.g., "active", "completed", "promoted", "abandoned"). An unmatched status simply returns an empty result set — this is consistent with how `list_entities` and `search_entities` handle status filtering.
- No filter = export all entities

### FR-5: Database Layer Method

Add `export_entities_json` method to `EntityDatabase`:

```python
def export_entities_json(
    self,
    entity_type: str | None = None,
    status: str | None = None,
    include_lineage: bool = True,
) -> dict
```

Returns the export dict (not serialized). The MCP tool handles JSON serialization and file I/O.

When `include_lineage` is True, each entity includes its `parent_type_id`. When False, `parent_type_id` is omitted from each entity dict (useful for flat exports).

### FR-6: Schema Version

The `schema_version` field is an integer starting at 1. It reflects the export format version, not the database schema version. This allows future changes to the export format (adding fields, changing structure) while maintaining backward compatibility for import tools.

## Success Criteria

1. `export_entities()` with no args returns JSON string containing all entities with `schema_version: 1`
2. `export_entities(entity_type="feature")` returns only feature entities
3. `export_entities(status="completed")` returns only completed entities
4. `export_entities(entity_type="feature", status="active")` returns only active features
5. `export_entities(output_path="backup/entities.json")` writes file and returns confirmation
6. Empty database returns valid JSON with `entity_count: 0` and empty `entities` array
7. Export completes within 5 seconds for up to 1000 entities (NFR-5 from PRD; verified via unit test with bulk inserts)
8. Invalid `entity_type` returns descriptive error message
9. `export_entities(include_lineage=False)` omits `parent_type_id` from entity dicts
10. Output file parent directories are created if they don't exist

## Acceptance Criteria

- AC-1: **Given** the entity-registry MCP server is running, **when** `export_entities` is called with no arguments, **then** it returns a valid JSON string containing all entities with `schema_version: 1` and `entity_count` matching the total entity count.
- AC-2: **Given** entities of types backlog, brainstorm, project, and feature exist, **when** `export_entities(entity_type="feature")` is called, **then** only entities with `entity_type == "feature"` appear in the result.
- AC-3: **Given** entities with various statuses exist, **when** `export_entities(entity_type="feature", status="active")` is called, **then** only entities matching both filters appear (AND logic).
- AC-4: **Given** an `output_path` is provided, **when** `export_entities(output_path="backup/entities.json")` is called, **then** the file is created (with parent directories), contains valid JSON, and the tool returns `"Exported {n} entities to {resolved_path}"`.
- AC-5: **Given** existing MCP tools are registered, **when** `export_entities` is added, **then** all existing tools (`register_entity`, `get_entity`, `search_entities`, etc.) continue to function identically.
- AC-6: **Given** a path like `"../../etc/passwd"` is provided as `output_path`, **when** `export_entities` is called, **then** it returns an error about path escaping artifacts root.
- AC-7: **Given** `include_lineage=False`, **when** `export_entities` is called, **then** entity dicts do not contain `parent_type_id`.
- AC-8: **Given** entities exist with NULL metadata in the database, **when** exported, **then** metadata appears as `{}` (empty object), never `null` or omitted.
- AC-9: **Given** an empty database, **when** `export_entities` is called, **then** it returns valid JSON with `entity_count: 0` and an empty `entities` array.
- AC-10: **Given** each entity has a `uuid` field, **when** exported, **then** the `uuid` appears in each entity dict.
- AC-11: **Given** a database containing 1000 entities, **when** `export_entities()` is called with no arguments, **then** it returns within 5 seconds (NFR-5).

## Scope Boundaries

### In Scope
- Export to JSON format
- Filtering by entity_type and status
- File output with path resolution and containment check
- Schema version metadata
- UUID inclusion for backup identity preservation

### Out of Scope
- Import/restore from JSON (future feature)
- Export to formats other than JSON — PRD UC-3 includes a `format` parameter but this feature implements JSON-only export as the initial version; additional formats can be added in a future feature
- Streaming export for very large datasets
- Incremental/differential export
- Export of workflow_phases table data — PRD UC-3 mentions "phase state" but phase data lives in `.meta.json` files and the `workflow_phases` table belongs to Feature 008 (WorkflowStateEngine). Entity-level export is the correct initial scope; phase export can be added once the workflow engine features are complete

## Dependencies

- Feature 001 (entity UUID primary key migration) — completed
- Existing entity registry database layer (`database.py`)
- Existing entity MCP server (`entity_server.py`)
- Existing `resolve_output_path` helper in `server_helpers.py`
