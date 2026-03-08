# Design: Brainstorm & Backlog State Tracking

## Prior Art Research

**Codebase patterns found:**
- Migration 3 (`_create_workflow_phases_table`) — table recreation pattern with FK safety, used as template for Migration 5
- `_catch_value_error` decorator — prefix-based ValueError routing, template for `_catch_entity_value_error`
- `_process_*` pattern — sync processing functions wrapped with decorators, async MCP tool functions delegate to them
- `backfill_workflow_phases()` — INSERT OR IGNORE pattern with 3-tier status resolution
- Board card template — Jinja2 conditional rendering with global `phase_colors` dict

**External research:** Skipped (domain expert — this is internal tooling extending an existing system).

## Architecture Overview

### Component Map

```
┌────────────────────────────────────────────────────────────────┐
│  Callers (Skills / Commands)                                   │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────┐ │
│  │ brainstorming │  │ add-to-backlog│  │ cleanup-brainstorms  │ │
│  │ SKILL.md      │  │ command.md    │  │ command.md           │ │
│  └──────┬───────┘  └──────┬────────┘  └──────────────────────┘ │
│         │                  │                                    │
│         ▼                  ▼                                    │
│  ┌─────────────────────────────────────┐                       │
│  │  MCP: workflow_state_server.py      │                       │
│  │  ┌─────────────────────────────┐    │                       │
│  │  │ NEW: init_entity_workflow   │    │                       │
│  │  │ NEW: transition_entity_phase│    │                       │
│  │  └─────────────────────────────┘    │                       │
│  │  ┌─────────────────────────────┐    │                       │
│  │  │ EXISTING (untouched):       │    │                       │
│  │  │ get_phase, transition_phase │    │                       │
│  │  │ complete_phase, etc.        │    │                       │
│  │  └─────────────────────────────┘    │                       │
│  └────────────────┬────────────────────┘                       │
│                   │                                             │
│                   ▼                                             │
│  ┌─────────────────────────────────────┐                       │
│  │  DB: entity_registry/database.py    │                       │
│  │  ┌─────────────────────────────┐    │                       │
│  │  │ Migration 5: CHECK expand   │    │                       │
│  │  └─────────────────────────────┘    │                       │
│  │  ┌─────────────────────────────┐    │                       │
│  │  │ backfill.py: phase-aware    │    │                       │
│  │  │ brainstorm/backlog logic    │    │                       │
│  │  └─────────────────────────────┘    │                       │
│  └────────────────┬────────────────────┘                       │
│                   │                                             │
│                   ▼                                             │
│  ┌─────────────────────────────────────┐                       │
│  │  UI: _card.html + __init__.py       │                       │
│  │  Entity-type-aware card rendering   │                       │
│  │  + expanded PHASE_COLORS            │                       │
│  └─────────────────────────────────────┘                       │
└────────────────────────────────────────────────────────────────┘
```

### Isolation Principle

New tools (`init_entity_workflow`, `transition_entity_phase`) share **zero code paths** with existing feature tools. They:
- Use a different error decorator (`_catch_entity_value_error` vs `_catch_value_error`)
- Query the `entities` table directly (no `_validate_feature_type_id`, no `WorkflowStateEngine`)
- Have their own state machine definitions (no dependency on `transition_gate/`)

This means existing feature workflow tests cannot be broken by changes in this feature.

## Components

### C1: Migration 5 — `_expand_workflow_phase_check`

**File:** `plugins/iflow/hooks/lib/entity_registry/database.py`

**What changes:**
1. Add `_expand_workflow_phase_check(conn)` function after `_create_fts_index`
2. Add entry `5: _expand_workflow_phase_check` to `MIGRATIONS` dict
3. Bump `SCHEMA_VERSION` to 5

**Migration logic:**
```
PRAGMA foreign_keys = OFF
BEGIN IMMEDIATE
  PRAGMA foreign_key_check  (abort on violations)
  CREATE TABLE workflow_phases_new (same schema, expanded CHECK)
  INSERT INTO workflow_phases_new SELECT * FROM workflow_phases
  DROP TABLE workflow_phases
  ALTER TABLE workflow_phases_new RENAME TO workflow_phases
  Recreate trigger: enforce_immutable_wp_type_id
  Recreate index: idx_wp_kanban_column
  Recreate index: idx_wp_workflow_phase
  UPDATE schema_version = 5
COMMIT
PRAGMA foreign_keys = ON
PRAGMA foreign_key_check  (post-migration verify)
```

**Expanded CHECK values for `workflow_phase`:**
```
'brainstorm','specify','design','create-plan','create-tasks','implement','finish',
'draft','reviewing','promoted','abandoned',
'open','triaged','dropped'
```

Same expansion for `last_completed_phase`.

**Idempotency:** If `schema_version` is already 5, `_migrate()` skips this function (existing behavior in the migration framework).

### C2: Error Decorator — `_catch_entity_value_error`

**File:** `plugins/iflow/mcp/workflow_state_server.py`

**Placement:** After `_catch_value_error` (line ~367), before `_validate_feature_type_id`.

```python
def _catch_entity_value_error(func):
    """Map entity-related ValueErrors to structured error dicts."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            msg = str(e)
            for prefix in ("entity_not_found:", "invalid_entity_type:", "invalid_transition:"):
                if msg.startswith(prefix):
                    error_type = prefix.rstrip(":")
                    return _make_error(error_type, msg, _ENTITY_RECOVERY_HINTS.get(error_type, ""))
            raise
    return wrapper

_ENTITY_RECOVERY_HINTS = {
    "entity_not_found": "Verify type_id exists via get_entity",
    "invalid_entity_type": "Only brainstorm and backlog entities support lifecycle transitions",
    "invalid_transition": "Check current phase — transition may not be valid from current state",
}
```

**Stacking order:** `@_with_error_handling` (outer) → `@_catch_entity_value_error` (inner) → `_process_*`

### C3: State Machine Constants

**File:** `plugins/iflow/mcp/workflow_state_server.py`

**Placement:** After imports, before helper functions. Module-level constants.

```python
# Entity lifecycle state machines — single registry keyed by entity_type.
# Each entry defines: valid transitions, phase-to-kanban-column mapping,
# and forward transition set (for last_completed_phase updates).
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
```

**Usage in C5:** `ENTITY_MACHINES[entity_type]["transitions"]`, `ENTITY_MACHINES[entity_type]["columns"]`, `ENTITY_MACHINES[entity_type]["forward"]`.

### C4: `_process_init_entity_workflow`

**File:** `plugins/iflow/mcp/workflow_state_server.py`

```python
@_with_error_handling
@_catch_entity_value_error
def _process_init_entity_workflow(
    db: EntityDatabase, type_id: str, workflow_phase: str, kanban_column: str
) -> str:
    # 1. Validate entity exists
    entity = db.get_entity(type_id)
    if entity is None:
        raise ValueError(f"entity_not_found: {type_id}")

    # 1b. Validate workflow_phase/kanban_column against ENTITY_MACHINES
    if ":" in type_id:
        entity_type = type_id.split(":", 1)[0]
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

    # 2. Check idempotency — existing row means no-op (preserves MCP-managed state)
    existing = db._conn.execute(
        "SELECT workflow_phase, kanban_column FROM workflow_phases WHERE type_id = ?",
        (type_id,),
    ).fetchone()
    if existing:
        return json.dumps({
            "created": False,
            "type_id": type_id,
            "workflow_phase": existing["workflow_phase"],
            "kanban_column": existing["kanban_column"],
            "reason": "already_exists",
        })

    # 3. Insert workflow_phases row
    db._conn.execute(
        "INSERT INTO workflow_phases (type_id, workflow_phase, kanban_column, updated_at) "
        "VALUES (?, ?, ?, ?)",
        (type_id, workflow_phase, kanban_column, db._now_iso()),
    )
    db._conn.commit()

    return json.dumps({
        "created": True,
        "type_id": type_id,
        "workflow_phase": workflow_phase,
        "kanban_column": kanban_column,
    })
```

**MCP tool registration:**
```python
@mcp.tool()
async def init_entity_workflow(type_id: str, workflow_phase: str, kanban_column: str) -> str:
    """Create a workflow_phases row for any entity type."""
    if _db is None:
        return _NOT_INITIALIZED
    return _process_init_entity_workflow(_db, type_id, workflow_phase, kanban_column)
```

### C5: `_process_transition_entity_phase`

**File:** `plugins/iflow/mcp/workflow_state_server.py`

```python
@_with_error_handling
@_catch_entity_value_error
def _process_transition_entity_phase(
    db: EntityDatabase, type_id: str, target_phase: str
) -> str:
    # 1. Parse entity_type
    if ":" not in type_id:
        raise ValueError(f"invalid_entity_type: malformed type_id: {type_id}")
    entity_type = type_id.split(":", 1)[0]

    # 2. Validate entity_type
    if entity_type not in ENTITY_MACHINES:
        raise ValueError(
            f"invalid_entity_type: {entity_type} — only brainstorm and backlog supported"
        )

    # 3. Validate entity exists
    entity = db.get_entity(type_id)
    if entity is None:
        raise ValueError(f"entity_not_found: {type_id}")

    # 4. Get current phase
    row = db._conn.execute(
        "SELECT workflow_phase FROM workflow_phases WHERE type_id = ?", (type_id,)
    ).fetchone()
    if row is None:
        raise ValueError(f"entity_not_found: no workflow_phases row for {type_id}")
    current_phase = row["workflow_phase"]
    if current_phase is None:
        raise ValueError(
            f"invalid_transition: {type_id} has NULL current_phase — "
            "call init_entity_workflow first"
        )

    # 5. Validate transition
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

    # 8. Atomic update in transaction
    now = db._now_iso()
    db._conn.execute(
        "UPDATE entities SET status = ?, updated_at = ? WHERE type_id = ?",
        (target_phase, now, type_id),
    )

    if is_forward:
        db._conn.execute(
            "UPDATE workflow_phases SET workflow_phase = ?, kanban_column = ?, "
            "last_completed_phase = ?, updated_at = ? WHERE type_id = ?",
            (target_phase, kanban_column, current_phase, now, type_id),
        )
    else:
        db._conn.execute(
            "UPDATE workflow_phases SET workflow_phase = ?, kanban_column = ?, "
            "updated_at = ? WHERE type_id = ?",
            (target_phase, kanban_column, now, type_id),
        )

    db._conn.commit()

    return json.dumps({
        "transitioned": True,
        "type_id": type_id,
        "from_phase": current_phase,
        "to_phase": target_phase,
        "kanban_column": kanban_column,
    })
```

**MCP tool registration:**
```python
@mcp.tool()
async def transition_entity_phase(type_id: str, target_phase: str) -> str:
    """Transition a brainstorm or backlog entity to a new lifecycle phase."""
    if _db is None:
        return _NOT_INITIALIZED
    return _process_transition_entity_phase(_db, type_id, target_phase)
```

### C6: Backfill Update

**File:** `plugins/iflow/hooks/lib/entity_registry/backfill.py`

**Change location:** Inside `backfill_workflow_phases()`, after the feature-specific block (line ~257), add brainstorm/backlog phase derivation.

**Current code (line 224):** `workflow_phase = None` for non-feature entities.

**Ordering fix:** The brainstorm/backlog early-exit block below must be placed **BEFORE** the existing `STATUS_TO_KANBAN` lookup (line ~225). Currently, non-feature entities with statuses like `"draft"` or `"open"` fall through to `STATUS_TO_KANBAN.get(status)` which returns `None` and triggers a log warning. By handling brainstorm/backlog entities first and `continue`-ing, we avoid spurious warnings.

**New logic:**
```python
if entity_type == "feature":
    # ... existing feature logic unchanged ...
elif entity_type in ("brainstorm", "backlog"):
    # Check if workflow_phases row already exists with non-null phase
    existing_row = db._conn.execute(
        "SELECT workflow_phase FROM workflow_phases WHERE type_id = ?",
        (type_id,)
    ).fetchone()

    if existing_row and existing_row["workflow_phase"] is not None:
        # Preserve MCP-managed state — skip this entity
        skipped += 1
        continue

    # Derive default phase/column for new or null-phase rows
    if entity_type == "brainstorm":
        workflow_phase = "draft"
        kanban_column = "wip"
    else:  # backlog
        workflow_phase = "open"
        kanban_column = "backlog"
```

The rest of the function (INSERT OR IGNORE) handles the actual row creation. The `continue` on existing non-null rows short-circuits to skip the INSERT.

**Child-completion override** remains at line 210-221 — it runs before this new block, and `kanban_column` may be overridden to `"completed"` regardless of the derived phase.

**Known v1 limitation:** The `continue` on non-null `workflow_phase` (step "Preserve MCP-managed state") will skip the entity even if the child-completion override would change `kanban_column` to `"completed"`. This means a brainstorm/backlog whose MCP-managed phase was set early won't get its `kanban_column` updated by backfill when all children complete. Acceptable because: (1) brainstorms rarely have children at the time of backfill, (2) the `transition_entity_phase` MCP tool handles lifecycle transitions for actively-managed entities, and (3) a future backfill enhancement can reconcile kanban_column post-hoc if needed.

### C7: UI Card Template Update

**File:** `plugins/iflow/ui/templates/_card.html`

**Current template:** Renders `workflow_phase` badge, `mode` badge, and `last_completed_phase` for all entities (feature-centric).

**Entity type derivation:** Jinja2 inline expression `item.type_id.split(':')[0]` — same pattern already used on line 4 of `_card.html` for display name extraction. No Python route changes needed.

**New template with entity-type-aware rendering:**

```html
<a href="/entities/{{ item.type_id }}" class="block no-underline [color:inherit]">
<div class="card bg-base-200 shadow-sm p-3 transition-all duration-150 hover:bg-base-300 hover:shadow-md">
    <div class="font-semibold text-sm truncate">
        {{ item.type_id.split(':')[1] if ':' in item.type_id else item.type_id }}
    </div>
    <div class="text-xs text-base-content/50 truncate mt-0.5">
        {{ item.type_id }}
    </div>
    {# Extract entity type from type_id #}
    {% set entity_type = item.type_id.split(':')[0] if ':' in item.type_id else 'unknown' %}
    <div class="flex flex-wrap gap-1 mt-2">
        {% if item.workflow_phase %}
        <span class="badge badge-xs {{ phase_colors.get(item.workflow_phase, 'badge-ghost') }}">
            {{ item.workflow_phase }}
        </span>
        {% endif %}
        {% if entity_type == 'feature' %}
            {% if item.mode %}
            <span class="badge badge-xs badge-ghost">{{ item.mode }}</span>
            {% endif %}
        {% elif entity_type == 'brainstorm' %}
            <span class="badge badge-xs badge-info badge-outline">brainstorm</span>
        {% elif entity_type == 'backlog' %}
            <span class="badge badge-xs badge-ghost badge-outline">backlog</span>
        {% elif entity_type == 'project' %}
            <span class="badge badge-xs badge-secondary badge-outline">project</span>
        {% endif %}
    </div>
    {% if entity_type == 'feature' and item.last_completed_phase %}
    <div class="text-xs text-base-content/40 mt-1">
        last: {{ item.last_completed_phase }}
    </div>
    {% endif %}
</div>
</a>
```

### C8: PHASE_COLORS Update

**File:** `plugins/iflow/ui/__init__.py`

**Add new phase colors** to the `PHASE_COLORS` dict:

```python
PHASE_COLORS = {
    # Feature phases (existing)
    "brainstorm": "badge-info",
    "specify": "badge-secondary",
    "design": "badge-accent",
    "create-plan": "badge-warning",
    "create-tasks": "badge-warning",
    "implement": "badge-primary",
    "finish": "badge-success",
    # Brainstorm lifecycle phases (new)
    "draft": "badge-info",
    "reviewing": "badge-secondary",
    "promoted": "badge-success",
    "abandoned": "badge-neutral",
    # Backlog lifecycle phases (new)
    "open": "badge-ghost",
    "triaged": "badge-info",
    "dropped": "badge-neutral",
}
```

**Note:** `promoted` and `dropped` share colors with feature completion/abandon states for visual consistency.

**Test update required:** `test_phase_colors_match_db_check_constraint` in `plugins/iflow/ui/tests/test_filters.py` hardcodes the 7 feature phases. This test must be updated to include the 7 new phase values. This is a consistency assertion test (PHASE_COLORS keys match CHECK constraint), so updating it alongside the CHECK constraint is correct. "Existing tests pass without modification" (NFR-1) means no behavioral regressions, not zero test file changes.

### C9: Skill/Command File Updates

**File:** `plugins/iflow/skills/brainstorming/SKILL.md`

**Changes (3 insertion points):**

1. **Stage 3 (Entity Registration):** After `register_entity` call, add:
   ```
   init_entity_workflow(
     type_id="brainstorm:{stem}",
     workflow_phase="draft",
     kanban_column="wip"
   )
   ```

2. **Stage 4 entry:** Add `transition_entity_phase` call before dispatching prd-reviewer.

3. **Stage 6 decision handlers:** Add `transition_entity_phase` calls for "Promote to Feature" (→ promoted) and "Refine Further" (→ draft).

**Backlog reference handling sequence** (when brainstorm references `*Source: Backlog #NNNNN*`):
1. Call `register_entity(entity_type="backlog", entity_id="{id}", ...)` — if duplicate error (already registered by add-to-backlog), swallow and continue
2. Call `init_entity_workflow(type_id="backlog:{id}", workflow_phase="open", kanban_column="backlog")` — idempotent, safe regardless of step 1 outcome
3. Call `transition_entity_phase(type_id="backlog:{id}", target_phase="triaged")` — if fails (already triaged or entity missing), warn and continue

**File:** `plugins/iflow/commands/add-to-backlog.md`

**Changes:** After markdown row append, add `register_entity` + `init_entity_workflow` calls with error handling.

**File:** `plugins/iflow/commands/cleanup-brainstorms.md`

**No changes required.** `cleanup-brainstorms` is a file listing/deletion utility — it operates on `.prd.md` files only. It does not interact with entities, workflow_phases, or MCP tools. If a brainstorm file is deleted via this command, the `brainstorm:*` entity and its `workflow_phases` row remain in the DB as orphaned records (harmless — the entity registry has no FK to the filesystem). A future cleanup-entities command could garbage-collect these, but that's out of scope for this feature.

## Technical Decisions

### TD-1: Co-locate in workflow_state_server.py

**Decision:** Place new MCP tools in the existing `workflow_state_server.py` instead of creating a new server.

**Rationale:**
- Avoids MCP server startup overhead (each server is a separate process)
- `_db` (EntityDatabase) and `_engine` references are already available via `lifespan`
- New tools need only `_db`, not `_engine` — no coupling to feature logic
- Separation maintained via distinct decorators and function names

**Trade-off:** Larger file (~1050 lines → ~1200 lines). Acceptable for internal tooling.

### TD-2: Mixed access pattern — public API + direct `db._conn` for workflow_phases

**Decision:** Use EntityDatabase public API for entity lookups (`db.get_entity()`), but access `db._conn` directly for `workflow_phases` table operations (SELECT, INSERT, UPDATE).

**Rationale:**
- `db.get_entity()` is the canonical way to check entity existence — used throughout `workflow_state_server.py`
- The `workflow_phases` table has no dedicated public API methods for the operations we need (idempotent insert, atomic multi-table update)
- `backfill_workflow_phases()` in `backfill.py` (line 258-270) already uses `db._conn.execute()` directly for `workflow_phases` operations — this is the established pattern for this table
- Direct `_conn` access enables atomic multi-table updates (see TD-5)

**Trade-off:** Uses private `_conn` attribute for workflow_phases only. Acceptable — it's the established pattern for this table.

### TD-5: Accept non-atomicity for cross-table updates in `transition_entity_phase`

**Decision:** Use two separate SQL UPDATE statements with a single `db._conn.commit()` at the end, rather than requiring a formal transaction.

**Rationale:**
- SQLite in WAL mode with a single connection serializes writes. The two UPDATEs execute sequentially within the same connection — no interleaving from other connections is possible.
- `db._conn` is in autocommit=False mode (Python sqlite3 default). Multiple `execute()` calls before a `commit()` form an implicit transaction. If the process crashes between UPDATEs, SQLite's journal rolls back both.
- Adding a formal `BEGIN`/`COMMIT` block would be redundant given Python sqlite3's implicit transaction behavior.
- Failure between `entities.status` update and `workflow_phases` update is recoverable: backfill corrects inconsistencies on next server restart.

**Alternative considered:** Adding `EntityDatabase.transaction()` context manager — rejected as over-engineering for two single-row UPDATEs on the same connection.

### TD-3: Sync processing functions

**Decision:** All `_process_*` functions are synchronous `def`, matching existing codebase pattern.

**Rationale:** SQLite operations are CPU-bound and fast. The async MCP tool wrappers delegate to sync processing functions — this is the established pattern in the codebase (lines 404-1028).

### TD-4: INSERT OR IGNORE in backfill

**Decision:** Continue using `INSERT OR IGNORE` pattern in backfill, with a pre-check for non-null `workflow_phase` on existing rows.

**Rationale:**
- `INSERT OR IGNORE` handles the "no row exists" case
- Pre-check for non-null `workflow_phase` prevents overwriting MCP-managed state
- `continue` on non-null rows avoids the INSERT entirely (cleaner than UPDATE OR IGNORE)

**Alternative considered:** UPDATE all rows — rejected because it would overwrite MCP-managed phases.

## Risks

### R1: Phase name collision

**Risk:** `promoted` appears in both brainstorm and backlog lifecycles. If the CHECK constraint or phase_colors dict assumes unique phase names per entity type, there could be ambiguity.

**Mitigation:** Phase names are stored alongside `type_id` which includes entity type. The `PHASE_COLORS` dict maps by phase name only (shared `badge-success` for `promoted` is intentional). No collision issue.

### R2: Backfill race with MCP tools

**Risk:** If `backfill_workflow_phases()` runs concurrently with `transition_entity_phase`, the backfill could overwrite a just-set phase.

**Mitigation:** The pre-check `SELECT workflow_phase ... WHERE type_id = ?` before INSERT prevents overwriting non-null phases. Additionally, backfill runs at server startup before MCP tools are available to clients.

### R3: Orphaned workflow_phases rows

**Risk:** If `register_entity` succeeds but `init_entity_workflow` fails, the entity exists without a workflow_phases row.

**Mitigation:** Backfill creates missing rows on next server restart. The MCP tool error is warned but doesn't block. The kanban board handles entities without workflow_phases rows (they appear in "backlog" column by default).

## Interfaces

### I1: `init_entity_workflow` MCP Tool

```
Input:  { type_id: str, workflow_phase: str, kanban_column: str }
Output: { created: bool, type_id: str, workflow_phase?: str, kanban_column?: str, reason?: str }
Error:  { error: true, error_type: "entity_not_found", message: str, recovery_hint: str }
```

### I2: `transition_entity_phase` MCP Tool

```
Input:  { type_id: str, target_phase: str }
Output: { transitioned: bool, type_id: str, from_phase: str, to_phase: str, kanban_column: str }
Error:  { error: true, error_type: "entity_not_found"|"invalid_entity_type"|"invalid_transition",
          message: str, recovery_hint: str }
```

### I3: Migration 5 Function Signature

```python
def _expand_workflow_phase_check(conn: sqlite3.Connection) -> None:
```

Follows same pattern as `_create_workflow_phases_table` (Migration 3):
- Self-managed transaction (BEGIN IMMEDIATE / COMMIT / ROLLBACK)
- FK safety (PRAGMA foreign_keys OFF/ON)
- Post-migration FK check

### I4: Backfill — Updated `backfill_workflow_phases()` Signature

No signature change. Return type unchanged: `{"created": int, "skipped": int, "errors": list[str]}`.

Behavioral change: brainstorm/backlog entities now get `workflow_phase` set (instead of NULL) when backfill creates their rows.

### I5: Card Template Data Contract

Template receives `item` dict from `list_workflow_phases()` with fields:
- `type_id` (str) — used to extract entity_type via `split(':')[0]`
- `workflow_phase` (str | None)
- `kanban_column` (str)
- `mode` (str | None) — only shown for feature entities
- `last_completed_phase` (str | None) — only shown for feature entities

No changes to the data source — only the template rendering logic changes.

**Note on entity_detail.html:** The entity detail page also displays workflow_phase, mode, and last_completed_phase. For non-feature entities, mode and backward_transition_reason will display as "-" (existing null rendering). This is acceptable for v1 — the detail page already handles null gracefully. Cleaner entity-type-aware detail rendering is a follow-up.

## Dependencies

```
C1 (Migration 5) ← C4, C5 (MCP tools need expanded CHECK constraint)
C2 (Error decorator) ← C4, C5 (MCP tools use the decorator)
C3 (Constants) ← C5 (transition_entity_phase uses state machine defs)
C6 (Backfill) ← C1 (needs expanded CHECK for new phase values)
C7 (Card template) — independent (Jinja2 only)
C8 (PHASE_COLORS) — independent (Python dict only)
C9 (Skill/command) ← C4, C5 (calls the new MCP tools)
```

**Implementation order:**
1. C1 (Migration 5) — DB foundation
2. C2, C3 (Error decorator + Constants) — MCP infrastructure
3. C4, C5 (MCP tools) — core functionality
4. C6 (Backfill) — legacy data support
5. C7, C8 (UI) — visual layer
6. C9 (Skill/command updates) — caller integration
