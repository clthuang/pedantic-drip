# RCA: Feature kanban_column Never Updates from "backlog"

**Date:** 2026-03-09
**Severity:** High (user-visible, affects all features on kanban board)
**Status:** Root causes identified, fix not yet applied

## Problem Statement

Feature entities in the `workflow_phases` table retain their initial `kanban_column="backlog"` value throughout their entire lifecycle. Completed features appear stuck in the "backlog" column on the kanban board instead of moving to "completed" (or through "wip" during active development).

**Observed symptoms:**
- `feature:034-enforced-state-machine` -- workflow_phase=finish, kanban_column=backlog
- `feature:035-brainstorm-backlog-state-track` -- workflow_phase=finish, kanban_column=backlog, last_completed_phase=finish

## Root Causes (6 contributing causes)

### RC-1: No kanban_column parameter passed during feature workflow_phases creation

**Location:** `plugins/iflow/hooks/lib/workflow_engine/engine.py` line 590
**Evidence:** `create_workflow_phase()` is called with `workflow_phase`, `last_completed_phase`, and `mode` but NOT `kanban_column`. The default in `database.py` line 1252 is `kanban_column="backlog"`.

Every feature gets `kanban_column="backlog"` at row creation regardless of its actual status or phase.

### RC-2: `_process_transition_phase()` never updates kanban_column

**Location:** `plugins/iflow/mcp/workflow_state_server.py` lines 486-532
**Evidence:** After a successful transition, this function updates entity metadata (phase_timing) via `db.update_entity()` but never calls `db.update_workflow_phase()` with a kanban_column value. The workflow_phases row is untouched.

### RC-3: `_process_complete_phase()` never updates kanban_column

**Location:** `plugins/iflow/mcp/workflow_state_server.py` lines 537-587
**Evidence:** After completing a phase, this function updates entity metadata and sets entity status to "completed" for the terminal (finish) phase, but never calls `db.update_workflow_phase()` at all. The workflow_phases.kanban_column remains at its initial "backlog" value.

### RC-4: No feature phase-to-kanban mapping exists

**Location:** `plugins/iflow/mcp/workflow_state_server.py` lines 49-86
**Evidence:** `ENTITY_MACHINES` defines phase-to-kanban mappings for `brainstorm` and `backlog` entity types only. No equivalent mapping exists for features. Even if RC-2/RC-3 were fixed to attempt a kanban update, there would be no mapping to look up.

### RC-5: Drift detection ignores kanban_column

**Location:** `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py` lines 236-265
**Evidence:** `_check_single_feature()` compares `last_completed_phase`, `workflow_phase`, and `mode` between .meta.json and DB. It does NOT compare `kanban_column`. This means drift detection never identifies kanban column mismatches, and reconciliation never corrects them.

### RC-6: Reconciliation update skips kanban_column

**Location:** `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py` lines 296-301
**Evidence:** `_reconcile_single_feature()` calls `db.update_workflow_phase()` with only `workflow_phase`, `last_completed_phase`, and `mode`. Even when reconciling a meta_json_ahead feature, kanban_column is never included in the update.

## Interaction Effects

These causes form a closed system with no escape hatch:

1. **Creation** (RC-1): Sets kanban_column="backlog"
2. **Transitions** (RC-2): Never updates it
3. **Completions** (RC-3): Never updates it
4. **No mapping** (RC-4): Even if code tried, no mapping exists for features
5. **Drift detection** (RC-5): Never notices the problem
6. **Reconciliation** (RC-6): Never fixes it

The only code path that correctly computes feature kanban_column is `backfill.py` `backfill_workflow_phases()`, which uses `STATUS_TO_KANBAN` mapping. However, this only runs once during initial DB population and uses `INSERT OR IGNORE`, so it cannot correct existing rows.

## Entity Type Comparison

| Capability | Feature | Brainstorm | Backlog |
|---|---|---|---|
| Phase-to-kanban mapping | MISSING | ENTITY_MACHINES | ENTITY_MACHINES |
| Transition updates kanban | NO | YES (line 1028) | YES (line 1028) |
| Completion updates kanban | NO | N/A | N/A |
| Drift detects kanban | NO | N/A | N/A |
| Reconciliation fixes kanban | NO | N/A | N/A |
| Backfill sets kanban | YES (one-time) | YES (one-time) | YES (one-time) |

## Reproduction

Fully reproduced with automated scripts:
- `agent_sandbox/20260309/rca-kanban-column-drift/reproduction/reproduce_minimal.py` -- 5 independent confirmations
- `agent_sandbox/20260309/rca-kanban-column-drift/experiments/verify_all_update_paths.py` -- AST-based exhaustive search of all kanban_column write paths

## Files Requiring Changes

| File | What Needs to Change |
|---|---|
| `plugins/iflow/mcp/workflow_state_server.py` | Add feature entry to ENTITY_MACHINES or create separate mapping; update `_process_transition_phase()` and `_process_complete_phase()` to set kanban_column |
| `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py` | Add kanban_column to drift detection fields; include kanban_column in reconciliation updates |
| `plugins/iflow/hooks/lib/workflow_engine/engine.py` | Pass computed kanban_column to `create_workflow_phase()` in degraded-mode backfill |

## Data Remediation

Existing features with stale kanban_column values will need a one-time data fix. The backfill module's `STATUS_TO_KANBAN` mapping provides the correct logic:
- `planned` -> `backlog`
- `active` -> `wip`
- `completed` -> `completed`
- `abandoned` -> `completed`
