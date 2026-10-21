# Plan: Kanban Column Lifecycle Fix

## Implementation Order

Tasks follow TDD: write failing tests first, then implement to make them pass.

### Phase 1: Shared Constant (foundation for all other changes)

**Task 1: Create `workflow_engine/constants.py` with `FEATURE_PHASE_TO_KANBAN`**
- File: `plugins/iflow/hooks/lib/workflow_engine/constants.py` (new)
- Create module with the 7-entry mapping dict
- No imports needed — pure data
- Why first: every subsequent task imports from this module
- AC: AC-10

**Task 2: Unit test for `FEATURE_PHASE_TO_KANBAN` completeness**
- File: `plugins/iflow/hooks/lib/workflow_engine/test_constants.py` (new)
- Test all 7 phases from `PHASE_SEQUENCE` are present
- Test all values are valid kanban columns (hardcoded set: backlog, prioritised, wip, agent_review, human_review, blocked, documenting, completed — matches UI board columns)
- Depends on: Task 1
- AC: AC-10

### Phase 2: Engine backfill fix (low-risk, isolated)

**Task 3a: Write failing test for engine degraded-mode backfill kanban**
- File: `plugins/iflow/hooks/lib/workflow_engine/test_workflow_engine.py` (existing)
- Test: when engine.get_state() triggers degraded-mode backfill (no DB row), the created workflow_phases row has kanban_column from FEATURE_PHASE_TO_KANBAN (not "backlog")
- Test should FAIL initially
- Depends on: Task 1
- AC: R8

**Task 3b: Pass `kanban_column` in engine degraded-mode backfill**
- File: `plugins/iflow/hooks/lib/workflow_engine/engine.py` (~line 590)
- Import `FEATURE_PHASE_TO_KANBAN` from `.constants`
- Add `kanban_column=FEATURE_PHASE_TO_KANBAN.get(state.current_phase, "backlog")` to `create_workflow_phase()` call
- Makes Task 3a test pass
- Depends on: Task 3a
- AC: R8

### Phase 3: Reconciliation (detect + fix drift) — TDD

**Task 4a: Write failing unit tests for `_derive_expected_kanban()` helper** ← TDD RED
- File: `plugins/iflow/hooks/lib/workflow_engine/test_reconciliation.py` (same package as reconciliation module)
- Test cases:
  - None phase → returns None
  - finish+finish → returns "completed"
  - finish+specify → returns "documenting"
  - implement+specify → returns "wip"
  - unknown phase → returns None
- Tests should FAIL initially (helper not yet implemented)
- Depends on: Task 1

**Task 4b: Implement `_derive_expected_kanban()` helper** ← TDD GREEN
- File: `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py`
- Add import: `from .constants import FEATURE_PHASE_TO_KANBAN`
- Add pure function with signature `(workflow_phase: str | None, last_completed_phase: str | None) -> str | None`
- Three branches: None→None, finish+finish→completed, otherwise→lookup
- Makes Task 4a tests pass
- Depends on: Task 4a

**Task 5: Write failing tests for kanban drift detection and reconciliation fix**
- File: `plugins/iflow/hooks/lib/workflow_engine/test_reconciliation.py`
- Test: _check_single_feature detects kanban drift (DB=backlog, expected=wip → WorkflowMismatch with field="kanban_column")
- Test: _check_single_feature no false positive when kanban matches
- Test: _reconcile_single_feature corrects kanban_column via update_workflow_phase
- Test: _reconcile_single_feature skips kanban_column when _derive_expected_kanban returns None
- These tests should FAIL initially (kanban check/fix not yet implemented)
- Depends on: Task 4b
- AC: AC-4, AC-5

**Task 6: Implement kanban drift detection in `_check_single_feature()`**
- File: `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py` (~line 236)
- Call `_derive_expected_kanban(state.current_phase, state.last_completed_phase)`
- Compare against `row["kanban_column"]`, append `WorkflowMismatch` if different
- Makes Task 5 drift detection tests pass
- Depends on: Task 5
- AC: AC-4

**Task 7: Implement kanban fix in `_reconcile_single_feature()`**
- File: `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py` (~line 296)
- Call `_derive_expected_kanban(meta["workflow_phase"], meta["last_completed_phase"])`
- Use kwargs dict pattern — only include `kanban_column` when not None (avoids NULL corruption)
- Makes Task 5 reconciliation fix tests pass
- Depends on: Task 5
- AC: AC-5

### Phase 4: MCP server changes (transition + complete + init) — TDD

**Task 8: Write failing integration tests for MCP server kanban updates**
- File: `plugins/iflow/mcp/test_workflow_state_server.py` (existing)
- Test: transition_phase to implement → kanban_column="wip" (AC-1)
- Test: complete_phase finish → kanban_column="completed" (AC-2)
- Test: complete_phase specify → kanban_column="prioritised" via state.current_phase=design (AC-3)
- Test: complete_phase design → kanban_column="prioritised" via state.current_phase=create-plan (AC-3b)
- Test: init_feature_state with status="active" → kanban_column="wip" (AC-6)
- Test: init_feature_state with status="planned" → kanban_column="backlog"
- These tests should FAIL initially
- Depends on: Task 1
- AC: AC-1, AC-2, AC-3, AC-3b, AC-6

**Task 9: Implement `_process_transition_phase()` kanban update**
- File: `plugins/iflow/mcp/workflow_state_server.py` (~line 503)
- Add feature guard + FEATURE_PHASE_TO_KANBAN lookup + db.update_workflow_phase call
- Insert after db.update_entity() call (line 521). _project_meta_json (line 524) does not modify workflow_phases, so placement relative to it is safe
- Makes Task 8 transition tests pass
- Depends on: Task 8
- AC: AC-1

**Task 10: Implement `_process_complete_phase()` kanban update**
- File: `plugins/iflow/mcp/workflow_state_server.py` (~line 578)
- Add feature guard + conditional logic (finish→completed, else→lookup from state.current_phase)
- Insert after db.update_entity() call (line 578) and before _project_meta_json (line 581)
- Makes Task 8 complete tests pass
- Depends on: Task 8
- AC: AC-2, AC-3, AC-3b

**Task 11: Implement `_process_init_feature_state()` kanban override**
- File: `plugins/iflow/mcp/workflow_state_server.py` (~line 726)
- Add STATUS_TO_KANBAN inline dict (with cross-ref comments to backfill.py:35-40 and scripts/fix_kanban_columns.py)
- Insert AFTER _project_meta_json() call which triggers engine hydration → create_workflow_phase
- The try/except ValueError guards against engine initialization failure where create_workflow_phase didn't execute. Verified: database.py:1377 raises `ValueError("Workflow phase not found: {type_id}")` when the row doesn't exist
- Makes Task 8 init tests pass
- Depends on: Task 8
- AC: AC-6

### Phase 5: Data remediation — TDD

**Task 12: Write failing test for remediation script**
- File: `scripts/test_fix_kanban_columns.py` (new)
- Create in-memory DB with both `entities` and `workflow_phases` tables
- Insert synthetic features: planned, active, completed, abandoned statuses — all with kanban_column="backlog"
- Insert an orphaned workflow_phases row (no matching entity) to test ELSE clause
- Define expected kanban_column per STATUS_TO_KANBAN
- Test should FAIL initially (script not yet implemented)
- AC: AC-7

**Task 13: Implement `scripts/fix_kanban_columns.py` remediation script**
- File: `scripts/fix_kanban_columns.py` (new)
- Python script using sqlite3 to run the STATUS_TO_KANBAN-based UPDATE
- Accept DB path as argument (default: `~/.claude/iflow/entities/entities.db`)
- Dry-run mode (--dry-run) to show what would change
- ELSE clause to preserve orphaned rows
- STATUS_TO_KANBAN inline with cross-ref comments to backfill.py:35-40 and workflow_state_server.py
- Makes Task 12 test pass
- Depends on: Task 12
- AC: AC-7

### Phase 6: Regression verification

**Task 14: Run full existing test suite**
- No file changes
- Run all test commands from CLAUDE.md
- Verify zero regressions, specifically AC-8: brainstorm entity transition_entity_phase still sets kanban correctly
- Depends on: Tasks 1-13
- AC: AC-8, AC-9

## Dependency Graph

```
Task 1 (constants.py)
├── Task 2 (test constants)
├── Task 3a (failing engine backfill test) ← TDD RED
│   └── Task 3b (engine backfill impl) ← TDD GREEN
├── Task 4a (failing helper tests) ← TDD RED
│   └── Task 4b (helper impl) ← TDD GREEN
│       └── Task 5 (failing recon tests) ← TDD RED
│       ├── Task 6 (drift detection impl) ← TDD GREEN
│       └── Task 7 (recon fix impl) ← TDD GREEN
├── Task 8 (failing MCP tests) ← TDD RED
│   ├── Task 9 (transition impl) ← TDD GREEN
│   ├── Task 10 (complete impl) ← TDD GREEN
│   └── Task 11 (init impl) ← TDD GREEN
└── Task 12 (failing remediation test) ← TDD RED
    └── Task 13 (remediation impl) ← TDD GREEN

Task 14 (regression) ← depends on all above
```

## Parallel Execution Opportunities

After Task 1 completes, Tasks 2, 3a, 4a, 8, and 12 can proceed in parallel (different files, independent test suites). Note: Tasks 9-11 each depend on Task 8 being in RED (tests failing) before implementation begins.

## Risk Mitigation During Implementation

- Run existing tests after each phase to catch regressions early
- Phase 3 (reconciliation) is safest to implement first — read-only detection path
- Phase 4 (MCP server) modifies the hot path — test thoroughly before Phase 5
- Phase 5 (remediation) runs last, only on production DB after all code changes verified
