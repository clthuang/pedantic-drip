# Specification: Hook Migration — yolo-stop.sh and State-Writing Hooks

## Overview

Replace the hardcoded `phase_map` dictionary in `yolo-stop.sh` with the canonical `PHASE_SEQUENCE` from the transition gate constants module. The hook currently duplicates workflow phase ordering inline (lines 173-183) — this creates a maintenance burden and drift risk when the phase sequence changes. The state engine already defines the authoritative phase sequence in `transition_gate.constants.PHASE_SEQUENCE`.

Additionally, replace the inline `.meta.json` parsing for feature state (status, lastCompletedPhase) with a direct call to the workflow state engine's `get_state()` method, which already implements graceful degradation (falls back to `.meta.json` if the database is unavailable).

## Functional Requirements

### FR-1: Replace `phase_map` with `PHASE_SEQUENCE`-derived next-phase lookup

The `yolo-stop.sh` hook must derive the next phase from `transition_gate.constants.PHASE_SEQUENCE` instead of the hardcoded `phase_map` dict. The Python snippet on lines 172-184 must be replaced with an import from the transition gate module.

**Current behavior (lines 172-184):**
```python
phase_map = {
    'null': 'specify',
    'brainstorm': 'specify',
    'specify': 'design',
    'design': 'create-plan',
    'create-plan': 'create-tasks',
    'create-tasks': 'implement',
    'implement': 'finish',
}
last = '${LAST_COMPLETED_PHASE}'
print(phase_map.get(last, ''))
```

**Target behavior:**
Import `PHASE_SEQUENCE` from `transition_gate.constants` and compute next phase. The `null` → `specify` mapping must be preserved (feature with no completed phase should proceed to `specify`). The `brainstorm` → `specify` mapping is implicit in the sequence.

### FR-2: Replace inline `.meta.json` feature-finding with engine `get_state()`

The hook currently:
1. Scans `{artifacts_root}/features/*/.meta.json` for `status="active"` (lines 75-107)
2. Reads feature state by parsing `.meta.json` directly (lines 110-130)
3. Checks `lastCompletedPhase` and `status` fields (lines 132-135)

Replace steps 2-3 with a call to `WorkflowStateEngine.get_state()`, which:
- Reads from the database first
- Falls back to `.meta.json` parsing if database is unavailable (graceful degradation)
- Returns a `FeatureWorkflowState` object with `current_phase`, `last_completed_phase`, `completed_phases`, `mode`, and `source` fields

**Note:** Step 1 (active feature scanning) must remain as-is because `get_state()` requires a `feature_type_id` — the hook must still discover which feature is active first. The engine's `list_by_status("active")` could replace this, but that requires database availability (no graceful degradation for listing). Since the hook runs in all environments (including when DB is down), retain the filesystem scan for discovery.

### FR-3: Resolve PYTHONPATH for transition gate imports

The hook runs as a standalone bash script. It must set `PYTHONPATH` to include the `hooks/lib/` directory so that `transition_gate` and `workflow_engine` modules are importable. Use the existing plugin root detection pattern from `common.sh`.

**Path resolution:** The hook's `SCRIPT_DIR` already points to the hooks directory. `PYTHONPATH` should be set to `${SCRIPT_DIR}/lib` before invoking Python.

### FR-4: Preserve all existing controls

All existing YOLO controls must be preserved with identical behavior:
- YOLO mode check (lines 20-23)
- YOLO paused check (lines 25-29)
- Usage limit check (lines 32-69)
- Active feature scanning (lines 75-107) — filesystem-based, retained per FR-2 note
- Completion check: `status == "completed"` or feature workflow is at terminal phase (lines 132-135)
- Stuck detection (lines 148-154)
- Max iterations / stop count (lines 159-169)
- Block message format (lines 191-199)

### FR-5: Update hook tests

Existing tests in `hooks/tests/test-hooks.sh` that exercise `yolo-stop.sh` must continue to pass. No new test infrastructure is needed — the existing test cases cover the phase transition logic via `.meta.json` fixtures.

## Non-Functional Requirements

### NFR-1: No new dependencies

The hook must not introduce any new Python packages. `transition_gate` and `workflow_engine` are already available in the hooks/lib directory.

### NFR-2: Performance

The hook must complete within 500ms. The current hook completes in ~100ms. Adding the engine import may add ~50ms for module loading — acceptable.

### NFR-3: Graceful degradation

If the Python import fails (e.g., module path issues), the hook must fall back to the current hardcoded `phase_map` behavior rather than crashing. This is a safety net — not a long-term design.

### NFR-4: Stderr suppression

All Python subprocess calls must continue to suppress stderr (`2>/dev/null`) to prevent corrupting JSON output, per the hook development guide.

## Acceptance Criteria

- AC-1: `yolo-stop.sh` no longer contains a hardcoded `phase_map` dictionary
- AC-2: Next-phase lookup uses `transition_gate.constants.PHASE_SEQUENCE` as the source of truth
- AC-3: Given a feature with `lastCompletedPhase="specify"`, the hook produces `"Invoke /iflow:design"` in the block reason — identical to current behavior
- AC-4: Given a feature with `lastCompletedPhase=null`, the hook produces `"Invoke /iflow:specify"` — identical to current behavior
- AC-5: Given a feature with `lastCompletedPhase="finish"` or `status="completed"`, the hook exits cleanly (no block)
- AC-6: All existing tests in `test-hooks.sh` pass without modification
- AC-7: If `transition_gate` import fails, the hook falls back gracefully (does not crash or produce invalid JSON)
- AC-8: `WorkflowStateEngine.get_state()` is called to retrieve feature state, with the engine constructing from `.meta.json` path when database is unavailable
- AC-9: PYTHONPATH is set correctly to resolve `transition_gate` and `workflow_engine` imports

## Out of Scope

- Migrating `yolo-guard.sh` (PreToolUse hook) — separate feature or follow-up
- Migrating `session-start.sh` `.meta.json` parsing — separate concern
- Adding MCP client calls from bash hooks — hooks use Python library imports, not MCP protocol
- Changing the block message format
- Adding new test cases (existing coverage is sufficient for this migration)

## Technical Notes

- The `PHASE_SEQUENCE` constant is a tuple of `Phase` enum values. Each `Phase` has a `.value` attribute that returns the string name (e.g., `"specify"`, `"design"`). The `create_plan` enum member has value `"create-plan"` (hyphenated).
- The `WorkflowStateEngine` constructor requires `db: EntityDatabase` and `artifacts_root: str`. For the hook, the database may be unavailable — the engine handles this via graceful degradation internally.
- The engine's `get_state()` method accepts `feature_type_id` in format `"feature:{id}-{slug}"`.
