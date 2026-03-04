# Plan: State Engine MCP Tools — Phase Read/Write

## Implementation Order

The plan follows a TDD-compatible dependency order: bootstrap infrastructure first, then the server module (tests before production code where possible), then integration.

### Phase 1: Bootstrap Infrastructure

**Goal:** Create the shell bootstrap script and its tests so the Python environment resolution is proven before writing any Python code.

#### 1.1 Create `run-workflow-server.sh`

- **File:** `plugins/iflow/mcp/run-workflow-server.sh` (Create)
- **Source:** Clone `run-entity-server.sh`, change diagnostic prefix to `"workflow-engine"` and `SERVER_SCRIPT` to `workflow_state_server.py`
- **Verification:** `bash -n` syntax check, `chmod +x`
- **Depends on:** Nothing
- **Design ref:** I5

#### 1.2 Create `test_run_workflow_server.sh`

- **File:** `plugins/iflow/mcp/test_run_workflow_server.sh` (Create)
- **Source:** Clone `test_entity_server.sh` (at `plugins/iflow/mcp/test_entity_server.sh`), update paths and prefixes for `run-workflow-server.sh`
- **Tests:**
  - Bash syntax check (`bash -n`)
  - Executable permission check
  - PYTHONPATH includes `hooks/lib/`
  - PYTHONUNBUFFERED=1
  - No stdout before exec
  - **Server starts without immediate crash** — start the server process via the bootstrap script, verify it stays running for 2 seconds (mirroring Test 4 from `test_entity_server.sh`). Catches import errors, missing dependencies, and lifespan failures at bootstrap time.
- **Depends on:** 1.1
- **Design ref:** I5, I7 (bootstrap tests)
- **AC coverage:** AC-8 (PYTHONPATH + PYTHONUNBUFFERED), SC-1 (smoke), SC-3, SC-5

### Phase 2: Server Module — Processing Functions (TDD)

**Goal:** Implement and test all 6 processing functions plus serialization helpers. This is the core logic layer, tested in isolation without MCP overhead.

**TDD discipline:** For each step 2.3–2.8, write failing test(s) first (RED), then implement the processing function to make them pass (GREEN). The design provides exact function signatures and behavior, making test-first straightforward.

#### 2.1 Create test file with fixtures

- **File:** `plugins/iflow/mcp/test_workflow_state_server.py` (Create)
- **Content:** Test fixtures (`db`, `engine`, `seeded_engine` per design I7), imports
- **Note:** The `seeded_engine` fixture calls `db.register_entity("feature", "009-test", ...)` which internally constructs `type_id = "feature:009-test"`, then `db.create_workflow_phase("feature:009-test", workflow_phase="specify")` which stores the phase row keyed by that same `type_id`. Verified: `get_state("feature:009-test")` will find both records via this consistent `type_id` format.
- **Depends on:** Nothing (can run in parallel with Phase 1)
- **Design ref:** I7

#### 2.2 Implement `_serialize_state` and `_serialize_result` + tests

- **File:** `plugins/iflow/mcp/workflow_state_server.py` (Create — partial: imports I0, serializers I4)
- **Tests:** Verify dict output shape, `severity.value` string conversion, `completed_phases` as list
- **Depends on:** 2.1
- **Design ref:** I0, I4 (serializers)
- **AC coverage:** SC-2

#### 2.3 Tests + `_process_get_phase`

- **Tests (RED):** (a) success with seeded feature, (b) not-found returns string, (d) unexpected exception
- **Implement (GREEN):** Write `_process_get_phase` to pass tests
- **Depends on:** 2.2
- **Design ref:** I4
- **AC coverage:** AC-1, AC-10

#### 2.4 Tests + `_process_transition_phase`

- **Tests (RED):** (a) all gates pass → `transitioned: true`, (a2) gate blocks → `transitioned: false` (use target_phase where hard prerequisite artifacts are missing, e.g., transition to `design` without spec.md in tmp_path), (a3) `yolo_active=True` passes YOLO-overridable gates — seed a feature where a YOLO-overridable guard would normally block, call with `yolo_active=True`, assert `transitioned: true`, (c) ValueError, (d) unexpected exception
- **Implement (GREEN):** Write `_process_transition_phase` to pass tests
- **Depends on:** 2.2
- **Design ref:** I4
- **AC coverage:** AC-2, AC-7 (yolo_active), AC-11 (invalid phase)

#### 2.5 Tests + `_process_complete_phase`

- **Tests (RED):** (a) success advances phase (seeded fixture has `workflow_phase="specify"`, so call `complete_phase(type_id, "specify")` which succeeds because phase matches current_phase), (c) ValueError on unknown phase/mismatch, (d) unexpected exception
- **Implement (GREEN):** Write `_process_complete_phase` to pass tests
- **Depends on:** 2.2
- **Design ref:** I4
- **AC coverage:** AC-3

#### 2.6 Tests + `_process_validate_prerequisites`

- **Tests (RED):** (a) gates pass, (a2) gates fail, (c) ValueError, (d) unexpected exception, verify no DB mutation
- **Implement (GREEN):** Write `_process_validate_prerequisites` to pass tests
- **Depends on:** 2.2
- **Design ref:** I4
- **AC coverage:** AC-4, AC-11

#### 2.7 Tests + `_process_list_features_by_phase`

- **Tests (RED):** (a) populated result, (b) empty array for unknown phase, (d) unexpected exception → "Internal error:"
- **Implement (GREEN):** Write `_process_list_features_by_phase` to pass tests
- **Depends on:** 2.2
- **Design ref:** I4
- **AC coverage:** AC-5

#### 2.8 Tests + `_process_list_features_by_status`

- **Tests (RED):** (a) populated result, (b) empty array for unknown status, (d) unexpected exception
- **Implement (GREEN):** Write `_process_list_features_by_status` to pass tests
- **Depends on:** 2.2
- **Design ref:** I4
- **AC coverage:** AC-6

### Phase 3: Server Module — MCP Wiring

**Goal:** Add lifespan, tool handlers, and entry point to complete the server module.

#### 3.1 Add lifespan context manager

- **File:** `plugins/iflow/mcp/workflow_state_server.py` (Modify — add I1, I2)
- **Content:** Module-level globals, `@asynccontextmanager` lifespan
- **Depends on:** 2.2 (imports already in place; lifespan does not depend on processing functions)
- **Design ref:** I1, I2

#### 3.2 Add MCP tool handlers and entry point

- **File:** `plugins/iflow/mcp/workflow_state_server.py` (Modify — add I3)
- **Content:** `mcp = FastMCP(...)`, 6 `@mcp.tool()` async functions with None-guards, `if __name__ == "__main__"` entry point
- **Depends on:** 3.1 AND all of 2.3–2.8 (tool handlers call processing functions which must exist)
- **Design ref:** I3

### Phase 4: Plugin Registration

**Goal:** Register the new server in plugin.json so Claude discovers it.

#### 4.1 Update `plugin.json`

- **File:** `plugins/iflow/.claude-plugin/plugin.json` (Modify)
- **Content:** Add `"workflow-engine"` entry under `mcpServers`
- **Depends on:** 3.2 (server module must be complete)
- **Gate:** Do NOT proceed with this step if bootstrap tests (5.2) or processing function tests (5.1) fail. A broken server entry in plugin.json causes MCP initialization errors on every Claude session. This is the last file committed.
- **Design ref:** I6
- **AC coverage:** AC-9, SC-4

### Phase 5: Validation

**Goal:** Run all tests, verify bootstrap, confirm end-to-end.

#### 5.1 Run processing function tests

- **Command:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`
- **Depends on:** All of Phase 2 and Phase 3
- **AC coverage:** SC-2, AC-10

#### 5.2 Run bootstrap tests

- **Command:** `bash plugins/iflow/mcp/test_run_workflow_server.sh`
- **Depends on:** Phase 1 AND Phase 3 (smoke test needs complete server module)
- **AC coverage:** AC-8, SC-1 (smoke), SC-3, SC-5

#### 5.3 Run existing test suite (regression)

- **Command:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ -v`
- **Depends on:** 5.1, 5.2
- **Purpose:** Ensure no regressions in entity_server or memory_server

#### 5.4 Lightweight performance check (SC-6)

- **Command:** Add timing assertions to `test_workflow_state_server.py` — seed 50 features with workflow phases, then assert `_process_get_phase`, `_process_list_features_by_phase`, `_process_list_features_by_status`, and `_process_validate_prerequisites` each complete in < 100ms wall-clock time.
- **Depends on:** 5.1 (tests must pass first)
- **AC coverage:** SC-6
- **Note:** `validate_prerequisites` involves filesystem I/O for artifact checks, so the 100ms budget accounts for this. If the assertion fails on CI due to resource contention, mark the test with `@pytest.mark.slow` and document the local result.

## Parallel Execution Groups

Tasks that can execute concurrently:

| Group | Tasks | Rationale |
|-------|-------|-----------|
| A | 1.1, 2.1 | Bootstrap script and test fixtures have no dependencies on each other |
| B | 2.3, 2.4, 2.5, 2.6, 2.7, 2.8 | All processing functions depend only on 2.2 (serializers), not on each other |
| C | 5.1, 5.2 | Test suites are independent (but both must pass before 4.1 commit) |

## Dependency Graph

```
1.1 (bootstrap script)
 └─ 1.2 (bootstrap tests)

2.1 (test fixtures)
 └─ 2.2 (serializers + tests)
     ├─ 2.3 (get_phase)         ─┐
     ├─ 2.4 (transition_phase)  ─┤
     ├─ 2.5 (complete_phase)    ─┤
     ├─ 2.6 (validate_prereqs)  ─┤
     ├─ 2.7 (list_by_phase)     ─┤
     ├─ 2.8 (list_by_status)    ─┤
     └─ 3.1 (lifespan)          ─┤
                                  ▼
                          3.2 (tool handlers) ← fan-in: 3.1 + [2.3–2.8]
                           │
                           ▼
                    ┌─ 5.1 (processing tests)
                    ├─ 5.2 (bootstrap tests) ← also depends on 1.2
                    │      │
                    ▼      ▼
              [both must pass]
                    │
                    ▼
              4.1 (plugin.json) ← last commit
                    │
                    ▼
              5.3 (regression)
```

## Acceptance Criteria Coverage

| AC/SC | Covered By |
|-------|-----------|
| AC-1 | 2.3 |
| AC-2 | 2.4 |
| AC-3 | 2.5 |
| AC-4 | 2.6 |
| AC-5 | 2.7 |
| AC-6 | 2.8 |
| AC-7 | 2.4 |
| AC-8 | 1.2, 5.2 |
| AC-9 | 4.1 |
| AC-10 | 2.3–2.8, 5.1 |
| AC-11 | 2.4, 2.6 |
| SC-1 | 4.1, 5.2 (smoke test) |
| SC-2 | 2.2–2.8, 5.1 |
| SC-3 | 1.2, 5.2 |
| SC-4 | 4.1 |
| SC-5 | 1.2, 5.2 |
| SC-6 | 5.4 (timing assertions with 50 seeded features) |

## Risk Mitigations

| Risk | Mitigation in Plan |
|------|-------------------|
| `create_workflow_phase` API mismatch | 2.1 fixtures exercise the actual `EntityDatabase` API — fails fast if method signature differs. type_id format verified: `register_entity` constructs `"{type}:{id}"` internally. |
| Severity enum serialization | 2.2 tests explicitly check `.value` produces string, not enum object |
| Bootstrap path resolution | 1.2 tests verify before any Python code runs |
| Import failures from missing `hooks/lib/` PYTHONPATH | 2.2 creates the module with I0 sys.path safety net — tests run against real imports |
| Broken plugin.json breaks all sessions | 4.1 gated behind 5.1 + 5.2 passing. Last file committed. |
| Latent lifespan/import bug | 1.2 includes "server starts without crash" smoke test (2s runtime check) |
