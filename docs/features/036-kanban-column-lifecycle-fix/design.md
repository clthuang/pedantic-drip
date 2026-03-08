# Design: Kanban Column Lifecycle Fix

## Prior Art Research

**Codebase patterns found:**
- `ENTITY_MACHINES` (workflow_state_server.py:49-86) — dict-of-dicts with `columns` sub-dict mapping phase→kanban_column for brainstorm/backlog. Used by `_process_transition_entity_phase()` which does atomic UPDATE of both `workflow_phase` and `kanban_column` in a single SQL statement.
- `STATUS_TO_KANBAN` (backfill.py:35-40) — status-based mapping (`planned→backlog`, `active→wip`, `completed→completed`, `abandoned→completed`). Used during initial DB population.
- `db.update_workflow_phase()` (database.py:1330) — accepts `kanban_column` as optional kwarg with `_UNSET` sentinel. Already supports partial updates.
- `db.create_workflow_phase()` (database.py:1248) — accepts `kanban_column` with default `"backlog"`. The engine's degraded-mode backfill (engine.py:590) never passes it.
- `workflow_engine/__init__.py` exports `WorkflowStateEngine` and `FeatureWorkflowState`. A new `constants.py` in this package is importable via `from workflow_engine.constants import ...` by both reconciliation.py (same package: `from .constants import ...`) and workflow_state_server.py (sys.path includes hooks/lib).

**Design principle:** Follow the existing `ENTITY_MACHINES.columns` pattern — a simple dict mapping phase→kanban_column, with the same atomic update approach.

## Architecture Overview

### Two Mapping Regimes

There are two distinct contexts where kanban_column is determined:

1. **Init-time (feature creation):** Entity status drives kanban — `active→wip`, `planned→backlog`. This matches `STATUS_TO_KANBAN` in backfill.py and ensures newly created features appear in the correct column immediately.

2. **Runtime (transitions & completions):** Workflow phase drives kanban — `brainstorm→backlog`, `implement→wip`, etc. This uses `FEATURE_PHASE_TO_KANBAN` and tracks the feature's progression through the pipeline.

**Why two mappings?** At creation, an active feature at phase `brainstorm` should show as `wip` (it's being worked on). After the first transition, the phase-based mapping takes over. The remediation script uses status-based mapping for the same reason — it corrects historical data to match what init-time should have set.

After remediation, runtime transitions use FEATURE_PHASE_TO_KANBAN. For active features in early phases (brainstorm/specify), the kanban column may change from `wip` to `backlog` on next transition — this is correct behavior as the phase-based mapping is authoritative during the lifecycle.

### Component Changes

**1. New file: `plugins/iflow/hooks/lib/workflow_engine/constants.py`**

Single constant shared between MCP server and reconciliation:

```python
FEATURE_PHASE_TO_KANBAN: dict[str, str] = {
    "brainstorm": "backlog",
    "specify": "backlog",
    "design": "prioritised",
    "create-plan": "prioritised",
    "create-tasks": "prioritised",
    "implement": "wip",
    "finish": "documenting",
}
```

`"finish"` maps to `"documenting"` (active finish phase). The terminal `"completed"` kanban value is derived conditionally: when `phase == "finish"` AND the feature is fully completed (R3 logic).

No changes to `workflow_engine/__init__.py` — `constants.py` is imported directly by consumers, not re-exported.

**2. `workflow_state_server.py` — 3 function changes**

Both `_process_transition_phase` and `_process_complete_phase` apply the same `feature_type_id.startswith("feature:")` guard before the kanban update. This is defensive — these functions currently only receive feature type_ids, but the guard prevents breakage if they're ever called with other entity types.

*a. `_process_transition_phase()` (line ~503):*
After `db.update_entity()` call, add kanban update for features:
```python
if feature_type_id.startswith("feature:"):
    from workflow_engine.constants import FEATURE_PHASE_TO_KANBAN
    kanban = FEATURE_PHASE_TO_KANBAN.get(target_phase)
    if kanban:
        db.update_workflow_phase(feature_type_id, kanban_column=kanban)
```

*b. `_process_complete_phase()` (line ~578):*
After `db.update_entity()` call, add kanban update for features:
```python
if feature_type_id.startswith("feature:"):
    from workflow_engine.constants import FEATURE_PHASE_TO_KANBAN
    if phase == "finish":
        kanban = "completed"
    else:
        kanban = FEATURE_PHASE_TO_KANBAN.get(state.current_phase)
    if kanban:
        db.update_workflow_phase(feature_type_id, kanban_column=kanban)
```

`state` is the return value of `engine.complete_phase()` (line 545) — `state.current_phase` is the phase the feature advanced INTO. If `state.current_phase` is not in `FEATURE_PHASE_TO_KANBAN`, `kanban` is None and the update is skipped (log warning).

*c. `_process_init_feature_state()` (line ~726):*
After `_project_meta_json()` call (which triggers engine hydration → `create_workflow_phase` via degraded-mode backfill), add explicit kanban correction:
```python
# Fix kanban_column based on status (init-time uses STATUS_TO_KANBAN)
STATUS_TO_KANBAN = {"active": "wip", "planned": "backlog",
                    "completed": "completed", "abandoned": "completed"}
init_kanban = STATUS_TO_KANBAN.get(status)
if init_kanban:
    try:
        db.update_workflow_phase(feature_type_id, kanban_column=init_kanban)
    except ValueError:
        pass  # Row may not exist yet in edge cases
```

This corrects the kanban_column AFTER the engine's degraded backfill creates the row with phase-based mapping. The init_feature_state flow is: `register_entity` → `_project_meta_json` → `engine.get_state()` → `create_workflow_phase(kanban=FEATURE_PHASE_TO_KANBAN[brainstorm]=backlog)` → **then** `update_workflow_phase(kanban=STATUS_TO_KANBAN[active]=wip)`. This satisfies AC-6.

**3. `engine.py` — degraded-mode backfill (line ~590)**

Pass `kanban_column` to `create_workflow_phase`:
```python
from workflow_engine.constants import FEATURE_PHASE_TO_KANBAN

kanban = FEATURE_PHASE_TO_KANBAN.get(state.current_phase, "backlog")
self.db.create_workflow_phase(
    feature_type_id,
    kanban_column=kanban,
    workflow_phase=state.current_phase,
    last_completed_phase=state.last_completed_phase,
    mode=state.mode,
)
```

This ensures the degraded-mode path creates rows with phase-appropriate kanban rather than always `"backlog"`.

**4. `reconciliation.py` — 2 function changes + 1 new helper**

New helper with explicit signature:

```python
from .constants import FEATURE_PHASE_TO_KANBAN

def _derive_expected_kanban(
    workflow_phase: str | None,
    last_completed_phase: str | None,
) -> str | None:
    """Derive expected kanban_column from workflow state.

    Parameters
    ----------
    workflow_phase : str | None
        Current workflow phase from .meta.json state.
    last_completed_phase : str | None
        Last completed phase from .meta.json state.

    Returns
    -------
    str | None
        Expected kanban column, or None if phase is None (skip comparison).
        Returns "completed" for terminal finish state (finish + finish).
        Otherwise looks up FEATURE_PHASE_TO_KANBAN.
    """
    if workflow_phase is None:
        return None
    if workflow_phase == "finish" and last_completed_phase == "finish":
        return "completed"
    return FEATURE_PHASE_TO_KANBAN.get(workflow_phase)
```

*a. `_check_single_feature()` (line ~236):*
After existing mismatch checks, add kanban drift detection. Passes `state.current_phase` and `state.last_completed_phase` from the FeatureWorkflowState:
```python
expected_kanban = _derive_expected_kanban(
    state.current_phase, state.last_completed_phase
)
if expected_kanban is not None and expected_kanban != row["kanban_column"]:
    mismatches.append(WorkflowMismatch(
        field="kanban_column",
        meta_json_value=expected_kanban,
        db_value=row["kanban_column"],
    ))
```

*b. `_reconcile_single_feature()` (line ~296):*
Add kanban_column to the update call. Passes `meta["workflow_phase"]` and `meta["last_completed_phase"]` from `report.meta_json`:
```python
expected_kanban = _derive_expected_kanban(
    meta["workflow_phase"], meta["last_completed_phase"]
)
db.update_workflow_phase(
    feature_type_id,
    workflow_phase=meta["workflow_phase"],
    last_completed_phase=meta["last_completed_phase"],
    mode=meta["mode"],
    kanban_column=expected_kanban,  # NEW
)
```

**5. Data remediation: `scripts/fix_kanban_columns.py`**

One-time script using STATUS_TO_KANBAN (status-based mapping, matching init-time semantics):

```python
"""One-time fix for stale feature kanban_column values.

Uses STATUS_TO_KANBAN (status-based) rather than FEATURE_PHASE_TO_KANBAN
(phase-based) because this remediates what init_feature_state should have
set at creation time. For active features in early phases (brainstorm/specify),
the kanban may change from 'wip' to 'backlog' on next runtime transition —
this is correct behavior as phase-based mapping becomes authoritative during
the feature lifecycle.

For completed/abandoned features, both mappings agree (→ 'completed').
"""

# SQL (idempotent):
UPDATE workflow_phases
SET kanban_column = CASE
    (SELECT status FROM entities WHERE entities.type_id = workflow_phases.type_id)
    WHEN 'planned' THEN 'backlog'
    WHEN 'active' THEN 'wip'
    WHEN 'completed' THEN 'completed'
    WHEN 'abandoned' THEN 'completed'
END,
updated_at = datetime('now')
WHERE type_id LIKE 'feature:%'
```

## Interface Design

### New Constant

```python
# plugins/iflow/hooks/lib/workflow_engine/constants.py

FEATURE_PHASE_TO_KANBAN: dict[str, str] = {
    "brainstorm": "backlog",
    "specify": "backlog",
    "design": "prioritised",
    "create-plan": "prioritised",
    "create-tasks": "prioritised",
    "implement": "wip",
    "finish": "documenting",
}
```

### New Helper

```python
# plugins/iflow/hooks/lib/workflow_engine/reconciliation.py

def _derive_expected_kanban(
    workflow_phase: str | None,
    last_completed_phase: str | None,
) -> str | None:
```

Callers:
- `_check_single_feature()` passes `(state.current_phase, state.last_completed_phase)` from FeatureWorkflowState
- `_reconcile_single_feature()` passes `(meta["workflow_phase"], meta["last_completed_phase"])` from report.meta_json dict

### Modified Function Signatures

No signature changes. All modifications add logic within existing function bodies using existing parameters.

### Data Flow

```
Feature created (init_feature_state)
  └→ _project_meta_json → engine.get_state() → create_workflow_phase(kanban=FEATURE_PHASE_TO_KANBAN[phase])
  └→ db.update_workflow_phase(kanban=STATUS_TO_KANBAN[status])  ← init-time override

Feature transitions (transition_phase MCP tool)
  └→ _process_transition_phase → db.update_workflow_phase(kanban=FEATURE_PHASE_TO_KANBAN[target])

Phase completed (complete_phase MCP tool)
  └→ _process_complete_phase → db.update_workflow_phase(kanban="completed" | FEATURE_PHASE_TO_KANBAN[next])

Drift detected (reconcile_check MCP tool)
  └→ _check_single_feature → _derive_expected_kanban(phase, last_completed) → compare vs row["kanban_column"]

Drift fixed (reconcile_apply MCP tool)
  └→ _reconcile_single_feature → db.update_workflow_phase(kanban=_derive_expected_kanban(...))
```

## Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Constant location | `workflow_engine/constants.py` | Avoids reconciliation.py importing from MCP server (dependency inversion). Both consumers import from workflow_engine package. No __init__.py changes needed. |
| Finish dual mapping | Dict maps `finish→documenting`; code handles `finish+completed→completed` | Simple dict can't have two values for same key. Conditional logic is 2 lines in helper. |
| Init-time kanban | Uses STATUS_TO_KANBAN (status-based) then overrides engine's phase-based default | New active features should appear as `wip`, not `backlog`. Phase-based takes over on first transition. |
| Data remediation | Standalone script, status-based | One-time operation. Status-based matches init-time semantics. Phase-based takes over at runtime. |
| Guard condition | `feature_type_id.startswith("feature:")` on both transition and complete | Defensive. Applied consistently to both functions. |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Feature transition updates kanban but fails mid-transaction | Low | Medium | Same SQLite connection (implicit transaction). Reconciliation catches drift. |
| Unknown phase in FEATURE_PHASE_TO_KANBAN lookup | Very Low | Low | `.get()` returns None, code skips update. |
| Reconciliation derives wrong expected kanban | Low | Medium | `_derive_expected_kanban` is pure function with explicit signature, well-tested. Same mapping everywhere. |
| Init-time kanban overwritten on first transition | Expected | None | By design — phase-based mapping is authoritative during lifecycle. |

## Test Plan

| Test Location | Coverage |
|---|---|
| `plugins/iflow/hooks/lib/workflow_engine/test_constants.py` | FEATURE_PHASE_TO_KANBAN completeness (AC-10) |
| `plugins/iflow/mcp/test_workflow_state_server.py` | transition_phase kanban (AC-1), complete_phase kanban (AC-2, AC-3, AC-3b), init_feature_state kanban (AC-6) |
| `plugins/iflow/hooks/lib/workflow_engine/test_reconciliation.py` | Kanban drift detection (AC-4), kanban reconciliation (AC-5) |
| `scripts/test_fix_kanban_columns.py` or inline | Data remediation on in-memory DB (AC-7) |
| Existing test suites | Regression (AC-8, AC-9) |
