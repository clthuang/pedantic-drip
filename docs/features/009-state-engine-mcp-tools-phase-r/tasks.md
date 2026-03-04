# Tasks: State Engine MCP Tools — Phase Read/Write

## Phase 1: Bootstrap Infrastructure

### Task 1.1: Create `run-workflow-server.sh`

- [ ] Clone `plugins/iflow/mcp/run-entity-server.sh` to `plugins/iflow/mcp/run-workflow-server.sh`
- [ ] Change diagnostic prefix from `"entity-registry"` to `"workflow-engine"`
- [ ] Change `SERVER_SCRIPT` variable to `workflow_state_server.py`
- [ ] Run `bash -n plugins/iflow/mcp/run-workflow-server.sh` — must pass syntax check
- [ ] Run `chmod +x plugins/iflow/mcp/run-workflow-server.sh`

**File:** `plugins/iflow/mcp/run-workflow-server.sh` (Create)
**Source template:** `plugins/iflow/mcp/run-entity-server.sh`
**Design ref:** I5
**Depends on:** Nothing
**Done when:** File exists, passes `bash -n`, is executable, uses `"workflow-engine"` prefix and `workflow_state_server.py` script name.

---

### Task 1.2a: Create `test_run_workflow_server.sh` (static tests)

- [ ] Clone `plugins/iflow/mcp/test_entity_server.sh` to `plugins/iflow/mcp/test_run_workflow_server.sh`
- [ ] Update all path references from `run-entity-server.sh` to `run-workflow-server.sh`
- [ ] Update diagnostic prefix checks from `"entity-registry"` to `"workflow-engine"`
- [ ] Ensure tests verify: `bash -n`, executable permission, PYTHONPATH includes `hooks/lib/`, PYTHONUNBUFFERED=1, no stdout before exec
- [ ] **Comment out** the smoke test (server start check) with `# DEFERRED: uncomment after Phase 3 — needs complete server module`
- [ ] Run `chmod +x plugins/iflow/mcp/test_run_workflow_server.sh`
- [ ] Run `bash plugins/iflow/mcp/test_run_workflow_server.sh` — all static tests pass

**File:** `plugins/iflow/mcp/test_run_workflow_server.sh` (Create)
**Source template:** `plugins/iflow/mcp/test_entity_server.sh`
**Design ref:** I5, I7
**Depends on:** 1.1 (bootstrap script must exist)
**AC coverage:** AC-8, SC-3, SC-5
**Done when:** File exists, static tests (bash -n, permissions, PYTHONPATH, PYTHONUNBUFFERED, no stdout) all pass. Smoke test is commented out.

---

### Task 1.2b: Enable smoke test in `test_run_workflow_server.sh`

- [ ] Uncomment the smoke test in `test_run_workflow_server.sh` (server starts without immediate crash, stays running 2 seconds)
- [ ] Run `bash plugins/iflow/mcp/test_run_workflow_server.sh` — all tests pass including smoke test

**File:** `plugins/iflow/mcp/test_run_workflow_server.sh` (Modify — uncomment smoke test)
**Depends on:** 1.2a AND 3.2 (server module must be complete for smoke test)
**AC coverage:** SC-1 (smoke)
**Done when:** Smoke test uncommented and passes — server process stays alive for 2 seconds.

---

## Phase 2: Server Module — Processing Functions (TDD)

**TDD discipline:** For tasks 2.3–2.8, write failing tests first (RED), then implement the processing function (GREEN).

### Task 2.1: Create test file with fixtures

- [ ] Create `plugins/iflow/mcp/test_workflow_state_server.py`
- [ ] Add `import pytest`, `import json`
- [ ] Add `from entity_registry.database import EntityDatabase`
- [ ] Add `from workflow_engine.engine import WorkflowStateEngine`
- [ ] **Verify API signatures exist:** Run `plugins/iflow/.venv/bin/python -c "from entity_registry.database import EntityDatabase; db = EntityDatabase(':memory:'); db.register_entity('feature', 'x', 'X'); db.create_workflow_phase('feature:x', workflow_phase='specify'); print('API OK')"` — must print "API OK" without error
- [ ] Create `db` fixture returning `EntityDatabase(":memory:")`
- [ ] Create `engine` fixture returning `WorkflowStateEngine(db, str(tmp_path))`
- [ ] Create `seeded_engine` fixture: register entity `("feature", "009-test", "Test Feature", status="active")`, create workflow phase `("feature:009-test", workflow_phase="specify")`, return engine
- [ ] Verify fixtures work: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v --collect-only`

**File:** `plugins/iflow/mcp/test_workflow_state_server.py` (Create)
**Design ref:** I7
**Depends on:** Nothing (parallel with Phase 1)
**Done when:** API signature verification passes. `pytest --collect-only` shows fixtures collected without import errors.

---

### Task 2.2: Implement `_serialize_state`, `_serialize_result` + tests

- [ ] Create `plugins/iflow/mcp/workflow_state_server.py` with imports from I0
- [ ] Add `_serialize_state(state: FeatureWorkflowState) -> dict` per I4
- [ ] Add `_serialize_result(result: TransitionResult) -> dict` per I4 (with `.value` for severity enum)
- [ ] Write test: `_serialize_state` returns dict with correct keys (`feature_type_id`, `current_phase`, `last_completed_phase`, `completed_phases`, `mode`, `source`)
- [ ] Write test: `_serialize_state` converts `completed_phases` tuple to list
- [ ] Write test: `_serialize_result` returns dict with `severity` as string (not enum object)
- [ ] Write test: `_serialize_result` returns dict with `allowed`, `reason`, `severity`, `guard_id` keys
- [ ] Run tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v -k serialize`

**File:** `plugins/iflow/mcp/workflow_state_server.py` (Create — partial: I0 imports + I4 serializers)
**Design ref:** I0, I4
**Depends on:** 2.1 (test file with fixtures)
**AC coverage:** SC-2
**Done when:** All serialize tests pass. `severity.value` produces string, `completed_phases` is list.

---

### Task 2.3: Tests + `_process_get_phase`

- [ ] **RED:** Write test `test_get_phase_success` — seeded engine returns JSON with `feature_type_id`, `current_phase == "specify"`
- [ ] **RED:** Write test `test_get_phase_not_found` — returns `"Feature not found: feature:nonexistent"`
- [ ] **RED:** Write test `test_get_phase_unexpected_exception` — monkeypatch `get_state` to raise, assert `"Internal error: ..."` prefix
- [ ] Verify tests fail (RED)
- [ ] **GREEN:** Implement `_process_get_phase` per I4
- [ ] Run tests: all 3 pass (GREEN)

**File:** `plugins/iflow/mcp/workflow_state_server.py` (Modify — add `_process_get_phase`)
**Design ref:** I4
**Depends on:** 2.2
**AC coverage:** AC-1, AC-10
**Done when:** 3 tests pass — success, not-found, unexpected exception.

---

### Task 2.4: Tests + `_process_transition_phase`

- [ ] **RED:** Write test `test_transition_phase_success` — all gates pass → `transitioned: true`, `allowed: true`
- [ ] **RED:** Write test `test_transition_phase_blocked` — transition to `design` without `spec.md` in `tmp_path`. Gate G-08 (`check_hard_prerequisites`, enforcement=hard_block, yolo_behavior=unchanged) blocks because `spec.md` is a hard prerequisite for `design` phase. Assert `transitioned: false` and result contains `guard_id: "G-08"`.
- [ ] **RED:** Write test `test_transition_phase_yolo_active` — seed feature at `specify` phase (via `seeded_engine`), attempt transition to `create-plan` without completing `specify` first (no `specify` in `completed_phases`). Gate G-23 (`check_soft_prerequisites`, enforcement=soft_warn, yolo_behavior=auto_select) would normally block. Call with `yolo_active=True` → YOLO overrides G-23 → assert `transitioned: true`. Note: still need `spec.md` in `tmp_path` for G-08 hard prereq to pass.
- [ ] **RED:** Write test `test_transition_phase_value_error` — monkeypatch `engine.transition_phase` to raise `ValueError("bad phase")`, assert `"Error: bad phase"`
- [ ] **RED:** Write test `test_transition_phase_unexpected_exception` — monkeypatch `engine.transition_phase` to raise `RuntimeError`, assert `"Internal error: ..."` prefix
- [ ] Verify tests fail (RED)
- [ ] **GREEN:** Implement `_process_transition_phase` per I4
- [ ] Run tests: all 5 pass (GREEN)

**File:** `plugins/iflow/mcp/workflow_state_server.py` (Modify — add `_process_transition_phase`)
**Design ref:** I4
**Depends on:** 2.2
**AC coverage:** AC-2, AC-7 (yolo_active), AC-11 (invalid phase)
**Gate details:** G-08 (hard_block, unchanged — blocks missing hard prereq artifacts), G-23 (soft_warn, auto_select — YOLO-overridable soft prerequisites)
**Done when:** 5 tests pass — success, blocked (G-08), yolo_active (G-23 overridden), ValueError, unexpected exception.

---

### Task 2.5: Tests + `_process_complete_phase`

- [ ] **RED:** Write test `test_complete_phase_success` — seeded fixture has `workflow_phase="specify"`, call `complete_phase(type_id, "specify")` → returns JSON with advanced `current_phase`
- [ ] **RED:** Write test `test_complete_phase_value_error` — unknown phase/mismatch → `"Error: ..."`
- [ ] **RED:** Write test `test_complete_phase_unexpected_exception` — monkeypatch, assert `"Internal error: ..."` prefix
- [ ] Verify tests fail (RED)
- [ ] **GREEN:** Implement `_process_complete_phase` per I4
- [ ] Run tests: all 3 pass (GREEN)

**File:** `plugins/iflow/mcp/workflow_state_server.py` (Modify — add `_process_complete_phase`)
**Design ref:** I4
**Depends on:** 2.2
**AC coverage:** AC-3
**Fixture constraint:** Seeded fixture has `workflow_phase="specify"` — call `complete_phase` with `"specify"` to match current_phase.
**Done when:** 3 tests pass — success, ValueError, unexpected exception.

---

### Task 2.6: Tests + `_process_validate_prerequisites`

- [ ] **RED:** Write test `test_validate_prerequisites_pass` — gates pass → `all_passed: true`
- [ ] **RED:** Write test `test_validate_prerequisites_fail` — gates fail → `all_passed: false`, results array populated
- [ ] **RED:** Write test `test_validate_prerequisites_value_error` — monkeypatch `engine.validate_prerequisites` to raise `ValueError("unknown feature")`, assert result starts with `"Error: unknown feature"`
- [ ] **RED:** Write test `test_validate_prerequisites_unexpected_exception` — monkeypatch `engine.validate_prerequisites` to raise `RuntimeError`, assert `"Internal error: ..."` prefix
- [ ] **RED:** Write test `test_validate_prerequisites_no_mutation` — call validate, then verify DB state unchanged (get_state returns same result before and after)
- [ ] Verify tests fail (RED)
- [ ] **GREEN:** Implement `_process_validate_prerequisites` per I4
- [ ] Run tests: all 5 pass (GREEN)

**File:** `plugins/iflow/mcp/workflow_state_server.py` (Modify — add `_process_validate_prerequisites`)
**Design ref:** I4
**Depends on:** 2.2
**AC coverage:** AC-4, AC-11
**Monkeypatch target:** `engine.validate_prerequisites` (same pattern as tasks 2.3–2.5)
**Done when:** 5 tests pass — gates pass, gates fail, ValueError, unexpected exception, no DB mutation.

---

### Task 2.7: Tests + `_process_list_features_by_phase`

- [ ] **RED:** Write test `test_list_features_by_phase_populated` — seeded feature in "specify" phase → JSON array with 1 element
- [ ] **RED:** Write test `test_list_features_by_phase_empty` — unknown phase → empty JSON array `[]`
- [ ] **RED:** Write test `test_list_features_by_phase_unexpected_exception` — monkeypatch, assert `"Internal error: ..."` prefix
- [ ] Verify tests fail (RED)
- [ ] **GREEN:** Implement `_process_list_features_by_phase` per I4
- [ ] Run tests: all 3 pass (GREEN)

**File:** `plugins/iflow/mcp/workflow_state_server.py` (Modify — add `_process_list_features_by_phase`)
**Design ref:** I4
**Depends on:** 2.2
**AC coverage:** AC-5
**Done when:** 3 tests pass — populated, empty, unexpected exception.

---

### Task 2.8: Tests + `_process_list_features_by_status`

- [ ] **RED:** Write test `test_list_features_by_status_populated` — seeded feature with status "active" → JSON array with 1 element
- [ ] **RED:** Write test `test_list_features_by_status_empty` — unknown status → empty JSON array `[]`
- [ ] **RED:** Write test `test_list_features_by_status_unexpected_exception` — monkeypatch, assert `"Internal error: ..."` prefix
- [ ] Verify tests fail (RED)
- [ ] **GREEN:** Implement `_process_list_features_by_status` per I4
- [ ] Run tests: all 3 pass (GREEN)

**File:** `plugins/iflow/mcp/workflow_state_server.py` (Modify — add `_process_list_features_by_status`)
**Design ref:** I4
**Depends on:** 2.2
**AC coverage:** AC-6
**Done when:** 3 tests pass — populated, empty, unexpected exception.

---

## Phase 3: Server Module — MCP Wiring

### Task 3.1: Add lifespan context manager

- [ ] Add module-level globals to `workflow_state_server.py`: `_db`, `_engine`, `_artifacts_root` per I1
- [ ] Add `@asynccontextmanager async def lifespan(server)` per I2
- [ ] Verify: lifespan resolves `ENTITY_DB_PATH` env var with `~/.claude/iflow/entities/entities.db` default
- [ ] Verify: lifespan resolves `PROJECT_ROOT` env var with `os.getcwd()` fallback
- [ ] Verify: lifespan uses `read_config()` for `artifacts_root`
- [ ] Verify: lifespan creates `WorkflowStateEngine(_db, _artifacts_root)`
- [ ] Verify: cleanup closes DB and sets globals to None
- [ ] **Integration check:** Run `plugins/iflow/.venv/bin/python -c "import workflow_state_server; print('lifespan OK')"` — verify module still imports without error after adding lifespan

**File:** `plugins/iflow/mcp/workflow_state_server.py` (Modify — add I1, I2)
**Design ref:** I1, I2
**Depends on:** 2.2 (imports already in place)
**Done when:** Lifespan function added with DB init, engine init, and cleanup. Module imports without error.

---

### Task 3.2: Add MCP tool handlers and entry point

- [ ] Add `mcp = FastMCP("workflow-engine", lifespan=lifespan)` per I3
- [ ] Add 6 `@mcp.tool()` async functions: `get_phase`, `transition_phase`, `complete_phase`, `validate_prerequisites`, `list_features_by_phase`, `list_features_by_status` per I3
- [ ] Each handler: None-guard on `_engine`, delegates to corresponding `_process_*()` function
- [ ] Add `if __name__ == "__main__": mcp.run(transport="stdio")` entry point
- [ ] Verify: `plugins/iflow/.venv/bin/python -c "import workflow_state_server"` succeeds (no import errors)

**File:** `plugins/iflow/mcp/workflow_state_server.py` (Modify — add I3)
**Design ref:** I3
**Depends on:** 3.1 AND 2.3–2.8 (all processing functions must exist)
**Done when:** All 6 tool handlers, `mcp` instance, and entry point added. Module imports without error.

---

## Phase 4: Plugin Registration

### Task 4.1: Update `plugin.json`

- [ ] Read `plugins/iflow/.claude-plugin/plugin.json`
- [ ] Add `"workflow-engine"` entry under `mcpServers` per I6: `{"command": "${CLAUDE_PLUGIN_ROOT}/mcp/run-workflow-server.sh", "args": []}`
- [ ] Verify JSON is valid: `python3 -c "import json; json.load(open('plugins/iflow/.claude-plugin/plugin.json'))"`

**File:** `plugins/iflow/.claude-plugin/plugin.json` (Modify)
**Design ref:** I6
**Depends on:** 3.2 (server module complete) AND 5.1+5.2 pass (gate: tests must pass first)
**AC coverage:** AC-9, SC-4
**Done when:** plugin.json contains `workflow-engine` entry, valid JSON.

---

## Phase 5: Validation

### Task 5.1: Run processing function tests

- [ ] Run: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`
- [ ] All tests pass
- [ ] Verify test count matches expected (~27 tests across 8 test groups)

**Command:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`
**Depends on:** Phase 2 + Phase 3
**AC coverage:** SC-2, AC-10
**Done when:** All processing function tests pass.

---

### Task 5.2: Run bootstrap tests

- [ ] Run: `bash plugins/iflow/mcp/test_run_workflow_server.sh`
- [ ] All tests pass including smoke test (server stays running 2s)

**Command:** `bash plugins/iflow/mcp/test_run_workflow_server.sh`
**Depends on:** Phase 1 + Phase 3
**AC coverage:** AC-8, SC-1, SC-3, SC-5
**Done when:** All bootstrap tests pass.

---

### Task 5.3: Run regression test suite

- [ ] Run: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ -v`
- [ ] No regressions in existing entity_server, memory_server, or entity_registry tests

**Command:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ -v`
**Depends on:** 5.1, 5.2
**Done when:** Full test suite passes with no regressions.

---

### Task 5.4: Performance check (SC-6)

- [ ] Add `large_db` fixture: create `EntityDatabase(":memory:")`, loop `for i in range(50)`: `db.register_entity("feature", f"perf-{i:03d}", f"Perf Test {i}", status="active")` then `db.create_workflow_phase(f"feature:perf-{i:03d}", workflow_phase="specify")`. Return `WorkflowStateEngine(db, str(tmp_path))`.
- [ ] Add `test_performance_get_phase`: use `large_db` fixture, assert `_process_get_phase(engine, "feature:perf-025")` completes in < 100ms (use `time.perf_counter()`)
- [ ] Add `test_performance_list_by_phase`: assert `_process_list_features_by_phase(engine, "specify")` completes in < 100ms with 50 features
- [ ] Add `test_performance_list_by_status`: assert `_process_list_features_by_status(engine, "active")` completes in < 100ms with 50 features
- [ ] Add `test_performance_validate_prerequisites`: assert `_process_validate_prerequisites(engine, "feature:perf-025", "design")` completes in < 100ms with 50 features
- [ ] Run performance tests: all pass under 100ms wall-clock time

**File:** `plugins/iflow/mcp/test_workflow_state_server.py` (Modify — add timing tests)
**Depends on:** 5.1
**AC coverage:** SC-6
**Done when:** All 4 performance tests pass under 100ms. If CI fails due to contention, mark with `@pytest.mark.slow`.

---

## Parallel Execution Groups

| Group | Tasks | Rationale |
|-------|-------|-----------|
| A | 1.1, 2.1 | Bootstrap script and test fixtures have no shared dependencies |
| B | 2.3, 2.4, 2.5, 2.6, 2.7, 2.8 | All processing functions depend only on 2.2, not each other |
| C | 5.1, 5.2 | Test suites are independent (both must pass before 4.1) |

Note: Task 1.2a flows from 1.1 (Group A). Task 1.2b depends on both 1.2a and 3.2, so it runs with Group C timing.

## Dependency Summary

```
Group A (parallel):
  1.1 → 1.2a (static tests)
  2.1 → 2.2

Group B (parallel, after 2.2):
  2.2 → {2.3, 2.4, 2.5, 2.6, 2.7, 2.8}

Sequential:
  2.2 → 3.1
  {3.1, 2.3–2.8} → 3.2

Post-Phase 3:
  {1.2a, 3.2} → 1.2b (smoke test)

Group C (parallel, after 3.2):
  3.2 → {5.1, 5.2}
  {5.1, 5.2} → 4.1 (gated)
  4.1 → 5.3
  5.1 → 5.4
```
