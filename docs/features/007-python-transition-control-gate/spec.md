# Spec: Python Transition Control Gate

## Overview

Implement a Python library (`transition_gate.py`) that encodes the 43 transition guards identified in feature 006's guard inventory with `consolidation_target: "transition_gate"`. This library replaces the LLM's interpretation of markdown pseudocode with deterministic, unit-tested Python functions callable via the existing entity registry infrastructure.

This is a **library feature** — deliverable is a Python module with pure functions and comprehensive tests, not an MCP server or UI. The library will be consumed by feature 008 (WorkflowStateEngine core) and future command migrations.

## Background

Feature 006 audited all 60 transition guards in iflow's workflow system and classified 43 for encoding in Python. Currently, these guards exist as markdown pseudocode (e.g., `validateTransition()`, `validateArtifact()`) that the LLM reads and re-interprets on each invocation. This produces non-deterministic behavior — identical inputs can produce different transition decisions depending on context window state.

The audit report's consolidation summary maps 43 guards to 25 Python functions across categories: phase sequence validation, artifact checks, branch validation, status transitions, review quality gates, and pre-merge guards.

## Feasibility

- **Python infrastructure exists:** `plugins/iflow/hooks/lib/entity_registry/` provides the established pattern for Python libraries in this codebase — module structure, test conventions, venv usage (`plugins/iflow/.venv/bin/python`).
- **Guard definitions are complete:** Feature 006's `guard-rules.yaml` provides machine-readable input with all required fields (trigger, enforcement, affected_phases, yolo_behavior).
- **No runtime integration yet:** This feature produces a standalone library. Integration with MCP tools (feature 009) and command migration (features 014-017) are separate features.
- **Primary risk:** The library must exactly reproduce the behavior currently described in markdown pseudocode. Behavioral drift between the Python implementation and the existing markdown instructions would create dual-authority confusion during the migration period.

## Success Criteria

- SC-1: Every guard with `consolidation_target: "transition_gate"` in `guard-rules.yaml` (43 guards) is encoded as a Python function in `transition_gate.py` or a submodule.
- SC-2: Each Python function returns a structured result (`TransitionResult` dataclass) with: allowed (bool), reason (str), severity (enum: block/warn/info), and guard_id (str).
- SC-3: All functions are pure — they accept state as input parameters, have no side effects, and do not read files, environment variables, or databases directly. State is injected by callers.
- SC-4: Test coverage achieves 100% of guard IDs — every G-XX has at least one test case exercising its pass and fail conditions. Pass = `allowed: true`, fail = `allowed: false` with severity matching the Enforcement Mapping below.
- SC-5: The library's phase sequence definition is the single canonical source — it must match the sequence in `workflow-state/SKILL.md` exactly, with a test that verifies this. The test should search for the arrow-delimited sequence line (e.g., `brainstorm → specify → ...`) under the "Canonical Sequence" heading. Note: SC-3 purity applies to library functions, not test code.
- SC-6: YOLO mode behavior is encoded per guard as documented in `guard-rules.yaml`'s `yolo_behavior` field, following the YOLO Behavior Semantics defined below.

## Acceptance Criteria

- AC-1: `plugins/iflow/hooks/lib/transition_gate/__init__.py` exists and exports all public functions.
- AC-2: `plugins/iflow/hooks/lib/transition_gate/gate.py` contains the core validation functions (~25 functions per the consolidation summary).
- AC-3: `plugins/iflow/hooks/lib/transition_gate/models.py` contains dataclasses: `TransitionResult`, `FeatureState`, `PhaseInfo`, and enums: `Phase`, `Severity`, `Enforcement`, `YoloBehavior`. See Data Models section for field definitions.
- AC-4: `plugins/iflow/hooks/lib/transition_gate/constants.py` contains the canonical phase sequence, hard prerequisites map, artifact-phase map, guard metadata, default max_iterations per gate type (brainstorm: 3, all others: 5), and artifact validation thresholds (min size: 100 bytes).
- AC-5: `plugins/iflow/hooks/lib/transition_gate/test_gate.py` contains tests for all 43 guards (minimum 86 test cases — one pass + one fail per guard).
- AC-6: All tests pass: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/ -v`
- AC-7: The 2 guards marked `deprecated` in the audit (G-24, G-26) are NOT encoded — they should be retired, not reimplemented.
- AC-8: The 15 guards marked `consolidation_target: "hook"` are NOT encoded — they remain in their existing hook files.

## Function Consolidation Map

Per the feature 006 audit report Section 4, the 43 guards consolidate to these Python functions:

| Function | Guard IDs | Description |
|----------|-----------|-------------|
| `validate_artifact(phase, artifact_path_exists, artifact_size, has_headers, has_required_sections)` | G-02, G-03, G-04, G-05, G-06 | 4-level artifact content validation with per-phase BLOCKED messages. Callers pre-compute booleans; size threshold (100 bytes) lives in constants. |
| `check_hard_prerequisites(phase, existing_artifacts)` | G-08 | Maps phases to required artifacts, returns missing list |
| `validate_prd(prd_path_exists)` | G-07 | PRD existence check for project creation |
| `check_prd_exists(prd_path_exists, meta_has_brainstorm_source)` | G-09 | Soft redirect for specify when PRD missing |
| `check_branch(current_branch, expected_branch)` | G-11 | Branch mismatch detection with switch suggestion |
| `fail_open_mcp(service_name, service_available)` | G-13, G-14, G-15, G-16 | Returns warn (not block) when MCP/external service unavailable |
| `check_partial_phase(phase, phase_started, phase_completed)` | G-17 | Detects interrupted phases, suggests resume |
| `check_backward_transition(target_phase, last_completed_phase)` | G-18 | Warns on re-running completed phases |
| `validate_transition(current_phase, target_phase, completed_phases)` | G-22 | Canonical phase sequence validation |
| `check_soft_prerequisites(target_phase, completed_phases)` | G-23 | Warns about skipped optional phases |
| `get_next_phase(last_completed_phase)` | G-25 | Returns next phase in sequence |
| `pre_merge_validation(checks_passed, max_attempts, current_attempt)` | G-27, G-29 | Pre-merge validation gate |
| `check_merge_conflict(is_yolo, merge_succeeded)` | G-28, G-30 | YOLO hard-stop on merge conflict |
| `brainstorm_quality_gate(iteration, max_iterations, reviewer_approved)` | G-32 | PRD quality review loop |
| `brainstorm_readiness_gate(iteration, max_iterations, reviewer_approved, has_blockers)` | G-31, G-33 | Readiness check with circuit breaker |
| `review_quality_gate(phase, iteration, max_iterations, reviewer_approved, has_blockers_or_warnings)` | G-34, G-36, G-38, G-40, G-46 | Pure state evaluator: determines whether a review loop should continue. For multi-reviewer phases (G-40), caller aggregates approvals into single boolean (True only when ALL approve). |
| `phase_handoff_gate(phase, iteration, max_iterations, reviewer_approved, has_blockers_or_warnings)` | G-35, G-37, G-39, G-47 | Pure state evaluator: determines whether a handoff review loop should continue. Caller manages loop and aggregates reviewer state. |
| `implement_circuit_breaker(is_yolo, iteration, max_iterations)` | G-41 | YOLO safety boundary (hard-stop after 5 failed reviews) |
| `check_active_feature_conflict(active_feature_count)` | G-48 | Warns about existing active features |
| `secretary_review_criteria(confidence, is_direct_match)` | G-45 | Routing optimization: skip reviewer when confidence > 85% and direct match |
| `check_active_feature(has_active_feature)` | G-49 | Soft-warns when starting specification without active feature |
| `planned_to_active_transition(current_status, branch_exists)` | G-50 | Multi-step Planned→Active gate |
| `check_terminal_status(current_status)` | G-51 | Blocks modification of completed/abandoned features (enforcement override, see below) |
| `check_task_completion(incomplete_task_count)` | G-52, G-53 | Task completion gate before finish |
| `check_orchestrate_prerequisite(is_yolo)` | G-60 | Requires YOLO for orchestrate subcommand |

## Data Models

### TransitionResult (dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `allowed` | `bool` | Whether the transition/action is permitted |
| `reason` | `str` | Human-readable explanation of the decision |
| `severity` | `Severity` | block, warn, or info |
| `guard_id` | `str` | Guard ID (e.g., "G-22") for traceability |

### FeatureState (dataclass)

Convenience container for callers (e.g., feature 008's WorkflowStateEngine) to aggregate feature state before passing individual fields to gate functions. Gate functions do NOT accept FeatureState directly — they accept primitive parameters per SC-3's purity constraint.

| Field | Type | Description |
|-------|------|-------------|
| `feature_id` | `str` | Feature identifier (e.g., "007") |
| `status` | `str` | Current status: planned, active, completed, abandoned |
| `current_branch` | `str` | Current git branch name |
| `expected_branch` | `str` | Expected feature branch name |
| `completed_phases` | `list[str]` | List of completed phase names |
| `active_phase` | `str or None` | Currently active phase, if any |
| `meta_has_brainstorm_source` | `bool` | Whether .meta.json has brainstorm_source |

### PhaseInfo (dataclass)

| Field | Type | Description |
|-------|------|-------------|
| `phase` | `Phase` | Phase enum value |
| `started` | `bool` | Whether phase has been started |
| `completed` | `bool` | Whether phase has been completed |

### Phase (enum)

All 7 canonical phases matching `workflow-state/SKILL.md`: `brainstorm`, `specify`, `design`, `create_plan`, `create_tasks`, `implement`, `finish`. The enum includes `brainstorm` as the first phase to match the full canonical sequence. Guard functions that only apply to command-driven phases (specify through finish) accept a `phase` parameter restricted to those values.

### Severity (enum)

`block`, `warn`, `info` — maps from guard-rules.yaml enforcement levels.

### Enforcement (enum)

`hard_block`, `soft_warn`, `informational` — used in guard metadata constants for traceability against guard-rules.yaml. Not part of function signatures; stored in `GUARD_METADATA` in constants.py.

### YoloBehavior (enum)

`auto_select`, `hard_stop`, `skip`, `unchanged` — from guard-rules.yaml yolo_behavior field.

## Enforcement Mapping

Maps guard-rules.yaml `enforcement` values to `TransitionResult` fields:

| guard-rules.yaml enforcement | TransitionResult.severity | TransitionResult.allowed (on fail) |
|------------------------------|---------------------------|-------------------------------------|
| `hard-block` | `Severity.block` | `False` |
| `soft-warn` | `Severity.warn` | `True` (warn but allow) |
| `informational` | `Severity.info` | `True` (info only) |

On pass (guard condition satisfied), all guards return `allowed: True` with `Severity.info`.

## Enforcement Overrides

Guards where the Python implementation intentionally changes enforcement from the guard-rules.yaml baseline:

| Guard | guard-rules.yaml | Python implementation | Rationale |
|-------|-------------------|-----------------------|-----------|
| G-51 | `soft-warn` | `hard-block` (`Severity.block`) | Audit consolidation notes: "Should be hard-block in Python." Terminal statuses must be absolute — no workflow should operate on completed/abandoned features. |

## YOLO Behavior Semantics

Maps `yolo_behavior` values to their effect on `TransitionResult` when YOLO mode is active:

| YoloBehavior | Effect on TransitionResult |
|--------------|---------------------------|
| `skip` | Return `allowed: True`, `severity: info`, reason: "Skipped in YOLO mode" — guard is bypassed entirely |
| `hard_stop` | Return `allowed: False`, `severity: block` — YOLO cannot bypass this guard |
| `auto_select` | Return `allowed: True`, `severity: warn`, reason: "Auto-selected default in YOLO mode" — guard auto-resolves |
| `unchanged` | Normal evaluation, no YOLO override — guard runs as in non-YOLO mode |

Functions that support YOLO mode accept an `is_yolo: bool` parameter. When `is_yolo=False`, the yolo_behavior field has no effect.

## Test Naming Convention

Test functions follow the pattern: `test_G{XX}_{function_name}_{pass|fail}[_variant]`

Examples:
- `test_G02_validate_artifact_pass`
- `test_G02_validate_artifact_fail_missing`
- `test_G22_validate_transition_pass`
- `test_G45_secretary_review_criteria_fail`

This makes guard IDs traceable from test names to `guard-rules.yaml` entries (per Constraints).

## Scope

### In Scope
- Python library implementing all 43 `transition_gate` guards as pure functions
- Dataclass models for structured input/output
- Canonical phase sequence and prerequisite constants
- Comprehensive unit tests (minimum 86 test cases)
- YOLO behavior encoding per guard

### Out of Scope
- MCP server wrapping (feature 009)
- Integration with existing commands (features 014-017)
- Modifying existing hook files or command markdown
- Database reads/writes (callers inject state)
- Graceful degradation fallback logic (feature 010)
- WorkflowStateEngine orchestration class (feature 008)

## Dependencies

- **006-transition-guard-audit-and-rul** (completed) — provides `guard-rules.yaml` as authoritative input

## Related Features

- **005-workflowphases-table-with-dual** (completed) — provides `workflow_phases` table schema (informational context)
- **008-workflowstateengine-core** (planned) — consumes this library for orchestration
- **009-state-engine-mcp-tools-phase-r** (planned) — wraps this library as MCP tools
- **010-graceful-degradation-to-metajs** (planned) — adds fallback when engine unavailable

## Constraints

- All functions must be pure (no I/O, no side effects)
- Module must work with existing venv: `plugins/iflow/.venv/bin/python`
- Follow existing `entity_registry` coding patterns (dataclasses, type hints, pytest)
- Guard IDs (G-XX) must be traceable from test names to `guard-rules.yaml` entries
- Phase sequence constant must be the single canonical definition — duplicates will be removed in features 014-017

## Risks

| Risk | Mitigation |
|------|-----------|
| Behavioral drift between Python and markdown pseudocode | Test cases derived from markdown examples; cross-reference each function against source SKILL.md |
| Guard consolidation loses edge cases | Each G-XX has dedicated test; consolidation preserves all guard behaviors as code paths |
| Downstream features may need different signatures | Pure functions with simple parameters are easy to wrap; avoid premature abstraction |
| venv dependency conflicts | No new runtime dependencies — uses only stdlib (dataclasses, enum, typing). Test dependency (pytest) already in existing venv. |

## Deliverables

1. `plugins/iflow/hooks/lib/transition_gate/__init__.py` — Public API exports
2. `plugins/iflow/hooks/lib/transition_gate/models.py` — Dataclasses and enums
3. `plugins/iflow/hooks/lib/transition_gate/constants.py` — Phase sequence, prerequisites, guard metadata
4. `plugins/iflow/hooks/lib/transition_gate/gate.py` — Core validation functions (~25 functions)
5. `plugins/iflow/hooks/lib/transition_gate/test_gate.py` — Comprehensive tests (86+ test cases)
