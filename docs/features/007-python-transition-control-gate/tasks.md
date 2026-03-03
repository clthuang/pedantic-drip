# Tasks: Python Transition Control Gate

## Phase 1: Models (models.py) + Tests

**Dependencies:** None

### Task 1.1: Create package directory and stub __init__.py
- [ ] Create `plugins/iflow/hooks/lib/transition_gate/` directory
- [ ] Create empty `__init__.py` stub (ensures importability during TDD Phases 1-3; replaced in Phase 4)
- **Done when:** Directory exists and `python -c "import transition_gate"` succeeds from hooks/lib/

### Task 1.2: Create models.py with Phase and Severity enums
- [ ] Create `models.py` with file header (`"""Transition gate models."""` + `from __future__ import annotations`)
- [ ] Implement `Phase(str, Enum)` — 7 values: brainstorm, specify, design, create_plan="create-plan", create_tasks="create-tasks", implement, finish
- [ ] Implement `Severity(str, Enum)` — block, warn, info
- **Done when:** `Phase.create_plan == "create-plan"` and `Severity.block == "block"` in Python REPL

### Task 1.3: Add Enforcement and YoloBehavior enums to models.py
- [ ] Implement `Enforcement(str, Enum)` — hard_block, soft_warn, informational
- [ ] Implement `YoloBehavior(str, Enum)` — auto_select, hard_stop, skip, unchanged
- **Done when:** All 4 enum values for each constructible without error

### Task 1.4: Add dataclasses to models.py
- [ ] Implement `TransitionResult(frozen=True)` — allowed: bool, reason: str, severity: Severity, guard_id: str
- [ ] Implement `FeatureState` — feature_id, status, current_branch, expected_branch, completed_phases, active_phase, meta_has_brainstorm_source
- [ ] Implement `PhaseInfo` — phase: Phase, started: bool, completed: bool
- **Done when:** All 3 dataclasses constructible with valid field values

### Task 1.5: Create test_gate.py with model instantiation tests
- [ ] Create `test_gate.py` with naming convention comment: `# NAMING: All guard tests MUST follow test_G{XX}_{description} pattern (uppercase G) for coverage introspection.`
- [ ] Add model instantiation tests: construct each enum value, each dataclass
- [ ] Verify `Phase.create_plan == "create-plan"` (str mixin test)
- [ ] Verify `TransitionResult` is frozen: construct instance, attempt `result.allowed = False`, assert `FrozenInstanceError` is raised
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v` passes with all model tests green

## Phase 2: Constants (constants.py) + Tests

**Dependencies:** Phase 1 complete

### Task 2.1: Create constants.py with phase sequences
- [ ] Create `constants.py` with file header
- [ ] Import Phase, Enforcement, YoloBehavior from `.models`
- [ ] Define `PHASE_SEQUENCE: tuple[Phase, ...]` — all 7 phases in canonical order
- [ ] Define `COMMAND_PHASES: tuple[Phase, ...]` — `PHASE_SEQUENCE[1:]`
- **Done when:** `len(PHASE_SEQUENCE) == 7` and `COMMAND_PHASES[0] == Phase.specify`

### Task 2.2: Add prerequisite and artifact maps
- [ ] Define `HARD_PREREQUISITES: dict[str, list[str]]` — 7 entries with transitive enrichment. Docstring must document G-08 divergence (transitive closure vs direct-only semantics)
- [ ] Define `ARTIFACT_PHASE_MAP: dict[str, str]` — 5 entries
- [ ] Define `ARTIFACT_GUARD_MAP: dict[tuple[str, str], str]` — exactly 2 explicit entries: `{("implement", "spec.md"): "G-05", ("implement", "tasks.md"): "G-06"}`. All other (phase, artifact_name) pairs resolve to G-05 via caller-side default lookup (not stored in dict).
- **Done when:** `HARD_PREREQUISITES["create-tasks"] == ["spec.md", "design.md", "plan.md"]` and `ARTIFACT_GUARD_MAP[("implement", "tasks.md")] == "G-06"` and `len(ARTIFACT_GUARD_MAP) == 2`

### Task 2.3: Add service, iteration, and phase guard maps
- [ ] Define `SERVICE_GUARD_MAP: dict[str, str]` — 4 entries (G-13..16)
- [ ] Define `PHASE_GUARD_MAP: dict[str, dict[str, str]]` — review_quality (5 phases) + phase_handoff (4 phases)
- [ ] Define `MIN_ARTIFACT_SIZE: int = 100`
- [ ] Define `MAX_ITERATIONS: dict[str, int]` — brainstorm:3, default:5
- **Done when:** `PHASE_GUARD_MAP["review_quality"]["specify"] == "G-46"` and `MIN_ARTIFACT_SIZE == 100`

### Task 2.4a: Define GUARD_METADATA first half (G-02..G-33, ~22 entries)
- [ ] Define `GUARD_METADATA: dict[str, dict]` — begin populating from `docs/features/006-transition-guard-audit-and-rul/guard-rules.yaml`, including only guards where `consolidation_target: transition_gate` (filter out guards with consolidation_target: hook or deprecated)
- [ ] Each entry: `{"enforcement": Enforcement.X, "yolo_behavior": YoloBehavior.Y, "affected_phases": [...]}`
- [ ] Populate guards G-02 through G-33 (approximately 22 entries)
- **Done when:** All guards from G-02 through G-33 with `consolidation_target: transition_gate` are present in GUARD_METADATA

### Task 2.4b: Define GUARD_METADATA second half (G-34..G-60, ~21 entries)
**Prerequisite:** Task 2.4a complete.
- [ ] Populate guards G-34 through G-60 (approximately 21 entries)
- [ ] Apply G-51 enforcement override: set to `Enforcement.hard_block` (YAML source says soft-warn, but spec requires hard-block — this is an intentional upgrade, add inline comment documenting the override)
- **Done when:** `len(GUARD_METADATA) == 43` and `GUARD_METADATA["G-51"]["enforcement"] == Enforcement.hard_block`. Note: after writing all 43 entries, immediately write Task 2.8's YAML validation test and run it (`-k "yaml_validation"`) to catch transcription errors before proceeding to Task 2.5+.

### Task 2.5: Define EXPECTED_GUARD_IDS
- [ ] Define `EXPECTED_GUARD_IDS: frozenset[str]` — explicit set of all 43 guard IDs (G-02 through G-60, excluding deprecated G-24/G-26 and 15 hook guards)
- **Done when:** `len(EXPECTED_GUARD_IDS) == 43` and `"G-22" in EXPECTED_GUARD_IDS`

### Task 2.6: Add integrity tests
- [ ] `assert set(GUARD_METADATA.keys()) == EXPECTED_GUARD_IDS` (exact membership)
- [ ] `assert len(GUARD_METADATA) == 43`
- [ ] Assert all Phase enum values present in PHASE_SEQUENCE, length == 7
- [ ] 3 spot-check tests: G-22 enforcement=soft_warn, G-41 yolo_behavior=hard_stop, G-49 enforcement=soft_warn. Note: only G-51 has enforcement override.
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "integrity or spot"` all green

### Task 2.7: Add guard coverage introspection test (xfail)
- [ ] Implement test: collect test function names matching `test_G\d+_` via inspect module, extract guard IDs, assert coverage of all 43 in EXPECTED_GUARD_IDS
- [ ] Mark entire introspection test function with single `@pytest.mark.xfail` (removed in Phase 5 after all guards implemented)
- **Done when:** Test exists, runs as xfail (expected failure since guard tests not yet written)

### Task 2.8: Add YAML validation test
- [ ] Implement test: reads `guard-rules.yaml` via line-by-line regex parsing (no PyYAML)
- [ ] Path resolution: walk up from `Path(__file__).resolve()` until `.git/` found, then `docs/features/006-transition-guard-audit-and-rul/guard-rules.yaml`
- [ ] Normalize YAML hyphens to Python underscores: `yaml_value.replace("-", "_")` for enforcement and yolo_behavior
- [ ] Special-case G-51: skip enforcement comparison for G-51 (intentional override from soft-warn to hard-block per spec), add comment explaining the exception
- [ ] Graceful: `pytest.skip("guard-rules.yaml not found")` if file missing
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "yaml_validation"` passes

## Phase 3: Gate Functions (gate.py) + Tests

**Dependencies:** Phase 2 complete
**Parallelism:** Tasks 3.3–3.8 are independent of each other and can be worked in parallel. All depend only on Tasks 3.1 and 3.2.

### Task 3.1: Create gate.py with internal helpers
- [ ] Create `gate.py` with file header
- [ ] Import TransitionResult, Severity, Phase from `.models` and all constants from `.constants`
- [ ] Implement `_pass_result(guard_id, reason)` → TransitionResult(True, reason, Severity.info, guard_id)
- [ ] Implement `_block(guard_id, reason)` → TransitionResult(False, reason, Severity.block, guard_id)
- [ ] Implement `_warn(guard_id, reason)` → TransitionResult(True, reason, Severity.warn, guard_id)
- [ ] Implement `_phase_index(phase)` → index in PHASE_SEQUENCE or -1 for invalid
- [ ] Add 3 `_phase_index` tests: valid returns index, invalid returns -1, first/last return 0/6
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "phase_index"` passes

### Task 3.2: Implement check_yolo_override + tests
**Prerequisite:** Task 3.1 complete.
- [ ] Implement `check_yolo_override(guard_id, is_yolo)` — lookup GUARD_METADATA, return pre-built result for skip/auto_select, None for hard_stop/unchanged/unknown
- [ ] Add 6 tests: skip→TransitionResult(allowed=True), auto_select→TransitionResult(allowed=True, severity=warn), hard_stop→None, unchanged→None, unknown guard_id→None, is_yolo=False→None
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "yolo_override"` passes

### Task 3.3: Implement artifact & prerequisite functions (G-02..09) + tests
**Prerequisite:** Tasks 3.1 and 3.2 complete.
**Naming:** Guard IDs in test names must be zero-padded: `test_G02_`, `test_G05_`, not `test_G2_`, `test_G5_`. This is required for coverage introspection regex matching.
- [ ] `validate_artifact(phase, artifact_name, artifact_path_exists, artifact_size, has_headers, has_required_sections)` — 4-level validation, guard_id from ARTIFACT_GUARD_MAP
- [ ] `check_hard_prerequisites(phase, existing_artifacts)` — lookup HARD_PREREQUISITES, return missing list
- [ ] `validate_prd(prd_path_exists)` — G-07 simple boolean check
- [ ] `check_prd_exists(prd_path_exists, meta_has_brainstorm_source)` — G-09 soft redirect
- [ ] Add 18 tests: G-02..06 (10+ covering all 4 levels pass/fail), G-07 (2), G-08 (4 including empty prerequisites), G-09 (2)
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "G02 or G03 or G04 or G05 or G06 or G07 or G08 or G09"` passes

### Task 3.4: Implement branch & service functions (G-11, G-13..16) + tests
**Prerequisite:** Tasks 3.1 and 3.2 complete.
- [ ] `check_branch(current_branch, expected_branch)` — G-11 string comparison
- [ ] `fail_open_mcp(service_name, service_available)` — G-13..16, always allowed=True on failure (warn)
- [ ] Add 10 tests: G-11 (2), G-13..16 (8: 4 services x pass/fail)
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "G11 or G13 or G14 or G15 or G16"` passes

### Task 3.5: Implement phase transition functions (G-17, G-18, G-22, G-23, G-25) + tests
**Prerequisite:** Tasks 3.1 and 3.2 complete.
- [ ] `check_partial_phase(phase, phase_started, phase_completed)` — G-17
- [ ] `check_backward_transition(target_phase, last_completed_phase)` — G-18
- [ ] `validate_transition(current_phase, target_phase, completed_phases)` — G-22
- [ ] `check_soft_prerequisites(target_phase, completed_phases)` — G-23
- [ ] `get_next_phase(last_completed_phase)` — G-25
- [ ] Add 11 tests: G-17 (2), G-18 (2), G-22 (3), G-23 (2), G-25 (2 including end-of-sequence)
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "G17 or G18 or G22 or G23 or G25"` passes

### Task 3.6: Implement pre-merge functions (G-27..30) + tests
**Prerequisite:** Tasks 3.1 and 3.2 complete.
- [ ] `pre_merge_validation(checks_passed, max_attempts, current_attempt)` — G-27/29 with truth table
- [ ] `check_merge_conflict(is_yolo, merge_succeeded)` — G-28/30 with truth table
- [ ] Add 8 tests: G-27/29 (4 covering truth table), G-28/30 (4 covering truth table)
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "G27 or G28 or G29 or G30"` passes

### Task 3.7a: Implement brainstorm gate functions (G-31..33) + tests
**Prerequisite:** Tasks 3.1 and 3.2 complete.
- [ ] `brainstorm_quality_gate(iteration, max_iterations, reviewer_approved)` — G-32
- [ ] `brainstorm_readiness_gate(iteration, max_iterations, reviewer_approved, has_blockers)` — G-31/33 with decision matrix
- [ ] Add 7 tests: G-31/33 (4), G-32 (3)
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "G31 or G32 or G33"` passes

### Task 3.7b: Implement review/handoff gate + circuit breaker functions (G-34..41, G-46, G-47) + tests
**Prerequisite:** Tasks 3.1 and 3.2 complete.
- [ ] `review_quality_gate(phase, iteration, max_iterations, reviewer_approved, has_blockers_or_warnings)` — G-34/36/38/40/46 via PHASE_GUARD_MAP
- [ ] `phase_handoff_gate(phase, iteration, max_iterations, reviewer_approved, has_blockers_or_warnings)` — G-35/37/39/47 via PHASE_GUARD_MAP
- [ ] `implement_circuit_breaker(is_yolo, iteration, max_iterations)` — G-41
- [ ] Add 21 tests: G-34/36/38/40/46 (10 across phases), G-35/37/39/47 (8 across phases), G-41 (3 including YOLO hard-stop)
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "G34 or G35 or G36 or G37 or G38 or G39 or G40 or G41 or G46 or G47"` passes

### Task 3.8: Implement status & feature functions (G-45, G-48..53, G-60) + tests
**Prerequisite:** Tasks 3.1 and 3.2 complete.
- [ ] `check_active_feature_conflict(active_feature_count)` — G-48
- [ ] `secretary_review_criteria(confidence, is_direct_match)` — G-45
- [ ] `check_active_feature(has_active_feature)` — G-49
- [ ] `planned_to_active_transition(current_status, branch_exists)` — G-50
- [ ] `check_terminal_status(current_status)` — G-51 (enforcement override: hard-block)
- [ ] `check_task_completion(incomplete_task_count)` — G-52/53
- [ ] `check_orchestrate_prerequisite(is_yolo)` — G-60
- [ ] Add 16 tests: G-45 (2), G-48 (2), G-49 (2), G-50 (3), G-51 (3 including terminal statuses), G-52/53 (2), G-60 (2)
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "G45 or G48 or G49 or G50 or G51 or G52 or G53 or G60"` passes

## Phase 4: Public API (__init__.py) + Tests

**Dependencies:** Phase 3 complete

### Task 4.1: Replace stub __init__.py with full exports
- [ ] Replace empty `__init__.py` with file header and all imports
- [ ] Re-export all 25 gate functions + `check_yolo_override` (26 total)
- [ ] Re-export all 4 enums: Phase, Severity, Enforcement, YoloBehavior
- [ ] Re-export all 3 dataclasses: TransitionResult, FeatureState, PhaseInfo
- [ ] Re-export key constants: PHASE_SEQUENCE, COMMAND_PHASES, GUARD_METADATA, ARTIFACT_GUARD_MAP, SERVICE_GUARD_MAP
- [ ] Define `__all__` listing all exported names
- **Done when:** `from transition_gate import validate_transition, TransitionResult, Phase` succeeds

### Task 4.2: Add import verification tests
- [ ] Verify `from transition_gate import validate_transition, TransitionResult, Phase` works
- [ ] Verify `__all__` length matches expected count (26 functions + 4 enums + 3 dataclasses + 5 constants = 38)
- [ ] Verify all names in `__all__` are accessible: iterate `__all__`, call `getattr(transition_gate, name)` for each, assert no `AttributeError`
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "import"` passes with zero `AttributeError`s and `len(__all__) == 38`

## Phase 5: Integration Verification + SC-5 Test

**Dependencies:** Phase 4 complete

### Task 5.1: Implement SC-5 canonical sequence test
- [ ] `test_canonical_sequence_matches_skill_md` — reads SKILL.md under "Canonical Sequence" heading (note: spec says "Phase Sequence" but SKILL.md uses "Canonical Sequence" — search for either heading to handle both)
- [ ] Path: `Path(__file__).resolve().parents[3] / "skills" / "workflow-state" / "SKILL.md"`
- [ ] Extract arrow-delimited sequence, compare against PHASE_SEQUENCE
- [ ] Graceful: `pytest.skip("SKILL.md not found at expected path")` if file missing; `pytest.fail("Arrow-delimited sequence not found under any expected heading in SKILL.md")` if file exists but heading not found
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/test_gate.py -v -k "canonical_sequence"` passes (must not show skip — if test skips, verify path resolution before proceeding)

### Task 5.2: Remove xfail and verify full coverage
- [ ] Remove `@pytest.mark.xfail` from guard coverage introspection test (Phase 2 Task 2.7)
- [ ] Verify all 43 guard IDs now have test coverage
- **Done when:** Introspection test passes (not xfail) with 43/43 guard IDs covered

### Task 5.3: Run full test suite
- [ ] Run: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/ -v`
- [ ] Verify all tests pass, zero failures
- **Done when:** Full suite green with 100+ test cases

### Task 5.4: Verify zero external runtime dependencies
- [ ] Run: `grep -r "^import\|^from" plugins/iflow/hooks/lib/transition_gate/ | grep -v "transition_gate\|dataclasses\|enum\|typing\|__future__\|pytest\|pathlib\|inspect\|re"`
- [ ] Verify empty output (no external deps; pytest/inspect/re/pathlib are stdlib, test-only)
- **Done when:** Grep returns no matches
