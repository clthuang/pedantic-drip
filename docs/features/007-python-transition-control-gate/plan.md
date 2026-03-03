# Plan: Python Transition Control Gate

## Implementation Order

The implementation follows a bottom-up dependency chain with tests interleaved at each phase (TDD-aligned). Each phase includes its own verification tests before proceeding.

```
Phase 1: Models (models.py) + model tests     — zero dependencies
    ↓
Phase 2: Constants (constants.py) + integrity tests — imports models.py
    ↓
Phase 3: Gate Functions (gate.py) + per-category tests — imports models.py + constants.py
    ↓
Phase 4: Public API (__init__.py) + import tests — re-exports from all modules
    ↓
Phase 5: Integration Verification + SC-5 test   — end-to-end validation
```

## Phase 1: Models (models.py) + Tests

**Goal:** Define all type contracts — enums and dataclasses — with zero business logic. Verify with instantiation tests.

**Dependencies:** None (stdlib only: `enum`, `dataclasses`, `__future__`).

**Steps:**
1. Create `plugins/iflow/hooks/lib/transition_gate/` directory
2. Create `models.py` with file header (`"""Transition gate models."""` + `from __future__ import annotations`)
3. Implement `Phase(str, Enum)` — 7 values with hyphen string values: `brainstorm="brainstorm"`, `specify="specify"`, `design="design"`, `create_plan="create-plan"`, `create_tasks="create-tasks"`, `implement="implement"`, `finish="finish"`
4. Implement `Severity(str, Enum)` — `block="block"`, `warn="warn"`, `info="info"`
5. Implement `Enforcement(str, Enum)` — `hard_block="hard_block"`, `soft_warn="soft_warn"`, `informational="informational"`
6. Implement `YoloBehavior(str, Enum)` — `auto_select="auto_select"`, `hard_stop="hard_stop"`, `skip="skip"`, `unchanged="unchanged"`
7. Implement `TransitionResult(frozen=True)` dataclass — fields: `allowed: bool`, `reason: str`, `severity: Severity`, `guard_id: str`
8. Implement `FeatureState` dataclass — fields per spec Data Models section
9. Implement `PhaseInfo` dataclass — fields: `phase: Phase`, `started: bool`, `completed: bool`
10. Create `test_gate.py` with imports from models
11. Add model instantiation tests: construct each enum value, each dataclass. Verify `Phase.create_plan == "create-plan"` (str mixin).

**Verification:** Run tests — all model instantiation tests pass.

**Risks:** Phase enum hyphen values must exactly match codebase convention. Verified during design review.

## Phase 2: Constants (constants.py) + Tests

**Goal:** Define all static configuration as the single source of truth. Verify with integrity tests.

**Dependencies:** `models.py` (Phase, Enforcement, YoloBehavior enums).

**Steps:**
1. Create `constants.py` with file header
2. Import `Phase`, `Enforcement`, `YoloBehavior` from `.models`
3. Define `PHASE_SEQUENCE: tuple[Phase, ...]` — all 7 phases in canonical order
4. Define `COMMAND_PHASES: tuple[Phase, ...]` — `PHASE_SEQUENCE[1:]` (specify through finish)
5. Define `HARD_PREREQUISITES: dict[str, list[str]]` — 7 entries. **Note:** This is a transitive enrichment of guard-rules.yaml's G-08 (which only defines per-phase direct prerequisites). The library adds transitive closure for caller convenience — e.g., create-tasks requires spec.md+design.md+plan.md (not just plan.md). This design decision is documented in design.md Technical Decisions. **Implementation note:** The docstring for HARD_PREREQUISITES must document this transitive enrichment so callers understand the semantic difference from guard-rules.yaml. Entries: brainstorm:[], specify:[], design:["spec.md"], create-plan:["spec.md","design.md"], create-tasks:["spec.md","design.md","plan.md"], implement:["spec.md","tasks.md"], finish:[]
6. Define `ARTIFACT_PHASE_MAP: dict[str, str]` — 5 entries mapping phase→output artifact
7. Define `ARTIFACT_GUARD_MAP: dict[tuple[str, str], str]` — default G-05; (implement, tasks.md)→G-06
8. Define `SERVICE_GUARD_MAP: dict[str, str]` — 4 entries for fail_open_mcp (G-13..16)
9. Define `PHASE_GUARD_MAP: dict[str, dict[str, str]]` — review_quality (5 phases) + phase_handoff (4 phases, no implement)
10. Define `MIN_ARTIFACT_SIZE: int = 100`
11. Define `MAX_ITERATIONS: dict[str, int]` — brainstorm:3, default:5
12. Define `GUARD_METADATA: dict[str, dict]` — 43 entries from guard-rules.yaml, each with enforcement, yolo_behavior, affected_phases. Derive values directly from guard-rules.yaml.
13. Define `EXPECTED_GUARD_IDS: frozenset[str]` — explicit set of all 43 guard IDs (G-02 through G-60) for exact membership testing. This prevents both missing and extraneous entries.
14. Add integrity tests to `test_gate.py`:
    - `assert set(GUARD_METADATA.keys()) == EXPECTED_GUARD_IDS` (exact membership, not just count)
    - `assert len(GUARD_METADATA) == 43` (redundant count check for clarity)
    - Assert all Phase enum values present in PHASE_SEQUENCE, assert PHASE_SEQUENCE length is 7
    - Add 3 spot-check tests verifying specific GUARD_METADATA entries against known guard-rules.yaml values (e.g., G-22 enforcement=hard_block, G-41 yolo_behavior=hard_stop, G-49 enforcement=soft_warn)
15. Add guard coverage introspection test: collect all test function names matching `test_G\d+_` pattern via `inspect` module, extract guard IDs, assert coverage of all 43 guard IDs in EXPECTED_GUARD_IDS. This test runs at Phase 2 so missing coverage is caught early (test will initially fail for unimplemented guards — mark with `@pytest.mark.xfail` until Phase 3 completes all categories, then remove xfail).
16. Add programmatic GUARD_METADATA validation test: reads `guard-rules.yaml` (path: `pathlib.Path(__file__).resolve().parents[3] / "references" / "guard-rules.yaml"`), parses YAML, validates every entry in GUARD_METADATA matches the source file's enforcement, yolo_behavior, and affected_phases. Graceful failure: if guard-rules.yaml not found, `pytest.skip("guard-rules.yaml not found at expected path")`. **Note:** Test code may perform I/O (SC-3 purity applies to library functions, not tests).

**Verification:** Run tests — all integrity, spot-check, coverage introspection, and YAML validation tests pass.

**Risks:** GUARD_METADATA must exactly match guard-rules.yaml. Step 12 is the highest-effort step — 43 entries. Cross-reference each entry against YAML source. Spot-check tests (step 14) catch transcription errors for critical guards. Programmatic validation (step 16) provides exhaustive verification.

## Phase 3: Gate Functions (gate.py) + Tests

**Goal:** Implement 25 pure functions + 4 internal helpers + 1 YOLO helper. Test each category immediately after implementation.

**Dependencies:** `models.py` (TransitionResult, Severity, Phase), `constants.py` (all constants).

**Sub-phases:** Functions are grouped by category for logical coherence. Each sub-phase includes its tests. Sub-phases 3c through 3h are independent of each other (all depend only on 3a/3b helpers).

### Phase 3a: Internal Helpers

1. Implement `_pass_result(guard_id, reason)` → `TransitionResult(True, reason, Severity.info, guard_id)`
2. Implement `_block(guard_id, reason)` → `TransitionResult(False, reason, Severity.block, guard_id)`
3. Implement `_warn(guard_id, reason)` → `TransitionResult(True, reason, Severity.warn, guard_id)`
4. Implement `_phase_index(phase)` → returns index in PHASE_SEQUENCE or -1 for invalid

No tests for internal helpers (tested indirectly via public functions).

### Phase 3b: YOLO Helper (exported) + Tests

1. Implement `check_yolo_override(guard_id, is_yolo)` — lookup GUARD_METADATA, return pre-built result for skip/auto_select, None for hard_stop/unchanged. For unknown guard_ids (not in GUARD_METADATA), return None (treat as unchanged — guard runs normally).
2. Add tests: skip guard → returns TransitionResult(allowed=True), auto_select guard → returns TransitionResult(allowed=True, severity=warn), hard_stop guard → returns None, unchanged guard → returns None, unknown guard_id → returns None, is_yolo=False → returns None regardless.

### Phase 3c: Artifact & Prerequisite Functions (G-02..09) + Tests

1. `validate_artifact(phase, artifact_name, artifact_path_exists, artifact_size, has_headers, has_required_sections)` — 4-level validation, guard_id from ARTIFACT_GUARD_MAP
2. `check_hard_prerequisites(phase, existing_artifacts)` — lookup HARD_PREREQUISITES, return missing list
3. `validate_prd(prd_path_exists)` — G-07 simple boolean check
4. `check_prd_exists(prd_path_exists, meta_has_brainstorm_source)` — G-09 soft redirect
5. Add tests: G-02..06 (10+ cases covering all 4 levels pass/fail), G-07 (2 cases), G-08 (4 cases including empty prerequisites), G-09 (2 cases)

### Phase 3d: Branch & Service Functions (G-11, G-13..16) + Tests

1. `check_branch(current_branch, expected_branch)` — G-11 string comparison
2. `fail_open_mcp(service_name, service_available)` — G-13..16, always allowed=True on failure (warn)
3. Add tests: G-11 (2 cases), G-13..16 (8 cases: 4 services x pass/fail)

### Phase 3e: Phase Transition Functions (G-17, G-18, G-22, G-23, G-25) + Tests

1. `check_partial_phase(phase, phase_started, phase_completed)` — G-17 started-but-not-completed detection
2. `check_backward_transition(target_phase, last_completed_phase)` — G-18 backward movement warning
3. `validate_transition(current_phase, target_phase, completed_phases)` — G-22 canonical sequence validation
4. `check_soft_prerequisites(target_phase, completed_phases)` — G-23 skipped phase warning
5. `get_next_phase(last_completed_phase)` — G-25 next phase lookup
6. Add tests: G-17 (2 cases), G-18 (2 cases), G-22 (3 cases), G-23 (2 cases), G-25 (2 cases including end-of-sequence)

### Phase 3f: Pre-Merge Functions (G-27..30) + Tests

1. `pre_merge_validation(checks_passed, max_attempts, current_attempt)` — G-27/29 with truth table
2. `check_merge_conflict(is_yolo, merge_succeeded)` — G-28/30 with truth table
3. Add tests: G-27/29 (4 cases covering truth table), G-28/30 (4 cases covering truth table)

### Phase 3g: Review Gate Functions (G-31..41, G-46, G-47) + Tests

1. `brainstorm_quality_gate(iteration, max_iterations, reviewer_approved)` — G-32
2. `brainstorm_readiness_gate(iteration, max_iterations, reviewer_approved, has_blockers)` — G-31/33 with decision matrix
3. `review_quality_gate(phase, iteration, max_iterations, reviewer_approved, has_blockers_or_warnings)` — G-34/36/38/40/46 via PHASE_GUARD_MAP
4. `phase_handoff_gate(phase, iteration, max_iterations, reviewer_approved, has_blockers_or_warnings)` — G-35/37/39/47 via PHASE_GUARD_MAP
5. `implement_circuit_breaker(is_yolo, iteration, max_iterations)` — G-41
6. Add tests: G-31/33 (4 cases for decision matrix), G-32 (3 cases), G-34/36/38/40/46 (10 cases across phases), G-35/37/39/47 (8 cases across phases), G-41 (3 cases including YOLO hard-stop)

### Phase 3h: Status & Feature Functions (G-45, G-48..53, G-60) + Tests

1. `check_active_feature_conflict(active_feature_count)` — G-48
2. `secretary_review_criteria(confidence, is_direct_match)` — G-45
3. `check_active_feature(has_active_feature)` — G-49
4. `planned_to_active_transition(current_status, branch_exists)` — G-50
5. `check_terminal_status(current_status)` — G-51 (enforcement override: hard-block)
6. `check_task_completion(incomplete_task_count)` — G-52/53
7. `check_orchestrate_prerequisite(is_yolo)` — G-60
8. Add tests: G-45 (2 cases), G-48 (2 cases), G-49 (2 cases), G-50 (3 cases), G-51 (3 cases including terminal statuses), G-52/53 (2 cases), G-60 (2 cases)

**Error handling:** All public functions return `TransitionResult(allowed=False, reason="Invalid input: {detail}", severity=Severity.block, guard_id="INVALID")` for unknown phases or invalid inputs. No exceptions.

## Phase 4: Public API (__init__.py) + Tests

**Goal:** Clean re-export of all public symbols. Verify imports work.

**Dependencies:** All Phase 1-3 modules.

**Steps:**
1. Create `__init__.py` with file header
2. Import and re-export all 25 gate functions + `check_yolo_override` (26 total exported functions)
3. Import and re-export all 4 enums: Phase, Severity, Enforcement, YoloBehavior
4. Import and re-export all 3 dataclasses: TransitionResult, FeatureState, PhaseInfo
5. Import and re-export key constants: PHASE_SEQUENCE, COMMAND_PHASES, GUARD_METADATA, ARTIFACT_GUARD_MAP, SERVICE_GUARD_MAP
6. Define `__all__` listing all exported names
7. Add import tests to `test_gate.py`: verify `from transition_gate import validate_transition, TransitionResult, Phase` works, verify `__all__` length matches expected count

**Verification:** Import tests pass — all public symbols accessible from package root.

## Phase 5: Integration Verification + SC-5 Test

**Goal:** Confirm end-to-end package integrity and canonical sequence alignment.

**Dependencies:** Complete transition_gate package (Phases 1-4).

**Steps:**
1. Implement SC-5 test: `test_canonical_sequence_matches_skill_md` — reads SKILL.md, searches for arrow-delimited sequence under the "Phase Sequence" heading (line format: `brainstorm → specify → ...`), extracts phase names, compares against PHASE_SEQUENCE tuple. Path resolution: `pathlib.Path(__file__).resolve().parents[3] / "skills" / "workflow-state" / "SKILL.md"` (navigates from `hooks/lib/transition_gate/` up to plugin root). Graceful failure: if SKILL.md not found, `pytest.skip("SKILL.md not found at expected path")`. **Spec divergence note:** The spec references this as "Canonical Sequence" heading, but the actual SKILL.md heading is "Phase Sequence" — this plan uses the actual heading. The test searches for "Phase Sequence".
2. Remove `@pytest.mark.xfail` from guard coverage introspection test (Phase 2 step 15) — all 43 guard IDs should now have test coverage after Phase 3.
3. Run full test suite: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/ -v`
4. Verify no new dependencies: `grep -r "^import\|^from" plugins/iflow/hooks/lib/transition_gate/ | grep -v "transition_gate\|dataclasses\|enum\|typing\|__future__\|pytest\|pathlib\|yaml\|inspect\|re"` — should return empty (no external deps except pytest, pyyaml, inspect, re for tests)

**Verification:** All tests pass, all 43 guard IDs covered, zero external runtime dependencies (yaml/inspect/re are test-only).

## Dependency Graph

```
models.py ──────────────────┐
    │                       │
    ▼                       ▼
constants.py            gate.py
    │                   │   │
    └───────────────────┘   │
                            ▼
                    __init__.py
                            │
                            ▼
                    test_gate.py
```

## Parallel Execution Opportunities

Within Phase 3, sub-phases 3c through 3h are independent of each other (all depend only on 3a/3b helpers). An implementer can work on any category without waiting for others.

## Estimated Scope

- **models.py:** ~60 lines (4 enums + 3 dataclasses)
- **constants.py:** ~210 lines (dominated by 43-entry GUARD_METADATA + EXPECTED_GUARD_IDS)
- **gate.py:** ~400 lines (25 functions + helpers)
- **__init__.py:** ~30 lines (imports + __all__)
- **test_gate.py:** ~600 lines (90+ test cases including YAML validation and coverage introspection)
- **Total:** ~1300 lines of Python
