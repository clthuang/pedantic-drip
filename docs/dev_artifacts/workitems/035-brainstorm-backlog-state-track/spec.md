# Specification: Brainstorm & Backlog State Tracking

## Overview
Add lifecycle state tracking for brainstorm and backlog entities. DB-only state (no `.meta.json`), lightweight state machines per entity type, MCP tools for transitions, and entity-type-aware kanban board cards.

**Chosen approach:** Option B from PRD — Lightweight State Machines + MCP Tools (No `.meta.json`). DB is sole source of truth for brainstorm/backlog state.

## State Machine Definitions

### Brainstorm Lifecycle
```
draft → reviewing → promoted
                  → abandoned

Any state → abandoned (terminal)
```

| Phase | Description | Kanban Column |
|-------|-------------|---------------|
| `draft` | PRD being written, initial research | `wip` |
| `reviewing` | PRD under review (Stage 4/5) | `agent_review` |
| `promoted` | Promoted to feature (terminal) | `completed` |
| `abandoned` | Discarded (terminal) | `completed` |

**Valid transitions:**
| From | To | Trigger |
|------|-----|---------|
| `draft` | `reviewing` | Brainstorming skill enters Stage 4 |
| `reviewing` | `promoted` | User selects "Promote to Feature" in Stage 6 |
| `reviewing` | `draft` | User selects "Refine Further" in Stage 6 |
| `reviewing` | `abandoned` | User explicitly abandons |
| `draft` | `abandoned` | User explicitly abandons |

### Backlog Lifecycle
```
open → triaged → promoted
               → dropped

Any state → dropped (terminal)
```

| Phase | Description | Kanban Column |
|-------|-------------|---------------|
| `open` | Newly created, awaiting triage | `backlog` |
| `triaged` | Referenced by a brainstorm | `prioritised` |
| `promoted` | Promoted to feature via brainstorm (terminal) | `completed` |
| `dropped` | Discarded (terminal) | `completed` |

**Valid transitions:**
| From | To | Trigger |
|------|-----|---------|
| `open` | `triaged` | Brainstorm references via `*Source: Backlog #NNNNN*` |
| `triaged` | `promoted` | Brainstorm promotes to feature |
| `open` | `dropped` | User explicitly drops |
| `triaged` | `dropped` | User explicitly drops |

## DB Schema Changes

### Migration 5: Expand workflow_phase CHECK Constraint

Migration 4 (`_create_fts_index`) already exists. This is Migration 5.

The `workflow_phases.workflow_phase` column CHECK constraint must be expanded to include brainstorm and backlog phase names. SQLite does not support ALTER CHECK — table must be recreated.

**New CHECK constraint for `workflow_phase`:**
```sql
CHECK(workflow_phase IN (
    'brainstorm','specify','design','create-plan','create-tasks','implement','finish',
    'draft','reviewing','promoted','abandoned',
    'open','triaged','dropped'
) OR workflow_phase IS NULL)
```

**New CHECK constraint for `last_completed_phase`:**
```sql
CHECK(last_completed_phase IN (
    'brainstorm','specify','design','create-plan','create-tasks','implement','finish',
    'draft','reviewing','promoted','abandoned',
    'open','triaged','dropped'
) OR last_completed_phase IS NULL)
```

**Migration pattern:** Follow existing Migration 3 pattern in `database.py`:
1. Increment `SCHEMA_VERSION` to 5
2. `BEGIN IMMEDIATE` transaction
3. Create `workflow_phases_new` with updated constraints
4. `INSERT INTO workflow_phases_new SELECT * FROM workflow_phases`
5. `DROP TABLE workflow_phases`
6. `ALTER TABLE workflow_phases_new RENAME TO workflow_phases`
7. Recreate indexes
8. Update `schema_version`
9. `COMMIT`

**Acceptance criteria:**
- AC-DB-1: Existing `workflow_phases` rows are preserved after migration
- AC-DB-2: New phase values (`draft`, `reviewing`, `promoted`, `abandoned`, `open`, `triaged`, `dropped`) are accepted by CHECK constraint
- AC-DB-3: Existing feature phase values continue to work
- AC-DB-4: Migration is idempotent (running on already-migrated DB is a no-op)

## Entity Registration Changes

### Backlog Registration at Creation Time (FR-1)

**Current behavior:** `add-to-backlog` command appends a row to `{artifacts_root}/backlog.md` with no entity registration.

**New behavior:** After appending the markdown row, register the entity and create a `workflow_phases` row.

**Registration call:**
```
register_entity(
  entity_type="backlog",
  entity_id="{5-digit-id}",
  name="{description}",
  artifact_path="{artifacts_root}/backlog.md",
  status="open"
)
```

**Workflow phases row:** Created by the MCP server as part of registration (see FR-4 below).

**Error handling:** If MCP call fails, warn `"Entity registration failed: {error}"` but do NOT block backlog creation. The markdown row is the primary artifact.

**Acceptance criteria:**
- AC-REG-1: `/iflow:add-to-backlog` creates both markdown row AND entity registry entry
- AC-REG-2: Entity has `workflow_phases` row with `workflow_phase='open'`, `kanban_column='backlog'`
- AC-REG-3: Registration failure does not block markdown row creation
- AC-REG-4: Entity `type_id` format is `backlog:{5-digit-id}` (e.g., `backlog:00042`). ID is derived from the current row count in `backlog.md`, zero-padded to 5 digits, matching the existing `add-to-backlog` numbering scheme.

### Brainstorm workflow_phases Row at Registration (FR-4, FR-10)

**Current behavior:** Brainstorming skill registers entity via `register_entity` MCP call in Stage 3, but no `workflow_phases` row is created.

**New behavior:** After `register_entity` succeeds, create a `workflow_phases` row.

**Approach:** Add a new MCP tool `init_entity_workflow` that creates a `workflow_phases` row for any entity type. This is called after `register_entity`.

```
init_entity_workflow(
  type_id="brainstorm:{stem}",
  workflow_phase="draft",
  kanban_column="wip"
)
```

For backlog:
```
init_entity_workflow(
  type_id="backlog:{id}",
  workflow_phase="open",
  kanban_column="backlog"
)
```

**Acceptance criteria:**
- AC-REG-5: Brainstorm entity gets `workflow_phases` row with `workflow_phase='draft'`, `kanban_column='wip'` at Stage 3
- AC-REG-6: Backlog entity gets `workflow_phases` row at creation time
- AC-REG-7: `init_entity_workflow` is idempotent (duplicate call is a no-op or upsert)
- AC-REG-8: `init_entity_workflow` validates `type_id` exists in `entities` table before inserting

## MCP Tool Specifications

### New Tool: `init_entity_workflow`

**Purpose:** Create a `workflow_phases` row for any entity type.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `type_id` | string | yes | Entity type_id (e.g., `brainstorm:20260309-...`, `backlog:00042`) |
| `workflow_phase` | string | yes | Initial phase value |
| `kanban_column` | string | yes | Initial kanban column |

**Behavior:**
1. Validate `type_id` exists in `entities` table → raise `ValueError("entity_not_found: ...")` if missing
2. Check if `workflow_phases` row already exists → if so, return success (idempotent)
3. Insert `workflow_phases` row with provided values and `updated_at = now()`
4. Return `{"created": true, "type_id": "...", "workflow_phase": "...", "kanban_column": "..."}`

**Error handling:** Use `@_with_error_handling` decorator plus a `@_catch_entity_value_error` decorator (see Error Handling section below) that maps `entity_not_found:` prefix to `{"error": true, "error_type": "entity_not_found", "message": "..."}`.

**Hosted in:** `plugins/iflow/mcp/workflow_state_server.py`. Although PRD FR-5 says "separate from feature tools", co-locating avoids a new MCP server while maintaining separation via the `_catch_entity_value_error` decorator and distinct function names. The new tools share no code paths with feature tools.

### New Tool: `transition_entity_phase`

**Purpose:** Transition a brainstorm or backlog entity to a new lifecycle phase. Updates both `entities.status` and `workflow_phases.workflow_phase` atomically.

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `type_id` | string | yes | Entity type_id (e.g., `brainstorm:20260309-...`, `backlog:00042`) |
| `target_phase` | string | yes | Target phase to transition to |

**Behavior:**
1. Parse `entity_type` from `type_id` (split on `:`, take first part)
2. Validate `entity_type` is `brainstorm` or `backlog` → raise `ValueError("invalid_entity_type: ...")` if not
3. Validate `type_id` exists in `entities` table → raise `ValueError("entity_not_found: ...")` if missing
4. Get current phase from `workflow_phases.workflow_phase`
5. Validate transition is allowed per state machine definition:
   - **Brainstorm valid transitions:** `{draft: [reviewing, abandoned], reviewing: [promoted, draft, abandoned]}`
   - **Backlog valid transitions:** `{open: [triaged, dropped], triaged: [promoted, dropped]}`
   - Raise `ValueError("invalid_transition: cannot transition from {current} to {target}")` if not allowed
6. Look up target kanban column from phase-to-column mapping:
   - **Brainstorm:** `{draft: wip, reviewing: agent_review, promoted: completed, abandoned: completed}`
   - **Backlog:** `{open: backlog, triaged: prioritised, promoted: completed, dropped: completed}`
7. In a single transaction:
   a. Update `entities.status` = `target_phase`, `entities.updated_at` = now()
   b. Update `workflow_phases.workflow_phase` = `target_phase`, `workflow_phases.kanban_column` = mapped column, `workflow_phases.last_completed_phase` = `current_phase` (if transitioning forward), `workflow_phases.updated_at` = now()
8. Return `{"transitioned": true, "type_id": "...", "from_phase": "...", "to_phase": "...", "kanban_column": "..."}`

**Error handling:** Use `@_with_error_handling` decorator plus `@_catch_entity_value_error` decorator (see Error Handling section below) that maps ValueError prefixes to structured error responses.

**Hosted in:** `plugins/iflow/mcp/workflow_state_server.py` (alongside existing feature workflow tools).

**Acceptance criteria:**
- AC-MCP-1: Valid transitions succeed and update both `entities.status` and `workflow_phases` atomically
- AC-MCP-2: Invalid transitions raise `ValueError` with descriptive message
- AC-MCP-3: Transitioning a feature entity raises `invalid_entity_type` error
- AC-MCP-4: Transitioning to terminal states (`promoted`, `abandoned`, `dropped`) succeeds
- AC-MCP-5: Transitioning FROM terminal states raises `invalid_transition` error
- AC-MCP-6: Non-existent `type_id` raises `entity_not_found` error

## Error Handling: `_catch_entity_value_error` Decorator

The existing `_catch_value_error` decorator in `workflow_state_server.py` is feature-specific (hardcodes `feature_not_found` error type). A new `_catch_entity_value_error` decorator handles ValueError prefixes for entity-generic tools.

**Prefix-to-error mapping:**
| ValueError Prefix | `error_type` | HTTP-like Meaning |
|-------------------|-------------|-------------------|
| `entity_not_found:` | `entity_not_found` | 404 |
| `invalid_entity_type:` | `invalid_entity_type` | 400 |
| `invalid_transition:` | `invalid_transition` | 409 (conflict) |

**Implementation pattern:**
```python
def _catch_entity_value_error(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            msg = str(e)
            for prefix in ("entity_not_found:", "invalid_entity_type:", "invalid_transition:"):
                if msg.startswith(prefix):
                    return {"error": True, "error_type": prefix.rstrip(":"), "message": msg}
            raise  # re-raise unexpected ValueErrors
    return wrapper
```

**Note:** Synchronous `def wrapper`, matching the existing `_catch_value_error` pattern. All `_process_*` functions in `workflow_state_server.py` are synchronous.

**Stacking order:** `@_with_error_handling` (outer) → `@_catch_entity_value_error` (inner) → function. This ensures ValueErrors are caught before the generic Exception handler.

**Acceptance criteria:**
- AC-ERR-1: `entity_not_found` ValueError returns `{"error": true, "error_type": "entity_not_found", ...}`
- AC-ERR-2: `invalid_entity_type` ValueError returns `{"error": true, "error_type": "invalid_entity_type", ...}`
- AC-ERR-3: `invalid_transition` ValueError returns `{"error": true, "error_type": "invalid_transition", ...}`
- AC-ERR-4: Unexpected ValueErrors propagate to `_with_error_handling` (not swallowed)

## Forward Transition Definition

For `last_completed_phase` updates in `transition_entity_phase`, "forward" means moving toward a terminal state in the entity's lifecycle:

**Brainstorm forward transitions:** `draft→reviewing`, `reviewing→promoted`, `reviewing→abandoned`, `draft→abandoned`
**Brainstorm backward transition:** `reviewing→draft`

**Backlog forward transitions:** `open→triaged`, `triaged→promoted`, `triaged→dropped`, `open→dropped`
**Backlog has no backward transitions.**

Rule: `last_completed_phase = current_phase` only on forward transitions. On backward transitions (e.g., `reviewing→draft`), `last_completed_phase` is NOT updated.

## Brainstorm-to-Feature Linking on Promotion

When a brainstorm is promoted to a feature (Stage 6 "Promote to Feature"):
1. Call `transition_entity_phase(type_id="brainstorm:{stem}", target_phase="promoted")`
2. After `/iflow:create-feature` creates the new feature entity, call `set_parent(type_id="feature:{feature_id}", parent_type_id="brainstorm:{stem}")` to establish lineage

This enables PRD traceability: feature → brainstorm → (optionally) backlog.

**Note:** The `set_parent` call already exists in the create-feature command for `brainstorm_source`-linked features. No new code needed — just verify it works when the brainstorm entity has `workflow_phase='promoted'`.

## `register_entity` Idempotency Behavior

The existing `register_entity` MCP tool is **not** idempotent — calling it with an existing `type_id` returns an error. Callers (brainstorming skill, add-to-backlog command) must handle this:

- **Brainstorming skill Stage 3:** Calls `register_entity` once. If it fails with a duplicate error, warn and skip (the entity already exists from a previous run).
- **Add-to-backlog command:** Each invocation generates a new 5-digit ID, so duplicates are not expected. If `register_entity` fails for any reason, warn but continue.
- **Backlog reference handling:** The brainstorming skill may call `register_entity` for a backlog item that already exists (registered by add-to-backlog). The skill must catch the duplicate error and proceed to `transition_entity_phase`.

## Performance Note

The new MCP tools (`init_entity_workflow`, `transition_entity_phase`) should complete within typical MCP round-trip time (~100ms). No special performance optimization is needed — the operations are single-row INSERT or UPDATE queries on an indexed SQLite table.

## Backfill Updates (FR-9)

### Updated `backfill_workflow_phases()`

**Current behavior:** For brainstorm/backlog entities, sets `kanban_column` from `STATUS_TO_KANBAN` with child-completion override. `workflow_phase` is always NULL.

**New behavior:** Derive `workflow_phase` from entity status using the same phase-to-column mapping as MCP tools.

**Status-to-phase mapping for backfill:**
| Entity Type | Entity Status | workflow_phase | kanban_column |
|-------------|--------------|----------------|---------------|
| brainstorm | (any, no workflow_phases row) | `draft` | `wip` |
| brainstorm | (existing row with non-null phase) | preserve | preserve |
| backlog | (any, no workflow_phases row) | `open` | `backlog` |
| backlog | (existing row with non-null phase) | preserve | preserve |

**Backfill conditional logic for brainstorm/backlog entities:**
1. If no `workflow_phases` row exists → INSERT with derived phase/column (draft/wip for brainstorm, open/backlog for backlog)
2. If row exists AND `workflow_phase IS NOT NULL` → SKIP (preserve MCP-managed state)
3. If row exists AND `workflow_phase IS NULL` → UPDATE with derived phase/column (legacy rows from before this feature)

This differs from the existing backfill pattern (which updates all rows) by preserving non-null phases set by MCP tools.

**Child-completion override:** Preserved. If all child features are completed, override `kanban_column = "completed"` regardless of entity phase.

**Acceptance criteria:**
- AC-BF-1: Backfill creates `workflow_phases` rows for brainstorm entities without them, with `workflow_phase='draft'`
- AC-BF-2: Backfill creates `workflow_phases` rows for backlog entities without them, with `workflow_phase='open'`
- AC-BF-3: Backfill does not overwrite existing `workflow_phases` rows that have non-null `workflow_phase`
- AC-BF-4: Child-completion override still applies

## Board UI Changes (FR-6)

### Card Template Updates

**Current behavior:** Card displays `workflow_phase` badge (colored), `mode` badge, and `last_completed_phase` text. All are feature-specific.

**New behavior:** Card displays entity-type-aware metadata:

| Entity Type | Badge 1 | Badge 2 | Additional |
|-------------|---------|---------|------------|
| feature | `workflow_phase` (colored) | `mode` | `last_completed_phase` |
| brainstorm | `workflow_phase` (colored) | "brainstorm" type badge | — |
| backlog | `workflow_phase` (colored) | "backlog" type badge | — |
| project | — | "project" type badge | — |

**Implementation:** Add entity type extraction from `type_id` (split on `:`, take first part). Use conditional rendering in `_card.html`:
- Always show `workflow_phase` badge if non-null (works for all entity types)
- Show `mode` badge only for feature entities
- Show entity type badge for non-feature entities
- Show `last_completed_phase` only for feature entities

**Entity type badge colors:**
- `brainstorm`: blue/indigo
- `backlog`: gray
- `project`: purple

**Acceptance criteria:**
- AC-UI-1: Feature cards render identically to current behavior
- AC-UI-2: Brainstorm cards show `workflow_phase` badge + "brainstorm" type badge
- AC-UI-3: Backlog cards show `workflow_phase` badge + "backlog" type badge
- AC-UI-4: Project cards show "project" type badge
- AC-UI-5: Cards with NULL `workflow_phase` show type badge only (no empty phase badge)

## Hook Guard Audit (FR-13)

### Verify existing hooks don't fire on brainstorm/backlog entities

**Hooks to audit:**
1. `meta-json-guard.sh` — Matches on `.meta.json` file path. Brainstorms and backlogs don't have `.meta.json`, so this hook will NOT fire on them. **Safe.**
2. `pre-commit-guard.sh` — Guards against commits to main/master branches. Entity-type-agnostic. **Safe.**
3. `yolo-guard.sh` — Auto-selects recommended options. Entity-type-agnostic. **Safe.**
4. `pre-exit-plan-review.sh` — Gates plan mode exit. Entity-type-agnostic. **Safe.**

**Conclusion:** No existing hooks fire on entity type. All hooks guard on file paths or tool names, not entity types. No changes needed.

**Acceptance criteria:**
- AC-HOOK-1: Manual review confirms `meta-json-guard.sh` triggers on `.meta.json` file paths only, which brainstorm/backlog entities do not produce
- AC-HOOK-2: All existing feature workflow tests pass without modification

## Skill/Command Updates

### Brainstorming Skill Changes

**Stage 3 (Entity Registration):** After `register_entity` call, add `init_entity_workflow` call:
```
init_entity_workflow(
  type_id="brainstorm:{stem}",
  workflow_phase="draft",
  kanban_column="wip"
)
```

**Stage 4 entry:** Call `transition_entity_phase` to advance to `reviewing`:
```
transition_entity_phase(
  type_id="brainstorm:{stem}",
  target_phase="reviewing"
)
```

**Stage 6 "Promote to Feature":** Call `transition_entity_phase` to advance to `promoted`:
```
transition_entity_phase(
  type_id="brainstorm:{stem}",
  target_phase="promoted"
)
```

**Stage 6 "Save and Exit":** No transition (stays in current state).

**All other Stage 6 exit routes** (Promote to Project, Route to RCA, Create fix task, Save as Decision Document): No state transition — brainstorm stays in current phase. This is intentional: non-feature promotion routes leave brainstorm in reviewing/draft state on the kanban board. Future iteration may handle project promotion state tracking.

**Stage 6 "Refine Further" (from reviewing):** Call `transition_entity_phase` to go back to `draft`:
```
transition_entity_phase(
  type_id="brainstorm:{stem}",
  target_phase="draft"
)
```

**Error handling:** All MCP calls are wrapped in failure handling — warn but don't block brainstorm flow.

### Add-to-Backlog Command Changes

After appending markdown row, add:
1. `register_entity` call (as specified in Entity Registration Changes)
2. `init_entity_workflow` call:
```
init_entity_workflow(
  type_id="backlog:{5-digit-id}",
  workflow_phase="open",
  kanban_column="backlog"
)
```

### Brainstorming Skill — Backlog Reference Handling

When brainstorm references a backlog item via `*Source: Backlog #NNNNN*`:
1. Register backlog entity (idempotent, existing behavior)
2. Call `transition_entity_phase(type_id="backlog:{id}", target_phase="triaged")`
3. If transition fails (entity doesn't exist or already triaged), warn but continue

When brainstorm promotes to feature:
1. Call `transition_entity_phase(type_id="backlog:{id}", target_phase="promoted")`
2. If transition fails, warn but continue

## Test Requirements

### New Tests
- Migration 5 schema tests: constraint validation, data preservation, idempotency
- `init_entity_workflow` MCP tool: creation, idempotency, entity-not-found, invalid type_id
- `transition_entity_phase` MCP tool: valid transitions, invalid transitions, terminal state protection, entity-not-found, invalid entity type, atomic update verification
- Backfill updates: brainstorm/backlog row creation with correct phase/column, existing row preservation
- Board card template: entity-type-aware rendering for all 4 entity types

### Existing Tests (Must Pass)
- 289 workflow engine tests
- 257 transition gate tests
- 667+ entity registry tests
- 146 workflow state MCP server tests
- 178 UI server tests

## Scope Boundaries

### In Scope
- DB Migration 5 (CHECK constraint expansion)
- 2 new MCP tools (`init_entity_workflow`, `transition_entity_phase`)
- Backfill update for brainstorm/backlog phase derivation
- Board card template entity-type-aware rendering
- Brainstorming skill state transition calls
- Add-to-backlog command entity registration
- Hook guard audit (verification only, no changes expected)

### Out of Scope
- Feature workflow engine changes (WorkflowStateEngine untouched)
- `.meta.json` for brainstorms or backlogs
- Hook enforcement for brainstorm/backlog transitions
- Reconciliation for brainstorm/backlog state
- Board filtering by entity type
- RCA or project entity state tracking
- Brainstorm-to-feature automatic state propagation
