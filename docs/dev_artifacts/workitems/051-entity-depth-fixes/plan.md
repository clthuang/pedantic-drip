# Plan: Entity Depth Fixes

Four independent bug fixes. No cross-dependencies between requirements — each can be implemented and tested in isolation. Ordered by dependency depth: R1 modifies entity_registry (upstream), R2-R4 modify workflow_engine/reconciliation (downstream consumer).

## Dependency Graph

```
R1 (set_parent depth guard)     — standalone, entity_registry/database.py
R2 (kanban status-awareness)    — standalone, workflow_engine/reconciliation.py
R3 (artifact path verification) — standalone, workflow_engine/reconciliation.py (touches WorkflowDriftReport)
R4 (depth context reporting)    — depends on R3 (both modify WorkflowDriftReport dataclass)
```

R3 and R4 both add fields to `WorkflowDriftReport`. R3 should be done first so R4 can add its fields in the correct position (after `artifact_missing`).

## Implementation Steps

### Step 1: R1 — Depth-guard `set_parent()` CTE

**Files:** `plugins/pd/hooks/lib/entity_registry/database.py`, `plugins/pd/hooks/lib/entity_registry/test_database.py`

**TDD order:**
1. Write test `test_set_parent_depth_guard_11_hops_no_cycle` — creates 11-entity chain with no cycle, calls `set_parent()` to add 12th, asserts success (no hang, no exception)
2. Write test `test_set_parent_cycle_within_10_hops` — creates chain with cycle at hop 5, asserts `ValueError` raised
3. Modify `set_parent()` CTE at `database.py:704-716`:
   - Add `depth` column to CTE: `anc(uid, depth)` seeded with `(parent_uuid, 0)`
   - Add `AND a.depth < 10` guard to recursive step
4. Run both new tests + full `test_database.py` suite to verify no regressions

**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v`

### Step 2: R2 — `_derive_expected_kanban()` status-awareness

**Files:** `plugins/pd/hooks/lib/workflow_engine/reconciliation.py`, `plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py`

**TDD order:**
1. Write tests:
   - `test_derive_kanban_completed_status` — `status="completed"` → returns `"completed"`
   - `test_derive_kanban_abandoned_status` — `status="abandoned"` → returns `"completed"`
   - `test_derive_kanban_active_unchanged` — `status="active"` → unchanged from current behavior
   - `test_check_feature_kanban_drift_terminal_status` — feature with `status="completed"`, DB `kanban_column="wip"` → mismatch detected with `meta_json_value="completed"`
   - `test_reconcile_terminal_status_kanban` — reconciliation with `meta_json["status"]="completed"` → `kanban_column="completed"` in DB update
2. Add `_TERMINAL_STATUSES = frozenset({"completed", "abandoned"})` to `reconciliation.py`
3. Add `status: str | None = None` parameter to `_derive_expected_kanban()`
4. Add `if status in _TERMINAL_STATUSES: return "completed"` as first check
5. Update callers:
   - `_check_single_feature()` line 279: pass `status=meta.get("status")`
   - `_reconcile_single_feature()` line 326: pass `status=meta.get("status")` (where `meta = report.meta_json`)
6. Run all new tests + full reconciliation test suite

**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v`

### Step 3: R3 — Artifact path verification

**Files:** `plugins/pd/hooks/lib/workflow_engine/reconciliation.py`, `plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py`

**TDD note:** Sub-steps 1-7 form one atomic unit. Write all tests (sub-step 1), then implement (sub-steps 2-7), then run the suite. Tests reference `artifact_missing` which doesn't exist until sub-step 2 — expected red-green TDD.

**Intentional exclusion:** Error-path and db_only-path `WorkflowDriftReport` constructors in `check_workflow_drift()` (lines 488-496, 507-513, 531-539) are left unchanged — `artifact_missing` defaults to `False`. These paths represent error/edge conditions, not missing artifacts.

**TDD order:**
1. Write tests:
   - `test_artifact_missing_flag` — feature with non-existent artifact dir → `report.artifact_missing == True`
   - `test_artifact_missing_no_short_circuit` — feature with missing artifact AND DB drift → both `artifact_missing=True` and `mismatches` non-empty
   - `test_artifact_missing_count_summary` — drift result summary includes `artifact_missing_count` key with correct count
2. Add `artifact_missing: bool = False` field to `WorkflowDriftReport` dataclass (after `message`)
3. Add `artifact_dir: str | None = None` parameter to `_check_single_feature()`
4. Add artifact check: `artifact_missing = artifact_dir is not None and not os.path.exists(artifact_dir)`
5. Pass `artifact_missing` to `WorkflowDriftReport` constructor
6. Update `check_workflow_drift()`:
   - Single-feature path (line 486): compute `slug = engine._extract_slug(feature_type_id)`, `artifact_dir = os.path.join(artifacts_root, "features", slug)`, pass to `_check_single_feature()`
   - Bulk scan path (line 529): same computation for each `ftype_id`
7. Update `_build_drift_result()`: add `summary["artifact_missing_count"] = sum(1 for r in reports if r.artifact_missing)` after status-counting loop
8. Run all new tests + full reconciliation test suite

**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v`

### Step 4: R4 — Depth context in reconciliation reporting

**Files:** `plugins/pd/hooks/lib/workflow_engine/reconciliation.py`, `plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py`

**Depends on:** Step 3 (R3 adds `artifact_missing` field to `WorkflowDriftReport`; R4 adds `depth` and `parent_type_id` after it)

**TDD note:** Tests in sub-step 1 reference `depth`/`parent_type_id` fields which don't exist yet. Expected to fail until sub-step 2. Run tests after sub-step 5.

**TDD order:**
1. Write tests:
   - `test_drift_report_depth_context` — entity with parent → `report.depth` is int, `report.parent_type_id` is str, `report.message` contains depth info
   - `test_drift_report_root_entity_no_depth` — root entity → `report.depth is None`, `report.parent_type_id is None`, `report.message == ""`
   - `test_drift_report_depth_value_multi_level` — 3-level hierarchy (root→parent→child), drift check on child → `report.depth == 2`
2. Add `depth: int | None = None` and `parent_type_id: str | None = None` fields to `WorkflowDriftReport` (after `artifact_missing`)
3. In `_check_single_feature()` success path (before final return at line 289):
   - `entity = db.get_entity(feature_type_id)`
   - Extract `parent_type_id` from entity
   - If parent exists: `ancestors = db.get_lineage(feature_type_id, direction="up")`, `depth = (len(ancestors) - 1) if ancestors else None`
   - Set message: `msg = f"depth: {depth}, parent: {parent_tid}"` when depth is not None
   - Note: message is SET (not appended) — on success path, message defaults to `""`
4. Add comment near DB calls noting performance boundary (<100 features)
5. Pass `depth`, `parent_type_id`, and `message` to `WorkflowDriftReport` constructor
6. Run all new tests + full reconciliation test suite

**Verification:** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v`

### Step 5: Cross-module verification

Run full test suites for both affected modules to catch any interactions:

```bash
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v
plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ -v
plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v
```

The full entity_registry suite (710+ tests) and full workflow_engine suite (309 tests) catch regressions beyond individual test files, including any unexpected consumers of `WorkflowDriftReport`.

The MCP server tests exercise reconciliation through the MCP layer and will catch any serialization issues with the new dataclass fields.

## Risk Mitigation

| Risk | Step | Mitigation |
|------|------|------------|
| CTE depth guard off-by-one | 1 | Seed at depth=0, `< 10` gives 10 hops — matches `_lineage_up` convention |
| DB CHECK constraint violation | 2 | All terminal statuses map to `"completed"` — verified valid value |
| Existing test breakage from dataclass changes | 3-4 | All new fields use `default=` values — constructors unchanged |
| `get_lineage` includes self in results | 4 | Use `len(ancestors) - 1` — verified via CTE seed and existing tests |
