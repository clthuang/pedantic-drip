# Implementation Plan: WorkflowStateEngine Core (Feature 008)

## Implementation Order

The plan follows a bottom-up TDD approach: models first (no dependencies), then helpers (depend on models), then public methods (depend on helpers), then integration tests. Each phase writes failing tests first (RED), then implements minimum code to pass (GREEN), then refactors.

### Phase 1: Module Scaffold + Models

**Goal:** Create the module directory, frozen dataclass, and verify immutability.
**Why this item:** Models are the leaf dependency — every other component depends on `FeatureWorkflowState`.
**Why this order:** No dependencies; must exist before anything else can be built.

1. Create `plugins/iflow/hooks/lib/workflow_engine/` directory and empty `__init__.py`. Also create `conftest.py` with `sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))` to ensure `transition_gate` is resolvable — this is a concrete deliverable, not conditional
2. RED: Write `test_engine.py` — `TestModels` class: verify frozen attribute assignment raises `FrozenInstanceError`, verify `completed_phases` tuple cannot be mutated (tests import `FeatureWorkflowState` from `models.py` — will fail until step 3)
3. GREEN: Create `models.py` — `FeatureWorkflowState` frozen dataclass (I2) — tests now pass
4. Create `engine.py` — `WorkflowStateEngine` class skeleton with constructor (C1)
5. Update `__init__.py` — public API exports (C3)

**Dependencies:** None (leaf node)
**Artifacts:** `models.py`, `__init__.py`, `engine.py` (skeleton), `test_engine.py` (TestModels), `conftest.py`

### Phase 2: Private Helpers

**Goal:** Implement and test all private helper methods.
**Why this item:** Helpers are the building blocks consumed by get_state, _evaluate_gates, and all public methods.
**Why this order:** Depends only on Phase 1 (models + skeleton). Must precede Phase 3 (get_state uses _derive_completed_phases, _extract_slug).

**2a. _extract_slug**
- RED: Write `TestHelpers.test_extract_slug_valid`, `test_extract_slug_missing_colon`, `test_extract_slug_empty`
- GREEN: Implement in `engine.py`: split on `":"`, return second part. Raise `ValueError` for malformed input (missing colon)

**2b. _derive_completed_phases**
- RED: Write `TestHelpers.test_derive_completed_phases_none`, `test_derive_completed_phases_specify`, `test_derive_completed_phases_finish`, `test_derive_completed_phases_unknown`
- GREEN: Implement: extract `.value` from Phase enum members — `tuple(p.value for p in PHASE_SEQUENCE[:idx+1])` or `()` if None. Raise `ValueError` for unrecognized phase. Note: `PHASE_SEQUENCE` contains `Phase` enum members, not strings; `.value` extraction is required to produce `tuple[str, ...]`

**2c. _next_phase_value**
- RED: Write `TestHelpers.test_next_phase_value_specify_to_design`, `test_next_phase_value_finish_returns_none`, `test_next_phase_value_unknown`
- GREEN: Implement: `PHASE_SEQUENCE[idx+1].value` or `None` at end. Raise `ValueError` for unrecognized phase

**2d. _get_existing_artifacts**
- RED: Write `TestHelpers.test_get_existing_artifacts_some_present`, `test_get_existing_artifacts_none_present`, `test_get_existing_artifacts_all_present`
- GREEN: Implement: scan feature directory for filenames from `HARD_PREREQUISITES`. Uses `self.artifacts_root` + filesystem checks
- Import verification test: `test_hard_prerequisites_import` — verify `from transition_gate.constants import HARD_PREREQUISITES; assert isinstance(HARD_PREREQUISITES, dict)` succeeds (concrete R1 mitigation). Note: `conftest.py` created in Phase 1 ensures `transition_gate` is resolvable regardless of how pytest is invoked. Tests requiring filesystem operations (e.g., `test_get_existing_artifacts_*`) use pytest's `tmp_path` fixture for isolated temp directories — no manual cleanup needed

**2e. _GATE_GUARD_IDS class variable**
- Define mapping: `check_backward_transition→G-18`, `check_hard_prerequisites→G-08`, `check_soft_prerequisites→G-23`, `validate_transition→G-22`
- No unit test needed (static data, verified via integration tests in Phase 4)

**Dependencies:** Phase 1 (models + skeleton)
**Artifacts:** Updated `engine.py`, `test_engine.py` (TestHelpers)

### Phase 3: State Reading + Hydration

**Goal:** Implement `get_state()` and `_hydrate_from_meta_json()`.
**Why this item:** State reading is consumed by every public method (transition_phase, complete_phase, validate_prerequisites, list_by_*).
**Why this order:** Depends on Phase 2 helpers (_derive_completed_phases, _extract_slug). Must precede Phase 4 (gate evaluation needs state).

**3a. _hydrate_from_meta_json**
- RED: Write `TestHydration` class — tests for: active status, completed status (workflow_phase="finish"), planned status, unknown status, missing entity, missing .meta.json, malformed .meta.json (unrecognized phase), concurrent hydration race (ValueError "already exists"), active-but-finished edge case (status="active" + lastCompletedPhase="finish" → workflow_phase="finish"), `test_hydrate_active_no_completed_phase` (active status + lastCompletedPhase=None → workflow_phase=PHASE_SEQUENCE[0].value)
- GREEN: Implement: check entity exists → check .meta.json exists → parse JSON → derive state by status → create_workflow_phase() → return FeatureWorkflowState
  - Handle all status paths per FR-6: active, completed, planned, catch-all
  - **Active status derivation:** For active features, derive workflow_phase from lastCompletedPhase:
    - If lastCompletedPhase is None: set workflow_phase = `PHASE_SEQUENCE[0].value` (i.e., "brainstorm") directly — do NOT call `_next_phase_value(None)` which would raise ValueError (test already listed in RED above)
    - If lastCompletedPhase is the terminal phase ("finish"): set workflow_phase="finish" (semantically contradictory but defensive — treat as effectively completed)
    - Otherwise: use `_next_phase_value(lastCompletedPhase)`
  - Catch `ValueError` from `_derive_completed_phases` for malformed data → return None
  - **Race condition handling:** Wrap `create_workflow_phase()` in try/except for `ValueError` (message contains "already exists"). EntityDatabase.create_workflow_phase() internally catches `sqlite3.IntegrityError` and re-raises as `ValueError("Workflow phase already exists for: {type_id}")`. On this specific ValueError, fall back to `get_workflow_phase()` which returns the row created by the concurrent caller. Distinguish from other ValueErrors (e.g., "Entity not found") by checking the message substring "already exists".

**3b. get_state**
- RED: Write `TestGetState` class — tests for: DB row exists (SC-9 source="db"), DB row missing but .meta.json exists (SC-4 source="meta_json"), both missing returns None
- GREEN: Implement: try `db.get_workflow_phase()` → if found, build from DB → if None, call `_hydrate_from_meta_json()`
  - **DB dict-to-dataclass mapping:** `get_workflow_phase()` returns dict with keys: `type_id`, `workflow_phase`, `last_completed_phase`, `mode`, `kanban_column`, `backward_transition_reason`, `updated_at`. Map to FeatureWorkflowState: `feature_type_id=row["type_id"]`, `current_phase=row["workflow_phase"]`, `last_completed_phase=row["last_completed_phase"]`, `completed_phases=_derive_completed_phases(row["last_completed_phase"])`, `mode=row["mode"]`, `source="db"`. Unmapped columns (`kanban_column`, `backward_transition_reason`, `updated_at`) are intentionally ignored — kanban_column management is out of scope (TD-7), the others are metadata.
- Error tests inline: `test_get_state_missing_feature_returns_none`

**Dependencies:** Phase 2 (helpers)
**Artifacts:** Updated `engine.py`, `test_engine.py` (TestGetState, TestHydration)

### Phase 4: Gate Evaluation

**Goal:** Implement `_evaluate_gates()` with skip conditions and YOLO override.
**Why this item:** `_evaluate_gates` is the core orchestration logic consumed by both `transition_phase()` and `validate_prerequisites()` — shared extraction avoids code duplication.
**Why this order:** Depends on Phase 2 (_GATE_GUARD_IDS) and Phase 3 (get_state for integration testing). Must precede Phase 5 (transition_phase calls _evaluate_gates).

- RED: Write tests for gate ordering, I6 skip conditions, YOLO override behavior:
  - `test_gate_order_all_applicable` — verify results in expected order
  - `test_skip_backward_when_last_completed_none` — new feature, no backward check
  - `test_skip_validate_when_current_phase_none` — new feature, no ordering check
  - `test_yolo_overrides_soft_gates` — G-18 (auto_select), G-22 (auto_select), G-23 (auto_select) return YOLO override results
  - `test_yolo_does_not_override_hard_gate` — G-08 (check_hard_prerequisites) has `yolo_behavior=unchanged`, YOLO override returns None, gate runs normally even when `yolo_active=True`
- GREEN: Implement gate evaluation loop: iterate ordered gates, apply I6 skip conditions. For each non-skipped gate: if `yolo_active`, call `check_yolo_override(guard_id, True)` FIRST — if non-None, short-circuit (use override, skip gate call); if None, call gate normally. **Type note:** `state.completed_phases` is `tuple[str, ...]` (frozen dataclass); gate functions expect `list[str]` — pass `list(state.completed_phases)` at call sites

**YOLO override behavior by gate (critical distinction):**
| Gate | Guard ID | yolo_behavior | YOLO overridable? |
|------|----------|---------------|-------------------|
| check_backward_transition | G-18 | auto_select | Yes — returns auto-allowed warn result (allowed=True, severity=warn) |
| check_hard_prerequisites | G-08 | unchanged | **No** — always runs normally |
| check_soft_prerequisites | G-23 | auto_select | Yes — returns auto-allowed warn result (allowed=True, severity=warn) |
| validate_transition | G-22 | auto_select | Yes — returns auto-allowed warn result (allowed=True, severity=warn) |

Tests for SC-8 must verify both paths: (a) G-18, G-22, G-23 return auto_select override results in YOLO mode, (b) G-08 runs normally regardless of YOLO mode.

**Dependencies:** Phase 2 (_GATE_GUARD_IDS), Phase 3 (get_state for integration)
**Artifacts:** Updated `engine.py`, `test_engine.py` (TestGateEvaluation)

### Phase 5: Public Methods — Transition + Complete

**Goal:** Implement `transition_phase()` and `complete_phase()`.
**Why this item:** Core workflow operations that callers use to drive phase transitions.
**Why this order:** Depends on Phase 4 (_evaluate_gates) and Phase 3 (get_state).

**5a. transition_phase**
- RED: Write `TestTransitionPhase` — tests for:
  - Forward transition success (SC-1 partial — single phase)
  - Blocked by missing prerequisites (SC-2)
  - Backward transition warning (SC-3)
  - YOLO mode pass-through (SC-8)
  - ValueError on missing feature (error handling inline, not deferred)
- GREEN: Implement: `get_state()` → `ValueError` if None → `_get_existing_artifacts()` → `_evaluate_gates()` → if all pass (`all(r.allowed for r in results)`), `update_workflow_phase()` → return results

**5b. complete_phase**
- RED: Write `TestCompletePhase` — tests for:
  - Normal completion advances workflow_phase (SC-5: specify → design)
  - Terminal phase: complete_phase("finish") sets workflow_phase="finish" not None (TD-8)
  - Backward re-run: resets last_completed_phase to provided phase (TD-6). Detection: `_phase_index(phase) <= _phase_index(state.last_completed_phase)` — compare PHASE_SEQUENCE indices, not string values
  - ValueError on phase mismatch: phase != current_phase AND not a backward re-run (phase index > last_completed_phase index)
  - ValueError on missing feature
  - ValueError on current_phase=None: if feature has no active workflow_phase (e.g., planned status), raise `ValueError("Cannot complete phase: no active workflow phase")` — no phase can match and no backward re-run is applicable
- GREEN: Implement: `get_state()` → `ValueError` if None → check current_phase is not None → validate phase match or backward re-run → derive next phase via `_next_phase_value()` → handle terminal: `if next_phase is None: next_phase = phase` → `update_workflow_phase(type_id, last_completed_phase=phase, workflow_phase=next_phase)` → re-read and return updated state

**Dependencies:** Phase 4 (gate evaluation), Phase 3 (get_state)
**Artifacts:** Updated `engine.py`, `test_engine.py` (TestTransitionPhase, TestCompletePhase)

### Phase 6: Public Methods — Query + Validate

**Goal:** Implement remaining public methods.
**Why this item:** Batch query and dry-run methods needed by dashboards, MCP tools, and callers.
**Why this order:** validate_prerequisites shares gate evaluation logic with transition_phase (Phase 5). Batch queries depend on having features in various states (integration with Phases 3-5).

**6a. validate_prerequisites**
- RED: Write `TestValidatePrerequisites` — tests for: returns same gate results as transition_phase would, does NOT update workflow_phase in DB (SC-6), ValueError on missing feature
- GREEN: Implement: calls `get_state()` + `_get_existing_artifacts()` + `_evaluate_gates()` directly (same three calls as transition_phase but without the `update_workflow_phase` step). No dry_run flag — it's a separate method that simply omits the write.

**6b. list_by_phase**
- RED: Write `TestBatchQueries.test_list_by_phase_matches`, `test_list_by_phase_empty`
- GREEN: Implement: `db.list_workflow_phases(workflow_phase=phase)` → map each row dict to FeatureWorkflowState using same mapping as 3b

**6c. list_by_status**
- RED: Write `TestBatchQueries.test_list_by_status_matches`, `test_list_by_status_none_excluded`, `test_list_by_status_no_workflow_row` (SC-7)
- GREEN: Implement: `db.list_entities(entity_type="feature")` → filter by `row["status"] == status` (exact match, excludes None) → for each, join with `get_workflow_phase()` → build FeatureWorkflowState (if no workflow row: current_phase=None, last_completed_phase=None, completed_phases=(), mode=None, source="db"). Note: this is an N+1 query pattern (1 list_entities + N get_workflow_phase calls). Acceptable per NFR-5 guideline status; if performance becomes an issue, a single JOIN query could replace the loop.

**Dependencies:** Phase 5 (transition_phase for validate_prerequisites code sharing pattern)
**Artifacts:** Updated `engine.py`, `test_engine.py` (TestValidatePrerequisites, TestBatchQueries)

### Phase 7: Integration Tests

**Goal:** Full-lifecycle integration tests exercising all components together.
**Why this item:** Verifies end-to-end correctness across all layers — the unit tests in Phases 2-6 test components in isolation, integration tests verify composition.
**Why this order:** All public methods must be implemented first.

- RED: Write integration tests:
  - `test_full_lifecycle_all_6_phases` (SC-1): Create feature entity + .meta.json → get_state (triggers hydration) → for each of 6 command phases: transition_phase() + create required artifacts + complete_phase() → verify final state has last_completed_phase="finish", workflow_phase="finish". Artifact creation interleaving per HARD_PREREQUISITES: after completing specify→create spec.md, after design→create design.md, after create-plan→create plan.md, after create-tasks→create tasks.md (finish has no hard prerequisites)
  - `test_all_5_consumed_gates_exercised` (SC-10): Verify each of the 5 engine-consumed gates (check_backward_transition, check_hard_prerequisites, check_soft_prerequisites, validate_transition, check_yolo_override) is invoked through at least one integration test path
  - `test_hydration_then_transition` (SC-4 + SC-9 combined): Feature with .meta.json but no DB row → get_state hydrates → transition succeeds using hydrated state

**Dependencies:** Phase 6 (all public methods)
**Artifacts:** Updated `test_engine.py` (integration tests)

### Phase 8: Final Verification

**Goal:** Run full test suite, verify acceptance criteria.
**Why this item:** Final gate before marking implementation complete.
**Why this order:** All tests must be written first.

1. Run: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v`
2. Verify all 10 success criteria mapped to passing tests
3. Verify zero external dependencies added
4. Verify transition_gate and entity_registry consumed without modification

**Dependencies:** Phase 7 (all tests written)
**Artifacts:** Passing test suite

## Dependency Graph

```
Phase 1 (scaffold + models)
  └─▶ Phase 2 (helpers)
        ├─▶ Phase 3 (get_state + hydration)
        │     └─▶ Phase 4 (gate evaluation)
        │           └─▶ Phase 5 (transition + complete)
        │                 └─▶ Phase 6 (query + validate)
        │                       └─▶ Phase 7 (integration tests)
        │                             └─▶ Phase 8 (final verification)
        └─▶ Phase 2e (_GATE_GUARD_IDS → Phase 4)
```

All phases are sequential — no parallelism. Each phase depends on the previous. This is deliberate: the module is small (~300 lines) and each layer builds on the previous.

## TDD Approach

Each phase follows RED → GREEN → REFACTOR:

1. **RED:** Write failing test(s) for the target functionality
2. **GREEN:** Implement the minimum code to make tests pass
3. **REFACTOR:** Clean up, verify tests still pass

Every phase sub-step lists tests FIRST, then implementation. Error cases are tested alongside their corresponding methods (not deferred).

## Risk Mitigations

| Risk | Mitigation | Phase |
|------|-----------|-------|
| R1: HARD_PREREQUISITES import | Explicit import verification test: `assert isinstance(HARD_PREREQUISITES, dict)` | 2d |
| R2: .meta.json schema drift | Validate against I3b expected schema in hydration tests | 3a |
| R3: Gate signature mismatch | Test each gate call individually in Phase 4 | 4 |
| R4: EntityDatabase API changes | Full lifecycle integration tests in Phase 7 | 7 |
| R5: Concurrent hydration race | try/except ValueError("already exists") → fallback to get_workflow_phase() | 3a |

## Module File Summary

| File | Content | Deliverables |
|------|---------|-------------|
| `__init__.py` | Public API exports | 2 exports (WorkflowStateEngine, FeatureWorkflowState) |
| `models.py` | FeatureWorkflowState dataclass | 1 frozen dataclass, 6 fields |
| `engine.py` | WorkflowStateEngine class | 6 public methods + 6 private helpers |
| `test_engine.py` | Unit + integration tests | 9 unit test classes + 1 integration test class covering 10 success criteria |
