# Design: MCP Audit — Token Efficiency & Engineering Excellence

## Prior Art Research

Research performed during specify phase (3 parallel MCP server audits). Key findings:
- Entity registry: `server_helpers` pattern established for 5/8 tools. `export_entities` most expensive (15-30k tokens).
- Workflow engine: Clean 3-layer separation (MCP handler → `_process_*` → engine/library). 5 tools have inline logic with `db._conn` private access.
- Memory: Already well-structured — CLI backend exists, MCP tools are thin wrappers. `search_memory` lacks category filter.

## Architecture Overview

This feature modifies existing files only — no new modules except `entity_lifecycle.py` and `feature_lifecycle.py`. The architecture is "tighten existing patterns" not "introduce new patterns."

### Change Map

```
Phase 1 (Token Efficiency):
  entity_server.py          — export_entities fields param, get_entity compact, UUID removal
  workflow_state_server.py  — _serialize_state drop source/completed_phases, reconcile summary
  memory_server.py          — search_memory category filter + brief mode

Phase 2 (Library Extraction):
  hooks/lib/entity_registry/
    entity_lifecycle.py     [NEW] — init_entity_workflow, transition_entity_phase
    database.py             [MOD] — add upsert_workflow_phase()
    server_helpers.py       [MOD] — add _process_set_parent()

  hooks/lib/workflow_engine/
    feature_lifecycle.py    [NEW] — init_feature_state, init_project_state, activate_feature

  entity_server.py          [MOD] — set_parent delegates to server_helpers
  workflow_state_server.py  [MOD] — 5 tools delegate to new library modules
```

## Components

### P1-C1: export_entities Field Projection

**File:** `plugins/iflow/mcp/entity_server.py` → `server_helpers._process_export_entities`

**Change:** Add `fields` parameter to `export_entities` MCP tool and `_process_export_entities`.

```python
# MCP tool signature change
@server.tool()
async def export_entities(entity_type=None, status=None, output_path=None,
                          include_lineage=True, fields=None):  # NEW param

# In _process_export_entities (server_helpers.py):
# Actual signature includes artifacts_root — add fields param
def _process_export_entities(db, entity_type, status, output_path, include_lineage, artifacts_root, fields=None):
    data = db.export_entities_json(entity_type, status, include_lineage)  # returns dict

    if fields is not None:
        field_set = set(f.strip() for f in fields.split(","))
        data["entities"] = [
            {k: v for k, v in entity.items() if k in field_set}
            for entity in data["entities"]
        ]

    # Always use compact JSON for inline responses
    if output_path is None:
        return json.dumps(data, separators=(',', ':'))
    ...
```

**Default behavior:** When `fields=None`, full data returned (backward compatible). Callers opt-in to projection.

### P1-C2: get_entity Compact Output

**File:** `plugins/iflow/mcp/entity_server.py`

**Change:** Drop `uuid`, `entity_id`, `parent_uuid` from response. Use compact JSON.

```python
# Current (inline, line 189-192):
entity = db.get_entity(type_id)
return json.dumps(entity, indent=2)

# New:
entity = db.get_entity(type_id)
if entity is None:
    return f"Entity not found: {type_id}"
# Drop internal fields
for key in ("uuid", "entity_id", "parent_uuid"):
    entity.pop(key, None)
return json.dumps(entity, separators=(',', ':'))
```

### P1-C3: UUID Removal from Confirmations

**Files:** `entity_server.py` (register_entity, update_entity), `server_helpers.py` (_process_register_entity)

**Change:** Return `type_id` only, drop UUID from messages.

```python
# register_entity — in server_helpers._process_register_entity:
# Before: f"Registered entity: {uuid} ({type_id})"
# After:  f"Registered: {type_id}"

# update_entity — in entity_server.py:
# Before: f"Updated entity: {uuid} ({type_id})"
# After:  f"Updated: {type_id}"

# set_parent — in entity_server.py (current inline):
# Before: f"Set parent: {child_uuid} ({type_id}) → {parent['uuid']} ({parent_type_id})"
# After:  f"Parent set: {type_id} → {parent_type_id}"
```

### P1-C4: _serialize_state Cleanup

**File:** `plugins/iflow/mcp/workflow_state_server.py`

**Change:** Drop `source` and `completed_phases` from `_serialize_state()`.

```python
def _serialize_state(state: FeatureWorkflowState) -> dict:
    return {
        "feature_type_id": state.feature_type_id,
        "current_phase": state.current_phase,
        "last_completed_phase": state.last_completed_phase,
        # "completed_phases" REMOVED — derived array, callers don't need it
        "mode": state.mode,
        # "source" REMOVED — internal detail, callers use "degraded" instead
        # Note: FeatureWorkflowState has no .degraded attr — compute from .source
        "degraded": state.source == "meta_json_fallback",
    }
```

**Impact:** Affects get_phase, transition_phase, complete_phase, list_features_by_phase, list_features_by_status responses. All become more compact.

### P1-C5: reconcile_status Summary Mode

**File:** `plugins/iflow/mcp/workflow_state_server.py`

**Change:** Add `summary_only` param to `reconcile_status` MCP tool.

```python
@server.tool()
async def reconcile_status(summary_only: bool = False):
    return _process_reconcile_status(engine, db, _artifacts_root, summary_only)

def _process_reconcile_status(engine, db, artifacts_root, summary_only=False):
    workflow_reports = check_workflow_drift(engine, db, artifacts_root)
    frontmatter_reports = scan_all(db, artifacts_root)

    if summary_only:
        wf_drift = sum(1 for r in workflow_reports if r.status != "in_sync")
        fm_drift = sum(1 for r in frontmatter_reports if r.status != "in_sync")
        return json.dumps({
            "healthy": wf_drift == 0 and fm_drift == 0,
            "workflow_drift_count": wf_drift,
            "frontmatter_drift_count": fm_drift,
        })

    # ... existing full report logic
```

### P1-C6: reconcile_frontmatter Filter In-Sync

**File:** `plugins/iflow/mcp/workflow_state_server.py`

**Change:** Filter out `in_sync` reports from default output.

```python
def _process_reconcile_frontmatter(db, artifacts_root, feature_type_id=None):
    if feature_type_id:
        reports = [detect_drift(db, feature_type_id, artifacts_root)]
    else:
        reports = scan_all(db, artifacts_root)

    # Filter out in_sync reports (only show drift)
    drifted = [r for r in reports if r.status != "in_sync"]

    return json.dumps({
        "total_scanned": len(reports),
        "drifted_count": len(drifted),
        "reports": [_serialize_drift_report(r) for r in drifted],
    })
```

### P1-C7: search_memory Category Filter + Brief Mode

**File:** `plugins/iflow/mcp/memory_server.py`

**Change:** Add `category` and `brief` params.

```python
@server.tool()
async def search_memory(query: str, limit: int = 10,
                        category: str | None = None,  # NEW
                        brief: bool = False):          # NEW
    return _process_search_memory(db, query, limit, category, brief, ...)

def _process_search_memory(db, query, limit, category, brief, ...):
    # ... existing retrieval pipeline ...

    # Category filter BEFORE ranking to ensure limit returns full requested count
    if category:
        candidates = [e for e in candidates if e.get("category") == category]

    selected = ranking_engine.rank(candidates, limit)

    if brief:
        lines = [f"Found {len(selected)} entries:"]
        for e in selected:
            lines.append(f"- {e['name']} ({e.get('confidence', 'unknown')})")
        return "\n".join(lines)

    # ... existing full format ...
```

### P2-C1: entity_lifecycle.py — Entity Workflow State Machine

**File:** `plugins/iflow/hooks/lib/entity_registry/entity_lifecycle.py` [NEW]

**Purpose:** Extract `init_entity_workflow` and `transition_entity_phase` logic from `workflow_state_server.py` (lines 946-1094). Preserves ALL existing behavior including transition validation, forward/backward semantics, entities.status updates, and commit.

```python
"""Entity lifecycle state machine for brainstorm/backlog workflow phases.

Extracted from workflow_state_server.py _process_init_entity_workflow (line 946)
and _process_transition_entity_phase (line 1012). Preserves exact behavior.
"""
import json
from entity_registry.database import EntityDatabase

# Exact copy from workflow_state_server.py lines 50-87
ENTITY_MACHINES: dict[str, dict] = {
    "brainstorm": {
        "transitions": {
            "draft": ["reviewing", "abandoned"],
            "reviewing": ["promoted", "draft", "abandoned"],
        },
        "columns": {
            "draft": "wip",
            "reviewing": "agent_review",
            "promoted": "completed",
            "abandoned": "completed",
        },
        "forward": {
            ("draft", "reviewing"),
            ("reviewing", "promoted"),
            ("reviewing", "abandoned"),
            ("draft", "abandoned"),
        },
    },
    "backlog": {
        "transitions": {
            "open": ["triaged", "dropped"],
            "triaged": ["promoted", "dropped"],
        },
        "columns": {
            "open": "backlog",
            "triaged": "prioritised",
            "promoted": "completed",
            "dropped": "completed",
        },
        "forward": {
            ("open", "triaged"),
            ("triaged", "promoted"),
            ("triaged", "dropped"),
            ("open", "dropped"),
        },
    },
}


def init_entity_workflow(db: EntityDatabase, type_id: str,
                         workflow_phase: str, kanban_column: str) -> dict:
    """Create workflow_phases row for an entity. Idempotent.

    Preserves all validation from _process_init_entity_workflow:
    - Entity must exist in registry
    - feature/project types rejected (they use WorkflowStateEngine)
    - Phase/column validated against ENTITY_MACHINES when applicable
    - Idempotent: existing row returns with created=False
    """
    # 1. Validate entity exists
    entity = db.get_entity(type_id)
    if entity is None:
        raise ValueError(f"entity_not_found: {type_id}")

    # 1b. Reject entity types with their own workflow management
    if ":" in type_id:
        entity_type = type_id.split(":", 1)[0]
        if entity_type in ("feature", "project"):
            raise ValueError(
                f"invalid_entity_type: {entity_type} entities use the feature workflow engine"
            )
        if entity_type in ENTITY_MACHINES:
            machine = ENTITY_MACHINES[entity_type]
            if workflow_phase not in machine["columns"]:
                raise ValueError(
                    f"invalid_transition: {workflow_phase} is not a valid phase for {entity_type}"
                )
            expected_column = machine["columns"][workflow_phase]
            if kanban_column != expected_column:
                raise ValueError(
                    f"invalid_transition: kanban_column {kanban_column} does not match "
                    f"expected {expected_column} for phase {workflow_phase}"
                )

    # 2. Check idempotency
    existing = db.get_workflow_phase(type_id)
    if existing:
        return {"created": False, "type_id": type_id,
                "workflow_phase": existing["workflow_phase"],
                "kanban_column": existing["kanban_column"],
                "reason": "already_exists"}

    # 3. Insert workflow_phases row via public API
    db.upsert_workflow_phase(type_id,
                             workflow_phase=workflow_phase,
                             kanban_column=kanban_column)
    return {"created": True, "type_id": type_id,
            "workflow_phase": workflow_phase,
            "kanban_column": kanban_column}


def transition_entity_phase(db: EntityDatabase, type_id: str,
                            target_phase: str) -> dict:
    """Transition a brainstorm/backlog entity to a new lifecycle phase.

    Preserves ALL behavior from _process_transition_entity_phase:
    - Transition graph validation against ENTITY_MACHINES
    - Forward/backward distinction via 'forward' set
    - entities.status update via db.update_entity()
    - workflow_phases update: forward sets last_completed_phase, backward preserves it
    """
    # 1. Parse entity_type
    if ":" not in type_id:
        raise ValueError(f"invalid_entity_type: malformed type_id: {type_id}")
    entity_type = type_id.split(":", 1)[0]

    # 2. Validate entity_type has a state machine
    if entity_type not in ENTITY_MACHINES:
        raise ValueError(
            f"invalid_entity_type: {entity_type} — only brainstorm and backlog supported"
        )

    # 3. Validate entity exists
    entity = db.get_entity(type_id)
    if entity is None:
        raise ValueError(f"entity_not_found: {type_id}")

    # 4. Get current phase via public API
    current_row = db.get_workflow_phase(type_id)
    if current_row is None:
        raise ValueError(f"entity_not_found: no workflow_phases row for {type_id}")
    current_phase = current_row.get("workflow_phase")
    if current_phase is None:
        raise ValueError(
            f"invalid_transition: {type_id} has NULL current_phase — "
            "call init_entity_workflow first"
        )

    # 5. Validate transition against graph
    machine = ENTITY_MACHINES[entity_type]
    valid_targets = machine["transitions"].get(current_phase, [])
    if target_phase not in valid_targets:
        raise ValueError(
            f"invalid_transition: cannot transition {entity_type} from "
            f"{current_phase} to {target_phase}"
        )

    # 6. Look up target kanban column
    kanban_column = machine["columns"][target_phase]

    # 7. Determine if forward transition (for last_completed_phase)
    is_forward = (current_phase, target_phase) in machine["forward"]

    # 8. Update entities.status via public API
    db.update_entity(type_id, status=target_phase)

    # 9. Update workflow_phases via public API
    update_kwargs = {
        "workflow_phase": target_phase,
        "kanban_column": kanban_column,
    }
    if is_forward:
        update_kwargs["last_completed_phase"] = current_phase

    db.update_workflow_phase(type_id, **update_kwargs)

    return {"transitioned": True, "type_id": type_id,
            "from_phase": current_phase, "to_phase": target_phase,
            "kanban_column": kanban_column}
```

**Key differences from design v1:**
- ENTITY_MACHINES uses the actual schema (`transitions` graph, `columns`, `forward` set) — not the simplified `phases`/`kanban_map`
- `transition_entity_phase` validates transitions against the graph (not "any phase")
- Forward/backward distinction preserved for `last_completed_phase` updates
- `entities.status` updated via `db.update_entity()` (not `db._conn`)
- `workflow_phases` updated via `db.update_workflow_phase()` (not raw SQL)
- No `db._conn` access anywhere — all through public API

### P2-C2: EntityDatabase.upsert_workflow_phase()

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`

**Change:** Add public `upsert_workflow_phase()` method to replace inline `INSERT OR IGNORE` + `UPDATE` SQL.

```python
def upsert_workflow_phase(self, type_id: str, **kwargs) -> None:
    """Insert or update a workflow_phases row.

    Uses INSERT OR IGNORE + UPDATE to handle both new and existing rows.
    kwargs: workflow_phase, kanban_column, last_completed_phase, etc.
    """
    ALLOWED_COLUMNS = {
        "workflow_phase", "kanban_column", "last_completed_phase",
        "mode", "backward_transition_reason", "updated_at",
    }
    invalid = set(kwargs) - ALLOWED_COLUMNS
    if invalid:
        raise ValueError(f"Invalid workflow_phases columns: {invalid}")

    now = self._now_iso()

    # Atomic INSERT with all fields (no partial row risk)
    wf = kwargs.get("workflow_phase")
    kc = kwargs.get("kanban_column")
    self._conn.execute(
        "INSERT OR IGNORE INTO workflow_phases "
        "(type_id, workflow_phase, kanban_column, updated_at) VALUES (?, ?, ?, ?)",
        (type_id, wf, kc, now),
    )

    # UPDATE with provided fields (handles existing row case)
    if kwargs:
        kwargs["updated_at"] = now
        set_parts = []
        params = []
        for key, value in kwargs.items():
            set_parts.append(f"{key} = ?")
            params.append(value)
        params.append(type_id)
        self._conn.execute(
            f"UPDATE workflow_phases SET {', '.join(set_parts)} WHERE type_id = ?",
            params,
        )
    self._conn.commit()
```

### P2-C3: feature_lifecycle.py — Feature State Initialization

**File:** `plugins/iflow/hooks/lib/workflow_engine/feature_lifecycle.py` [NEW]

**Purpose:** Extract `init_feature_state`, `init_project_state`, `activate_feature` business logic.

```python
"""Feature and project state initialization and activation.

Mechanical extraction from workflow_state_server.py _process_init_feature_state
(~120 lines), _process_init_project_state (~70 lines), _process_activate_feature
(~40 lines). ALL existing behavior preserved exactly — no logic changes.
"""
from entity_registry.database import EntityDatabase
from workflow_engine.engine import WorkflowStateEngine


def init_feature_state(db: EntityDatabase, engine: WorkflowStateEngine,
                       artifacts_root: str,
                       feature_dir: str, feature_id: str, slug: str,
                       mode: str, branch: str,
                       brainstorm_source: str | None = None,
                       backlog_source: str | None = None,
                       status: str = "active") -> dict:
    """Create feature entity + workflow state + .meta.json. Idempotent.

    Returns: {"created": bool, "feature_type_id": str, "status": str,
              "meta_json_path": str, "projection_warning": str | None}

    Preserves: entity registration, kanban fixup for active/planned,
    retry path (preserves phase_timing on re-init), .meta.json projection.
    Error handling: raises ValueError on invalid input, returns error dict
    on entity-not-found after registration.
    """
    # Extracted from _process_init_feature_state — preserve all logic
    ...


def init_project_state(db: EntityDatabase, engine: WorkflowStateEngine | None,
                       artifacts_root: str,
                       project_dir: str, project_id: str, slug: str,
                       branch: str,
                       brainstorm_source: str | None = None,
                       status: str = "active") -> dict:
    """Create project entity + .meta.json.

    Returns: {"created": bool, "project_type_id": str, "status": str,
              "meta_json_path": str}

    Preserves: entity registration, .meta.json schema construction.
    """
    # Extracted from _process_init_project_state — preserve all logic
    ...


def activate_feature(db: EntityDatabase, engine: WorkflowStateEngine,
                     artifacts_root: str,
                     feature_type_id: str) -> dict:
    """Transition a planned feature to active status.

    Returns: {"activated": bool, "feature_type_id": str, "status": str,
              "kanban_column": str, "projection_warning": str | None}

    Validates: current status must be "planned". Rejects completed/abandoned/active.
    Updates: entities.status → "active", kanban_column → "wip",
    projects .meta.json via _project_meta_json.
    """
    # Extracted from _process_activate_feature — preserve all logic
    ...
```

**Implementation note:** These extractions are mechanical — copy the function body from the `_process_*` function, replace `_db`/`_engine`/`_artifacts_root` globals with function parameters. No logic changes. The `_project_meta_json` call stays in the MCP server (called after the library function returns) since it depends on the server's internal `_project_meta_json` helper. Alternatively, pass `_project_meta_json` as a callback parameter.

### P2-C4: set_parent Extraction

**File:** `plugins/iflow/hooks/lib/entity_registry/server_helpers.py`

**Change:** Add `_process_set_parent()` to match pattern of other entity tools.

```python
def _process_set_parent(db, type_id, parent_type_id):
    db.set_parent(type_id, parent_type_id)
    return f"Parent set: {type_id} → {parent_type_id}"
```

MCP handler becomes:
```python
@server.tool()
async def set_parent(type_id, parent_type_id):
    if _db is None:
        return "Entity registry not initialized"
    return server_helpers._process_set_parent(_db, type_id, parent_type_id)
```

### P2-C5: reconcile_apply Direction Removal

**File:** `plugins/iflow/mcp/workflow_state_server.py`

**Change:** Remove `direction` param from MCP tool. Hardcode in handler.

```python
# Before:
@server.tool()
async def reconcile_apply(feature_type_id=None, direction="meta_json_to_db", dry_run=False):

# After:
@server.tool()
async def reconcile_apply(feature_type_id=None, dry_run=False):
    return _process_reconcile_apply(engine, db, _artifacts_root,
                                    feature_type_id, "meta_json_to_db", dry_run)
```

Library function keeps the param unchanged.

## Technical Decisions

### TD-1: Field projection at serialization, not at DB query
**Decision:** `export_entities` filters fields after `db.export_entities_json()` returns, not with SQL projection.
**Rationale:** The DB method returns full rows for lineage traversal. Filtering at serialization is simpler and avoids changing the DB layer. The field filtering is O(n) in entity count — negligible for <100 entities.
**Trade-off:** Full rows still loaded from DB. Acceptable for private tooling scale.

### TD-2: Compact JSON as default for inline responses
**Decision:** All MCP tools returning JSON inline use `separators=(',',':')` instead of `indent=2`.
**Rationale:** `indent=2` adds ~20-30% whitespace tokens. No human reads MCP tool output directly — it's consumed by the LLM. Compact is strictly better.

### TD-3: entity_lifecycle.py in entity_registry, not workflow_engine
**Decision:** Entity workflow state machines live in `hooks/lib/entity_registry/entity_lifecycle.py`, not in `workflow_engine/`.
**Rationale:** These state machines govern brainstorm/backlog entities, not features. The `entity_registry` package owns entity types and their lifecycle. `workflow_engine` owns feature phase progression.

### TD-4: feature_lifecycle.py in workflow_engine, not entity_registry
**Decision:** Feature initialization/activation lives in `hooks/lib/workflow_engine/feature_lifecycle.py`.
**Rationale:** Feature lifecycle is tightly coupled with `WorkflowStateEngine` (phase transitions, `.meta.json` projection). Moving it to `entity_registry` would create circular dependencies.

## Risks

### R-1: Breaking existing callers of _serialize_state
**Risk:** Dropping `completed_phases` and `source` from state responses may break commands/skills that parse these fields.
**Likelihood:** Low — grep shows `completed_phases` is rarely consumed outside of test assertions. `source` is never consumed by commands.
**Mitigation:** Grep for all consumers before implementation. Update test assertions.

### R-2: export_entities field validation
**Risk:** Invalid field names in `fields` param produce empty entities (all fields filtered out).
**Likelihood:** Low — callers are LLM agents following command instructions.
**Mitigation:** If all fields in `fields` are invalid, return an error message listing valid field names.

### R-3: upsert_workflow_phase SQL injection surface
**Risk:** New public method constructs SQL dynamically from kwargs keys.
**Likelihood:** Very low — keys are hardcoded in callers, not user input.
**Mitigation:** Validate kwargs keys against an allowlist of column names.

## Interfaces

### I1: export_entities (modified)
```python
# MCP tool
async def export_entities(
    entity_type: str | None = None,
    status: str | None = None,
    output_path: str | None = None,
    include_lineage: bool = True,
    fields: str | None = None,  # NEW — comma-separated field names
) -> str
```

### I2: reconcile_status (modified)
```python
async def reconcile_status(
    summary_only: bool = False,  # NEW
) -> str
```

### I3: search_memory (modified)
```python
async def search_memory(
    query: str,
    limit: int = 10,
    category: str | None = None,  # NEW
    brief: bool = False,          # NEW
) -> str
```

### I4: entity_lifecycle public API
```python
# hooks/lib/entity_registry/entity_lifecycle.py
def init_entity_workflow(db: EntityDatabase, type_id: str,
                         workflow_phase: str, kanban_column: str) -> dict

def transition_entity_phase(db: EntityDatabase, type_id: str,
                            target_phase: str) -> dict
```

### I5: feature_lifecycle public API
```python
# hooks/lib/workflow_engine/feature_lifecycle.py
def init_feature_state(db, engine, artifacts_root, feature_dir, feature_id,
                       slug, mode, branch, brainstorm_source=None,
                       backlog_source=None, status="active") -> dict

def init_project_state(db, engine, artifacts_root, project_dir, project_id,
                       slug, branch, features="", milestones="",
                       brainstorm_source=None, status="active") -> dict

def activate_feature(db, engine, artifacts_root, feature_type_id) -> dict
```

**Return type convention:** Library functions return `dict`. MCP handlers call `json.dumps()` on the result. This matches the thin-wrapper pattern — library returns data, MCP serializes.

**Decorator handling:** MCP handlers retain `@_with_error_handling` and `@_catch_entity_value_error` decorators. Library functions raise `ValueError` on validation failures; the MCP decorator converts these to structured JSON error responses.

### I6: EntityDatabase.upsert_workflow_phase()
```python
def upsert_workflow_phase(self, type_id: str, **kwargs) -> None
```

## Dependency Graph

```
Phase 1 (all independent — can be implemented in parallel):
  P1-C1 (export_entities fields)
  P1-C2 (get_entity compact)
  P1-C3 (UUID removal)
  P1-C4 (_serialize_state cleanup)
  P1-C5 (reconcile_status summary)
  P1-C6 (reconcile_frontmatter filter)
  P1-C7 (search_memory category+brief)

Phase 2 (dependencies within phase):
  P2-C2 (upsert_workflow_phase) ──→ P2-C1 (entity_lifecycle.py)
  P2-C1 ──→ workflow_state_server.py updates (init_entity_workflow, transition_entity_phase)

  P2-C3 (feature_lifecycle.py) ──→ workflow_state_server.py updates (init_feature_state, etc.)

  P2-C4 (set_parent extraction) — independent
  P2-C5 (direction removal) — independent
```
