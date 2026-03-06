# Design: Reconciliation MCP Tool

## Prior Art Research

### Codebase Patterns
- **MCP tool pattern** (`workflow_state_server.py`): `@mcp.tool()` async handlers delegate to `_process_*` sync functions with explicit parameters; `_with_error_handling` and `_catch_value_error` decorators for structured JSON errors via `_make_error()`
- **Drift detection pattern** (`frontmatter_sync.py`): `detect_drift()` is stateless/never-raises, returns `DriftReport` dataclass with exhaustive status enum; `scan_all()` iterates entities from DB, calls `detect_drift()` per artifact file
- **State derivation** (`engine.py:366-414`): `_derive_state_from_meta(meta, feature_type_id, source)` converts `.meta.json` dict to `FeatureWorkflowState`; handles active/completed/other statuses
- **Filesystem scan** (`engine.py:511-523`): `_iter_meta_jsons()` yields `(feature_type_id, meta_dict)` for all parseable `.meta.json` files
- **DB CRUD** (`database.py:828-995`): `create_workflow_phase()`, `get_workflow_phase()`, `update_workflow_phase()` with `_UNSET` sentinel for sparse updates
- **Phase comparison** (`constants.py:12-20`): `PHASE_SEQUENCE` tuple of 7 Phase enum values; index-based comparison via `_PHASE_VALUES`

### External Patterns
- **Kubernetes reconciliation loop**: Observe desired state, observe actual state, diff, apply corrective actions, report. Functions must be idempotent. Level-triggered (current state) not edge-triggered (events).
- **Event sourcing analogy**: `.meta.json` is the write model (authoritative during degraded mode), DB is the projection (derived read model). Reconciliation = re-derive DB from filesystem state.
- **Drift detection separation**: Detection (read-only) and remediation (write) are separate operations. Detection produces structured diff reports; remediation is explicit and auditable.

## Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│  workflow_state_server.py (MCP adapter layer)           │
│  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │ Existing tools   │  │ New reconciliation tools     │  │
│  │ - get_phase      │  │ - reconcile_check            │  │
│  │ - transition_... │  │ - reconcile_apply            │  │
│  │ - complete_...   │  │ - reconcile_frontmatter      │  │
│  │ - validate_...   │  │ - reconcile_status           │  │
│  │ - list_by_...    │  │                              │  │
│  └────────┬─────────┘  └──────────────┬───────────────┘  │
│           │                           │                  │
│  ┌────────┴───────────────────────────┴───────────────┐  │
│  │ _process_* functions (thin adapter wrappers)       │  │
│  │ - _process_reconcile_check()                       │  │
│  │ - _process_reconcile_apply()                       │  │
│  │ - _process_reconcile_frontmatter()                 │  │
│  │ - _process_reconcile_status()                      │  │
│  └────────────────────────┬───────────────────────────┘  │
└───────────────────────────┼──────────────────────────────┘
                            │
┌───────────────────────────┼──────────────────────────────┐
│  reconciliation.py (pure logic module)                   │
│  ┌────────────────────────┴───────────────────────────┐  │
│  │ check_workflow_drift()                             │  │
│  │   reads: .meta.json + DB workflow_phases           │  │
│  │   returns: WorkflowDriftResult                     │  │
│  ├────────────────────────────────────────────────────┤  │
│  │ apply_workflow_reconciliation()                    │  │
│  │   reads: check_workflow_drift() results            │  │
│  │   writes: DB via db.update/create_workflow_phase() │  │
│  │   returns: ReconciliationResult                    │  │
│  ├────────────────────────────────────────────────────┤  │
│  │ _phase_index() / _compare_phases()                │  │
│  │   pure functions for phase comparison              │  │
│  └────────────────────────────────────────────────────┘  │
│  Dataclasses: WorkflowDriftReport, WorkflowMismatch,     │
│               ReconcileAction                            │
└──────────────────────────────────────────────────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ engine.py    │  │ database.py      │  │frontmatter_sync  │
│ (read-only)  │  │ (CRUD)           │  │(read-only)       │
│_derive_state │  │create/get/update │  │detect_drift      │
│_iter_meta    │  │_workflow_phase() │  │scan_all          │
│_extract_slug │  │get_entity()      │  │ARTIFACT_BASENAME │
└──────────────┘  └──────────────────┘  └──────────────────┘
```

### Components

**C1: `reconciliation.py`** — New module at `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py`
- Pure logic for workflow state drift detection and reconciliation
- Contains dataclasses for structured results
- No MCP awareness — accepts explicit parameters, returns dataclasses
- Depends on: `engine.py` (for `_derive_state_from_meta`, `_iter_meta_jsons`, `_extract_slug`), `database.py` (for CRUD), `transition_gate.constants` (for `PHASE_SEQUENCE`)

**C2: MCP adapter layer** — Additions to existing `plugins/iflow/mcp/workflow_state_server.py`
- 4 new `@mcp.tool()` async handlers
- 4 new `_process_*` sync functions with standard decorator chain
- Serialization of `reconciliation.py` dataclasses to JSON strings
- No new logic — pure delegation to C1

**C3: Frontmatter integration** — Reuses `entity_registry.frontmatter_sync` as-is
- `detect_drift()` and `scan_all()` called directly from `_process_reconcile_frontmatter`
- `DriftReport` and `FieldMismatch` serialized to JSON dicts
- No wrapper in `reconciliation.py` — frontmatter drift is a pass-through

### Technical Decisions

**TD-1: Separate reconciliation module vs inline in engine.py**
- Decision: Separate `reconciliation.py` module
- Rationale: Engine constraint ("Must not modify WorkflowStateEngine class"). Reconciliation wraps around the engine, not inside it. Follows same separation as `engine.py` (logic) vs `workflow_state_server.py` (MCP adapter).

**TD-2: Access private engine methods (`_derive_state_from_meta`, `_iter_meta_jsons`, `_extract_slug`)**
- Decision: Call private methods on the engine instance passed to reconciliation functions
- Rationale: Spec constraint C6 explicitly allows this ("private but accessible within the same `workflow_engine` package"). Duplicating phase derivation logic would violate DRY and create drift risk.

**TD-3: Frontmatter drift handled directly in `_process_reconcile_frontmatter` (no reconciliation.py wrapper)**
- Decision: Frontmatter drift detection goes straight from MCP adapter to `frontmatter_sync` functions
- Rationale: Feature 003's `detect_drift` and `scan_all` already provide the exact interface needed. Adding a wrapper in `reconciliation.py` would be pure pass-through with no added value.

**TD-4: Phase comparison uses `PHASE_SEQUENCE` from `transition_gate.constants`**
- Decision: Import `PHASE_SEQUENCE` and derive `_PHASE_VALUES` tuple in `reconciliation.py`
- Rationale: Single source of truth for phase ordering. Same pattern used by `engine.py:28-29`.

**TD-5: `reconcile_apply` only supports `meta_json_to_db` direction**
- Decision: Validate direction parameter, return error for unsupported values
- Rationale: Spec R2 limits scope to the primary post-degradation use case. Future directions can be added without breaking the interface.

### Risks

**Risk 1: Private API stability**
- Concern: `_derive_state_from_meta`, `_iter_meta_jsons`, `_extract_slug` are private methods subject to change
- Mitigation: Both `reconciliation.py` and `engine.py` are in the same `workflow_engine` package. Tests for reconciliation cover these code paths, so breakage is detected immediately.

**Risk 2: Race conditions during reconciliation**
- Concern: Another process could modify DB between drift check and apply
- Mitigation: Reconciliation operates on a single SQLite DB with WAL mode. Individual feature reconciliation is O(1) operations. The `_hydrate_from_meta_json` pattern already handles the duplicate-row race via re-fetch.

**Risk 3: `.meta.json` parse errors during bulk scan**
- Concern: Corrupted `.meta.json` could crash bulk reconciliation
- Mitigation: `_iter_meta_jsons()` already catches `OSError` and `json.JSONDecodeError` with `continue`. Reconciliation inherits this resilience.

## Interface Design

### I1: Dataclasses (`reconciliation.py`)

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class WorkflowMismatch:
    """Single-field comparison between .meta.json and DB."""
    field: str
    meta_json_value: str | None
    db_value: str | None

@dataclass(frozen=True)
class WorkflowDriftReport:
    """Drift assessment for a single feature's workflow state."""
    feature_type_id: str
    status: str  # "in_sync"|"meta_json_ahead"|"db_ahead"|"meta_json_only"|"db_only"|"error"
    meta_json: dict | None  # {workflow_phase, last_completed_phase, mode, status}
    db: dict | None  # {workflow_phase, last_completed_phase, mode, kanban_column}
    mismatches: tuple[WorkflowMismatch, ...]
    message: str = ""  # human-readable context for error/edge cases

@dataclass(frozen=True)
class WorkflowDriftResult:
    """Aggregate result from check_workflow_drift()."""
    features: tuple[WorkflowDriftReport, ...]
    summary: dict  # {in_sync, meta_json_ahead, db_ahead, meta_json_only, db_only, error}

@dataclass(frozen=True)
class ReconcileAction:
    """Outcome of reconciling a single feature.

    Design extends spec R2 action enum with "created" to differentiate
    update (existing DB row) vs create (new row for meta_json_only).
    This provides better caller diagnostics without breaking spec semantics.

    AC-8 mapping: "reconcile_apply on meta_json_only creates a new row"
    → test assertions should use action="created" for this case.
    AC-6 mapping: "reconcile_apply on meta_json_ahead updates existing row"
    → test assertions should use action="reconciled" for this case.
    """
    feature_type_id: str
    action: str  # "reconciled"|"skipped"|"created"|"error"
    direction: str  # "meta_json_to_db"
    changes: tuple[WorkflowMismatch, ...]  # reuse Mismatch as {field, old, new}
    # Serialization note: when serialized via _serialize_reconcile_action,
    # db_value → "old_value" and meta_json_value → "new_value".
    # This convention applies to meta_json_to_db direction only.
    message: str

@dataclass(frozen=True)
class ReconciliationResult:
    """Aggregate result from apply_workflow_reconciliation().

    Summary extends spec R2 with "created" count (design enhancement).
    Callers should expect both "reconciled" and "created" keys in summary.
    Spec R2 defines {reconciled, skipped, error, dry_run}; design adds
    "created" to distinguish new rows from updates.
    """
    actions: tuple[ReconcileAction, ...]
    summary: dict  # {reconciled, created, skipped, error, dry_run}
```

### I2: Public Functions (`reconciliation.py`)

```python
def check_workflow_drift(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None = None,
) -> WorkflowDriftResult:
    """Detect workflow state drift between .meta.json and DB.

    Parameters
    ----------
    engine : WorkflowStateEngine
        Engine instance (for _derive_state_from_meta, _iter_meta_jsons,
        _extract_slug).
    db : EntityDatabase
        Database instance (for get_workflow_phase).
    artifacts_root : str
        Root directory for artifact files.
    feature_type_id : str | None
        If provided, check single feature via _read_single_meta_json().
        If None, scan all via engine._iter_meta_jsons().

    Returns
    -------
    WorkflowDriftResult
        Per-feature drift reports and aggregate summary.

    Single-feature path: calls _read_single_meta_json() to read one
    .meta.json by slug-derived path. If None returned (file missing),
    checks DB for existing row — if found, returns status="db_only";
    if not found, returns status="error" with message
    "Feature not found: {feature_type_id}".

    Never raises — all exceptions caught and returned as status="error".
    """

def apply_workflow_reconciliation(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None = None,
    dry_run: bool = False,
) -> ReconciliationResult:
    """Sync .meta.json workflow state to DB for drifted features.

    Only reconciles features where .meta.json is ahead (post-degradation).
    Calls check_workflow_drift() internally to detect drift first.

    Parameters
    ----------
    engine : WorkflowStateEngine
        Engine instance.
    db : EntityDatabase
        Database instance (for create/update_workflow_phase).
    artifacts_root : str
        Root directory for artifact files.
    feature_type_id : str | None
        If provided, reconcile single feature. If None, reconcile all.
    dry_run : bool
        If True, compute changes without applying.

    Returns
    -------
    ReconciliationResult
        Per-feature actions and aggregate summary.

    Never raises — all exceptions caught and returned as action="error".
    """
```

### I3: Internal Functions (`reconciliation.py`)

```python
def _phase_index(phase: str | None) -> int:
    """Return ordinal index of a phase in PHASE_SEQUENCE, or -1 for None/unknown."""

def _compare_phases(
    meta_last: str | None,
    meta_current: str | None,
    db_last: str | None,
    db_current: str | None,
) -> str:
    """Compare phase positions and return drift status string.

    Implements the 8-step comparison algorithm from spec R8:
    1. Compare last_completed_phase indices
    2. Higher index = more advanced
    3-4. meta_json > db → "meta_json_ahead", db > meta → "db_ahead"
    5. If equal, compare workflow_phase (current phase)
    6. If both equal → "in_sync"
    7. None vs non-None → non-None is ahead
    8. Both None → equal at -1, proceed to workflow_phase comparison

    Returns: "in_sync"|"meta_json_ahead"|"db_ahead"
    """

def _read_single_meta_json(
    engine: WorkflowStateEngine,
    artifacts_root: str,
    feature_type_id: str,
) -> dict | None:
    """Read .meta.json for a single feature without bulk scan.

    Extracts slug via engine._extract_slug(feature_type_id), constructs
    path as {artifacts_root}/features/{slug}/.meta.json, reads and parses.

    Returns parsed dict or None if file missing/unparseable.
    """

def _check_single_feature(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    feature_type_id: str,
    meta: dict,
) -> WorkflowDriftReport:
    """Build drift report for one feature given its .meta.json dict and DB state.

    Field name mapping:
    - state.current_phase → workflow_phase (DB column name)
    - state.last_completed_phase → last_completed_phase
    - state.mode → mode
    """

def _reconcile_single_feature(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    report: WorkflowDriftReport,
    meta: dict,
    dry_run: bool,
) -> ReconcileAction:
    """Execute reconciliation for one feature based on its drift report.

    Status-based branching (mutually exclusive):
    - "meta_json_ahead" → update existing DB row via db.update_workflow_phase()
      with _UNSET sentinel for kanban_column; action="reconciled"
    - "meta_json_only" → entity-existence check first:
      - db.get_entity(feature_type_id) found → db.create_workflow_phase();
        action="created"
      - db.get_entity(feature_type_id) not found → action="error",
        message="Entity not found in DB — cannot create workflow_phases row"
    - "db_only" → action="skipped", message="No .meta.json to reconcile from"
    - "error" → action="error", propagate original error message
    - "in_sync" or "db_ahead" → action="skipped"

    Direction is hardcoded as "meta_json_to_db" in the ReconcileAction output
    (only supported direction per TD-5).
    """
```

### I4: Processing Functions (`workflow_state_server.py`)

```python
@_with_error_handling
@_catch_value_error
def _process_reconcile_check(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None,
) -> str:
    """Workflow drift detection. Returns JSON string.

    AC-18 compliance: When feature_type_id is provided, calls
    _validate_feature_type_id() BEFORE delegating to check_workflow_drift().
    _catch_value_error intercepts the ValueError from validation (not from
    check_workflow_drift, which never raises).
    """

@_with_error_handling
@_catch_value_error
def _process_reconcile_apply(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None,
    direction: str,
    dry_run: bool,
) -> str:
    """Workflow reconciliation. Validates direction, returns JSON string.

    AC-18 compliance: When feature_type_id is provided, calls
    _validate_feature_type_id() BEFORE delegating to
    apply_workflow_reconciliation(). _catch_value_error intercepts the
    ValueError from validation (not from apply_workflow_reconciliation,
    which never raises).
    Direction validation handled explicitly before delegation.
    """

@_with_error_handling
@_catch_value_error
def _process_reconcile_frontmatter(
    db: EntityDatabase,
    artifacts_root: str,
    feature_type_id: str | None,
) -> str:
    """Frontmatter drift detection. Returns JSON string.

    AC-18 compliance: When feature_type_id is provided, calls
    _validate_feature_type_id() BEFORE delegating to frontmatter_sync
    functions. _catch_value_error intercepts the ValueError from
    validation (not from detect_drift/scan_all, which never raise).
    """

@_with_error_handling
def _process_reconcile_status(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    artifacts_root: str,
) -> str:
    """Combined drift report. Returns JSON string.

    Delegates directly to check_workflow_drift() and scan_all() (no
    _process_reconcile_check/_process_reconcile_frontmatter wrappers)
    to avoid double-serialization. Combines both results into a single
    JSON response with these fields (per spec R4):
    - workflow_drift: serialized WorkflowDriftResult
    - frontmatter_drift: serialized list of DriftReports
    - total_features_checked: len(workflow_drift_result.features)
    - total_files_checked: len(frontmatter_reports)
    - healthy: True when BOTH dimensions report zero drift:
      (1) Workflow: every count in summary except "in_sync" equals 0
          (meta_json_ahead=0, db_ahead=0, meta_json_only=0, db_only=0, error=0)
      (2) Frontmatter: every count in summary except "in_sync" equals 0
          (same zero-check pattern applied to frontmatter DriftReport statuses)
      Any non-zero count in either dimension sets healthy=False.

    No _catch_value_error needed — reconcile_status accepts no
    feature_type_id parameter (always scans all).
    """
```

### I5: MCP Tool Handlers (`workflow_state_server.py`)

All handlers follow existing pattern: guard `_engine`/`_db` for None (returns
`_NOT_INITIALIZED` error), then delegate to `_process_*` function.

```python
@mcp.tool()
async def reconcile_check(feature_type_id: str | None = None) -> str:
    """Compare .meta.json workflow state against DB for drift detection."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_check(_engine, _db, _artifacts_root, feature_type_id)

@mcp.tool()
async def reconcile_apply(
    feature_type_id: str | None = None,
    direction: str = "meta_json_to_db",
    dry_run: bool = False,
) -> str:
    """Sync .meta.json workflow state to DB for features where .meta.json is ahead."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_apply(_engine, _db, _artifacts_root, feature_type_id, direction, dry_run)

@mcp.tool()
async def reconcile_frontmatter(feature_type_id: str | None = None) -> str:
    """Check frontmatter headers against DB entity records for drift."""
    if _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_frontmatter(_db, _artifacts_root, feature_type_id)

@mcp.tool()
async def reconcile_status() -> str:
    """Unified health report across workflow state and frontmatter drift."""
    if _engine is None or _db is None:
        return _NOT_INITIALIZED
    return _process_reconcile_status(_engine, _db, _artifacts_root)
```

### I6: Direction Validation (`_process_reconcile_apply`)

```python
_SUPPORTED_DIRECTIONS = frozenset({"meta_json_to_db"})

# In _process_reconcile_apply:
if direction not in _SUPPORTED_DIRECTIONS:
    return _make_error(
        "invalid_transition",
        f"Unsupported direction: {direction}. Supported: {', '.join(sorted(_SUPPORTED_DIRECTIONS))}",
        "Use direction='meta_json_to_db' (the only supported direction)",
    )
```

### I7: Path-Traversal Validation (module-level helper in `workflow_state_server.py`)

`_validate_feature_type_id` is a module-level helper in `workflow_state_server.py`, called
by all three `_process_*` functions that accept `feature_type_id` (check, apply, frontmatter).

```python
def _validate_feature_type_id(feature_type_id: str, artifacts_root: str) -> str:
    """Validate feature_type_id and extract slug with realpath defense.

    1. Split on ':', raise ValueError if no colon present
    2. Extract slug from second part
    3. Resolve realpath of {artifacts_root}/features/{slug}/
    4. Verify resolved path starts with realpath(artifacts_root)
    5. Return validated slug

    Matches engine._extract_slug defense-in-depth (realpath resolution).
    Raises ValueError on invalid input (caught by _catch_value_error).
    """
```

### I8: Frontmatter DriftReport Serialization

```python
def _serialize_drift_report(report: DriftReport) -> dict:
    """Convert frontmatter_sync.DriftReport to JSON-serializable dict."""
    return {
        "filepath": report.filepath,
        "type_id": report.type_id,
        "status": report.status,
        "file_fields": report.file_fields,
        "db_fields": report.db_fields,
        "mismatches": [
            {"field": m.field, "file_value": m.file_value, "db_value": m.db_value}
            for m in report.mismatches
        ],
    }
```

### I9: Workflow Dataclass Serialization

```python
def _serialize_workflow_drift_report(report: WorkflowDriftReport) -> dict:
    """Convert WorkflowDriftReport to JSON-serializable dict."""
    return {
        "feature_type_id": report.feature_type_id,
        "status": report.status,
        "meta_json": report.meta_json,
        "db": report.db,
        "mismatches": [
            {"field": m.field, "meta_json_value": m.meta_json_value, "db_value": m.db_value}
            for m in report.mismatches
        ],
    }

def _serialize_reconcile_action(action: ReconcileAction) -> dict:
    """Convert ReconcileAction to JSON-serializable dict.

    For meta_json_to_db direction: old_value = DB (being overwritten),
    new_value = .meta.json (source of truth).
    """
    return {
        "feature_type_id": action.feature_type_id,
        "action": action.action,
        "direction": action.direction,
        "changes": [
            {"field": c.field, "old_value": c.db_value, "new_value": c.meta_json_value}
            for c in action.changes
        ],
        "message": action.message,
    }
```

### I10: Import Map

```
reconciliation.py imports:
  from transition_gate.constants import PHASE_SEQUENCE
  from workflow_engine.engine import WorkflowStateEngine
  from workflow_engine.models import FeatureWorkflowState
  from entity_registry.database import EntityDatabase

workflow_state_server.py new imports:
  from workflow_engine.reconciliation import (
      check_workflow_drift,
      apply_workflow_reconciliation,
      WorkflowDriftResult,
      ReconciliationResult,
  )
  from entity_registry.frontmatter_sync import (
      detect_drift,
      scan_all,
      DriftReport,
      FieldMismatch,
      ARTIFACT_BASENAME_MAP,
  )
```

Note: `ARTIFACT_BASENAME_MAP` is imported from `entity_registry.frontmatter_sync` (re-exported there from `frontmatter_inject.py`).

## Dependencies

- `workflow_engine.engine.WorkflowStateEngine` — read-only access to `_derive_state_from_meta()`, `_iter_meta_jsons()`, `_extract_slug()`
- `entity_registry.database.EntityDatabase` — CRUD via `get_workflow_phase()`, `create_workflow_phase()`, `update_workflow_phase()`, `get_entity()`
- `entity_registry.frontmatter_sync` — `detect_drift()`, `scan_all()`, `DriftReport`, `FieldMismatch`, `ARTIFACT_BASENAME_MAP`
- `transition_gate.constants` — `PHASE_SEQUENCE` for phase ordering
