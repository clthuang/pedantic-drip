# Spec: Kanban Column Lifecycle Fix

## Problem

Feature entities in `workflow_phases` retain `kanban_column="backlog"` throughout their lifecycle. Six contributing root causes form a closed system: no phase-to-kanban mapping for features, no kanban update in transition/completion code paths, and no drift detection or reconciliation for kanban_column.

RCA report: `docs/rca/20260309-kanban-column-drift.md`

## Requirements

### R1: Feature Phase-to-Kanban Mapping

Define a canonical mapping from feature workflow phases to kanban columns:

| Feature Phase | Kanban Column |
|---|---|
| brainstorm | backlog |
| specify | backlog |
| design | prioritised |
| create-plan | prioritised |
| create-tasks | prioritised |
| implement | wip |
| finish | documenting |

These 7 phases (brainstorm, specify, design, create-plan, create-tasks, implement, finish) are the complete set from `PHASE_SEQUENCE` in `backfill.py`. The mapping is exhaustive.

The constant `FEATURE_PHASE_TO_KANBAN` maps `"finish"` → `"documenting"` (the in-progress case). The terminal completed case (`kanban_column="completed"`) is handled by conditional logic in R3 when `phase == "finish"` and the feature is fully complete.

**Location:** Define `FEATURE_PHASE_TO_KANBAN` as a module-level dict in a shared location importable by both `workflow_state_server.py` and `reconciliation.py`. Recommended: add to `plugins/iflow/hooks/lib/workflow_engine/constants.py` (or create if absent) since both modules already import from the workflow_engine package. This avoids reconciliation.py importing from the MCP server (which would invert the dependency direction). Only `FEATURE_PHASE_TO_KANBAN` is added to constants.py — existing constants (`PHASE_SEQUENCE` in backfill.py, `STATUS_TO_KANBAN` in backfill.py) remain in their current locations; consolidation is out of scope.

### R2: Transition Phase Updates Kanban Column

`_process_transition_phase()` must update `workflow_phases.kanban_column` after a successful transition by:
1. Checking if `feature_type_id` starts with `"feature:"` (non-feature entities continue using existing `ENTITY_MACHINES`-based kanban logic via `transition_entity_phase`)
2. Looking up the target phase in `FEATURE_PHASE_TO_KANBAN`
3. Calling `db.update_workflow_phase(feature_type_id, kanban_column=mapped_column)`

Only applies when `transitioned == True` and `db is not None` and entity type is `"feature"`.

### R3: Complete Phase Updates Kanban Column

`_process_complete_phase()` must update `workflow_phases.kanban_column` after a successful completion by:
1. Checking if `feature_type_id` starts with `"feature:"`
2. Determining the kanban column:
   - If `phase == "finish"`: kanban_column = `"completed"` (terminal state)
   - Otherwise: after `engine.complete_phase()` returns the new state, use `state.current_phase` (which is the phase the feature has transitioned INTO after completion) as the lookup key in `FEATURE_PHASE_TO_KANBAN`. If `state.current_phase` is not in `FEATURE_PHASE_TO_KANBAN`, log a warning and leave kanban_column unchanged.
3. Calling `db.update_workflow_phase(feature_type_id, kanban_column=mapped_column)`

Only applies when `db is not None` and entity type is `"feature"`.

### R4: Reconciliation Detects Kanban Drift

`_check_single_feature()` in `reconciliation.py` must:
1. Derive the expected `kanban_column` from the `.meta.json` state using this logic:
   - If `workflow_phase == "finish"` AND `last_completed_phase == "finish"`: expected = `"completed"`
   - Otherwise: look up `workflow_phase` in `FEATURE_PHASE_TO_KANBAN`
2. Compare expected against `row["kanban_column"]`
3. If mismatched, add a `WorkflowMismatch(field="kanban_column", meta_json_value=expected, db_value=row["kanban_column"])` to the mismatches list

### R5: Reconciliation Fixes Kanban Column

`_reconcile_single_feature()` in `reconciliation.py` must:
1. Derive the expected `kanban_column` from `report.meta_json` state (same logic as R4)
2. Include `kanban_column=expected` in the `db.update_workflow_phase()` call

### R6: Init Feature State Sets Correct Initial Kanban

`init_feature_state` MCP tool (and its underlying `create_workflow_phase` call) must set `kanban_column` based on the initial status:
- `"active"` → `"wip"` (not `"backlog"`)
- `"planned"` → `"backlog"`

This aligns with `STATUS_TO_KANBAN` in `backfill.py`.

### R7: Data Remediation

Provide a one-time SQL remediation that fixes existing stale `kanban_column` values. The remediation must:
1. Join `workflow_phases` with `entities` on `type_id`
2. Set `kanban_column` based on entity status using `STATUS_TO_KANBAN` mapping
3. Only update rows where `type_id LIKE 'feature:%'`
4. Be idempotent (safe to run multiple times)

Implement as a standalone script at `scripts/fix_kanban_columns.py` (preferred for one-time operations — keeps backfill.py focused on initial population).

### R8: Engine Degraded-Mode Backfill Passes Kanban Column

`create_workflow_phase()` in `engine.py` (degraded-mode backfill path, ~line 590) must pass `kanban_column` derived from the feature's current phase using `FEATURE_PHASE_TO_KANBAN` (consistent with R1-R3). The engine has `current_phase` from `.meta.json` state, so no additional DB lookup is needed. Currently it omits `kanban_column`, inheriting the `"backlog"` default regardless of actual phase.

**Note:** This path is a safety net for degraded mode. Even if not fixed here, once the row exists with wrong kanban_column, R4/R5 reconciliation would correct it on the next reconcile run. However, fixing it at source prevents temporary drift.

## Acceptance Criteria

- AC-1: After `transition_phase("feature:X", "implement")`, the `workflow_phases` row for `feature:X` has `kanban_column="wip"`.
- AC-2: After `complete_phase("feature:X", "finish")`, the `workflow_phases` row for `feature:X` has `kanban_column="completed"`.
- AC-3: After `complete_phase("feature:X", "specify")`, the `workflow_phases` row for `feature:X` has `kanban_column="prioritised"` (mapped from `state.current_phase == "design"` after completion).
- AC-3b: After `complete_phase("feature:X", "design")`, the `workflow_phases` row has `kanban_column="prioritised"` (mapped from `state.current_phase == "create-plan"` after completion).
- AC-4: `reconcile_check()` detects kanban_column mismatch as a `WorkflowMismatch` with `field="kanban_column"`.
- AC-5: `reconcile_apply()` corrects kanban_column when `meta_json_ahead`.
- AC-6: A newly created active feature via `init_feature_state` has `kanban_column="wip"` (not `"backlog"`).
- AC-7: Running data remediation on a test DB with synthetic features in various statuses correctly sets kanban_column per `STATUS_TO_KANBAN`. Manual verification: existing production DB has feature:034 and feature:035 set to `kanban_column="completed"` after remediation.
- AC-8: Existing `transition_entity_phase` tests for brainstorm/backlog pass unchanged. Specifically: given a brainstorm entity in state `"draft"`, `transition_entity_phase` to `"reviewing"` sets `kanban_column="agent_review"`.
- AC-9: All existing tests pass without modification (no regressions).
- AC-10: `FEATURE_PHASE_TO_KANBAN` mapping is tested with a unit test verifying all 7 phases from `PHASE_SEQUENCE` map to valid kanban column values (one of: backlog, prioritised, wip, agent_review, human_review, blocked, documenting, completed).

## Scope Boundaries

### In Scope
- Feature kanban_column updates in transition_phase, complete_phase, reconciliation, and init
- Data remediation for existing stale rows
- New constant `FEATURE_PHASE_TO_KANBAN` in shared workflow_engine module
- Engine degraded-mode backfill kanban_column fix (R8)

### Out of Scope
- Refactoring features to use `ENTITY_MACHINES` (brainstorm/backlog use a different transition model — features use WorkflowStateEngine with gate functions, not a simple adjacency list)
- UI changes (the board already reads `kanban_column` correctly — it just gets wrong data)
- Changes to `transition_entity_phase` or `init_entity_workflow` (these already work for brainstorm/backlog)
- Changes to backfill.py initial population logic (existing backfill logic is correct for INSERT)

## Files to Modify

| File | Changes |
|---|---|
| `plugins/iflow/hooks/lib/workflow_engine/constants.py` | Add `FEATURE_PHASE_TO_KANBAN` constant (create file if absent) |
| `plugins/iflow/mcp/workflow_state_server.py` | Import `FEATURE_PHASE_TO_KANBAN`; update `_process_transition_phase()`, `_process_complete_phase()`, and `_process_init_feature_state()` to set kanban_column |
| `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py` | Import `FEATURE_PHASE_TO_KANBAN`; add kanban_column to `_check_single_feature()` drift comparison and `_reconcile_single_feature()` update call |
| `plugins/iflow/hooks/lib/workflow_engine/engine.py` | Pass kanban_column in degraded-mode `create_workflow_phase()` call |

## Test Strategy

- Unit tests for `FEATURE_PHASE_TO_KANBAN` completeness (all phases mapped, all values are valid kanban columns)
- Integration tests: transition_phase → verify kanban_column updated in DB
- Integration tests: complete_phase → verify kanban_column updated in DB
- Integration tests: reconcile_check → verify kanban_column mismatch detected
- Integration tests: reconcile_apply → verify kanban_column corrected
- Unit test: data remediation against in-memory DB with synthetic features in various statuses
- Regression: run full existing test suite to confirm no breakage
