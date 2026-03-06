# Design: Entity Export MCP Tool

## Prior Art Research

### Codebase Patterns
- `export_lineage_markdown` is the direct structural template — MCP tool delegates to `_process_*` helper in `server_helpers.py`, which calls a database method and handles file I/O
- `resolve_output_path` provides path containment (returns None if path escapes `artifacts_root`)
- `list_entities(entity_type)` returns `[dict(row)]` with all columns; no ORDER BY
- `VALID_ENTITY_TYPES` tuple at `database.py:421` for entity_type validation
- MCP tools never raise — return error strings
- Module-level globals `_db`, `_artifacts_root` used by all tools

### External Patterns
- Industry standard JSON export envelope: schema version + named array + metadata with count
- Firefox BackupService pattern: global `SCHEMA_VERSION` constant, separate from DB schema version

## Architecture Overview

Three-layer design following the established pattern:

```
MCP Tool Layer          →  export_entities() in entity_server.py
  ↓
Helper Layer            →  _process_export_entities() in server_helpers.py
  ↓
Database Layer          →  export_entities_json() in database.py
```

### Component 1: Database Method (`database.py`)

**`EntityDatabase.export_entities_json()`** — builds the export dict.

Responsibilities:
- Query entities with optional `entity_type` and `status` filters
- Order results by `created_at ASC, type_id ASC`
- Normalize metadata: NULL → `{}`
- Build entity dicts with selected columns (uuid, type_id, entity_type, entity_id, name, status, artifact_path, parent_type_id, created_at, updated_at, metadata)
- Conditionally include `parent_type_id` based on `include_lineage` flag
- Assemble envelope with `schema_version`, `exported_at`, `entity_count`, `filters_applied`
- Return dict (not serialized JSON)

**Entity type validation** is the first operation (when `entity_type` is not None): `self._validate_entity_type(entity_type)` — reuses `VALID_ENTITY_TYPES` tuple. Invalid entity_type raises `ValueError`.

**Timestamp generation:** `exported_at = datetime.now().astimezone().isoformat()` — uses local timezone per spec FR-2 (differs from `_now_iso()` which uses UTC).

**Export schema version** is a module-level constant `EXPORT_SCHEMA_VERSION = 1`, separate from the database schema version (`get_schema_version()`).

### Component 2: Server Helper (`server_helpers.py`)

**`_process_export_entities()`** — orchestrates serialization and file I/O.

Responsibilities:
- Call `db.export_entities_json()` to get the export dict
- Handle `ValueError` from entity_type validation → return error string
- If `output_path` provided:
  - Resolve via `resolve_output_path()` (reuse existing helper)
  - If resolution returns None (path escape) → return error string
  - Create parent directories (`os.makedirs`)
  - Write JSON with UTF-8 encoding and 2-space indentation
  - Catch `OSError` only (intentional narrow scope per spec FR-3)
  - Return confirmation message
- If `output_path` is None:
  - Serialize dict to JSON string and return directly

### Component 3: MCP Tool (`entity_server.py`)

**`export_entities()`** — thin MCP entry point.

Responsibilities:
- `_db` null guard (standard pattern)
- Delegate to `_process_export_entities()`
- Pass `_artifacts_root` for path resolution

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| JSON serialization layer | Helper, not database | Database returns dict for testability; helper handles I/O concerns |
| Error handling scope | `OSError` only in helper | Spec FR-3 explicitly requires narrow scope; differs from `export_lineage_markdown` (broad `Exception`) to surface bugs early |
| entity_type validation | Database layer via `VALID_ENTITY_TYPES` | Reuses existing constant; consistent with `register_entity` validation |
| status validation | None | Spec FR-4: free-form string, unmatched returns empty result set |
| `exported_at` timestamp | `datetime.now().astimezone().isoformat()` (local timezone) | Spec FR-2 requires local timezone; differs from `_now_iso()` which uses UTC |
| `include_lineage` in `filters_applied` | Excluded | Controls output shape (column presence), not row selection; consumers detect via `parent_type_id` key presence |
| SQL query building | Python-conditional (like `list_entities`) | Matches existing codebase pattern; avoids unusual parameterized-NULL approach |
| Error message propagation | Use `str(exc)` from ValueError | Avoids duplicating valid types list; stays consistent with database layer's canonical message. Note: database format is `Invalid entity_type 'xyz'. Must be one of ('backlog', ...)` (repr-quoted, tuple parens) — differs slightly from spec FR-4's plain format but carries identical information. Database format is authoritative. |
| Metadata normalization | Database layer | Spec FR-2: NULL→`{}` in `export_entities_json`, not helper |
| Export schema version | Module constant `EXPORT_SCHEMA_VERSION = 1` | Separate from DB schema version per spec FR-6 |
| Entity ordering | SQL `ORDER BY created_at ASC, type_id ASC` | Spec FR-2: deterministic output |
| parent_type_id inclusion | Conditional on `include_lineage` | Spec FR-5: when False, key is omitted from entity dict |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Large export payloads (1000+ entities) | Low | Medium | Spec NFR-5 requires <5s; SQL query is simple SELECT, no joins needed |
| Metadata JSON parsing errors | Low | Low | Metadata stored as JSON string; use `json.loads` with fallback to `{}` |
| Path traversal attacks | Low | High | Reuse existing `resolve_output_path` which enforces containment |
| Schema version drift | Low | Low | Version is a simple integer constant; bump only when format changes |

## Test Strategy

**Database layer (`test_database.py`):**
- Filter combinations: no filters, entity_type only, status only, both, invalid entity_type
- Metadata normalization: valid JSON, NULL, malformed JSON
- `include_lineage` toggle: True includes parent_type_id, False omits it
- Empty result set: no matching entities returns entity_count 0
- Entity ordering: verify created_at ASC, type_id ASC
- Envelope structure: schema_version, exported_at format, filters_applied

**Helper layer (`test_server_helpers.py`):**
- File write: output_path creates file with valid JSON, parent directories created
- Path escape: `../../etc/passwd` returns error
- OSError handling: permission denied returns error string
- ValueError propagation: invalid entity_type returns error with database message
- No output_path: returns JSON string directly

**MCP tool (`entity_server.py`):**
- Null `_db` guard returns error
- Delegation to helper (integration-level)

## Interfaces

### Database Layer Interface

```python
# database.py — new constant at module level near EXPORT section
EXPORT_SCHEMA_VERSION = 1

# database.py — new method in EntityDatabase class, in Export section
def export_entities_json(
    self,
    entity_type: str | None = None,
    status: str | None = None,
    include_lineage: bool = True,
) -> dict:
    """Export entities as a structured dict with schema version metadata.

    Parameters
    ----------
    entity_type:
        Filter by entity type. Must be one of VALID_ENTITY_TYPES if provided.
        Raises ValueError if invalid.
    status:
        Filter by status string. No validation (free-form).
    include_lineage:
        If True, include parent_type_id in each entity dict.
        If False, omit parent_type_id.

    Returns
    -------
    dict
        Export envelope: {schema_version, exported_at, entity_count,
        filters_applied, entities: [...]}.
    """
```

**Method pseudocode:**
```python
def export_entities_json(self, entity_type=None, status=None, include_lineage=True):
    # 1. Validate entity_type (only when provided)
    if entity_type is not None:
        self._validate_entity_type(entity_type)

    # 2. Build query conditionally (matches list_entities pattern)
    query = "SELECT uuid, type_id, entity_type, entity_id, name, status, "
            "artifact_path, parent_type_id, created_at, updated_at, metadata "
            "FROM entities"
    conditions, params = [], []
    if entity_type is not None:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at ASC, type_id ASC"

    rows = self._conn.execute(query, params).fetchall()

    # 3. Build entity dicts with metadata normalization
    entities = []
    for row in rows:
        try:
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        except (json.JSONDecodeError, ValueError):
            metadata = {}
        entity = {
            "uuid": row["uuid"],
            "type_id": row["type_id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "name": row["name"],
            "status": row["status"],
            "artifact_path": row["artifact_path"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "metadata": metadata,
        }
        if include_lineage:
            entity["parent_type_id"] = row["parent_type_id"]
        entities.append(entity)

    # 4. Assemble envelope
    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.now().astimezone().isoformat(),
        "entity_count": len(entities),
        "filters_applied": {
            "entity_type": entity_type,
            "status": status,
        },
        "entities": entities,
    }
```

### Server Helper Interface

```python
# server_helpers.py — new function
def _process_export_entities(
    db,
    entity_type: str | None,
    status: str | None,
    output_path: str | None,
    include_lineage: bool,
    artifacts_root: str,
) -> str:
    """Export entities as JSON, optionally writing to a file.

    Returns
    -------
    str
        JSON string, file-write confirmation, or error message.
        Never raises exceptions.
    """
```

**Logic flow:**
```python
def _process_export_entities(db, entity_type, status, output_path, include_lineage, artifacts_root):
    try:
        data = db.export_entities_json(entity_type, status, include_lineage)
    except ValueError as exc:
        return f"Error: {exc}"   # propagates database layer's canonical message

    if output_path is not None:
        resolved = resolve_output_path(output_path, artifacts_root)
        if resolved is None:
            return "Error: output path escapes artifacts root"
        try:
            parent_dir = os.path.dirname(resolved)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(resolved, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return f"Exported {data['entity_count']} entities to {resolved}"
        except OSError as exc:
            return f"Error writing export: {exc}"

    return json.dumps(data, indent=2, ensure_ascii=False)
```

### MCP Tool Interface

```python
# entity_server.py — new tool
@mcp.tool()
async def export_entities(
    entity_type: str | None = None,
    status: str | None = None,
    output_path: str | None = None,
    include_lineage: bool = True,
) -> str:
    """Export all entities (or a filtered subset) as structured JSON.

    Parameters
    ----------
    entity_type:
        Filter by type (backlog, brainstorm, project, feature).
    status:
        Filter by status string.
    output_path:
        Write to file; if None, return as string.
    include_lineage:
        Include parent/child relationships (default True).

    Returns JSON string or file-write confirmation.
    """
    if _db is None:
        return "Error: database not initialized (server not started)"
    return _process_export_entities(
        _db, entity_type, status, output_path, include_lineage, _artifacts_root
    )
```

### Import Changes

**`entity_server.py`** — add `_process_export_entities` to the import from `server_helpers`:
```python
from entity_registry.server_helpers import (
    _process_export_lineage_markdown,
    _process_export_entities,       # new
    _process_get_lineage,
    _process_register_entity,
    parse_metadata,
)
```

**`server_helpers.py`** — `json` is already imported at line 8; no new import needed.

**`database.py`** — `datetime` is already imported at line 9 (`from datetime import datetime, timezone`); no new import needed. The method uses `datetime.now().astimezone()` (local timezone) rather than the existing `_now_iso()` helper (UTC) — intentional per spec FR-2.

### File Change Summary

| File | Change |
|------|--------|
| `plugins/iflow/hooks/lib/entity_registry/database.py` | Add `EXPORT_SCHEMA_VERSION` constant, add `export_entities_json()` method |
| `plugins/iflow/hooks/lib/entity_registry/server_helpers.py` | Add `_process_export_entities()` function |
| `plugins/iflow/mcp/entity_server.py` | Add `export_entities` MCP tool, update import |
| `plugins/iflow/hooks/lib/entity_registry/test_database.py` | Tests for `export_entities_json()` |
| `plugins/iflow/hooks/lib/entity_registry/test_server_helpers.py` | Tests for `_process_export_entities()` |
