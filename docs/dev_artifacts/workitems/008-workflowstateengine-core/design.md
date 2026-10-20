# Design: WorkflowStateEngine Core (Feature 008)

## Prior Art Research

### Codebase Patterns

- **transition_gate (feature 007):** 25 pure gate functions returning `TransitionResult(allowed, reason, severity, guard_id)`. Gate functions accept only primitives (no state objects). The engine consumes 5 of 25 gates. `PHASE_SEQUENCE` is a 7-element `tuple[Phase, ...]` where `Phase` is a `str`-Enum. `HARD_PREREQUISITES` maps phase→artifact filenames using transitive closure semantics.
- **entity_registry (feature 005):** `EntityDatabase` with WAL mode, foreign keys, auto-migration. Workflow phases CRUD: `create_workflow_phase()`, `get_workflow_phase()`, `update_workflow_phase()`, `list_workflow_phases()`. Uses `_UNSET` sentinel for optional kwargs. Constructor takes `db_path: str` (`:memory:` for tests).
- **backfill.py:** Existing `.meta.json` → DB hydration logic with `STATUS_TO_KANBAN` mapping and `_derive_next_phase()` using `PHASE_SEQUENCE.index()`. The engine's lazy hydration follows the same pattern but imports from `transition_gate` (not a local duplicate).
- **Test conventions:** `class TestFeatureName`, `test_{guard_id}_{description}`, pytest fixtures with `tmp_path`/`:memory:` databases, `from __future__ import annotations` as first import.

### External Research

- **Stateless orchestrator pattern (django-fsm, AWS Lambda FSM):** State lives in the DB, the engine holds only the transition graph. Each invocation: read state → evaluate transitions → execute action → write state. Canonical for DB-backed workflow engines.
- **Guard composition:** Industry standard is AND-composition — `all(gate(ctx) for gate in gates)`. Guards are pure predicates, validators raise exceptions. Maps directly to transition_gate's `allowed: bool` pattern.
- **SQLite WAL mode:** Concurrent readers with single writer. EntityDatabase already configures WAL, `cache_size=-8000`, `busy_timeout=5000`.

### Decision: No external FSM library

The engine does NOT use `transitions`, `python-statemachine`, or any external FSM library. Rationale:
1. NFR-2 prohibits new pip dependencies
2. The phase sequence is linear (not a graph) — a full FSM is over-engineering
3. Gate functions already exist in transition_gate — the engine composes them, not replaces them
4. Total code is estimated at 250-350 lines (engine + models + tests) — the overhead of integrating a library exceeds writing it directly

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Callers                           │
│  (MCP tools, commands, hooks, dashboards)            │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│              WorkflowStateEngine                     │
│                                                      │
│  get_state()          → FeatureWorkflowState         │
│  transition_phase()   → list[TransitionResult]       │
│  complete_phase()     → FeatureWorkflowState         │
│  validate_prerequisites() → list[TransitionResult]   │
│  list_by_phase()      → list[FeatureWorkflowState]   │
│  list_by_status()     → list[FeatureWorkflowState]   │
│                                                      │
│  Constructor: (db: EntityDatabase, artifacts_root)   │
│  Instance state: db reference + artifacts_root path  │
│  No mutable state — stateless orchestrator           │
└──────┬──────────────────────┬───────────────────────┘
       │                      │
       ▼                      ▼
┌──────────────┐    ┌────────────────────┐
│ transition_  │    │  EntityDatabase    │
│ gate         │    │  (entity_registry) │
│              │    │                    │
│ 5 consumed:  │    │ workflow_phases:   │
│ - check_     │    │ - create/get/      │
│   backward   │    │   update/list/     │
│ - check_hard │    │   delete           │
│ - check_soft │    │                    │
│ - validate   │    │ entities:          │
│ - check_yolo │    │ - get_entity       │
│              │    │ - list_entities    │
│ constants:   │    │                    │
│ - PHASE_     │    │ .meta.json:        │
│   SEQUENCE   │    │ (filesystem        │
│ - HARD_      │    │  fallback only)    │
│   PREREQS    │    │                    │
└──────────────┘    └────────────────────┘
```

### Data Flow: transition_phase()

```
1. get_state(type_id)
   ├─ DB: get_workflow_phase(type_id)
   │  ├─ found → build FeatureWorkflowState(source="db")
   │  └─ None → _hydrate_from_meta_json()
   │            ├─ entity exists? → parse .meta.json → create_workflow_phase() → FeatureWorkflowState(source="meta_json")
   │            └─ no entity → return None
   │
2. _get_existing_artifacts(slug)
   └─ scan filesystem for artifacts in HARD_PREREQUISITES

3. gate evaluation (ordered, skip inapplicable):
   For each gate:
   ├─ if yolo_active: check_yolo_override(guard_id, True) FIRST
   │  └─ if non-None → short-circuit, use override result (skip gate call)
   │  └─ if None → proceed to call gate normally
   ├─ check_backward_transition(target, last_completed)  [skip if last_completed is None]
   ├─ check_hard_prerequisites(target, artifacts)
   ├─ check_soft_prerequisites(target, completed_phases)
   └─ validate_transition(current, target, completed)    [skip if current is None]

4. all gates pass?
   ├─ yes → update_workflow_phase(type_id, workflow_phase=target)
   └─ no  → skip DB write

5. return list[TransitionResult]
```

## Components

### C1: WorkflowStateEngine (engine.py)

**Responsibility:** Stateless orchestrator composing gate functions + DB operations.

**Constructor:** `__init__(self, db: EntityDatabase, artifacts_root: str)`
- Stores references only — no initialization logic, no DB calls
- `db` is an already-initialized `EntityDatabase` instance
- `artifacts_root` is the filesystem path for resolving feature artifact directories

**Public methods:** 6 methods matching spec (FR-1 through FR-7)
**Private helpers:** `_extract_slug()`, `_get_existing_artifacts()`, `_hydrate_from_meta_json()`, `_derive_completed_phases()`, `_next_phase_value()`, `_evaluate_gates()` (applies I6 skip conditions and YOLO override per TD-3)

### C2: FeatureWorkflowState (models.py)

**Responsibility:** Frozen dataclass representing a feature's workflow state at a point in time.

```python
@dataclass(frozen=True)
class FeatureWorkflowState:
    feature_type_id: str
    current_phase: str | None
    last_completed_phase: str | None
    completed_phases: tuple[str, ...]
    mode: str | None
    source: str  # "db" | "meta_json"
```

**Design decision:** Frozen dataclass (not mutable) because:
- State is a snapshot — callers should not mutate it
- Matches `TransitionResult` pattern from transition_gate
- Eliminates accidental mutation bugs

### C3: Public API (__init__.py)

**Responsibility:** Clean import surface.

```python
from .engine import WorkflowStateEngine
from .models import FeatureWorkflowState

__all__ = ["WorkflowStateEngine", "FeatureWorkflowState"]
```

### C4: Tests (test_engine.py)

**Responsibility:** Unit + integration tests covering all 10 success criteria.

**Test organization:**
- `TestGetState` — FR-1, SC-4, SC-9 (DB read, hydration, source indicator)
- `TestTransitionPhase` — FR-2, SC-1, SC-2, SC-3, SC-8, SC-10 (forward, blocked, backward, YOLO)
- `TestCompletePhase` — FR-3, SC-5 (phase completion, advancement)
- `TestValidatePrerequisites` — FR-4, SC-6 (dry run, no side effects)
- `TestBatchQueries` — FR-5, SC-7 (list_by_phase, list_by_status)
- `TestHydration` — FR-6 (all status paths, entity precondition)
- `TestHelpers` — internal helpers (_extract_slug, _get_existing_artifacts)
- `TestErrorHandling` — ValueError on missing feature, malformed type_id, unrecognized phase

## Interfaces

### I1: WorkflowStateEngine Public API

```python
class WorkflowStateEngine:
    """Stateless orchestrator — no mutable instance state beyond constructor refs."""

    def __init__(self, db: EntityDatabase, artifacts_root: str) -> None:
        """Store references only. No DB calls, no I/O."""

    def get_state(self, feature_type_id: str) -> FeatureWorkflowState | None:
        """Read feature workflow state from DB, falling back to .meta.json hydration.

        Args:
            feature_type_id: Entity type_id, e.g. "feature:008-workflowstateengine-core"

        Returns:
            FeatureWorkflowState with source="db" or source="meta_json",
            or None if entity not registered AND no .meta.json exists.

        Side effects:
            May create a workflow_phases row (hydration) if DB row missing
            but entity exists and .meta.json is present.
        """

    def transition_phase(
        self,
        feature_type_id: str,
        target_phase: str,
        yolo_active: bool = False,
    ) -> list[TransitionResult]:
        """Validate and enter a target phase.

        Args:
            feature_type_id: Entity type_id
            target_phase: Phase value string (e.g. "design")
            yolo_active: If True, check YOLO overrides per gate

        Returns:
            List of TransitionResult in gate evaluation order.
            Skipped gates are omitted. YOLO overrides appear in place of skipped gates.
            Identical return type for success and failure paths.

        Side effects:
            If all gates pass: updates workflow_phase in DB.
            If any gate fails: no DB write.

        Raises:
            ValueError: If feature not found (get_state returns None).
        """

    def complete_phase(
        self, feature_type_id: str, phase: str
    ) -> FeatureWorkflowState:
        """Record a phase as completed and advance workflow_phase.

        Args:
            feature_type_id: Entity type_id
            phase: Phase value being completed (must match current_phase
                   or be a backward re-run)

        Returns:
            Updated FeatureWorkflowState reflecting the new state.

        Behavior:
            Sets last_completed_phase = phase.
            Sets workflow_phase = _next_phase_value(phase), EXCEPT:
            - Terminal phase (finish): sets workflow_phase = "finish"
              (not None) per TD-8 convention.
            - Backward re-run (phase < last_completed_phase): resets
              last_completed_phase to phase, sets workflow_phase =
              _next_phase_value(phase), effectively rolling back progress.

        Raises:
            ValueError: If phase doesn't match current_phase and is not
                        a backward re-run (target index > last_completed index).
            ValueError: If feature not found (get_state returns None).
        """

    def validate_prerequisites(
        self, feature_type_id: str, target_phase: str
    ) -> list[TransitionResult]:
        """Dry-run gate evaluation without executing the transition.

        Same gate evaluation logic as transition_phase() but never writes
        to the DB. Used by dashboards and MCP tools.

        Args:
            feature_type_id: Entity type_id
            target_phase: Proposed target phase

        Returns:
            List of TransitionResult (same as transition_phase would return).

        Side effects:
            Does not update workflow_phase. However, if get_state() triggers
            lazy hydration (creating a workflow_phases row from .meta.json),
            that DB write occurs as a side effect of reading state.

        Raises:
            ValueError: If feature not found (get_state returns None).
        """

    def list_by_phase(self, phase: str) -> list[FeatureWorkflowState]:
        """All features currently in the given phase.

        Args:
            phase: Phase value string (e.g. "design")

        Returns:
            List of FeatureWorkflowState with source="db".
            Empty list if no features match.

        Implementation:
            Calls db.list_workflow_phases(workflow_phase=phase).
            Each returned dict row is mapped to FeatureWorkflowState:
            - feature_type_id = row["type_id"]
            - current_phase = row["workflow_phase"]
            - last_completed_phase = row["last_completed_phase"]
            - completed_phases = _derive_completed_phases(row["last_completed_phase"])
            - mode = row["mode"]
            - source = "db"
        """

    def list_by_status(self, status: str) -> list[FeatureWorkflowState]:
        """All features with the given entity status.

        Args:
            status: Entity status string (e.g. "active", "completed")

        Returns:
            List of FeatureWorkflowState. Features without workflow_phases
            rows are included with current_phase=None, source="db".
            Empty list if no features match.
            Entities with status=None in the DB are excluded (only
            entities with an explicit status value are matched).

        Implementation:
            Calls db.list_entities(entity_type="feature"), filters by
            row["status"] == status (exact match, excludes None).
            For each matching entity, joins with get_workflow_phase()
            to build FeatureWorkflowState. If no workflow_phases row
            exists, populates current_phase=None, last_completed_phase=None,
            completed_phases=(), mode=None, source="db".
        """
```

### I2: FeatureWorkflowState Contract

```python
@dataclass(frozen=True)
class FeatureWorkflowState:
    feature_type_id: str            # "feature:{id}-{slug}"
    current_phase: str | None       # current workflow_phase value, None if no workflow_phases row exists
    last_completed_phase: str | None # None if no phases completed yet
    completed_phases: tuple[str, ...]  # derived from last_completed_phase via PHASE_SEQUENCE
    mode: str | None                # "standard" | "full" | None
    source: str                     # "db" | "meta_json"
```

**Invariants:**
- `completed_phases` is always `tuple(PHASE_SEQUENCE[:idx+1])` where `idx = index(last_completed_phase)`, or `()` if `last_completed_phase` is None
- `completed_phases` is a `tuple` (immutable) — prevents accidental mutation despite `frozen=True` (frozen prevents attribute reassignment but does not prevent mutation of mutable containers)
- `source` is always one of `"db"` or `"meta_json"` — never any other value
- Frozen: callers must not mutate (enforced by dataclass)

### I3: Private Helpers

```python
# Guard ID mapping — resolves guard_id BEFORE calling the gate,
# enabling YOLO override checks without parsing gate return values.
_GATE_GUARD_IDS: ClassVar[dict[str, str]] = {
    "check_backward_transition": "G-18",
    "check_hard_prerequisites": "G-08",
    "check_soft_prerequisites": "G-23",
    "validate_transition": "G-22",
}

def _extract_slug(self, feature_type_id: str) -> str:
    """Extract slug from type_id. 'feature:008-foo' → '008-foo'.
    Splits on ':' and returns second part.
    Raises ValueError if type_id does not contain ':'."""

def _get_existing_artifacts(self, feature_slug: str) -> list[str]:
    """Scan filesystem for artifacts listed in HARD_PREREQUISITES.
    Returns sorted list of filenames that exist in the feature directory."""

def _hydrate_from_meta_json(self, feature_type_id: str) -> FeatureWorkflowState | None:
    """Lazy hydration: parse .meta.json, derive state, backfill DB row.
    Calls _extract_slug(feature_type_id) to resolve the feature directory path.
    Returns None if entity not registered or .meta.json missing.
    Catches ValueError from _derive_completed_phases for malformed
    .meta.json data (unrecognized phase values) and returns None."""

def _derive_completed_phases(self, last_completed: str | None) -> tuple[str, ...]:
    """Static helper: tuple(PHASE_SEQUENCE[:idx+1]) or () if None.
    Raises ValueError if last_completed is not a recognized phase value."""

def _next_phase_value(self, current_phase: str) -> str | None:
    """Static helper: PHASE_SEQUENCE[idx+1] or None if at end.
    Raises ValueError if current_phase is not a recognized phase value."""

def _evaluate_gates(
    self,
    state: FeatureWorkflowState,
    target_phase: str,
    existing_artifacts: list[str],
    yolo_active: bool,
) -> list[TransitionResult]:
    """Run ordered gate evaluation. Returns results list.
    Skips inapplicable gates (per I6 skip conditions).
    For each non-skipped gate, if yolo_active:
      1. Call check_yolo_override(guard_id, True) FIRST (short-circuit)
      2. If non-None → use override result, do NOT call the gate
      3. If None → call the gate normally
    Uses _GATE_GUARD_IDS to resolve guard_id before the YOLO check."""
```

### I3b: .meta.json Expected Schema

The engine's `_hydrate_from_meta_json` expects these fields:

```json
{
  "id": "string",            // Feature numeric ID
  "slug": "string",          // Feature slug
  "status": "string",        // "active" | "completed" | "planned" | ...
  "mode": "string | null",   // "standard" | "full" | null
  "lastCompletedPhase": "string | null",  // Phase value or null
  "phases": {                // Object keyed by phase name
    "<phase>": {
      "started": "ISO timestamp",
      "completed": "ISO timestamp | absent"
    }
  }
}
```

Only `lastCompletedPhase`, `status`, and `mode` are read by hydration.
`phases` is not consumed by the engine (used by iflow commands directly).

### I4: Consumed Gate Function Signatures

The engine imports and calls these 5 functions from `transition_gate`:

```python
# From transition_gate (public API)
def check_backward_transition(
    target_phase: str, last_completed_phase: str
) -> TransitionResult:
    """G-18: Warns when target ≤ last_completed. Returns invalid_input for None/unknown."""

def check_hard_prerequisites(
    phase: str, existing_artifacts: list[str]
) -> TransitionResult:
    """G-08: Blocks if required artifacts missing per HARD_PREREQUISITES."""

def check_soft_prerequisites(
    target_phase: str, completed_phases: list[str]
) -> TransitionResult:
    """G-23: Warns about skipped optional phases. NOT about artifacts."""

def validate_transition(
    current_phase: str, target_phase: str, completed_phases: list[str]
) -> TransitionResult:
    """G-22: Validates phase ordering. Returns invalid_input for None/unknown."""

def check_yolo_override(
    guard_id: str, is_yolo: bool
) -> TransitionResult | None:
    """Returns non-None to replace a gate's result, or None to let gate run normally."""

# From transition_gate.constants (internal import — not in __all__)
HARD_PREREQUISITES: dict[str, list[str]]

# From transition_gate (public API)
PHASE_SEQUENCE: tuple[Phase, ...]
```

### I5: Consumed EntityDatabase Methods

```python
# Already-initialized instance received via constructor
class EntityDatabase:
    def get_workflow_phase(self, type_id: str) -> dict | None: ...
    def create_workflow_phase(
        self, type_id: str, *, kanban_column: str = "backlog",
        workflow_phase: str | None = None,
        last_completed_phase: str | None = None,
        mode: str | None = None,
        backward_transition_reason: str | None = None,
    ) -> dict: ...
    def update_workflow_phase(
        self, type_id: str, *, kanban_column=_UNSET,
        workflow_phase=_UNSET, last_completed_phase=_UNSET,
        mode=_UNSET, backward_transition_reason=_UNSET,
    ) -> dict: ...
    def list_workflow_phases(
        self, *, kanban_column: str | None = None,
        workflow_phase: str | None = None,
    ) -> list[dict]: ...
    def get_entity(self, type_id: str) -> dict | None: ...
    def list_entities(self, entity_type: str | None = None) -> list[dict]: ...
```

### I6: Gate Evaluation Skip Conditions

| Gate | Skip When | Rationale |
|------|-----------|-----------|
| `check_backward_transition` | `last_completed_phase is None` | New feature — no backward possible |
| `validate_transition` | `current_phase is None` | New feature entering first phase |
| `check_hard_prerequisites` | Never skipped | Always applicable |
| `check_soft_prerequisites` | Never skipped | Returns info-level for empty completed_phases |
| `check_yolo_override` | `yolo_active is False` | Only checked when YOLO mode active |

### I7: Interaction Sequences

**Typical lifecycle (caller perspective):**
```
engine = WorkflowStateEngine(db, artifacts_root)

# Enter specify phase
results = engine.transition_phase("feature:008-foo", "specify")
# ... work happens ...
state = engine.complete_phase("feature:008-foo", "specify")
# state.current_phase == "design", state.last_completed_phase == "specify"

# Enter design phase
results = engine.transition_phase("feature:008-foo", "design")
# ... work happens ...
state = engine.complete_phase("feature:008-foo", "design")
# state.current_phase == "create-plan"
```

**Dashboard query:**
```
active_features = engine.list_by_status("active")
features_in_design = engine.list_by_phase("design")
readiness = engine.validate_prerequisites("feature:008-foo", "implement")
```

## Technical Decisions

### TD-1: Stateless Engine, No Caching

The engine performs no in-memory caching of feature states. Every `get_state()` call hits the DB.

**Rationale:** Simplicity. SQLite with WAL mode handles concurrent reads efficiently. Caching introduces invalidation complexity with zero measurable benefit at the expected scale (<100 features). If performance becomes an issue, caching can be added later without API changes.

### TD-2: Gate Evaluation Order Is Fixed

Gates are always evaluated in the same order: backward → hard_prereq → soft_prereq → validate_transition. This is not configurable.

**Rationale:** Deterministic behavior. Changing evaluation order could change which gates are reached (if YOLO overrides earlier gates). Fixed order matches the spec and eliminates a category of bugs.

### TD-3: YOLO Override Is Per-Gate, Not Global

Each gate is independently checked for YOLO override. `check_yolo_override(guard_id, True)` returns non-None only if the guard's metadata specifies `yolo_behavior != "unchanged"`.

**Rationale:** Granular control. Some guards (like hard_block) should NOT be YOLO-skippable. The existing `GUARD_METADATA` in transition_gate already encodes this per-guard behavior.

### TD-4: Hydration Returns None for Missing Entity (Not Exception)

When `get_entity(type_id)` returns None during hydration, the engine returns None rather than raising an exception.

**Rationale:** The engine does not manage entities. A missing entity is not an engine error — it means the caller should register the entity first. Returning None lets callers handle this gracefully.

### TD-5: Internal Import of HARD_PREREQUISITES

The engine imports `HARD_PREREQUISITES` from `transition_gate.constants` (not the public `__init__.py`).

**Rationale:** `HARD_PREREQUISITES` is not in transition_gate's `__all__`. Co-located modules with shared release cycles can use internal imports. This avoids modifying transition_gate's public API.

### TD-6: complete_phase() Backward Re-run Resets Progress

When `complete_phase()` is called with a phase earlier than `last_completed_phase`, it resets `last_completed_phase` to that phase and sets `workflow_phase` to `_next_phase_value(phase)`. Subsequent phases are no longer considered completed.

**DB writes for backward re-run:** `update_workflow_phase(type_id, last_completed_phase=phase, workflow_phase=_next_phase_value(phase))`. This is identical to the forward case — the engine does not special-case backward re-runs in its DB write logic.

**Rationale:** Backward re-runs represent intentional rework. The caller is redoing a phase and should expect the workflow to reflect the reset state. Preserving a stale `last_completed_phase` would create inconsistency between what the user intends and what the DB reflects.

### TD-7: kanban_column Management Out of Scope

The engine reads `kanban_column` from the DB but does not manage or update it. Kanban column transitions are a UI concern (features 018-022) and will be managed by a separate Kanban module.

**Rationale:** Separation of concerns. The engine manages workflow phase transitions. Kanban columns represent visual board state which has different update triggers and rules.

### TD-8: Completed Features Use workflow_phase="finish"

For completed features, hydration sets `workflow_phase="finish"` (not `None`). This matches the existing `backfill.py` convention where completed features get `workflow_phase="finish"`.

**Terminal phase in complete_phase():** When `complete_phase("finish")` is called, `_next_phase_value("finish")` returns `None` (finish is the last element). The engine detects this and writes `workflow_phase="finish"` instead of `None`, ensuring consistency with hydration and backfill. The check: `if next_phase is None: next_phase = phase` (i.e., keep current phase as workflow_phase).

**Rationale:** Consistency with existing DB data. `backfill.py` has already populated `workflow_phase="finish"` for completed features. Using `None` would create a split where backfilled rows have "finish" and engine-hydrated rows have `None`, breaking `list_by_phase("finish")` queries. Note: Spec FR-6 line 129 is updated as errata to align with this convention.

### TD-9: Consistent Error Handling — ValueError for Missing Features

All public methods that operate on a specific feature (`transition_phase`, `complete_phase`, `validate_prerequisites`) raise `ValueError` when the feature is not found. Only `get_state()` returns `None` — it's the primitive reader that callers use to check existence.

**Rationale:** Consistent caller contract. Returning empty lists from `transition_phase()` creates ambiguity (does empty mean "all gates passed" or "feature missing"?). ValueError is explicit and matches Python conventions for invalid arguments.

## Risks

### R1: HARD_PREREQUISITES Import Breakage (Low)

**Risk:** If transition_gate reorganizes its internal modules, the `from transition_gate.constants import HARD_PREREQUISITES` import breaks.

**Mitigation:** Co-located modules with shared release cycle. Any transition_gate refactor would naturally update workflow_engine. Tests catch this immediately.

### R2: .meta.json Schema Changes (Low)

**Risk:** If .meta.json fields are renamed or restructured, hydration breaks.

**Mitigation:** .meta.json is project-internal with a stable schema. Hydration is a bridge mechanism — once all features have workflow_phases rows, it becomes a no-op.

### R3: Gate Function Signature Changes (Low)

**Risk:** If transition_gate changes gate function signatures, engine calls break.

**Mitigation:** Gate functions have a stable, tested API (feature 007). The engine's tests will catch signature mismatches immediately.

### R4: EntityDatabase API Changes (Low)

**Risk:** If entity_registry changes CRUD method signatures.

**Mitigation:** Same co-location and release cycle argument. Integration tests catch this.
