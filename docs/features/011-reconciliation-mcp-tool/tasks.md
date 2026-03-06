# Tasks: Reconciliation MCP Tool

## Phase 1: Core Dataclasses and Helpers

> Parallel group — tasks 1.1, 1.2, 1.3 have no cross-dependencies.

### Task 1.1: Dataclass definitions (TDD step 1)

- [ ] **RED:** Create `plugins/iflow/hooks/lib/workflow_engine/test_reconciliation.py`. Write tests for `WorkflowMismatch`, `WorkflowDriftReport`, `WorkflowDriftResult`, `ReconcileAction`, `ReconciliationResult` — construction, frozen enforcement (`with pytest.raises(FrozenInstanceError)`), field access, tuple fields default to empty tuple.
- [ ] **GREEN:** Create `plugins/iflow/hooks/lib/workflow_engine/reconciliation.py`. Implement all 5 frozen dataclasses with `from dataclasses import dataclass, field`. Match design I1 signatures exactly.
- [ ] **REFACTOR:** Verify all dataclass tests pass. No test modifications needed.

**Acceptance:** `pytest test_reconciliation.py -k "dataclass or frozen or WorkflowMismatch or WorkflowDriftReport or WorkflowDriftResult or ReconcileAction or ReconciliationResult"` — all pass.

**Files:** `reconciliation.py` (NEW), `test_reconciliation.py` (NEW)

---

### Task 1.2: Phase comparison helpers (TDD step 2)

- [ ] **RED:** In `test_reconciliation.py`, write tests for `_phase_index()` and `_compare_phases()`:
  - `_phase_index`: known phases → correct indices; `None` → -1; unknown phase → -1
  - `_compare_phases`: all 8 spec R8 comparison steps — `meta_json_ahead`, `db_ahead`, `in_sync`, `None` vs non-`None`, both-`None` fallthrough to `workflow_phase`, terminal phase edge cases
- [ ] **GREEN:** In `reconciliation.py`, implement `_phase_index(phase)` and `_compare_phases(meta_last, meta_current, db_last, db_current)`. Import `from transition_gate.constants import PHASE_SEQUENCE`. Derive `_PHASE_VALUES = tuple(p.value for p in PHASE_SEQUENCE)` at module level.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** All phase comparison tests pass. Coverage of all 8 spec R8 steps verified.

**Files:** `reconciliation.py`, `test_reconciliation.py`

---

### Task 1.3: Path-traversal validation (TDD step 3)

- [ ] **RED:** In `plugins/iflow/mcp/test_workflow_state_server.py`, write tests for `_validate_feature_type_id(feature_type_id, artifacts_root)`:
  - Valid `"feature:010-slug"` → returns slug
  - No colon → `ValueError`
  - `".."` in slug → `ValueError`
  - Null bytes → `ValueError`
  - Symlink traversal → `ValueError` (setup: create actual symlink via `os.symlink()` in tempdir pointing outside `artifacts_root`)
  - Prefix collision (slug that is prefix of another dir) → `ValueError` (setup: create sibling dir e.g. `artifacts_root/features/010-slug-extra/` so realpath demonstrates the `+ os.sep` suffix defense)
- [ ] **GREEN:** In `plugins/iflow/mcp/workflow_state_server.py`, implement `_validate_feature_type_id()` as module-level helper. Logic: split on `:` — if no colon found, `raise ValueError("invalid_input: missing colon in feature_type_id")`. Extract slug, check null bytes BEFORE `os.path.realpath()`, realpath resolve, verify resolved path starts with `realpath(artifacts_root) + os.sep` — on any path failure, `raise ValueError("feature_not_found: {slug} not found or path traversal blocked")`. This prefix convention enables `_catch_value_error` routing (see Task 5.1).
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** All 6 validation test scenarios pass.

**Files:** `workflow_state_server.py`, `test_workflow_state_server.py`

---

## Phase 2: Drift Detection

> Sequential — 2.1 → 2.2 → 2.3. Depends on Phase 1.

### Task 2.1: Single-feature meta reader (TDD step 4)

- [ ] **RED:** In `test_reconciliation.py`, write tests for `_read_single_meta_json(engine, artifacts_root, feature_type_id)`:
  - Valid `.meta.json` file → returns parsed dict
  - Missing file → returns `None`
  - Corrupt JSON → returns `None`
- [ ] **GREEN:** In `reconciliation.py`, implement `_read_single_meta_json()`. Uses `engine._extract_slug()` for path construction, reads/parses JSON, returns `None` on missing/corrupt.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** All 3 meta reader test scenarios pass.

**Files:** `reconciliation.py`, `test_reconciliation.py`

**Depends on:** None from this plan (uses only pre-existing `engine._extract_slug()`). Soft dependency on 1.1 for file locality if implementing in same session.

---

### Task 2.2: Single-feature drift check (TDD step 5)

- [ ] **RED:** In `test_reconciliation.py`, write tests for `_check_single_feature(engine, db, feature_type_id, meta)`:
  - `in_sync` (all fields match)
  - `meta_json_ahead`
  - `db_ahead`
  - `db_only` (no meta)
  - Mode mismatch with phase sync → status still `"in_sync"` but mismatch present
  - `_derive_state_from_meta` returns `None` → `status="error"`
  - Verify output dict key is `workflow_phase` (not `current_phase`) from field name mapping
- [ ] **GREEN:** In `reconciliation.py`, implement `_check_single_feature()`. Calls `engine._derive_state_from_meta(meta, feature_type_id, source='meta_json')`, reads DB via `db.get_workflow_phase()`, builds `meta_json`/`db` dicts, detects mismatches. None guard: if `_derive_state_from_meta()` returns `None` → `WorkflowDriftReport` with `status="error"`.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** All 7 drift check test scenarios pass. Field name mapping `current_phase` → `workflow_phase` verified.

**Files:** `reconciliation.py`, `test_reconciliation.py`

**Depends on:** 1.1, 1.2, 2.1

---

### Task 2.3: Public drift detection (TDD step 6)

- [ ] **RED:** In `test_reconciliation.py`, write tests for `check_workflow_drift(engine, db, artifacts_root, feature_type_id=None)`:
  - Single feature — all statuses (AC-1 through AC-4)
  - Bulk scan — multiple features (AC-5)
  - Exception handling → error status
  - Summary counts correct
  - `db_only` detection via `list_workflow_phases` set difference filtered to `feature:` type_ids only
  - Non-feature type_ids in DB excluded from `db_only` detection
- [ ] **GREEN:** In `reconciliation.py`, implement `check_workflow_drift()`. Single-feature path: `_read_single_meta_json()` → if `None`, check DB → `db_only` or `error`. Bulk path: `engine._iter_meta_jsons()` → `_check_single_feature()` per feature; detect `db_only` via `db.list_workflow_phases()` set difference filtered to `feature:` prefix. Summary aggregation.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** AC-1 through AC-5 tests pass. `db_only` detection correctly filters non-feature type_ids.

**Files:** `reconciliation.py`, `test_reconciliation.py`

**Depends on:** 2.1, 2.2

---

## Phase 3: Reconciliation Apply

> Sequential — 3.1 → 3.2. Depends on Phase 2.

### Task 3.1: Single-feature reconcile (TDD step 7)

- [ ] **RED:** In `test_reconciliation.py`, write tests for `_reconcile_single_feature(engine, db, report, dry_run)`:
  - `meta_json_ahead` → update (AC-6)
  - `in_sync` → skip (AC-7)
  - `meta_json_only` + entity exists → create (AC-8); verify `report.meta_json` dict contains keys `workflow_phase`, `last_completed_phase`, `mode` before create
  - `meta_json_only` + entity not found → `action="error"`, message contains "Entity not found" (error flows through `ReconcileAction`, not via `_catch_value_error`)
  - `meta_json_only` + `meta_json` is `None` → error
  - `db_ahead` → skip
  - `dry_run=True` → no DB writes (AC-9)
  - Idempotency (AC-10)
  - `ValueError` from `update_workflow_phase` → `action="error"`
  - `ValueError` from `create_workflow_phase` → `action="error"` (covers duplicate row AND entity-deleted races)
- [ ] **GREEN:** In `reconciliation.py`, implement `_reconcile_single_feature()`. Note: design deviation — no `meta` parameter (removed per plan 3.1 rationale; `report.meta_json` contains all needed data). Status-based branching: `meta_json_ahead` → `db.update_workflow_phase()`, `meta_json_only` → defensive `None` guard then `db.create_workflow_phase()`, `in_sync`/`db_ahead` → skip, `db_only` → skip, `error` → propagate. Catch ALL `ValueError` uniformly from DB calls.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** `pytest test_reconciliation.py -k "reconcile_single_feature or meta_json_ahead or meta_json_only or dry_run or idempotent or ValueError"` — all pass. Design deviation (no `meta` param) documented. Defensive guard for `meta_json is None` covered.

**Files:** `reconciliation.py`, `test_reconciliation.py`

**Depends on:** 2.2, 2.3 (test fixtures for WorkflowDriftReport constructed manually via dataclass constructor, not via check_workflow_drift; 2.3 dependency is for integration verification only)

---

### Task 3.2: Public reconciliation (TDD step 8)

- [ ] **RED:** In `test_reconciliation.py`, write tests for `apply_workflow_reconciliation(engine, db, artifacts_root, feature_type_id=None, dry_run=False)`:
  - Bulk reconcile multiple features
  - `dry_run` preview (AC-9)
  - Idempotency — second run all skipped (AC-10)
  - Summary counts include `reconciled`, `created`, `skipped`, `error`, `dry_run`
- [ ] **GREEN:** In `reconciliation.py`, implement `apply_workflow_reconciliation()`. Calls `check_workflow_drift()` internally, then `_reconcile_single_feature()` per feature. Summary aggregation by action type. Never raises.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** Bulk reconcile, dry_run, and idempotency tests pass. Summary dict has all 5 keys.

**Files:** `reconciliation.py`, `test_reconciliation.py`

**Depends on:** 2.3, 3.1

---

## Phase 4: Serialization Helpers

> Parallel group — tasks 4.1, 4.2 only depend on 1.1 (dataclasses). Can run in parallel with Phases 2-3.

### Task 4.1: Workflow dataclass serializers (TDD step 9)

- [ ] **RED:** In `test_workflow_state_server.py`, write tests for `_serialize_workflow_drift_report(report)` and `_serialize_reconcile_action(action)`:
  - Round-trip serialization
  - Empty mismatches/changes
  - `None` values
  - Verify `ReconcileAction.changes` serializes as `old_value=c.db_value`, `new_value=c.meta_json_value`
- [ ] **GREEN:** In `workflow_state_server.py`, implement both serializers per design I9.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** `pytest test_workflow_state_server.py -k "serialize_workflow_drift_report or serialize_reconcile_action"` — all pass. `old_value`/`new_value` mapping direction verified for `meta_json_to_db`.

**Files:** `workflow_state_server.py`, `test_workflow_state_server.py`

**Depends on:** 1.1

---

### Task 4.2: Frontmatter DriftReport serializer (TDD step 10)

- [ ] **RED:** In `test_workflow_state_server.py`, write tests for `_serialize_drift_report(report)`:
  - With mismatches
  - Empty mismatches
  - All status values
- [ ] **GREEN:** In `workflow_state_server.py`, implement `_serialize_drift_report()` per design I8. Import `DriftReport`, `FieldMismatch` from `entity_registry.frontmatter_sync`.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** `pytest test_workflow_state_server.py -k "serialize_drift_report"` — all pass.

**Files:** `workflow_state_server.py`, `test_workflow_state_server.py`

**Depends on:** Existing `DriftReport`/`FieldMismatch` from `frontmatter_sync`

---

## Phase 5: Processing Functions

> Sequential — 5.1 → 5.2 → 5.3 → 5.4. Depends on Phases 2-4.

### Task 5.1: _process_reconcile_check (TDD step 11)

- [ ] **RED:** In `test_workflow_state_server.py`, write tests for `_process_reconcile_check()`:
  - Single feature → JSON with drift report
  - Bulk → JSON with summary
  - Validation error: non-existent slug (realpath fails) → `_validate_feature_type_id` raises `ValueError` → `_catch_value_error` maps to `_make_error("feature_not_found", ...)` (AC-18 case 1). Verify by asserting error JSON contains `"feature_not_found"` type.
  - Validation error: malformed input (no colon) → `_validate_feature_type_id` raises `ValueError` → `_catch_value_error` maps to `_make_error("invalid_transition", ...)` (AC-18 case 2). Verify by asserting error JSON contains `"invalid_transition"` type.
- [ ] **GREEN:** In `workflow_state_server.py`, implement `_process_reconcile_check()`. Decorated with `@_with_error_handling` and `@_catch_value_error`. **Error-type routing convention:** `_validate_feature_type_id` raises `ValueError` with distinct prefixes — `raise ValueError("feature_not_found: ...")` for realpath/traversal failures, `raise ValueError("invalid_input: ...")` for missing colon or malformed format. The `_catch_value_error` decorator checks `str(e).startswith("feature_not_found:")` → `_make_error("feature_not_found", ...)`, otherwise → `_make_error("invalid_transition", ...)`. If `feature_type_id` provided: call `_validate_feature_type_id()` FIRST, then `check_workflow_drift()`. Serialize result to JSON string.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** `pytest test_workflow_state_server.py -k "_process_reconcile_check"` — all pass, including both AC-18 error type assertions.

**Files:** `workflow_state_server.py`, `test_workflow_state_server.py`

**Depends on:** 1.3, 2.3, 4.1

---

### Task 5.2: _process_reconcile_apply (TDD step 12)

- [ ] **RED:** In `test_workflow_state_server.py`, write tests for `_process_reconcile_apply()`:
  - Reconcile → JSON with actions
  - `dry_run`
  - Invalid direction → error (AC-17)
  - Validation error: non-existent slug → `_catch_value_error` maps to `_make_error("feature_not_found", ...)` (AC-18 case 1)
  - Validation error: malformed input (no colon) → `_catch_value_error` maps to `_make_error("invalid_transition", ...)` (AC-18 case 2)
- [ ] **GREEN:** In `workflow_state_server.py`, implement `_process_reconcile_apply()`. Decorated with `@_with_error_handling` and `@_catch_value_error` (same prefix-based error-type routing as 5.1: `"feature_not_found:"` prefix → `feature_not_found`, else → `invalid_transition`). Validates `direction` against `_SUPPORTED_DIRECTIONS`. If `feature_type_id` provided: `_validate_feature_type_id()` FIRST. Delegates to `apply_workflow_reconciliation()`.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** `pytest test_workflow_state_server.py -k "_process_reconcile_apply"` — all pass, including AC-17 and both AC-18 error type assertions.

**Files:** `workflow_state_server.py`, `test_workflow_state_server.py`

**Depends on:** 1.3, 3.2, 4.1

---

### Task 5.3: _process_reconcile_frontmatter (TDD step 13)

- [ ] **RED:** In `test_workflow_state_server.py`, write tests for `_process_reconcile_frontmatter()`:
  - Single feature with valid frontmatter (AC-11)
  - No frontmatter (AC-12)
  - Bulk scan via `scan_all(db, artifacts_root)` (AC-13)
  - Non-existent directory → empty reports
  - Validation error: non-existent slug → `_catch_value_error` maps to `_make_error("feature_not_found", ...)` (AC-18 case 1)
  - Validation error: malformed input (no colon) → `_catch_value_error` maps to `_make_error("invalid_transition", ...)` (AC-18 case 2)
- [ ] **GREEN:** In `workflow_state_server.py`, implement `_process_reconcile_frontmatter()`. Decorated with `@_with_error_handling` and `@_catch_value_error` (same prefix-based error-type routing as 5.1: `"feature_not_found:"` prefix → `feature_not_found`, else → `invalid_transition`). If `feature_type_id` provided: `slug = _validate_feature_type_id(feature_type_id, artifacts_root)`, construct dir path, iterate `ARTIFACT_BASENAME_MAP` files, call `detect_drift()` per existing file. If omitted: call `scan_all(db, artifacts_root)` from `entity_registry.frontmatter_sync`. Non-existent dir → empty reports.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** `pytest test_workflow_state_server.py -k "_process_reconcile_frontmatter"` — all pass, including AC-11 through AC-13 and both AC-18 error type assertions.

**Files:** `workflow_state_server.py`, `test_workflow_state_server.py`

**Depends on:** 1.3, 4.2

---

### Task 5.4: _process_reconcile_status (TDD step 14)

- [ ] **RED:** In `test_workflow_state_server.py`, write tests for `_process_reconcile_status()`:
  - All in sync → `healthy=true` (AC-14)
  - Any drift → `healthy=false` (AC-15)
  - Error status in either dimension → `healthy=false`
  - Workflow drift succeeds then `scan_all` raises `sqlite3.Error` → entire response is structured error (all-or-nothing)
- [ ] **GREEN:** In `workflow_state_server.py`, implement `_process_reconcile_status()`. Decorated with `@_with_error_handling` only (no `_catch_value_error`). Calls `check_workflow_drift()` and `scan_all()` directly. Computes `healthy` flag: True when BOTH dimensions have all counts except `in_sync` equal to 0.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** AC-14, AC-15 tests pass. All-or-nothing error behavior verified.

**Files:** `workflow_state_server.py`, `test_workflow_state_server.py`

**Depends on:** 2.3, 4.1, 4.2

---

## Phase 6: MCP Tool Handlers

> Depends on Phase 5.

### Task 6.1: MCP tool registration (TDD step 15)

- [ ] **RED:** In `test_workflow_state_server.py`, write tests for 4 `@mcp.tool()` async handlers:
  - Handler returns structured JSON (SC-6)
  - `None` guards return `_NOT_INITIALIZED` (AC-16)
- [ ] **GREEN:** In `workflow_state_server.py`, implement 4 `@mcp.tool()` handlers per design I5: `reconcile_check`, `reconcile_apply`, `reconcile_frontmatter`, `reconcile_status`. Add imports per design I10. Each handler: guard `_engine`/`_db` for `None` → delegates to `_process_*`.
- [ ] **REFACTOR:** Verify tests pass.

**Acceptance:** SC-6 and AC-16 tests pass. All 4 handlers registered.

**Files:** `workflow_state_server.py`, `test_workflow_state_server.py`

**Depends on:** 5.1, 5.2, 5.3, 5.4

---

## Phase 7: End-to-End Integration Tests

> Depends on Phase 6. Unit tests already exist from Phases 1-6.

### Task 7.1: Full-cycle integration tests (TDD step 16)

- [ ] Write multi-feature drift detection → reconciliation → verify `in_sync` cycle in `test_reconciliation.py`:
  - Bulk scan with 3+ features in different drift states → reconcile all → re-check all `in_sync`
  - Idempotency verification (second reconcile produces all-skipped)
  - Edge cases: both-None phases, terminal phases, empty feature set
  - Uses in-memory SQLite DB, temp directories with real `.meta.json` files

**Acceptance:** All integration tests pass end-to-end.

**Files:** `test_reconciliation.py` (EXTEND)

**Depends on:** 3.2 (all reconciliation logic)

---

### Task 7.2: MCP end-to-end integration tests (TDD step 17)

- [ ] Write full processing function → handler → response chain tests in `test_workflow_state_server.py`:
  - `reconcile_status` returning `healthy=true` after `reconcile_apply`:
    **Fixture:** Create 2+ features with temp `.meta.json` files in `meta_json_ahead` state (phase values ahead of DB). Run `reconcile_apply` to sync. Then call `reconcile_status` and assert `healthy=true`, all counts except `in_sync` are 0.
  - `reconcile_frontmatter` with real temp files containing frontmatter headers:
    **Fixture:** Create temp markdown files with YAML frontmatter headers, register entities in DB, call `reconcile_frontmatter` and verify per-file drift reports.
  - Error paths: uninitialized guards (AC-16), invalid direction (AC-17), invalid `feature_type_id` (AC-18)

**Acceptance:** All MCP integration tests pass end-to-end.

**Files:** `test_workflow_state_server.py` (EXTEND)

**Depends on:** 6.1 (all MCP handlers)

---

## Summary

| Phase | Tasks | Parallel? | Depends On |
|-------|-------|-----------|------------|
| 1 | 1.1, 1.2, 1.3 | Yes (all parallel) | None |
| 2 | 2.1, 2.2, 2.3 | No (sequential) | Phase 1 |
| 3 | 3.1, 3.2 | No (sequential) | Phase 2 |
| 4 | 4.1, 4.2 | Yes (parallel; also parallel with Phases 2-3) | 1.1 only |
| 5 | 5.1, 5.2, 5.3, 5.4 | No (sequential) | Phases 2-4 |
| 6 | 6.1 | — | Phase 5 |
| 7 | 7.1, 7.2 | Yes (parallel) | Phase 6 |

**Total:** 17 tasks across 7 phases, 3 parallel groups (Phase 1, Phase 4, Phase 7).
