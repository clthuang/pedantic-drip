# Design: Entity Depth Fixes

## Prior Art Research

**Codebase patterns:**
- `_lineage_up()` / `_lineage_down()` at `database.py:808-842` use depth-guarded CTEs: `WITH RECURSIVE ancestors(uid, depth) AS (... WHERE a.depth < ?)` with `max_depth` parameter bound
- `_export_tree()` at `database.py:1176-1223` uses same pattern with post-query truncation detection
- `WorkflowDriftReport` already uses `default=''` for optional `message` field on frozen dataclass — proven pattern for backward-compatible extension
- `check_workflow_drift()` at `reconciliation.py:451-454` already receives `artifacts_root` and derives slug via `engine._extract_slug()`
- `FEATURE_PHASE_TO_KANBAN` tested exhaustively in `test_constants.py` — values validated against `VALID_KANBAN_COLUMNS` set

**External research:**
- SQLite docs recommend LIMIT clause as safety net alongside WHERE-based depth guards
- Python frozen dataclass extension: `default=None` on new fields avoids TypeError from field ordering constraints
- FSM best practice: terminal statuses should map to absorbing states with explicit enumeration

## Architecture Overview

This is a bug-fix batch — four independent, localized changes. No new components or architectural changes. Each fix modifies existing functions in-place.

### Component Map

```
entity_registry/database.py
  └─ set_parent()          ← R1: add depth guard to CTE

workflow_engine/reconciliation.py
  ├─ _derive_expected_kanban()  ← R2: add status parameter
  ├─ _check_single_feature()   ← R2: pass status; R3: check artifact_dir; R4: populate depth/parent
  ├─ _reconcile_single_feature() ← R2: pass status to kanban derivation
  ├─ check_workflow_drift()     ← R3: compute and pass artifact_dir
  ├─ WorkflowDriftReport        ← R3: add artifact_missing; R4: add depth, parent_type_id
  ├─ WorkflowDriftResult        ← (summary dict gains artifact_missing_count)
  └─ _build_drift_result()      ← R3: count artifact_missing
```

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| R1 depth limit hides cycles >10 hops | Low — trees enforced ≤10 by AC-14 | Document as known limitation |
| R2 `kanban_column` CHECK constraint | High — DB rejects invalid values | Map all terminal statuses to `"completed"` (verified valid) |
| R3 artifact_dir adds I/O to drift check | Low — one `os.path.exists()` per feature | Minimal overhead, already in I/O-heavy function |
| R4 entity DB lookup per feature | Medium — adds DB query to drift check | Use `db.get_entity()` which is already used elsewhere in reconciliation |

## Technical Decisions

### TD-1: Depth guard constant

Use literal `10` in the CTE (matching `_lineage_up`/`_lineage_down`) rather than extracting a shared constant. Rationale: the spec says "stays at 10" and "no configurable depth limits." A shared constant is premature abstraction for three call sites in the same file.

### TD-2: Terminal status set

Define `_TERMINAL_STATUSES = {"completed", "abandoned"}` as a module-level frozenset in `reconciliation.py`. This makes the status check extensible if new terminal statuses are added later, while keeping the logic in one place.

### TD-3: artifact_missing flag — no short-circuit

When `artifact_missing=True`, the drift check still runs DB comparison. This means a single report can have both `artifact_missing=True` and drift `mismatches`. Downstream consumers decide whether to act on missing-artifact reports.

### TD-4: Depth/parent lookup strategy

Use `db.get_entity(feature_type_id)` within `_check_single_feature()` to retrieve the entity record. Extract `parent_type_id` directly from the record. For depth, count ancestors via `db.get_lineage(feature_type_id, direction="up")` and use `len(result)` — reuses existing tested code rather than adding a new query.

**Trade-off:** One extra DB query per feature during drift check. Acceptable because drift checks are already I/O-bound (reading .meta.json files from disk + DB lookups).

## Interfaces

### R1: `set_parent()` CTE modification

**Before:**
```sql
WITH RECURSIVE anc(uid) AS (
    SELECT parent_uuid FROM entities WHERE uuid = :parent_uuid
    UNION ALL
    SELECT e.parent_uuid FROM entities e
    JOIN anc a ON e.uuid = a.uid
    WHERE e.parent_uuid IS NOT NULL
)
SELECT 1 FROM anc WHERE uid = :child_uuid
```

**After:**
```sql
WITH RECURSIVE anc(uid, depth) AS (
    SELECT parent_uuid, 0 FROM entities WHERE uuid = :parent_uuid
    UNION ALL
    SELECT e.parent_uuid, a.depth + 1 FROM entities e
    JOIN anc a ON e.uuid = a.uid
    WHERE e.parent_uuid IS NOT NULL
      AND a.depth < 10
)
SELECT 1 FROM anc WHERE uid = :child_uuid
```

Parameters: `{"parent_uuid": parent_uuid, "child_uuid": child_uuid}` (unchanged).

No signature change to `set_parent()`.

**Seed depth convention:** `depth = 0` at the seed row, consistent with `_lineage_up()` (database.py:809) and `_lineage_down()` (database.py:831). With `a.depth < 10`, the CTE traverses up to 10 ancestor hops (depth values 0-9).

### R2: `_derive_expected_kanban()` signature change

**Before:**
```python
def _derive_expected_kanban(
    workflow_phase: str | None,
    last_completed_phase: str | None,
) -> str | None:
```

**After:**
```python
_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "abandoned"})

def _derive_expected_kanban(
    workflow_phase: str | None,
    last_completed_phase: str | None,
    status: str | None = None,
) -> str | None:
    if status in _TERMINAL_STATUSES:
        return "completed"
    # ... existing logic unchanged
```

**Callers updated:**

`_check_single_feature()` at line 279:
```python
# Before
expected_kanban = _derive_expected_kanban(
    state.current_phase, state.last_completed_phase
)
# After
expected_kanban = _derive_expected_kanban(
    state.current_phase, state.last_completed_phase,
    status=meta.get("status"),
)
```

`_reconcile_single_feature()` at line 326 — note: `meta` here is the local variable assigned from `report.meta_json` at line 316:
```python
# Before
expected_kanban = _derive_expected_kanban(
    meta["workflow_phase"], meta["last_completed_phase"]
)
# After (meta = report.meta_json, status key guaranteed present from line 223)
expected_kanban = _derive_expected_kanban(
    meta["workflow_phase"], meta["last_completed_phase"],
    status=meta.get("status"),
)
```

### R3: `WorkflowDriftReport` extension + artifact check

**Dataclass change:**
```python
@dataclass(frozen=True)
class WorkflowDriftReport:
    feature_type_id: str
    status: str
    meta_json: dict | None
    db: dict | None
    mismatches: tuple[WorkflowMismatch, ...]
    message: str = ""
    artifact_missing: bool = False       # R3: new
    depth: int | None = None             # R4: new
    parent_type_id: str | None = None    # R4: new
```

New fields use defaults — all existing constructors continue to work.

**`check_workflow_drift()` change — both paths:**

Single-feature path (line 486):
```python
slug = engine._extract_slug(feature_type_id)
artifact_dir = os.path.join(artifacts_root, "features", slug)
report = _check_single_feature(engine, db, feature_type_id, meta, artifact_dir)
```

Bulk scan path (line 529):
```python
for ftype_id, meta in engine._iter_meta_jsons():
    meta_type_ids.add(ftype_id)
    try:
        slug = engine._extract_slug(ftype_id)
        artifact_dir = os.path.join(artifacts_root, "features", slug)
        report = _check_single_feature(engine, db, ftype_id, meta, artifact_dir)
```

**`_check_single_feature()` signature:**
```python
def _check_single_feature(
    engine: WorkflowStateEngine,
    db: EntityDatabase,
    feature_type_id: str,
    meta: dict,
    artifact_dir: str | None = None,  # R3: new, optional for backward compat
) -> WorkflowDriftReport:
```

**Artifact check within `_check_single_feature()`:**
```python
artifact_missing = artifact_dir is not None and not os.path.exists(artifact_dir)
```

Set on the returned `WorkflowDriftReport` constructor.

**`_build_drift_result()` change:**
```python
summary["artifact_missing_count"] = sum(1 for r in reports if r.artifact_missing)
```

Added after the status-counting loop.

### R4: Depth/parent population in `_check_single_feature()`

**Location:** Only the main success path (final return at line 289) is modified. Early-return paths (state=None at line 209, row=None at line 230) already set their own `message` values and do not reach this code — depth/parent remain None on those paths.

**After DB row lookup and before building the return WorkflowDriftReport:**
```python
# R4: Depth context
depth = None
parent_tid = None
entity = db.get_entity(feature_type_id)
if entity is not None:
    parent_tid = entity.get("parent_type_id")
    if parent_tid is not None:
        ancestors = db.get_lineage(feature_type_id, direction="up")
        # len - 1: get_lineage includes self (depth 0), so subtract 1 for tree depth
        # e.g., [root, parent, self] → depth = 2 (2 ancestor hops)
        depth = (len(ancestors) - 1) if ancestors else None  # None if broken parent ref

# Set (not append) message — on the success path, message defaults to ""
msg = ""
if depth is not None:
    msg = f"depth: {depth}, parent: {parent_tid}"
```

Passed to `WorkflowDriftReport(... message=msg, depth=depth, parent_type_id=parent_tid)`.

**Note:** The `message` field is SET, not appended. On the success path (line 289), `message` currently defaults to `""`, so there is no existing content to append to. The spec's AC-4.3 wording "appends" should be read as "sets" in this context — no existing message to concatenate with.

**Edge cases:**
- Early returns (error, meta_json_only): depth/parent remain None, existing message values preserved
- Entity not in registry: `get_entity()` returns None → depth/parent remain None
- Entity has parent but `get_lineage()` returns empty list (broken reference): `depth = None` (defensive guard), `parent_type_id` still set

**Scale note:** One extra `get_entity()` + conditional `get_lineage()` per feature. Acceptable for expected scale (<100 features per project). Drift checks are already I/O-bound.

### Test Impact

| File | Change |
|------|--------|
| `test_database.py` | Add: `test_set_parent_depth_guard_11_hops_no_cycle`, `test_set_parent_cycle_within_10_hops` |
| `test_reconciliation.py` | Add: `test_derive_kanban_completed_status`, `test_derive_kanban_abandoned_status`, `test_derive_kanban_active_unchanged`, `test_check_feature_kanban_drift_terminal_status`, `test_reconcile_terminal_status_kanban`, `test_artifact_missing_flag`, `test_artifact_missing_no_short_circuit`, `test_artifact_missing_count_summary`, `test_drift_report_depth_context`, `test_drift_report_root_entity_no_depth`, `test_drift_report_depth_value_multi_level` (3-level hierarchy: root→parent→child, asserts child depth=2) |
| Existing tests | No changes needed — all new dataclass fields have defaults |
