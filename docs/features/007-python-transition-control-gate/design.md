# Design: Python Transition Control Gate

## Prior Art Research

### Codebase Patterns

- **entity_registry module** (`plugins/iflow/hooks/lib/entity_registry/`): Flat module structure with co-located tests, dataclasses with `str | None` typing, file headers `"""Docstring."""` + `from __future__ import annotations`, section dividers `# ---...---`
- **PHASE_SEQUENCE prototype** in `backfill.py:30-68`: Tuple constant defining phase order with `_derive_next_phase()` — direct prototype for `get_next_phase()` (G-25)
- **No enum precedent** in codebase: First use of `enum.Enum`; adopt `class Phase(str, Enum)` for JSON serialization
- **`__init__.py` exports**: entity_registry has empty init; transition_gate will export all public functions per AC-1 (departure from pattern)

### External Research

- No Python FSM library (transitions, python-statemachine, sismic) natively supports structured guard results with guard_id traceability
- Custom `TransitionResult(allowed, reason, severity, guard_id)` is idiomatic Python — aligns with existing dataclass patterns
- Decision: Custom implementation, no external dependencies (stdlib only per spec constraints)

## Architecture Overview

### Module Structure

```
plugins/iflow/hooks/lib/transition_gate/
├── __init__.py      # Public API: re-exports gate functions + models + constants
├── models.py        # Dataclasses + Enums (zero business logic)
├── constants.py     # Phase sequence, prerequisites, guard metadata
├── gate.py          # 25 pure validation functions
└── test_gate.py     # 86+ test cases (pytest)
```

### Data Flow

```
Caller (feature 008 WorkflowStateEngine)
  │
  ├─ Reads .meta.json, artifacts, git state
  ├─ Constructs FeatureState (convenience container)
  ├─ Extracts primitive values from FeatureState
  │
  ▼
gate.py functions (pure)
  │
  ├─ Accepts primitives only (str, bool, int, float, list[str])
  ├─ References constants.py for sequence, prerequisites, metadata
  ├─ Returns TransitionResult(allowed, reason, severity, guard_id)
  │
  ▼
Caller interprets result
  ├─ severity=block → halt transition
  ├─ severity=warn → prompt user (or auto-resolve in YOLO)
  └─ severity=info → log and continue
```

### Dependency Direction

```
__init__.py ──imports──▶ gate.py ──imports──▶ models.py
                         │                    ▲
                         └──imports──▶ constants.py ──imports──┘
```

No circular dependencies. `models.py` has zero internal imports. `constants.py` imports only `models.py` (for Phase enum in PHASE_SEQUENCE). `gate.py` imports both.

## Components

### models.py

Defines all type contracts. Zero business logic, zero internal imports.

**Enums:**
- `Phase(str, Enum)` — 7 values matching SKILL.md: brainstorm, specify, design, create-plan, create-tasks, implement, finish. Python identifiers use underscores (`Phase.create_plan`) but string values use hyphens (`"create-plan"`) to match existing codebase convention. `str` mixin enables `Phase.create_plan == "create-plan"` and JSON serialization.
- `Severity(str, Enum)` — block, warn, info.
- `Enforcement(str, Enum)` — hard_block, soft_warn, informational. Guard metadata only, not in function signatures.
- `YoloBehavior(str, Enum)` — auto_select, hard_stop, skip, unchanged. YAML hyphens → Python underscores.

**Dataclasses:**
- `TransitionResult(frozen=True)` — Immutable output of every gate function. Fields: allowed (bool), reason (str), severity (Severity), guard_id (str).
- `FeatureState` — Mutable convenience container for callers. NOT passed to gate functions. Fields per spec.
- `PhaseInfo` — Phase state container. Fields: phase (Phase), started (bool), completed (bool).

### constants.py

Single source of truth for all static configuration. Imports only `models.py`.

- `PHASE_SEQUENCE: tuple[Phase, ...]` — Canonical 7-phase tuple. The authoritative definition per SC-5.
- `COMMAND_PHASES: tuple[Phase, ...]` — Subset excluding brainstorm (specify through finish). For guards that only apply to command-driven phases.
- `HARD_PREREQUISITES: dict[str, list[str]]` — Maps phase name → required artifact filenames.
- `ARTIFACT_PHASE_MAP: dict[str, str]` — Maps phase name → output artifact filename.
- `GUARD_METADATA: dict[str, dict]` — Maps guard_id (e.g., "G-22") → `{"enforcement": Enforcement, "yolo_behavior": YoloBehavior, "affected_phases": list[str]}`. Enables callers to look up enforcement and YOLO behavior per guard.
- `ARTIFACT_GUARD_MAP: dict[tuple[str, str], str]` — Maps `(phase, artifact_name)` → guard_id for Level 4 differentiation in `validate_artifact`. Default G-05; implement+tasks.md → G-06.
- `SERVICE_GUARD_MAP: dict[str, str]` — Maps service context → guard_id for `fail_open_mcp` (G-13: brainstorm, G-14: create-feature, G-15: create-project, G-16: retrospective).
- `PHASE_GUARD_MAP: dict[str, dict[str, str]]` — Maps gate type + phase → guard_id for multi-phase review gates (review_quality_gate, phase_handoff_gate).
- `MIN_ARTIFACT_SIZE: int` — 100 bytes.
- `MAX_ITERATIONS: dict[str, int]` — `{"brainstorm": 3, "default": 5}`.

### gate.py

25 pure functions. Each returns `TransitionResult`. Functions accept only primitive types (str, bool, int, float, list[str]) per SC-3.

**Internal helpers (not exported):**
- `_pass_result(guard_id, reason)` → `TransitionResult(allowed=True, reason, Severity.info, guard_id)`
- `_block(guard_id, reason)` → `TransitionResult(allowed=False, reason, Severity.block, guard_id)`
- `_warn(guard_id, reason)` → `TransitionResult(allowed=True, reason, Severity.warn, guard_id)`
- `_phase_index(phase)` → int index in PHASE_SEQUENCE. Returns -1 for invalid phase (never raises).

**Error handling strategy:** Public functions receiving invalid inputs (unknown phase, unknown service_name) return `TransitionResult(allowed=False, reason="Invalid input: {detail}", severity=Severity.block, guard_id="INVALID")`. No exceptions for predictable bad inputs — callers should not need try/except.

**YOLO helper (exported):**
- `check_yolo_override(guard_id: str, is_yolo: bool) -> TransitionResult | None` — Returns None if guard should run normally. Returns pre-built TransitionResult for skip (`allowed=True, severity=info, reason="Skipped in YOLO mode"`) or auto_select (`allowed=True, severity=warn, reason="Auto-selected default in YOLO mode"`). For hard_stop and unchanged, returns None (guard runs normally). Looks up `GUARD_METADATA[guard_id].yolo_behavior`. Callers invoke this before each gate function and short-circuit if non-None.

**Function categories (25 functions, 43 guards):**

| Category | Functions | Guards |
|----------|-----------|--------|
| Artifact validation | validate_artifact | G-02..06 |
| Prerequisite checks | check_hard_prerequisites, validate_prd, check_prd_exists | G-07, G-08, G-09 |
| Branch validation | check_branch | G-11 |
| Service availability | fail_open_mcp | G-13..16 |
| Phase transition | check_partial_phase, check_backward_transition, validate_transition, check_soft_prerequisites, get_next_phase | G-17, G-18, G-22, G-23, G-25 |
| Pre-merge | pre_merge_validation, check_merge_conflict | G-27, G-28, G-29, G-30 |
| Review gates | brainstorm_quality_gate, brainstorm_readiness_gate, review_quality_gate, phase_handoff_gate, implement_circuit_breaker | G-31..41, G-46, G-47 |
| Status/feature | check_active_feature_conflict, secretary_review_criteria, check_active_feature, planned_to_active_transition, check_terminal_status, check_task_completion | G-45, G-48..53 |
| YOLO-specific | check_orchestrate_prerequisite | G-60 |

### __init__.py

Re-exports all public symbols for clean imports:
```python
from transition_gate import validate_transition, TransitionResult, Phase
```

Uses `__all__` to define the public API explicitly. Exports: all 25 gate functions + `check_yolo_override`, all 4 enums, all 3 dataclasses, key constants (PHASE_SEQUENCE, COMMAND_PHASES, GUARD_METADATA, ARTIFACT_GUARD_MAP, SERVICE_GUARD_MAP).

### test_gate.py

Pytest module. Minimum 86 test cases (one pass + one fail per guard ID). Test naming: `test_G{XX}_{function_name}_{pass|fail}[_variant]`. Includes SC-5 canonical sequence verification test against SKILL.md.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| `str` enum mixin (`str, Enum`) | Enables string comparison (`Phase.specify == "specify"`) and JSON serialization without custom encoders |
| Flat module (no subpackages) | 25 functions fit in ~500 lines. Mirrors entity_registry pattern. Avoids over-engineering. |
| `frozen=True` for TransitionResult | Immutable output prevents accidental mutation. Pure function output should be read-only. |
| `tuple` for PHASE_SEQUENCE | Immutable. Prevents accidental mutation. Matches backfill.py prototype. |
| No `__post_init__` validation | Dataclasses are pure data containers. Validation is caller responsibility. Matches entity_registry pattern. |
| Multi-guard → first-failing guard_id | Functions covering multiple guards (e.g., validate_artifact for G-02..06) return the guard_id of the first failing check. On pass, return the primary guard_id. |
| YOLO split: 3 functions with `is_yolo`, rest via caller | Only functions where YOLO changes internal behavior accept `is_yolo` (hard_stop, specific logic). For skip/auto_select guards, caller checks GUARD_METADATA before calling. |
| `str` parameters (not Phase enum) | Functions accept `str` for phase parameters per SC-3 purity. Internally convert via `Phase(phase_str)` for validation and comparison. |
| G-51 enforcement override | `check_terminal_status` uses Severity.block despite guard-rules.yaml soft-warn. Per spec Enforcement Overrides table. |

## Risks

| Risk | Mitigation |
|------|-----------|
| Multi-guard functions may mask individual guard failures | Return first failing guard_id; callers can invoke per-guard if granularity needed |
| Phase enum string values must match SKILL.md exactly | SC-5 test verifies against SKILL.md canonical sequence |
| Guard metadata may drift from guard-rules.yaml | Test verifies guard count (43) and all guard IDs present in GUARD_METADATA |
| YOLO handling split between library and caller | GUARD_METADATA exposes yolo_behavior so callers can decide; boundary documented in __init__.py |

## Interfaces

### Enums

```python
class Phase(str, Enum):
    brainstorm = "brainstorm"
    specify = "specify"
    design = "design"
    create_plan = "create-plan"      # Python identifier: create_plan, value: "create-plan"
    create_tasks = "create-tasks"    # Python identifier: create_tasks, value: "create-tasks"
    implement = "implement"
    finish = "finish"

class Severity(str, Enum):
    block = "block"
    warn = "warn"
    info = "info"

class Enforcement(str, Enum):
    hard_block = "hard_block"
    soft_warn = "soft_warn"
    informational = "informational"

class YoloBehavior(str, Enum):
    auto_select = "auto_select"
    hard_stop = "hard_stop"
    skip = "skip"
    unchanged = "unchanged"
```

### Dataclasses

```python
@dataclass(frozen=True)
class TransitionResult:
    allowed: bool
    reason: str
    severity: Severity
    guard_id: str

@dataclass
class FeatureState:
    feature_id: str
    status: str
    current_branch: str
    expected_branch: str
    completed_phases: list[str]
    active_phase: str | None
    meta_has_brainstorm_source: bool

@dataclass
class PhaseInfo:
    phase: Phase
    started: bool
    completed: bool
```

### Gate Functions

#### Artifact Validation

```python
def validate_artifact(
    phase: str,
    artifact_name: str,
    artifact_path_exists: bool,
    artifact_size: int,
    has_headers: bool,
    has_required_sections: bool,
) -> TransitionResult:
    """4-level artifact content validation with per-phase BLOCKED messages.

    Level 1 (G-02): artifact_path_exists
    Level 2 (G-03): artifact_size >= MIN_ARTIFACT_SIZE
    Level 3 (G-04): has_headers (markdown structure)
    Level 4 (G-05/G-06): has_required_sections

    artifact_name distinguishes which artifact is validated (e.g., "spec.md"
    vs "tasks.md" for implement phase), enabling G-05/G-06 differentiation.
    Guard ID from ARTIFACT_GUARD_MAP[(phase, artifact_name)].
    Returns first failing level's guard_id. On pass, returns primary guard_id.
    BLOCKED message template: "BLOCKED: Valid {artifact_name} required before {phase}."
    """
```

#### Prerequisite Checks

```python
def check_hard_prerequisites(
    phase: str,
    existing_artifacts: list[str],
) -> TransitionResult:
    """G-08: Maps phase to required artifacts via HARD_PREREQUISITES.
    Returns missing artifact list in reason on failure."""

def validate_prd(prd_path_exists: bool) -> TransitionResult:
    """G-07: PRD existence check for project creation."""

def check_prd_exists(
    prd_path_exists: bool,
    meta_has_brainstorm_source: bool,
) -> TransitionResult:
    """G-09: Soft redirect for specify when PRD missing.
    Warns if no PRD and no brainstorm source."""
```

#### Branch Validation

```python
def check_branch(
    current_branch: str,
    expected_branch: str,
) -> TransitionResult:
    """G-11: Branch mismatch detection.
    Returns switch suggestion in reason on mismatch."""
```

#### Service Availability

```python
def fail_open_mcp(
    service_name: str,
    service_available: bool,
) -> TransitionResult:
    """G-13/14/15/16: Warn when MCP/external service unavailable.
    Always returns allowed=True (fail-open pattern).
    Guard ID from SERVICE_GUARD_MAP[service_name]."""
```

#### Phase Transition

```python
def check_partial_phase(
    phase: str,
    phase_started: bool,
    phase_completed: bool,
) -> TransitionResult:
    """G-17: Detects interrupted phases (started but not completed).
    Returns resume suggestion in reason."""

def check_backward_transition(
    target_phase: str,
    last_completed_phase: str,
) -> TransitionResult:
    """G-18: Warns when target phase is at or before last completed phase."""

def validate_transition(
    current_phase: str,
    target_phase: str,
    completed_phases: list[str],
) -> TransitionResult:
    """G-22: Canonical phase sequence validation.
    Verifies target is reachable from current position."""

def check_soft_prerequisites(
    target_phase: str,
    completed_phases: list[str],
) -> TransitionResult:
    """G-23: Warns about skipped optional phases between last completed
    and target."""

def get_next_phase(last_completed_phase: str) -> TransitionResult:
    """G-25: Returns next phase in PHASE_SEQUENCE.
    On success: allowed=True, reason contains next phase name.
    At end of sequence: allowed=False (no next phase)."""
```

#### Pre-Merge

```python
def pre_merge_validation(
    checks_passed: bool,
    max_attempts: int,
    current_attempt: int,
) -> TransitionResult:
    """G-27/29: Pre-merge validation gate.

    Truth table:
    checks_passed=True             → allowed=True, info (G-27)
    checks_passed=False, attempt<max → allowed=False, block (G-27, "retry")
    checks_passed=False, attempt>=max → allowed=False, block (G-29, "exhausted")
    """

def check_merge_conflict(
    is_yolo: bool,
    merge_succeeded: bool,
) -> TransitionResult:
    """G-28/30: YOLO hard-stop on merge conflict.
    Blocks in YOLO mode when merge fails (cannot auto-resolve)."""
```

#### Review Gates

```python
def brainstorm_quality_gate(
    iteration: int,
    max_iterations: int,
    reviewer_approved: bool,
) -> TransitionResult:
    """G-32: PRD quality review loop.
    allowed=True when approved or cap reached (with warn)."""

def brainstorm_readiness_gate(
    iteration: int,
    max_iterations: int,
    reviewer_approved: bool,
    has_blockers: bool,
) -> TransitionResult:
    """G-31/33: Readiness check with circuit breaker.

    Decision matrix:
    approved=True, no blockers          → allowed=True, info (G-31, "ready")
    approved=True, has blockers         → allowed=False, block (G-33, "blockers remain")
    approved=False, iteration<max       → allowed=False, block (G-31, "not ready, retry")
    approved=False, iteration>=max      → allowed=True, warn (G-33, "cap reached")
    """

def review_quality_gate(
    phase: str,
    iteration: int,
    max_iterations: int,
    reviewer_approved: bool,
    has_blockers_or_warnings: bool,
) -> TransitionResult:
    """G-34/36/38/40/46: Pure state evaluator for review loops.

    allowed=True: Review approved (proceed) or cap reached (warn).
    allowed=False: Not yet approved, under cap (continue loop).
    Guard ID from PHASE_GUARD_MAP["review_quality"][phase]."""

def phase_handoff_gate(
    phase: str,
    iteration: int,
    max_iterations: int,
    reviewer_approved: bool,
    has_blockers_or_warnings: bool,
) -> TransitionResult:
    """G-35/37/39/47: Pure state evaluator for handoff review loops.
    Same semantics as review_quality_gate.
    Guard ID from PHASE_GUARD_MAP["phase_handoff"][phase]."""

def implement_circuit_breaker(
    is_yolo: bool,
    iteration: int,
    max_iterations: int,
) -> TransitionResult:
    """G-41: YOLO safety boundary.
    Hard-stop in YOLO mode after max failed reviews.
    In non-YOLO mode, warns at cap."""
```

#### Status and Feature

```python
def check_active_feature_conflict(
    active_feature_count: int,
) -> TransitionResult:
    """G-48: Warns when active features already exist."""

def secretary_review_criteria(
    confidence: float,
    is_direct_match: bool,
) -> TransitionResult:
    """G-45: Skip reviewer when confidence > 85% and direct match.
    allowed=True (skip review) when both conditions met."""

def check_active_feature(
    has_active_feature: bool,
) -> TransitionResult:
    """G-49: Soft-warns when starting specification without active feature."""

def planned_to_active_transition(
    current_status: str,
    branch_exists: bool,
) -> TransitionResult:
    """G-50: Multi-step Planned->Active gate.
    Blocks if status is not 'planned' or branch doesn't exist."""

def check_terminal_status(current_status: str) -> TransitionResult:
    """G-51: Blocks modification of completed/abandoned features.
    ENFORCEMENT OVERRIDE: hard-block (overrides guard-rules.yaml soft-warn)."""

def check_task_completion(
    incomplete_task_count: int,
) -> TransitionResult:
    """G-52/53: Task completion gate before finish.
    Warns if incomplete tasks remain."""

def check_orchestrate_prerequisite(is_yolo: bool) -> TransitionResult:
    """G-60: Requires YOLO for orchestrate subcommand.
    Blocks when is_yolo=False."""
```

### Constants Structure

```python
PHASE_SEQUENCE = (
    Phase.brainstorm, Phase.specify, Phase.design,
    Phase.create_plan, Phase.create_tasks,
    Phase.implement, Phase.finish,
)

COMMAND_PHASES = PHASE_SEQUENCE[1:]  # specify through finish

HARD_PREREQUISITES = {
    "design": ["spec.md"],
    "create-plan": ["spec.md", "design.md"],
    "create-tasks": ["spec.md", "design.md", "plan.md"],
    "implement": ["spec.md", "tasks.md"],
    "finish": [],  # No artifact prereqs; task completion handled by check_task_completion (G-52/53)
}

ARTIFACT_PHASE_MAP = {
    "brainstorm": "prd.md",
    "specify": "spec.md",
    "design": "design.md",
    "create-plan": "plan.md",
    "create-tasks": "tasks.md",
}

ARTIFACT_GUARD_MAP = {
    # (phase, artifact_name) -> guard_id for Level 4 differentiation
    ("implement", "spec.md"): "G-05",
    ("implement", "tasks.md"): "G-06",
    # Default: all other (phase, artifact) pairs use "G-05"
}

MIN_ARTIFACT_SIZE = 100  # bytes
MAX_ITERATIONS = {"brainstorm": 3, "default": 5}

SERVICE_GUARD_MAP = {
    "brainstorm": "G-13",
    "create-feature": "G-14",
    "create-project": "G-15",
    "retrospective": "G-16",
}

PHASE_GUARD_MAP = {
    "review_quality": {
        "specify": "G-34", "design": "G-36",
        "create-plan": "G-38", "implement": "G-40",
        "create-tasks": "G-46",
    },
    "phase_handoff": {
        "specify": "G-35", "design": "G-37",
        "create-plan": "G-39", "create-tasks": "G-47",
    },
}

GUARD_METADATA = {
    "G-02": {"enforcement": Enforcement.hard_block, "yolo_behavior": YoloBehavior.unchanged, ...},
    # ... 43 entries total, one per guard with consolidation_target: transition_gate
}
```
