---
last-updated: 2026-05-13T00:00:00Z
source-feature: 109-polymorphic-taxonomy-and-event
audit-feature: 098-tier-doc-frontmatter-sweep
---

<!-- AUTO-GENERATED: START - source: codebase-analysis -->

# API Reference

Internal contracts for MCP tools and key module interfaces. This document covers the MCP tool signatures used by workflow skills and commands, and the entity metadata contracts consumed by the workflow engine.

## MCP: Workflow Engine Server

**Server:** `plugins/pd/mcp/workflow_state_server.py` (registered as `FastMCP("workflow-engine")`; the file is named `workflow_state_server.py` for legacy reasons but the MCP server name is `workflow-engine`)
**Bootstrap:** `plugins/pd/mcp/run-workflow-server.sh`

### complete_phase

Records phase completion in entity metadata and re-projects `.meta.json`.

```
complete_phase(
    feature_type_id: str | None = None,     # Feature entity type_id, e.g., "feature:097-iso8601-test-pin-v2"
    phase: str = "",                        # Phase name, e.g., "specify", "design", "implement"
    iterations: int | None = None,          # Review iteration count (optional)
    reviewer_notes: str | None = None,      # JSON-serialized array OR null; raw string passed directly
    ref: str | None = None,                 # Alternative to feature_type_id (UUID or slug-based)
) -> str
```

Writes to `phase_timing[phase].{completed, iterations, reviewerNotes}` in entity metadata. Does not write `phase_summaries` — that is handled separately via `update_entity` in `commitAndComplete` Step 3a. Note: `reviewer_notes` is parsed as a JSON blob, not passed as a Python list — callers must pre-serialize.

### transition_phase

Advances workflow state to the next phase in the engine.

```
transition_phase(
    feature_type_id: str | None = None,
    target_phase: str = "",
    yolo_active: bool = False,              # When True, validates with YOLO transition rules
    skipped_phases: str | None = None,      # JSON-serialized list; null means none skipped
    ref: str | None = None,                 # Alternative to feature_type_id
) -> str
```

### validate_prerequisites

Checks artifact prerequisites before entering a phase.

```
validate_prerequisites(
    type_id: str,
    target_phase: str,
) -> {"valid": bool, "missing": list[str], "warnings": list[str]}
```

### reconcile_check / reconcile_apply

Drift detection and repair between engine state and filesystem artifacts.

```
reconcile_check(type_id: str) -> {"drifts": list[dict], "status": str}
reconcile_apply(type_id: str, dry_run: bool) -> {"applied": list[str], "errors": list[str]}
```

## MCP: Entity Registry Server

**Server:** `plugins/pd/mcp/entity_server.py`
**Bootstrap:** `plugins/pd/mcp/run-entity-server.sh`
**Database:** `~/.claude/pd/entities/entities.db`

### register_entity

Raises `EntityExistsError` on `(workspace_uuid, type_id)` conflict — no silent ignore (feature 109, FR-4).

```
register_entity(
    type_id: str,           # "{kind}:{entity_id}", colon separator (not slash)
    name: str,
    artifact_path: str | None,
    parent_type_id: str | None,
    metadata: dict | str,   # dict preferred; auto-coerced to JSON string
) -> str                    # entity uuid
```

**Exception:** `EntityExistsError(ValueError)` — raised when the `(workspace_uuid, type_id)` pair already exists. Carries `.workspace_uuid` and `.type_id` attributes for caller inspection. Defined in `database.py` (not a separate `exceptions.py`).

### upsert_entity

Idempotent insert-or-status-update. Byte-identical signature to `register_entity` (feature 109, FR-4).

```
upsert_entity(
    type_id: str,
    name: str,
    artifact_path: str | None,
    parent_type_id: str | None,
    metadata: dict | str,
) -> str                    # entity uuid (existing or newly created)
```

**Semantics (three branches):**

| Branch | Condition | Side effects |
|--------|-----------|-------------|
| Insert | No existing `(workspace_uuid, type_id)` row | INSERT + emit `entity_created` phase_event (identical to `register_entity`) |
| Conflict + status change | Row exists, `status` differs | UPDATE `status` + `updated_at`, emit `entity_status_changed` phase_event with `metadata={"old_status": ..., "new_status": ...}` |
| Conflict + no status change | Row exists, `status` same or not passed | No-op — no UPDATE, no event emitted, `updated_at` unchanged |

`name`, `parent_uuid`, and `metadata` are **never updated** on the conflict branch. Use `update_entity` for those fields.

### promote_entity

Atomically promotes an entity to a new kind within the same workspace, rewriting the `type_id` prefix (feature 109, FR-3).

```
promote_entity(
    uuid: str,
    new_kind: str,
    new_lifecycle_class: str,
    project_id: str | None = None,
) -> dict                   # updated entity row
```

**Operation (single transaction):**

1. Pre-flight: read existing row by `uuid`; if the new `type_id` would collide with an existing `(workspace_uuid, new_type_id)` row, raise `PromotionConflictError`.
2. `UPDATE entities SET kind = ?, lifecycle_class = ?, type_id = ?, updated_at = ?`; the `type_id` prefix is rewritten using first-colon split (`backlog:42` → `feature:42`; subsequent colons in the suffix are preserved verbatim).
3. Append `entity_promoted` phase_event via `append_phase_event`, keyed on the new `type_id`. Metadata payload: `{"old_kind", "new_kind", "old_lifecycle_class", "new_lifecycle_class", "old_type_id", "new_type_id"}`.
4. Return updated entity dict.

The `uuid` and `workspace_uuid` are never changed. Dependencies referencing the uuid remain valid.

**Exception:** `PromotionConflictError(ValueError)` — raised on `(workspace_uuid, new_type_id)` collision. Carries `.workspace_uuid`, `.old_type_id`, `.new_type_id`. Defined in `database.py`.

**Allowed transitions:** any `(new_kind, new_lifecycle_class)` pair that satisfies the FR-1 composite CHECK constraint. Business-logic restrictions (e.g., only `backlog → feature`) must be enforced by callers.

### update_entity

Shallow-merges `metadata` dict into existing entity metadata. Pass only the keys to update.

```
update_entity(
    type_id: str,
    name: str | None,
    status: str | None,
    artifact_path: str | None,
    metadata: dict,         # shallow merge — unspecified keys are preserved
)
```

**Important:** When updating `phase_summaries`, pass the complete updated list. `update_entity` merges at the top-level key level only; it does not append to lists automatically.

### get_entity

```
get_entity(type_id: str) -> entity dict or None
```

### get_lineage

```
get_lineage(
    type_id: str | None = None,
    direction: str = "up",                  # "up" (ancestors) or "down" (descendants)
    max_depth: int = 10,                    # Walk depth cap; default 10 levels
    ref: str | None = None,                 # Alternative to type_id
) -> str                                    # Formatted tree string, NOT a list
```

Returns a human-readable formatted tree, not a structured list. Parse caller-side if structured access is needed.

### append_phase_event

Sole write path for `entities.status` and `workflow_phases.workflow_phase` mutations (feature 109, FR-2 Path A). Returns the event uuid.

```
append_phase_event(
    type_id: str,
    event_type: str,                # see domain table below
    *,
    metadata: dict | None = None,   # event-specific JSON payload
    project_id: str | None = None,
    iterations: int | None = None,
    reviewer_notes: str | None = None,
) -> str                            # event uuid
```

**Event type domain (expanded from 4 → 7 values in feature 109):**

| `event_type` | `phase` | `metadata` | Projection target |
|-------------|---------|-----------|------------------|
| `started` | required | NULL | `workflow_phases.workflow_phase` |
| `completed` | required | NULL | `workflow_phases.workflow_phase` |
| `skipped` | required | NULL | `workflow_phases.workflow_phase` |
| `backward` | required (target phase) | NULL | `workflow_phases.workflow_phase` |
| `entity_created` | NULL | optional (creation context) | `entities.status` |
| `entity_status_changed` | NULL | **required** `{"old_status": ..., "new_status": ...}` | `entities.status` |
| `entity_promoted` | NULL | **required** `{"old_kind", "new_kind", "old_lifecycle_class", "new_lifecycle_class", "old_type_id", "new_type_id"}` | `entities.status` |

**Operation order (single transaction):** INSERT phase_events row → UPDATE `entities.status` (entity_* event types only) → UPDATE `workflow_phases.workflow_phase` (workflow event types only). If any UPDATE step raises, the transaction rolls back and the event row is also discarded.

Passing params that are invalid for the given `event_type` (e.g., `iterations=1` with `event_type='entity_created'`) raises `ValueError`.

## phase_events Schema (Feature 109)

Migration 12 extends the `phase_events` table via copy-rename:

| Column | Change | Notes |
|--------|--------|-------|
| `event_type` CHECK | Expanded 4 → 7 values | Adds `entity_created`, `entity_status_changed`, `entity_promoted` |
| `phase` | Relaxed `NOT NULL` → NULL-able | New entity event types have no meaningful `phase` value |
| `metadata` | **New column** `TEXT` (JSON), NULL-able | Event-specific payload; required for `entity_status_changed` and `entity_promoted` |
| `workspace_uuid` | **New column** `TEXT`, NULL-able | Workspace scope for entity events; NULL for workflow phase events |

Existing rows (`started`, `completed`, `skipped`, `backward`) remain valid after the migration — legacy data is preserved unchanged (append-only event log).

## Entity Metadata Contracts

Entity metadata is stored as a JSON string in the `metadata` column of `entities.db`. The `feature` entity type uses the following schema (defined in `metadata.py:METADATA_SCHEMAS['feature']`):

| Key | Type | Written by | Read by |
|-----|------|-----------|---------|
| `id` | str | create-feature command | _project_meta_json |
| `slug` | str | create-feature command | _project_meta_json |
| `mode` | str | create-feature command | _project_meta_json |
| `branch` | str | workflow-transitions skill | _project_meta_json |
| `phase_timing` | dict | _process_complete_phase | _project_meta_json, validateAndSetup |
| `last_completed_phase` | str | workflow engine | _project_meta_json (fallback) |
| `skipped_phases` | list | validateAndSetup | _project_meta_json |
| `brainstorm_source` | str | create-feature command | _project_meta_json |
| `backlog_source` | str | create-feature command | _project_meta_json |
| `depends_on_features` | list | create-feature command | implement skill |
| `project_id` | str | create-feature command | implement skill |
| `phase_summaries` | list | commitAndComplete Step 3a (feature 075) | validateAndSetup Step 1b, _project_meta_json |
| `backward_context` | dict | handleReviewerResponse (feature 073) | validateAndSetup Step 1b, _project_meta_json |
| `backward_return_target` | str | handleReviewerResponse (feature 073) | validateAndSetup, _project_meta_json |
| `backward_history` | list | handleReviewerResponse (feature 073) | audit only — NOT projected to .meta.json |

Unknown keys produce validation warnings from `validate_metadata()` but never block writes.

## .meta.json Contract

`.meta.json` is the read surface for feature state in the current session. It is regenerated by `_project_meta_json()` after every state mutation. Skills and commands must not write to it directly.

### Field Reference

```json
{
  "id": "075-phase-context-accumulation",
  "slug": "phase-context-accumulation",
  "mode": "standard",
  "status": "active",
  "created": "2026-04-02T00:00:00Z",
  "branch": "feature/075-phase-context-accumulation",
  "lastCompletedPhase": "design",
  "phases": {
    "specify": {
      "started": "2026-04-02T08:00:00Z",
      "completed": "2026-04-02T09:00:00Z",
      "iterations": 3,
      "reviewerNotes": ["Reviewer note text"]
    }
  },
  "backward_context": {
    "source_phase": "design",
    "findings": [
      {
        "artifact": "spec.md",
        "section": "AC-3",
        "issue": "Gap in acceptance criteria",
        "suggestion": "Add edge case for empty input"
      }
    ],
    "downstream_impact": "Design assumptions may be invalid."
  },
  "backward_return_target": "design",
  "phase_summaries": [
    {
      "phase": "specify",
      "timestamp": "2026-04-02T09:00:00Z",
      "outcome": "Approved after 3 iterations.",
      "artifacts_produced": ["spec.md"],
      "key_decisions": "Chose append-list storage over keyed dict for rework history preservation.",
      "reviewer_feedback_summary": "Reviewer requested tighter AC scoping in first iteration.",
      "rework_trigger": null
    }
  ]
}
```

### Backward Transition Detection

Skills detect backward transitions by checking `.meta.json`:

```python
def is_backward_transition(phase_name: str, meta_json: dict) -> bool:
    phase_timing = meta_json.get("phases", {})
    target_phase_timing = phase_timing.get(phase_name, {})
    return "completed" in target_phase_timing
```

Note: `.meta.json` projects `phase_timing` as `phases` (see `_project_meta_json` line 377). Detection reads from `.meta.json`, hence uses the `phases` key.

<!-- AUTO-GENERATED: END -->
