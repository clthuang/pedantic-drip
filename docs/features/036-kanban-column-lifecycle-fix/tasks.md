# Tasks: Kanban Column Lifecycle Fix

## Task Overview

| ID | Task | Est | Deps | AC |
|----|------|-----|------|----|
| 1 | Create constants.py with FEATURE_PHASE_TO_KANBAN | 5m | — | AC-10 |
| 2 | Unit test FEATURE_PHASE_TO_KANBAN completeness | 5m | 1 | AC-10 |
| 3a | Write failing engine backfill kanban test | 5m | 1 | R8 |
| 3b | Pass kanban_column in engine degraded-mode backfill | 5m | 3a | R8 |
| 4a | Write failing _derive_expected_kanban helper tests | 5m | 1 | — |
| 4b | Implement _derive_expected_kanban helper | 5m | 4a | — |
| 5 | Write failing kanban drift detection/reconciliation tests | 10m | 4b | AC-4, AC-5 |
| 6 | Implement kanban drift detection in _check_single_feature | 5m | 5 | AC-4 |
| 7 | Implement kanban fix in _reconcile_single_feature | 5m | 5 | AC-5 |
| 8a | Write failing MCP transition/complete kanban tests | 10m | 1 | AC-1,2,3,3b |
| 8b | Write failing MCP init_feature_state kanban tests | 10m | 1 | AC-6 |
| 9 | Implement _process_transition_phase kanban update | 5m | 8a | AC-1 |
| 10 | Implement _process_complete_phase kanban update | 5m | 8a | AC-2, AC-3, AC-3b |
| 11 | Implement _process_init_feature_state kanban override | 5m | 8b | AC-6 |
| 12 | Write failing remediation script test | 10m | — | AC-7 |
| 13 | Implement fix_kanban_columns.py remediation script | 10m | 12 | AC-7 |
| 14 | Run full regression test suite | 5m | 1-13 | AC-8, AC-9 |

## Parallel Groups

After Task 1: Tasks 2, 3a, 4a, 8a, 8b, 12 can run in parallel.

```
Group A: Task 2 (standalone)
Group B: Task 3a → 3b
Group C: Task 4a → 4b → Task 5 → Tasks 6, 7 (parallel)
Group D1: Task 8a → Tasks 9, 10 (parallel)
Group D2: Task 8b → Task 11
Group E: Task 12 → 13
Final:   Task 14 (after all above)
```

---

## Task 1: Create `constants.py` with `FEATURE_PHASE_TO_KANBAN`

**File:** `plugins/iflow/hooks/lib/workflow_engine/constants.py` (new)
**Deps:** None
**AC:** AC-10

### Steps
1. Create `plugins/iflow/hooks/lib/workflow_engine/constants.py`
2. Add module-level dict:
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
3. No `__init__.py` changes — consumers import directly via `from workflow_engine.constants import FEATURE_PHASE_TO_KANBAN` or `from .constants import FEATURE_PHASE_TO_KANBAN`

### Done when
- File exists with the 7-entry dict
- `python -c "from workflow_engine.constants import FEATURE_PHASE_TO_KANBAN; print(len(FEATURE_PHASE_TO_KANBAN))"` prints `7`

---

## Task 2: Unit test `FEATURE_PHASE_TO_KANBAN` completeness

**File:** `plugins/iflow/hooks/lib/workflow_engine/test_constants.py` (new)
**Deps:** Task 1
**AC:** AC-10

### Steps
1. Create `plugins/iflow/hooks/lib/workflow_engine/test_constants.py`
2. Import: `from transition_gate import PHASE_SEQUENCE` and `from workflow_engine.constants import FEATURE_PHASE_TO_KANBAN`
3. Write test `test_all_phases_mapped`: assert every phase in `PHASE_SEQUENCE` is a key in `FEATURE_PHASE_TO_KANBAN`
4. Write test `test_all_values_valid_kanban_columns`: assert every value in `FEATURE_PHASE_TO_KANBAN` is in the set `{"backlog", "prioritised", "wip", "agent_review", "human_review", "blocked", "documenting", "completed"}`
5. Run: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/test_constants.py -v`

### Done when
- Both tests pass
- All 7 phases covered, all values are valid kanban columns

---

## Task 3a: Write failing engine backfill kanban test

**File:** `plugins/iflow/hooks/lib/workflow_engine/test_engine.py` (existing)
**Deps:** Task 1
**AC:** R8

### Steps
1. Add test `test_degraded_mode_backfill_sets_kanban_from_phase` to `test_engine.py`
2. Test setup:
   - Create in-memory DB, register feature, create `.meta.json` with `last_completed_phase="design"` (so `current_phase` will be `create-plan`)
   - Create `WorkflowStateEngine` with `artifacts_root=tmp_path`
   - Call `engine.get_state(type_id)` — triggers degraded-mode backfill (no DB row exists)
3. Assert: `db.get_workflow_phase(type_id)["kanban_column"] == "prioritised"` (from `FEATURE_PHASE_TO_KANBAN["create-plan"]`)
   - Note: The engine derives `current_phase` as the phase immediately after `last_completed_phase` in `PHASE_SEQUENCE`. With `last_completed_phase="design"`, `current_phase` resolves to `"create-plan"`, so kanban_column should be `"prioritised"`.
4. Run test — should FAIL (current code always creates with `kanban_column="backlog"`)

### Done when
- Test exists and FAILS with `AssertionError: 'backlog' != 'prioritised'`

---

## Task 3b: Pass `kanban_column` in engine degraded-mode backfill

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py` (~line 590)
**Deps:** Task 3a
**AC:** R8

### Steps
1. Add module-level import at the top of engine.py alongside existing imports: `from .constants import FEATURE_PHASE_TO_KANBAN` — use module-level import here (NOT an inline/local import like the MCP server tasks use)
2. At line ~590, modify `create_workflow_phase()` call to include kanban_column:
   ```python
   self.db.create_workflow_phase(
       feature_type_id,
       kanban_column=FEATURE_PHASE_TO_KANBAN.get(state.current_phase, "backlog"),
       workflow_phase=state.current_phase,
       last_completed_phase=state.last_completed_phase,
       mode=state.mode,
   )
   ```
3. Run Task 3a test — should now PASS
4. Run full engine test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/test_engine.py -v`

### Done when
- Task 3a test passes
- All existing engine tests still pass

---

## Task 4a: Write failing `_derive_expected_kanban` helper tests

**File:** `plugins/iflow/hooks/lib/workflow_engine/test_reconciliation.py` (existing)
**Deps:** Task 1
**AC:** —

### Steps
1. Add import for `_derive_expected_kanban` to the imports block (will fail initially — function doesn't exist yet)
2. Add test class or test functions:
   - `test_derive_expected_kanban_none_phase`: `_derive_expected_kanban(None, None)` returns `None`
   - `test_derive_expected_kanban_finish_completed`: `_derive_expected_kanban("finish", "finish")` returns `"completed"`
   - `test_derive_expected_kanban_finish_in_progress`: `_derive_expected_kanban("finish", "specify")` returns `"documenting"`
   - `test_derive_expected_kanban_implement`: `_derive_expected_kanban("implement", "specify")` returns `"wip"`
   - `test_derive_expected_kanban_unknown_phase`: `_derive_expected_kanban("nonexistent", None)` returns `None`
3. Run tests — should FAIL with `ImportError` (function not yet defined)

### Done when
- Tests exist and FAIL because `_derive_expected_kanban` is not importable

---

## Task 4b: Implement `_derive_expected_kanban` helper

**File:** `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py`
**Deps:** Task 4a
**AC:** —

### Steps
1. Add import at top of reconciliation.py: `from .constants import FEATURE_PHASE_TO_KANBAN`
2. Add helper function before `_check_single_feature`:
   ```python
   def _derive_expected_kanban(
       workflow_phase: str | None,
       last_completed_phase: str | None,
   ) -> str | None:
       if workflow_phase is None:
           return None
       if workflow_phase == "finish" and last_completed_phase == "finish":
           return "completed"
       return FEATURE_PHASE_TO_KANBAN.get(workflow_phase)
   ```
3. Run Task 4a tests — should now PASS
4. Run full reconciliation test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/test_reconciliation.py -v`

### Done when
- All 5 helper tests pass
- All existing reconciliation tests still pass

---

## Task 5: Write failing kanban drift detection/reconciliation tests

**File:** `plugins/iflow/hooks/lib/workflow_engine/test_reconciliation.py` (existing)
**Deps:** Task 4b
**AC:** AC-4, AC-5

### Steps
1. Add test `test_check_single_feature_detects_kanban_drift`:
   - Setup: DB with `workflow_phase="implement"`, `kanban_column="backlog"`; meta.json with `current_phase="implement"`, `last_completed_phase="create-tasks"`
   - Call `_check_single_feature(db, type_id, state, tmp_path)`
   - Assert: result has mismatch with `field="kanban_column"`, `meta_json_value="wip"`, `db_value="backlog"`
2. Add test `test_check_single_feature_no_false_positive_kanban`:
   - Same setup but `kanban_column="wip"` in DB
   - Assert: no mismatch with `field="kanban_column"`
3. Add test `test_reconcile_single_feature_corrects_kanban`:
   - Setup: drift report with `meta_json_ahead` status, meta has `workflow_phase="implement"`, `last_completed_phase="create-tasks"`
   - Call `_reconcile_single_feature(db, report, dry_run=False)`
   - Assert: `db.get_workflow_phase(type_id)["kanban_column"] == "wip"`
4. Add test `test_reconcile_single_feature_skips_kanban_when_none`:
   - Setup: meta has `workflow_phase="nonexistent"` (so `_derive_expected_kanban` returns None)
   - Call `_reconcile_single_feature(db, report, dry_run=False)`
   - Assert: `kanban_column` unchanged (still "backlog")
5. Run tests — drift detection tests should FAIL (kanban check not yet in `_check_single_feature`)

### Done when
- Tests 1-2 FAIL (kanban drift detection not implemented)
- Tests 3-4 FAIL (kanban fix not implemented)

---

## Task 6: Implement kanban drift detection in `_check_single_feature`

**File:** `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py` (~line 258, before the `return` statement)
**Deps:** Task 5
**AC:** AC-4

### Steps
1. Add kanban drift check after the mode mismatch check (line ~257), before the `return` statement:
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
2. Run Task 5 drift detection tests — should now PASS
3. Run full reconciliation test suite

### Done when
- Task 5 drift detection tests (1, 2) pass
- All existing reconciliation tests pass

---

## Task 7: Implement kanban fix in `_reconcile_single_feature`

**File:** `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py` (~line 296)
**Deps:** Task 5
**AC:** AC-5

### Steps
1. In `_reconcile_single_feature`, replace the `db.update_workflow_phase()` call (lines 296-301) with kwargs pattern:
   ```python
   expected_kanban = _derive_expected_kanban(
       meta["workflow_phase"], meta["last_completed_phase"]
   )
   kwargs = dict(
       workflow_phase=meta["workflow_phase"],
       last_completed_phase=meta["last_completed_phase"],
       mode=meta["mode"],
   )
   if expected_kanban is not None:
       kwargs["kanban_column"] = expected_kanban
   db.update_workflow_phase(feature_type_id, **kwargs)
   ```
2. Run Task 5 reconciliation tests — should now PASS
3. Run full reconciliation test suite

### Done when
- Task 5 reconciliation tests (3, 4) pass
- All existing reconciliation tests pass

---

## Task 8a: Write failing MCP transition/complete kanban tests

**File:** `plugins/iflow/mcp/test_workflow_state_server.py` (existing)
**Deps:** Task 1
**AC:** AC-1, AC-2, AC-3, AC-3b

### Steps
1. Add test `test_transition_phase_sets_kanban_for_feature`:
   - Setup: feature at `brainstorm` phase, transition to `implement`
   - Assert: `db.get_workflow_phase(type_id)["kanban_column"] == "wip"`

2. Add test `test_complete_phase_finish_sets_kanban_completed`:
   - Setup: feature at `finish` phase, complete `finish`
   - Assert: `db.get_workflow_phase(type_id)["kanban_column"] == "completed"`

3. Add test `test_complete_phase_specify_sets_kanban_from_next_phase`:
   - Setup: feature at `specify` phase, complete `specify` → `state.current_phase` becomes `design`
   - Assert: `db.get_workflow_phase(type_id)["kanban_column"] == "prioritised"`

4. Add test `test_complete_phase_design_sets_kanban_from_next_phase`:
   - Setup: feature at `design` phase, complete `design` → `state.current_phase` becomes `create-plan`
   - Assert: `db.get_workflow_phase(type_id)["kanban_column"] == "prioritised"`

5. Run tests — all 4 should FAIL (kanban updates not yet implemented in MCP server)

### Done when
- All 4 tests exist and FAIL

---

## Task 8b: Write failing MCP init_feature_state kanban tests

**File:** `plugins/iflow/mcp/test_workflow_state_server.py` (existing)
**Deps:** Task 1
**AC:** AC-6

### Steps
1. Add test `test_init_feature_state_active_sets_kanban_wip`:
   - Construct engine: `engine = WorkflowStateEngine(db=db, artifacts_root=str(tmp_path))` — follow the engine fixture pattern in `test_engine.py`
   - Call `_process_init_feature_state(db=db, engine=engine, feature_dir=str(tmp_path/"features"/"099-test"), feature_id="099", slug="test", mode="standard", branch="feature/099-test", brainstorm_source=None, backlog_source=None, status="active", artifacts_root=str(tmp_path))`
   - Assert: `db.get_workflow_phase("feature:099-test")["kanban_column"] == "wip"`

2. Add test `test_init_feature_state_planned_sets_kanban_backlog`:
   - Same engine construction and call pattern but `status="planned"`, different feature_id/slug
   - Assert: `db.get_workflow_phase(type_id)["kanban_column"] == "backlog"`

3. Run tests — both should FAIL (kanban override not yet implemented in MCP server)

### Done when
- Both tests exist and FAIL

---

## Task 9: Implement `_process_transition_phase` kanban update

**File:** `plugins/iflow/mcp/workflow_state_server.py` (~line 521, after `db.update_entity()`)
**Deps:** Task 8a
**AC:** AC-1

### Steps
1. After `db.update_entity(feature_type_id, metadata=metadata)` (line 521), add:
   ```python
   # Update kanban_column for features based on phase
   if feature_type_id.startswith("feature:"):
       from workflow_engine.constants import FEATURE_PHASE_TO_KANBAN
       kanban = FEATURE_PHASE_TO_KANBAN.get(target_phase)
       if kanban:
           db.update_workflow_phase(feature_type_id, kanban_column=kanban)
   ```
2. Run Task 8a transition test — should now PASS
3. Run full MCP server test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`

### Done when
- Task 8a transition test passes
- All existing MCP server tests pass

---

## Task 10: Implement `_process_complete_phase` kanban update

**File:** `plugins/iflow/mcp/workflow_state_server.py` (~line 578, after `db.update_entity()`)
**Deps:** Task 8a
**AC:** AC-2, AC-3, AC-3b

### Steps
1. After `db.update_entity(feature_type_id, **update_kwargs)` (line 578), add:
   ```python
   # Update kanban_column for features based on completed phase
   if feature_type_id.startswith("feature:"):
       from workflow_engine.constants import FEATURE_PHASE_TO_KANBAN
       if phase == "finish":
           kanban = "completed"
       else:
           kanban = FEATURE_PHASE_TO_KANBAN.get(state.current_phase)
       if kanban:
           db.update_workflow_phase(feature_type_id, kanban_column=kanban)
   ```
2. Run Task 8a complete tests — should now PASS
3. Run full MCP server test suite

### Done when
- Task 8a complete tests (finish, specify, design) all pass
- All existing MCP server tests pass

---

## Task 11: Implement `_process_init_feature_state` kanban override

**File:** `plugins/iflow/mcp/workflow_state_server.py` (after `_project_meta_json()` call in `_process_init_feature_state`)
**Deps:** Task 8b
**AC:** AC-6

### Steps
1. After the `_project_meta_json(db, engine, feature_type_id, feature_dir)` call, before `result = {`, add:
   ```python
   # Fix kanban_column based on status (init-time uses STATUS_TO_KANBAN).
   # Inline copy — must match STATUS_TO_KANBAN in backfill.py:35-40.
   # See also: scripts/fix_kanban_columns.py
   STATUS_TO_KANBAN = {"active": "wip", "planned": "backlog",
                       "completed": "completed", "abandoned": "completed"}
   init_kanban = STATUS_TO_KANBAN.get(status)
   if init_kanban:
       try:
           db.update_workflow_phase(feature_type_id, kanban_column=init_kanban)
       except ValueError:
           pass  # Row may not exist if engine initialization failed
   ```
2. Run Task 8b init tests — should now PASS
3. Run full MCP server test suite

### Done when
- Task 8b init tests (active→wip, planned→backlog) pass
- All existing MCP server tests pass

---

## Task 12: Write failing remediation script test

**File:** `scripts/test_fix_kanban_columns.py` (new)
**Deps:** None
**AC:** AC-7

### Steps
1. Create `scripts/test_fix_kanban_columns.py`
2. Create in-memory SQLite DB with `entities` and `workflow_phases` tables matching production schema
3. Insert test data — all features with `kanban_column="backlog"`:
   - `feature:001-planned` with `entities.status="planned"` → expect `"backlog"`
   - `feature:002-active` with `entities.status="active"` → expect `"wip"`
   - `feature:003-completed` with `entities.status="completed"` → expect `"completed"`
   - `feature:004-abandoned` with `entities.status="abandoned"` → expect `"completed"`
   - `feature:005-orphaned` — in `workflow_phases` but NOT in `entities` → expect `"backlog"` (preserved)
4. Import and call: `from fix_kanban_columns import fix_kanban_columns; fix_kanban_columns(conn)` — the function accepts a `sqlite3.Connection` for testing
5. Assert each feature's kanban_column matches expected value
6. Run: `PYTHONPATH=scripts plugins/iflow/.venv/bin/python -m pytest scripts/test_fix_kanban_columns.py -v` — should FAIL (script not yet implemented)

### Done when
- Test exists and FAILS with `ImportError` or `ModuleNotFoundError`

---

## Task 13: Implement `scripts/fix_kanban_columns.py` remediation script

**File:** `scripts/fix_kanban_columns.py` (new)
**Deps:** Task 12
**AC:** AC-7

### Steps
1. Create `scripts/fix_kanban_columns.py` with:
   - `fix_kanban_columns(db_path_or_conn)` function (accepts path or sqlite3.Connection for testing)
   - SQL UPDATE using `CASE (SELECT status FROM entities WHERE entities.type_id = workflow_phases.type_id)` with `ELSE kanban_column` to preserve orphaned rows
   - `--dry-run` CLI flag to show changes without applying
   - `--db-path` CLI flag (default: `~/.claude/iflow/entities/entities.db`)
   - `STATUS_TO_KANBAN` inline dict with cross-ref comments to `backfill.py:35-40` and `workflow_state_server.py`
2. Run Task 12 test — should now PASS

### Done when
- Task 12 test passes (binary: all assertions in `test_fix_kanban_columns.py` green)

---

## Task 14: Run full regression test suite

**File:** No changes
**Deps:** Tasks 1-13 (all)
**AC:** AC-8, AC-9

### Steps
1. Run workflow engine tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v`
2. Run MCP server tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`
3. Run reconciliation tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_reconciliation.py -v`
4. Run transition gate tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/ -v`
5. Run entity registry tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
6. Run remediation test: `PYTHONPATH=scripts plugins/iflow/.venv/bin/python -m pytest scripts/test_fix_kanban_columns.py -v`
7. Verify AC-8 specifically: existing `transition_entity_phase` tests for brainstorm/backlog entities pass unchanged

### Done when
- Zero test failures across all 6 test suites
- No regressions in existing tests
