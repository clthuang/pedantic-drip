# Specification: WorkflowStateEngine Core (Feature 008)

## Problem Statement

Workflow phase transitions are currently managed by LLM-interpreted markdown pseudocode duplicated across 5+ locations. This produces:

1. **Duplication drift risk** — phase sequence defined in workflow-state/SKILL.md, secretary.md, create-specialist-team.md, and inline in multiple command files
2. **Token overhead** — every phase command re-reads and re-interprets ~1,500 lines of markdown transition logic
3. **Non-deterministic evaluation** — LLMs may interpret edge cases differently across invocations (theoretical risk, no observed failures yet)
4. **No programmatic state access** — dashboards, MCP tools, and hooks cannot query workflow state without parsing .meta.json

Feature 007 delivered 25 pure gate functions covering all 43 transition guards. Feature 005 delivered the `workflow_phases` database table. Feature 008 composes these into a `WorkflowStateEngine` module that orchestrates transitions deterministically.

## Scope

### In Scope

- **WorkflowStateEngine Python module** — stateless orchestrator that:
  - Accepts transition requests `(feature_type_id, target_phase)` and validates via transition_gate gate functions
  - Reads current state from `workflow_phases` table (or .meta.json fallback)
  - Writes updated state to `workflow_phases` table on successful transition
  - Returns structured `TransitionResult` (reuses transition_gate dataclass)
- **State hydration** — lazy per-feature: on first access, if `workflow_phases` row missing, derive state from `.meta.json` and backfill
- **Batch query functions** — `list_by_phase(phase)`, `list_by_status(status)` for dashboard/MCP consumers
- **Prerequisite validation** — `validate_prerequisites(feature_type_id, target_phase)` returns all gate results for a proposed transition without executing it
- **Unit and integration tests** — covering all transition paths, edge cases, fallback behavior

### Out of Scope

- MCP tool definitions (feature 009)
- Graceful degradation when DB fully unavailable (feature 010)
- Command migration to use engine (features 014-016)
- Kanban UI (features 018-022)
- Entity registration or .meta.json management (existing entity_registry handles these)

## Dependencies

| Dependency | What it provides | Status |
|-----------|-----------------|--------|
| 007-python-transition-control-gate | 25 gate functions, TransitionResult, Phase enum, constants | Completed |
| 005-workflowphases-table-with-dual | workflow_phases table, CRUD methods on EntityDatabase | Completed |

## Functional Requirements

### FR-1: State Reading

The engine reads feature workflow state from two sources with defined priority:

1. **Primary:** `EntityDatabase.get_workflow_phase(type_id)` — returns `{workflow_phase, kanban_column, last_completed_phase, mode}`
2. **Fallback:** Parse `.meta.json` from feature artifacts directory — derive `workflow_phase` from `lastCompletedPhase` using `PHASE_SEQUENCE` indexing (see Technical Notes: Deriving next phase)

State reading returns a `FeatureWorkflowState` dataclass:
```python
@dataclass(frozen=True)
class FeatureWorkflowState:
    feature_type_id: str       # e.g., "feature:008-workflowstateengine-core"
    current_phase: str | None  # current workflow_phase value
    last_completed_phase: str | None
    completed_phases: list[str]  # all phases up to and including last_completed_phase
    mode: str | None           # "standard" | "full" | None (workflow mode, not runtime YOLO flag)
    source: str                # "db" | "meta_json" — indicates which source was used
```

### FR-2: Phase Transition Execution

`transition_phase(feature_type_id, target_phase, yolo_active=False)` performs:

1. Read current state (FR-1)
2. Resolve existing artifacts via `_get_existing_artifacts()` (FR-7)
3. Validate transition via gate functions (in order, skipping inapplicable gates):
   - `check_backward_transition(target_phase, last_completed_phase)` — warn on backward, don't block. **Skip if `last_completed_phase` is None** (new feature, no completed phases — backward check is inapplicable)
   - `check_hard_prerequisites(target_phase, existing_artifacts)` — block if missing required artifacts
   - `check_soft_prerequisites(target_phase, completed_phases)` — warn on skipped optional phases between last completed and target
   - `validate_transition(current_phase, target_phase, completed_phases)` — validate phase ordering. **Skip if `current_phase` is None** (new feature entering first phase — ordering check is inapplicable)
   - For each gate: if `yolo_active=True`, prepend `check_yolo_override(guard_id, True)` — if override returns non-None, use that result instead of the gate result
4. If all gates pass (no `allowed=False` results): update `workflow_phases` table via `update_workflow_phase(type_id, workflow_phase=target_phase)` — only `workflow_phase` is updated; `last_completed_phase` is not changed during transition entry (it changes only in `complete_phase()`)
5. If any gate returns `allowed=False`: skip the DB update
6. Return list of all `TransitionResult` objects from gate checks in evaluation order (check_backward_transition, check_hard_prerequisites, check_soft_prerequisites, validate_transition — with YOLO override results replacing their corresponding gate result in-place; skipped gates are omitted). Identical return type for both success and failure paths — caller inspects results to determine outcome

**Engine-consumed gate functions:** The engine directly invokes these 5 gate functions from `transition_gate`:
- `check_backward_transition` — backward transition detection (skipped when `last_completed_phase` is None)
- `check_hard_prerequisites` — hard prerequisite blocking
- `check_soft_prerequisites` — skipped optional phase warnings
- `validate_transition` — phase ordering validation (skipped when `current_phase` is None)
- `check_yolo_override` — YOLO mode bypass wrapper

The remaining 20 gate functions (including `get_next_phase`, brainstorm gates, merge gates, branch checks, review gates, circuit breakers, etc.) are command-level concerns consumed directly by skill/command callers. They are out of scope for the engine.

**Usage pattern — `transition_phase()` vs `complete_phase()`:**
- `transition_phase(id, target)` validates and moves a feature INTO a phase (e.g., entering "design"). It checks prerequisites and updates `workflow_phase`.
- `complete_phase(id, phase)` records a phase as completed and advances `workflow_phase` to the next phase. It updates `last_completed_phase`.
- Typical caller sequence: `transition_phase(id, "design")` → (work happens) → `complete_phase(id, "design")` → `transition_phase(id, "create-plan")` → ...
- `transition_phase` is the entry gate; `complete_phase` is the exit gate. Both are needed for full lifecycle tracking.

### FR-3: Phase Completion

`complete_phase(feature_type_id, phase)` records phase as completed:

1. Read current state
2. Validate that `phase` matches the current active phase (or is a backward re-run where `phase` index <= `last_completed_phase` index). If `phase` does not match and is not a backward re-run, raise `ValueError` describing the mismatch
3. Derive next `workflow_phase` from `PHASE_SEQUENCE` indexing: find `phase` index in `PHASE_SEQUENCE`, set `workflow_phase = PHASE_SEQUENCE[idx + 1].value` if within bounds, else `None` (end of sequence)
4. Update `workflow_phases` table: set `last_completed_phase = phase`, `workflow_phase = derived_next_phase`
5. Return updated `FeatureWorkflowState`

### FR-4: Prerequisite Validation (Dry Run)

`validate_prerequisites(feature_type_id, target_phase)` returns all gate results without executing the transition. Used by UI/tools to show readiness status before user commits. Uses `self.artifacts_root` (set in constructor) for artifact resolution.

### FR-5: Batch Queries

- `list_by_phase(phase: str) -> list[FeatureWorkflowState]` — all features currently in given phase
- `list_by_status(status: str) -> list[FeatureWorkflowState]` — all features with given entity status

**Implementation approach:**
- `list_by_phase()` delegates to `EntityDatabase.list_workflow_phases(workflow_phase=phase)` and maps each row to `FeatureWorkflowState`
- `list_by_status()` delegates to `EntityDatabase.list_entities(entity_type="feature")`, filters by `status` field in Python, then for each matching entity calls `get_workflow_phase(type_id)` to build the `FeatureWorkflowState`. This cross-references the `entities` table (which has the `status` column) with `workflow_phases` data. Features without a `workflow_phases` row are included with `current_phase=None`.

### FR-6: Lazy State Hydration

On first access per feature (when `get_workflow_phase()` returns None):

**Precondition:** The entity must already be registered in the `entities` table (via entity_registry). If `get_entity(type_id)` returns None, hydration returns None — the engine does not register entities.

1. Check if `.meta.json` exists at `{artifacts_root}/features/{feature_slug}/`
2. If exists: parse `lastCompletedPhase`, `status`, `mode`, `phases` dict
3. Derive `workflow_phase` based on status (status field takes precedence over `lastCompletedPhase`):
   - If status is `"active"`: derive next phase from `PHASE_SEQUENCE` indexing — find `lastCompletedPhase` index, set `workflow_phase = PHASE_SEQUENCE[idx + 1].value` (or `PHASE_SEQUENCE[0].value` if `lastCompletedPhase` is null)
   - If status is `"completed"`: set `workflow_phase = None` (workflow is done), regardless of `lastCompletedPhase` value
   - If status is `"planned"`: set `workflow_phase = None`, `last_completed_phase = None` (not started — any non-null `lastCompletedPhase` in .meta.json is treated as stale data)
   - For any other status value (e.g., `"abandoned"`, `"on-hold"`): set `workflow_phase = None`, `last_completed_phase = None` (unknown/terminal statuses are treated as inactive)
4. Verify entity exists via `get_entity(type_id)`. If not found, return None
5. Call `create_workflow_phase()` to backfill the row
6. Return the hydrated state

If `.meta.json` also missing: return None (feature doesn't exist).

### FR-7: Artifact Existence Check

Gate functions like `check_hard_prerequisites` need to know which artifacts exist. The engine resolves this by checking the filesystem:

```python
from transition_gate.constants import HARD_PREREQUISITES

def _get_existing_artifacts(self, feature_slug: str) -> list[str]:
    """Return list of artifact filenames that exist for this feature."""
    feature_dir = os.path.join(self.artifacts_root, "features", feature_slug)
    # Derive artifact names from HARD_PREREQUISITES to maintain single source of truth
    all_artifacts = set()
    for artifacts_list in HARD_PREREQUISITES.values():
        all_artifacts.update(artifacts_list)
    return [name for name in sorted(all_artifacts)
            if os.path.exists(os.path.join(feature_dir, name))]
```

## Non-Functional Requirements

### NFR-1: Pure Orchestration

The engine module contains no LLM-dependent logic. All decisions are deterministic given the same inputs. The only I/O operations are:
- SQLite reads/writes via EntityDatabase
- Filesystem checks for artifact existence
- .meta.json reads for fallback/hydration

### NFR-2: No External Dependencies

The engine uses only stdlib + existing project libraries (transition_gate, entity_registry). No new pip dependencies.

### NFR-3: Testability

- All orchestration logic testable with mocked EntityDatabase
- Integration tests use real in-memory SQLite database
- Target: >90% line coverage of engine module

### NFR-4: Thread Safety

The engine is stateless — all state lives in EntityDatabase (which uses SQLite WAL mode). Multiple concurrent callers are safe. No instance-level mutable state.

### NFR-5: Performance

- Single transition: <50ms (gate function evaluation + single DB write)
- Batch query (100 features): <200ms

Performance measured as wall-clock time using `time.perf_counter()`, warm (second invocation), with in-memory SQLite. These are guidelines, not hard gates — no CI enforcement required.

## Success Criteria

| ID | Criterion | Verification |
|----|-----------|-------------|
| SC-1 | `transition_phase()` and `complete_phase()` correctly validate and execute forward transitions through all 6 command phases | Test: create feature, for each phase call `transition_phase(id, phase)` then `complete_phase(id, phase)`, verify workflow_phase advances correctly through specify→design→create-plan→create-tasks→implement→finish (brainstorm excluded — not a command-driven phase) |
| SC-2 | `transition_phase()` blocks transitions when hard prerequisites are missing | Test: attempt design without spec.md, verify `allowed=False` with correct guard_id |
| SC-3 | `transition_phase()` warns (but allows) backward transitions | Test: complete design, transition back to specify, verify warn severity |
| SC-4 | Lazy hydration correctly backfills workflow_phases from .meta.json | Test: create .meta.json with lastCompletedPhase="design", call get_state, verify DB row created |
| SC-5 | `complete_phase()` advances the workflow_phase to next phase | Test: complete_phase("specify"), verify workflow_phase becomes "design" |
| SC-6 | `validate_prerequisites()` returns all gate results without side effects | Test: call validate, verify no DB writes, verify results match what transition would produce |
| SC-7 | `list_by_phase()` and `list_by_status()` return correct results | Test: create 3 features in different phases, verify queries return correct subsets |
| SC-8 | YOLO mode passes through to gate functions correctly | Test: transition with yolo_active=True, verify YOLO-skippable gates return skip results |
| SC-9 | Engine returns "meta_json" source indicator when DB row missing and .meta.json used | Test: delete workflow_phases row, call get_state, verify source="meta_json" |
| SC-10 | All 5 engine-consumed gate functions (check_backward_transition, check_hard_prerequisites, check_soft_prerequisites, validate_transition, check_yolo_override) are exercised through engine operations | Test: for each of the 5 consumed gates, at least one integration test exercises a code path that invokes it |

## Acceptance Criteria

- [ ] `WorkflowStateEngine` module exists at `plugins/iflow/hooks/lib/workflow_engine/`
- [ ] Module exposes: `get_state()`, `transition_phase()`, `complete_phase()`, `validate_prerequisites()`, `list_by_phase()`, `list_by_status()`
- [ ] All 10 success criteria pass
- [ ] Tests pass: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v`
- [ ] Zero external dependency additions
- [ ] Engine consumes transition_gate and entity_registry without modification to either

## Technical Notes

### Module Location

`plugins/iflow/hooks/lib/workflow_engine/` with:
- `__init__.py` — public API exports
- `engine.py` — WorkflowStateEngine class (stateless, receives EntityDatabase via constructor)
- `models.py` — FeatureWorkflowState dataclass
- `test_engine.py` — unit and integration tests

### Engine Class Design

```python
class WorkflowStateEngine:
    def __init__(self, db: EntityDatabase, artifacts_root: str):
        self.db = db
        self.artifacts_root = artifacts_root

    def get_state(self, feature_type_id: str) -> FeatureWorkflowState | None: ...
    def transition_phase(self, feature_type_id: str, target_phase: str, yolo_active: bool = False) -> list[TransitionResult]: ...
    def complete_phase(self, feature_type_id: str, phase: str) -> FeatureWorkflowState: ...
    def validate_prerequisites(self, feature_type_id: str, target_phase: str) -> list[TransitionResult]: ...
    def list_by_phase(self, phase: str) -> list[FeatureWorkflowState]: ...
    def list_by_status(self, status: str) -> list[FeatureWorkflowState]: ...

    # Internal helpers
    def _get_existing_artifacts(self, feature_slug: str) -> list[str]: ...
    def _extract_slug(self, feature_type_id: str) -> str: ...
```

### feature_type_id Format

All engine methods accept `feature_type_id` in the format `"feature:{id}-{slug}"` (e.g., `"feature:008-workflowstateengine-core"`). This matches the entity_registry's `type_id` column.

### Slug Derivation

`feature_slug` is derived from `feature_type_id` by splitting on `":"` and taking the second part. Example: `"feature:008-workflowstateengine-core"` → slug `"008-workflowstateengine-core"`. The artifacts directory is `{artifacts_root}/features/{feature_slug}/`.

### Deriving completed_phases from last_completed_phase

```python
from transition_gate import PHASE_SEQUENCE

def _derive_completed_phases(last_completed: str | None) -> list[str]:
    if not last_completed:
        return []
    phase_values = [p.value for p in PHASE_SEQUENCE]
    idx = phase_values.index(last_completed)
    return phase_values[:idx + 1]
```

### Deriving next phase from PHASE_SEQUENCE

Phase advancement uses direct `PHASE_SEQUENCE` indexing — NOT `get_next_phase()` (which returns `TransitionResult`, not a phase string). The engine derives the next phase as:

```python
def _next_phase_value(current_phase: str) -> str | None:
    phase_values = [p.value for p in PHASE_SEQUENCE]
    idx = phase_values.index(current_phase)
    if idx >= len(phase_values) - 1:
        return None  # end of sequence
    return phase_values[idx + 1]
```

`get_next_phase()` is NOT consumed by the engine. Phase derivation uses `PHASE_SEQUENCE` indexing exclusively (see `_next_phase_value` above). `get_next_phase()` returns a `TransitionResult` which is useful for command-level callers but not needed by the engine's internal logic.

### Artifact List Source

The artifact existence check (FR-7) derives its artifact list from `transition_gate.constants.HARD_PREREQUISITES` (internal import, not part of transition_gate's public API) to maintain a single source of truth, rather than hardcoding filenames. This ensures the engine stays in sync if artifact requirements change in the gate definitions. This internal import is acceptable because workflow_engine and transition_gate are co-located in the same project and share the same release cycle.

### Traceability Note

This feature was created without a formal PRD. The Problem Statement section serves as the requirements source.
