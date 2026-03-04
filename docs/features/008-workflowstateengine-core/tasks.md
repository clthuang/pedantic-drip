# Tasks: WorkflowStateEngine Core (Feature 008)

## Phase 1: Module Scaffold + Models

### Task 1.1: Create module directory and conftest.py
- **Action:** Create `plugins/iflow/hooks/lib/workflow_engine/` directory, empty `__init__.py`, and `conftest.py` with `sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))` to resolve `transition_gate`
- **Done when:** Directory exists, `__init__.py` is empty, `conftest.py` has sys.path insert
- **Dependencies:** None

### Task 1.2: Write frozen dataclass tests (RED)
- **Action:** Create `test_engine.py` with `TestModels` class: `test_frozen_attribute_raises`, `test_completed_phases_tuple_immutable`
- **Done when:** Tests exist and fail with `ImportError` (models.py not yet created)
- **Dependencies:** Task 1.1

### Task 1.3: Implement FeatureWorkflowState dataclass (GREEN)
- **Action:** Create `models.py` with `FeatureWorkflowState` frozen dataclass — 6 fields: `feature_type_id: str`, `current_phase: str | None`, `last_completed_phase: str | None`, `completed_phases: tuple[str, ...]`, `mode: str | None`, `source: str`
- **Done when:** `TestModels` tests pass
- **Dependencies:** Task 1.2

### Task 1.4: Create engine.py skeleton
- **Action:** Create `engine.py` with `WorkflowStateEngine` class skeleton — `__init__(self, db: EntityDatabase, artifacts_root: str)` storing references only; all public method stubs raising `NotImplementedError`
- **Done when:** Class is importable, constructor stores `self.db` and `self.artifacts_root`
- **Dependencies:** Task 1.3

### Task 1.5: Update __init__.py with public API
- **Action:** Add exports: `from .engine import WorkflowStateEngine` and `from .models import FeatureWorkflowState`; set `__all__ = ["WorkflowStateEngine", "FeatureWorkflowState"]`
- **Done when:** `from workflow_engine import WorkflowStateEngine, FeatureWorkflowState` succeeds
- **Dependencies:** Task 1.4

## Phase 2: Private Helpers

### Task 2.1: Write _extract_slug tests (RED)
- **Action:** Add `TestHelpers` class with `test_extract_slug_valid` (`"feature:008-foo"` → `"008-foo"`), `test_extract_slug_missing_colon` (raises `ValueError`), `test_extract_slug_empty` (raises `ValueError`)
- **Done when:** 3 tests exist and fail (method not implemented)
- **Dependencies:** Task 1.5

### Task 2.2: Implement _extract_slug (GREEN)
- **Action:** Implement `_extract_slug(self, feature_type_id)` — split on `":"`, return second part, raise `ValueError` for malformed input
- **Done when:** All 3 `TestHelpers._extract_slug` tests pass
- **Dependencies:** Task 2.1

### Task 2.3: Write _derive_completed_phases tests (RED)
- **Action:** Add to `TestHelpers`: `test_derive_completed_phases_none` (returns `()`), `test_derive_completed_phases_specify` (returns `("brainstorm", "specify")`), `test_derive_completed_phases_finish` (returns all 7 phases), `test_derive_completed_phases_unknown` (raises `ValueError`)
- **Done when:** 4 tests exist and fail
- **Dependencies:** Task 2.2

### Task 2.4: Implement _derive_completed_phases (GREEN)
- **Action:** Implement: extract `.value` from `Phase` enum members — `tuple(p.value for p in PHASE_SEQUENCE[:idx+1])` or `()` if None. Raise `ValueError` for unrecognized phase
- **Done when:** All 4 `_derive_completed_phases` tests pass
- **Dependencies:** Task 2.3

### Task 2.5: Write _next_phase_value tests (RED)
- **Action:** Add to `TestHelpers`: `test_next_phase_value_specify_to_design`, `test_next_phase_value_finish_returns_none`, `test_next_phase_value_unknown` (raises `ValueError`)
- **Done when:** 3 tests exist and fail
- **Dependencies:** Task 2.4

### Task 2.6: Implement _next_phase_value (GREEN)
- **Action:** Implement: `PHASE_SEQUENCE[idx+1].value` or `None` at end. Raise `ValueError` for unrecognized phase
- **Done when:** All 3 `_next_phase_value` tests pass
- **Dependencies:** Task 2.5

### Task 2.7: Write _get_existing_artifacts tests (RED)
- **Action:** Add to `TestHelpers`: `test_get_existing_artifacts_some_present` (create spec.md + design.md in tmp_path), `test_get_existing_artifacts_none_present`, `test_get_existing_artifacts_all_present`. Also: `test_hard_prerequisites_import` — verify `from transition_gate.constants import HARD_PREREQUISITES; assert isinstance(HARD_PREREQUISITES, dict)`. Use pytest `tmp_path` fixture for filesystem isolation
- **Done when:** 4 tests exist; 3 filesystem tests fail (method not implemented), `test_hard_prerequisites_import` passes immediately
- **Dependencies:** Task 2.6

### Task 2.8: Implement _get_existing_artifacts (GREEN)
- **Action:** Implement: scan `{artifacts_root}/features/{slug}/` for filenames from `HARD_PREREQUISITES` values (flattened set). Return sorted list of existing filenames
- **Done when:** All 4 `_get_existing_artifacts` tests pass
- **Dependencies:** Task 2.7

### Task 2.9: Define _GATE_GUARD_IDS class variable
- **Action:** Add `_GATE_GUARD_IDS: ClassVar[dict[str, str]]` mapping: `check_backward_transition→G-18`, `check_hard_prerequisites→G-08`, `check_soft_prerequisites→G-23`, `validate_transition→G-22`
- **Done when:** `WorkflowStateEngine._GATE_GUARD_IDS` is accessible and has 4 entries
- **Dependencies:** Task 1.4

## Phase 3: State Reading + Hydration

### Task 3.1: Write _hydrate_from_meta_json tests (RED)
- **Action:** Create `TestHydration` class with tests: `test_hydrate_active_status`, `test_hydrate_completed_status` (workflow_phase="finish"), `test_hydrate_planned_status`, `test_hydrate_unknown_status`, `test_hydrate_missing_entity` (returns None), `test_hydrate_missing_meta_json` (returns None), `test_hydrate_malformed_meta_json` (unrecognized phase → returns None), `test_hydrate_concurrent_race` (ValueError "already exists" → fallback to get), `test_hydrate_active_finished_edge` (active + lastCompletedPhase="finish" → workflow_phase="finish"), `test_hydrate_active_no_completed_phase` (active + lastCompletedPhase=None → workflow_phase=PHASE_SEQUENCE[0].value)
- **Done when:** 10 tests exist and fail
- **Dependencies:** Task 2.8

### Task 3.2: Implement _hydrate_from_meta_json (GREEN)
- **Action:** Implement full hydration: check entity exists → check .meta.json → parse JSON → derive state by status (active 3-way derivation, completed→"finish", planned→None, catch-all→None) → create_workflow_phase() with try/except ValueError "already exists" → fallback to get_workflow_phase() → return FeatureWorkflowState(source="meta_json"). Catch ValueError from _derive_completed_phases for malformed data → return None
- **Done when:** All 10 `TestHydration` tests pass
- **Dependencies:** Task 3.1

### Task 3.3: Write get_state tests (RED)
- **Action:** Create `TestGetState` class: `test_get_state_db_row_exists` (source="db" path), `test_get_state_db_missing_meta_exists` (SC-4 + SC-9: source="meta_json"), `test_get_state_both_missing_returns_none`, `test_get_state_missing_feature_returns_none` (entity not registered, no .meta.json → returns None)
- **Done when:** 4 tests exist and fail
- **Dependencies:** Task 3.2

### Task 3.4: Implement get_state (GREEN)
- **Action:** Implement: try `db.get_workflow_phase()` → if found, build FeatureWorkflowState from dict (map type_id→feature_type_id, workflow_phase→current_phase, last_completed_phase, _derive_completed_phases, mode, source="db") → if None, call `_hydrate_from_meta_json()`
- **Done when:** All 4 `TestGetState` tests pass
- **Dependencies:** Task 3.3

## Phase 4: Gate Evaluation

### Task 4.1: Write _evaluate_gates tests (RED)
- **Action:** Create `TestGateEvaluation` class: `test_gate_order_all_applicable`, `test_skip_backward_when_last_completed_none`, `test_skip_validate_when_current_phase_none`, `test_yolo_overrides_soft_gates` (G-18/G-22/G-23 return override results), `test_yolo_does_not_override_hard_gate` (G-08 unchanged, runs normally even with yolo_active=True)
- **Done when:** 5 tests exist and fail
- **Dependencies:** Task 3.4, Task 2.9

### Task 4.2: Implement _evaluate_gates (GREEN)
- **Action:** Implement gate evaluation loop: iterate ordered gates (backward→hard→soft→validate), apply I6 skip conditions, for each non-skipped gate: if `yolo_active`, call `check_yolo_override(guard_id, True)` FIRST — if non-None, use override; if None, call gate normally. Pass `list(state.completed_phases)` at call sites (tuple→list cast)
- **Done when:** All 5 `TestGateEvaluation` tests pass
- **Dependencies:** Task 4.1

## Phase 5: Public Methods — Transition + Complete

### Task 5.1: Write transition_phase tests (RED)
- **Action:** Create `TestTransitionPhase` class: `test_forward_transition_success` (SC-1 partial), `test_blocked_missing_prerequisites` (SC-2), `test_backward_transition_warning` (SC-3), `test_yolo_mode_passthrough` (SC-8), `test_missing_feature_raises_valueerror`
- **Done when:** 5 tests exist and fail
- **Dependencies:** Task 4.2

### Task 5.2: Implement transition_phase (GREEN)
- **Action:** Implement: `get_state()` → ValueError if None → `_extract_slug()` → `_get_existing_artifacts()` → `_evaluate_gates()` → if all pass (`all(r.allowed for r in results)`): `update_workflow_phase(type_id, workflow_phase=target)` → return results
- **Done when:** All 5 `TestTransitionPhase` tests pass
- **Dependencies:** Task 5.1

### Task 5.3: Write complete_phase tests (RED)
- **Action:** Create `TestCompletePhase` class: `test_normal_completion_advances` (SC-5: specify→design), `test_terminal_phase_finish` (TD-8: workflow_phase="finish" not None), `test_backward_rerun_resets` (TD-6), `test_phase_mismatch_raises_valueerror`, `test_missing_feature_raises_valueerror`, `test_no_active_phase_raises_valueerror` (current_phase=None), `test_phase_mismatch_no_last_completed` (phase != current_phase AND last_completed_phase=None → ValueError)
- **Done when:** 7 tests exist and fail
- **Dependencies:** Task 5.2

### Task 5.4: Implement complete_phase (GREEN)
- **Action:** Implement: `get_state()` → ValueError if None → check current_phase not None → validate phase match or backward re-run (compare PHASE_SEQUENCE indices; if last_completed_phase is None, backward re-run is not applicable — raise ValueError on phase mismatch) → derive next via `_next_phase_value()` → terminal check: `if next_phase is None: next_phase = phase` → `update_workflow_phase(type_id, last_completed_phase=phase, workflow_phase=next_phase)` → re-read and return updated state
- **Done when:** All 7 `TestCompletePhase` tests pass
- **Dependencies:** Task 5.3

## Phase 6: Public Methods — Query + Validate

### Task 6.1: Write validate_prerequisites tests (RED)
- **Action:** Create `TestValidatePrerequisites` class: `test_returns_same_results_as_transition`, `test_no_db_write` (SC-6: verify workflow_phase unchanged after call), `test_missing_feature_raises_valueerror`
- **Done when:** 3 tests exist and fail
- **Dependencies:** Task 5.4

### Task 6.2: Implement validate_prerequisites (GREEN)
- **Action:** Implement: `get_state()` → ValueError if None → `_extract_slug()` → `_get_existing_artifacts()` → `_evaluate_gates(state, target_phase, existing_artifacts, yolo_active=False)` → return results. No `update_workflow_phase` call. Always pass `yolo_active=False` — validate_prerequisites is a pure dry-run with no YOLO override
- **Done when:** All 3 `TestValidatePrerequisites` tests pass
- **Dependencies:** Task 6.1

### Task 6.3: Write list_by_phase tests (RED)
- **Action:** Add to `TestBatchQueries` class: `test_list_by_phase_matches`, `test_list_by_phase_empty`
- **Done when:** 2 tests exist and fail
- **Dependencies:** Task 6.2

### Task 6.4: Implement list_by_phase (GREEN)
- **Action:** Implement: `db.list_workflow_phases(workflow_phase=phase)` → map each row dict to FeatureWorkflowState using same mapping as get_state DB path
- **Done when:** All 2 `TestBatchQueries.list_by_phase` tests pass
- **Dependencies:** Task 6.3

### Task 6.5: Write list_by_status tests (RED)
- **Action:** Add to `TestBatchQueries`: `test_list_by_status_matches`, `test_list_by_status_none_excluded`, `test_list_by_status_no_workflow_row` (SC-7: features without workflow_phases row included with current_phase=None)
- **Done when:** 3 tests exist and fail
- **Dependencies:** Task 6.4

### Task 6.6: Implement list_by_status (GREEN)
- **Action:** Implement: `db.list_entities(entity_type="feature")` → filter by `row["status"] == status` → for each, join with `get_workflow_phase()` → build FeatureWorkflowState (no workflow row: current_phase=None, last_completed_phase=None, completed_phases=(), mode=None, source="db")
- **Done when:** All 3 `TestBatchQueries.list_by_status` tests pass
- **Dependencies:** Task 6.5

## Phase 7: Integration Tests

### Task 7.1: Write full lifecycle integration test (RED+GREEN)
- **Action:** Write `test_full_lifecycle_all_6_phases` (SC-1): use `EntityDatabase(":memory:")` for DB fixture, `tmp_path` pytest fixture for artifacts directory, initialize `WorkflowStateEngine(db, str(tmp_path))`. Register entity via `db.create_entity(...)`. Create .meta.json in `tmp_path/features/{slug}/`. Call get_state (triggers hydration) → for each of 6 command phases: transition_phase() + create required artifacts + complete_phase() → verify final state. Interleave artifact creation per HARD_PREREQUISITES (specify→spec.md, design→design.md, create-plan→plan.md, create-tasks→tasks.md, implement→no new artifacts needed as spec.md+tasks.md already exist, finish→no prerequisites)
- **Done when:** Test passes end-to-end
- **Dependencies:** Task 6.6

### Task 7.2: Write gate coverage integration test (RED+GREEN)
- **Action:** Write `test_all_5_consumed_gates_exercised` (SC-10): patch all 5 gates — `transition_gate.check_backward_transition`, `transition_gate.check_hard_prerequisites`, `transition_gate.check_soft_prerequisites`, `transition_gate.validate_transition`, `transition_gate.check_yolo_override` — each with `side_effect=original_fn` so calls are tracked but still execute normally. Run a lifecycle scenario that exercises all gates. Assert `mock.call_count >= 1` for each of the 5 gates
- **Done when:** Test passes, all 5 gates verified with call_count >= 1
- **Dependencies:** Task 7.1

### Task 7.3: Write hydration-then-transition integration test (RED+GREEN)
- **Action:** Write `test_hydration_then_transition` (SC-4 + SC-9): feature with .meta.json but no DB row → get_state hydrates (source="meta_json") → transition succeeds using hydrated state
- **Done when:** Test passes
- **Dependencies:** Task 7.1

## Phase 8: Final Verification

### Task 8.1: Run full test suite
- **Action:** Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v` and verify all tests pass
- **Done when:** Zero failures, all tests listed above pass
- **Dependencies:** Task 7.3

### Task 8.2: Verify acceptance criteria
- **Action:** Verify each acceptance criterion concretely: (1) Module exists: `ls plugins/iflow/hooks/lib/workflow_engine/`. (2) 6 public methods: `python -c "from workflow_engine import WorkflowStateEngine; print([m for m in dir(WorkflowStateEngine) if not m.startswith('_')])"` lists exactly get_state, transition_phase, complete_phase, validate_prerequisites, list_by_phase, list_by_status. (3) All 10 SC: confirmed by test suite in Task 8.1. (4) Zero external deps: `grep -r "^import \|^from " plugins/iflow/hooks/lib/workflow_engine/ | grep -v "transition_gate\|entity_registry\|__future__\|dataclasses\|os\|json\|typing\|unittest\|pytest"` returns no matches. (5) No modifications: `git diff plugins/iflow/hooks/lib/transition_gate/ plugins/iflow/hooks/lib/entity_registry/` shows no changes
- **Done when:** All 5 verification commands produce expected results
- **Dependencies:** Task 8.1

## Dependency Graph

```
Phase 1 (sequential):
  1.1 → 1.2 → 1.3 → 1.4 → 1.5

Phase 2 (sequential, depends on 1.5):
  2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7 → 2.8
  2.9 (parallel with 2.1-2.8, depends only on 1.4)

Phase 3 (sequential, depends on 2.8):
  3.1 → 3.2 → 3.3 → 3.4

Phase 4 (sequential, depends on 3.4 + 2.9):
  4.1 → 4.2

Phase 5 (sequential, depends on 4.2):
  5.1 → 5.2 → 5.3 → 5.4

Phase 6 (sequential, depends on 5.4):
  6.1 → 6.2 → 6.3 → 6.4 → 6.5 → 6.6

Phase 7 (sequential, depends on 6.6):
  7.1 → 7.2 (parallel with 7.3)
       → 7.3

Phase 8 (sequential, depends on 7.2 + 7.3):
  8.1 → 8.2

Note: Plan states "all phases sequential — no parallelism" but two safe
parallel groups are introduced: Task 2.9 only requires 1.4 (engine skeleton),
not 2.8 — parallel execution is safe. Tasks 7.2 and 7.3 have independent
scopes (gate spy verification vs hydration path) — parallel execution is safe.
```

## Summary

- **Total tasks:** 30
- **Phases:** 8
- **Parallel groups:** 2 (Task 2.9 parallel with 2.1-2.8; Task 7.2 parallel with 7.3)
- **TDD pattern:** RED task (write failing tests) → GREEN task (implement to pass) in each phase
