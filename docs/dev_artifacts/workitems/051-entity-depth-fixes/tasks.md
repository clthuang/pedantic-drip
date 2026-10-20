# Tasks: Entity Depth Fixes

## Phase 1: R1 — Depth-guard set_parent() CTE (standalone)

### Task 1.1: Write depth guard tests for set_parent()
- **File:** `plugins/pd/hooks/lib/entity_registry/test_database.py`
- **Do:** Add `test_set_parent_depth_guard_11_hops_no_cycle` — create 11-entity chain (no cycle), call `set_parent()` to link 12th entity, assert success without hang or exception
- **Do:** Add `test_set_parent_cycle_within_10_hops` — create chain with cycle at hop 5, call `set_parent()`, assert `ValueError` raised
- **Done when:** Both tests exist. `test_set_parent_depth_guard_11_hops_no_cycle` fails (red — no depth guard). `test_set_parent_cycle_within_10_hops` may already pass since the existing CTE detects short cycles — this is expected.
- **Spec:** AC-1.2, AC-1.3, AC-1.4

### Task 1.2: Add depth guard to set_parent() CTE
- **File:** `plugins/pd/hooks/lib/entity_registry/database.py`
- **Do:** In `set_parent()` at line ~704, modify the CTE from `anc(uid)` to `anc(uid, depth)`. Seed with `(parent_uuid, 0)`. Add `AND a.depth < 10` to recursive step WHERE clause. No signature change.
- **Done when:** Both new tests pass. Full `test_database.py` suite passes with zero regressions.
- **Spec:** AC-1.1
- **Verify (focused):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v -k "test_set_parent"`
- **Verify (regression):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/test_database.py -v`

## Phase 2: R2 — Kanban status-awareness (standalone)

### Task 2.1: Write kanban status-awareness tests
- **File:** `plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py`
- **Do:** Add 5 tests:
  - `test_derive_kanban_completed_status`: `_derive_expected_kanban(workflow_phase="implement", last_completed_phase=None, status="completed")` → `"completed"`
  - `test_derive_kanban_abandoned_status`: same with `status="abandoned"` → `"completed"`
  - `test_derive_kanban_active_unchanged`: `status="active"` → same as current (phase-based lookup)
  - `test_check_feature_kanban_drift_terminal_status`: feature with `status="completed"`, DB `kanban_column="wip"` → mismatch with `meta_json_value="completed"`
  - `test_reconcile_terminal_status_kanban`: reconciliation with `meta_json["status"]="completed"`, `dry_run=False` → DB update with `kanban_column="completed"`
- **Done when:** All 5 tests exist and the unit tests for `_derive_expected_kanban` fail (no status param yet)
- **Spec:** AC-2.1–AC-2.5

### Task 2.2: Implement kanban status-awareness
- **File:** `plugins/pd/hooks/lib/workflow_engine/reconciliation.py`
- **Do:**
  1. Add `_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "abandoned"})` at module level
  2. Add `status: str | None = None` parameter to `_derive_expected_kanban()`
  3. Add `if status in _TERMINAL_STATUSES: return "completed"` as first check in function body
  4. Update `_check_single_feature()` line ~279: pass `status=meta.get("status")` to `_derive_expected_kanban()`
  5. Update `_reconcile_single_feature()` line ~326: pass `status=meta.get("status")` (where `meta = report.meta_json`)
- **Done when:** All 5 new tests pass. Full `test_reconciliation.py` suite passes.
- **Verify (focused):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v -k "kanban"`
- **Verify (regression):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v`

## Phase 3: R3 — Artifact path verification (standalone)

### Task 3.1a: Write artifact verification tests (red)
- **File:** `plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py`
- **Do:** Add 3 tests (will fail until 3.1b implements the field):
  - `test_artifact_missing_flag`: feature with non-existent artifact dir → `report.artifact_missing == True`
  - `test_artifact_missing_no_short_circuit`: missing artifact AND DB drift → `artifact_missing=True` AND `mismatches` non-empty
  - `test_artifact_missing_count_summary`: drift result summary has `artifact_missing_count` key with correct count
- **Done when:** Tests written. Expected to fail (red phase).
- **Spec:** AC-3.1–AC-3.4

### Task 3.1b: Implement artifact path verification (green)
- **File:** `plugins/pd/hooks/lib/workflow_engine/reconciliation.py`
- **Do:**
  1. Add `artifact_missing: bool = False` field to `WorkflowDriftReport` (after `message`)
  2. Add `artifact_dir: str | None = None` param to `_check_single_feature()`
  3. Add `artifact_missing = artifact_dir is not None and not os.path.exists(artifact_dir)` in function body
  4. Pass `artifact_missing` to `WorkflowDriftReport` constructor
  5. Update `check_workflow_drift()` single-feature path: compute `slug = engine._extract_slug(feature_type_id)`, `artifact_dir = os.path.join(artifacts_root, "features", slug)`, pass to `_check_single_feature()`
  6. Update `check_workflow_drift()` bulk scan path: same computation per `ftype_id`
  7. In `_build_drift_result()`: add `summary["artifact_missing_count"] = sum(1 for r in reports if r.artifact_missing)` after status loop
- **Intentional exclusion:** Error-path constructors (lines ~488-496, ~507-513, ~531-539) unchanged — `artifact_missing` defaults to `False`.
- **Done when:** All 3 tests from 3.1a pass. Full `test_reconciliation.py` suite passes.
- **Verify (focused):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v -k "artifact"`
- **Verify (regression):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v`

## Phase 4: R4 — Depth context in reporting (BLOCKED by Phase 3 — must complete 3.1b first)

### Task 4.1a: Write depth context tests (red)
- **File:** `plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py`
- **Depends on:** Task 3.1b (WorkflowDriftReport must have `artifact_missing` field before adding `depth`/`parent_type_id` after it)
- **Do:** Add 3 tests (will fail until 4.1b implements the fields):
  - `test_drift_report_depth_context`: entity with parent → `report.depth` is int, `report.parent_type_id` is str, `report.message` contains `"depth:"` and `"parent:"`
  - `test_drift_report_root_entity_no_depth`: root entity → `report.depth is None`, `report.parent_type_id is None`, `report.message == ""`
  - `test_drift_report_depth_value_multi_level`: 3-level hierarchy (root→parent→child), drift check on child → `report.depth == 2`
- **Done when:** Tests written. Expected to fail (red phase).
- **Spec:** AC-4.1–AC-4.5

### Task 4.1b: Implement depth context reporting (green)
- **File:** `plugins/pd/hooks/lib/workflow_engine/reconciliation.py`
- **Do:**
  1. Add `depth: int | None = None` and `parent_type_id: str | None = None` fields to `WorkflowDriftReport` (after `artifact_missing`)
  2. In `_check_single_feature()` success path (before final return):
     - `entity = db.get_entity(feature_type_id)`
     - If entity: `parent_tid = entity.get("parent_type_id")`
     - If parent_tid: `ancestors = db.get_lineage(feature_type_id, direction="up")`, `depth = (len(ancestors) - 1) if ancestors else None`
     - Set `msg = f"depth: {depth}, parent: {parent_tid}"` when depth is not None (SET, not append)
  3. Add perf comment: `# Performance: +1 get_entity + conditional get_lineage per feature. OK for <100 features.`
  4. Pass `depth`, `parent_type_id`, `message=msg` to `WorkflowDriftReport` constructor
- **Done when:** All 3 tests from 4.1a pass. Full `test_reconciliation.py` suite passes.
- **Verify (focused):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v -k "depth"`
- **Verify (regression):** `plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py -v`

## Phase 5: Cross-module verification

### Task 5.1: Run full test suites
- **Do:** Run all three test suites:
  ```
  plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/entity_registry/ -v
  plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/ -v
  plugins/pd/.venv/bin/python -m pytest plugins/pd/mcp/test_workflow_state_server.py -v
  ```
- **Done when:** All suites pass (710+ entity_registry, 309+ workflow_engine, 272 MCP server tests). Zero regressions.
