# MCP Tool Capability Notes for show-status Migration

## Tool Analysis

### 1. `export_entities` (entity-registry server)

**Signature:**
```
export_entities(
    entity_type: str | None = None,   # "feature", "brainstorm", "project", "backlog"
    status: str | None = None,        # single status filter (exact match)
    output_path: str | None = None,   # write to file; None = return as string
    include_lineage: bool = True      # include parent_type_id
)
```

**Returns:** JSON envelope:
```json
{
  "schema_version": "...",
  "exported_at": "ISO-8601",
  "entity_count": 42,
  "filters_applied": {"entity_type": "feature", "status": null},
  "entities": [
    {
      "uuid": "...",
      "type_id": "feature:042-mcp-bootstrap",
      "entity_type": "feature",
      "entity_id": "042-mcp-bootstrap",
      "name": "MCP Bootstrap",
      "status": "active",
      "artifact_path": "docs/features/042-mcp-bootstrap/",
      "created_at": "ISO-8601",
      "updated_at": "ISO-8601",
      "metadata": {"project_id": "P001", ...},
      "parent_type_id": "project:P001-crypto" | null
    }
  ]
}
```

**Filter limitations:**
- `status` accepts only a single value (not NOT IN or multi-value)
- Client-side filtering required for exclusions (e.g., exclude completed, exclude promoted)
- `entity_type` accepts only one type per call

**Use for show-status:** Primary data source for Section 1.5, Section 2, Section 3.

### 2. `search_entities` (entity-registry server)

**Signature:**
```
search_entities(
    query: str,           # REQUIRED — search string (prefix-matched)
    entity_type: str | None = None,
    limit: int = 20       # max 100
)
```

**Returns:** Formatted text (not JSON):
```
Found 3 entities matching "auth":

1. feature:021-auth — "Auth Feature" (active)
2. feature:033-auth-refactor — "Auth Refactor" (completed)
...

3 results shown (limit: 20).
```

**Limitation:** Requires a `query` string — cannot list all entities. Returns formatted text, not structured JSON. Not suitable for "list all features" use case.

**Decision: NOT used for show-status.** `export_entities` is the correct tool for listing/filtering entities.

### 3. `list_features_by_status` (workflow-engine server)

**Signature:**
```
list_features_by_status(status: str)
```

**Returns:** JSON array of workflow state objects:
```json
[
  {
    "feature_type_id": "feature:042-mcp-bootstrap",
    "current_phase": "implement",
    "last_completed_phase": "create-tasks",
    "completed_phases": ["brainstorm", "specify", "design", "create-plan", "create-tasks"],
    "mode": "standard",
    "source": "db",
    "degraded": false
  }
]
```

**Limitation:** Filters by entity status (single value), not workflow phase. Useful for targeted queries but `export_entities` already provides status. Could be redundant.

**Decision: NOT used for show-status.** `export_entities` + `get_phase` covers all needs. Using `list_features_by_status` would add a dependency on the workflow-engine server for data that entity-registry already provides.

### 4. `get_phase` (workflow-engine server)

**Signature:**
```
get_phase(feature_type_id: str)
```

**Returns:** JSON workflow state object (same shape as `_serialize_state`):
```json
{
  "feature_type_id": "feature:042-mcp-bootstrap",
  "current_phase": "implement",
  "last_completed_phase": "create-tasks",
  "completed_phases": [...],
  "mode": "standard",
  "source": "db",
  "degraded": false
}
```

On error: `{"error": true, "code": "feature_not_found", ...}`

**Decision: Used for active features** to resolve current phase (existing pattern in show-status).

## Tool-to-Section Mapping

| Section | MCP Tool | Filter Strategy |
|---------|----------|-----------------|
| 1.5 Project Features | `export_entities(entity_type="feature")` | Client-side: filter by `metadata.project_id` present/non-null |
| 1.5 Active phase | `get_phase(feature_type_id=...)` | Per active feature |
| 2 Open Features | Same `export_entities` result | Client-side: exclude `status=="completed"`, exclude those with `project_id` |
| 2 Active phase | `get_phase(feature_type_id=...)` | Per active feature |
| 3 Open Brainstorms | `export_entities(entity_type="brainstorm")` | Client-side: exclude `status=="promoted"` AND `status=="archived"` |

## Key Insight

A single `export_entities(entity_type="feature")` call provides data for both Section 1.5 and Section 2. A second `export_entities(entity_type="brainstorm")` call covers Section 3. This minimizes MCP round-trips to:
- 1x `export_entities` for features
- 1x `export_entities` for brainstorms
- Nx `get_phase` for active features only
