# Tasks: Graceful Degradation to .meta.json

## Phase 1: Foundation (No Dependencies)

All Phase 1 tasks are independent and can be implemented in parallel.

### Task 1.1: Add `TransitionResponse` dataclass

**File:** `plugins/iflow/hooks/lib/workflow_engine/models.py`
**TDD Step:** 1
**Depends on:** none
**Complexity:** Simple
**Test file:** `plugins/iflow/hooks/lib/workflow_engine/test_engine.py`

- [ ] Write test functions named `test_transition_response_*` (e.g., `test_transition_response_construction`, `test_transition_response_frozen`, `test_transition_response_field_access`, `test_transition_response_results_is_tuple`): construction, frozen enforcement, field access, `results` is tuple, `degraded` is bool
- [ ] Add `TransitionResponse` frozen dataclass with `results: tuple[TransitionResult, ...]` and `degraded: bool`
- [ ] Update `source` field comment on `FeatureWorkflowState` to include `"meta_json_fallback"` as valid value
- [ ] Run: `pytest plugins/iflow/hooks/lib/workflow_engine/test_engine.py -v -k TransitionResponse`

**Done when:** Tests pass for construction, frozen enforcement, and field access. Source comment updated. The `-k TransitionResponse` filter matches test function names containing that string.

---

### Task 1.2: Add `_check_db_health()` method

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 2
**Depends on:** none
**Complexity:** Moderate

- [ ] Add `import sqlite3` at top of engine.py
- [ ] Write tests: healthy DB → True; mocked `_conn = None` → False (via `monkeypatch.setattr(engine.db, "_conn", None)` — defensive future-proofing); `db.close()` raising `sqlite3.ProgrammingError` → False (via `monkeypatch.setattr(engine.db, "_conn", MockConn())` where `MockConn` is defined inline in the test function as `class MockConn: def execute(self, *a): raise sqlite3.ProgrammingError("closed")`); generic `sqlite3.Error` → False
- [ ] Implement `_check_db_health()` on `WorkflowStateEngine`: guard `self.db._conn is None` → `False`, execute `SELECT 1`, catch `sqlite3.Error` → `False`
- [ ] Add code comment: `# NOTE: busy_timeout is inherited from EntityDatabase (5s). Accepted product decision — see design C1 NFR-1 interaction.`

**Done when:** All 4 test scenarios pass. `import sqlite3` present at top of file.

---

### Task 1.3: Extract `_derive_state_from_meta()` method

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 3
**Depends on:** none
**Complexity:** Complex

- [ ] Pre-step grep: `grep -n _hydrate_from_meta_json plugins/iflow/hooks/lib/workflow_engine/test_engine.py` — enumerate all ~14 test sites and confirm all pass before proceeding
- [ ] Write direct `_derive_state_from_meta` tests: active status → correct phase; completed status → `workflow_phase="finish"`; unknown status → `workflow_phase=None`; default `source="meta_json"` parameter (verify omitting source arg uses `"meta_json"`); `ValueError` from `_next_phase_value` returns `None`
- [ ] Extract phase derivation logic from `_hydrate_from_meta_json` (lines ~255-283 — verify at implementation time) into `_derive_state_from_meta(meta, feature_type_id, source="meta_json")`
- [ ] Refactor `_hydrate_from_meta_json`: after extraction, body from line ~255 onward becomes `state = self._derive_state_from_meta(meta, feature_type_id, source="meta_json"); if state is None: return None` followed by the unchanged backfill block (lines ~286-310). File+JSON-read block (lines ~249-253) is untouched. Exception handling is NOT modified during refactor.
- [ ] Run full test suite: `pytest plugins/iflow/hooks/lib/workflow_engine/ -v` — ALL existing `_hydrate_from_meta_json` tests MUST still pass

**Done when:** New `_derive_state_from_meta` tests pass. ALL existing `_hydrate_from_meta_json` tests pass (zero regressions). Extraction is mechanical — no behavioral changes.

---

### Task 1.4: Add `_iso_now()` helper

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 4
**Depends on:** none
**Complexity:** Simple

- [ ] Add `from datetime import datetime, timezone` at top of engine.py
- [ ] Write test: verify output matches ISO 8601 with timezone offset, matches `.meta.json` convention
- [ ] Implement module-level `_iso_now()` function returning `datetime.now(timezone.utc).astimezone().isoformat()`

**Done when:** Test verifies ISO 8601 format with timezone offset.

---

### Task 1.5: Add `_make_error()` helper

**File:** `plugins/iflow/mcp/workflow_state_server.py`
**TDD Step:** 5
**Depends on:** none
**Complexity:** Simple

- [ ] Write tests in `plugins/iflow/mcp/test_workflow_state_server.py` as new `TestMakeError` class (before `TestProcessGetPhase`): verify JSON structure has `error`, `error_type`, `message`, `recovery_hint` keys; verify all error_type values produce valid JSON
- [ ] Implement module-level `_make_error(error_type, message, recovery_hint)` returning JSON string

**Done when:** Tests verify JSON structure for all error types (`db_unavailable`, `feature_not_found`, `invalid_transition`, `internal`, `not_initialized`).

---

## Phase 2: Filesystem Operations (Depends on Phase 1)

### Task 2.1: Add `_read_state_from_meta_json()` method

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 6
**Depends on:** Task 1.3 (`_derive_state_from_meta`)
**Complexity:** Moderate

- [ ] Write tests: valid `.meta.json` → correct `FeatureWorkflowState` with `source="meta_json_fallback"`; missing file → `None`; corrupt JSON → `None`; `OSError` → `None`; active/completed/unknown status variants
- [ ] Implement `_read_state_from_meta_json(feature_type_id)`: extract slug, construct path, read JSON, delegate to `_derive_state_from_meta` with `source="meta_json_fallback"`
- [ ] Note: catches `OSError` in addition to `json.JSONDecodeError` (asymmetry with `_hydrate_from_meta_json` is intentional — see plan 2.1)

**Done when:** All test scenarios pass. Method returns `None` on any filesystem/JSON error.

---

### Task 2.2: Add `_write_meta_json_fallback()` method

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 7
**Depends on:** Task 1.4 (`_iso_now`)
**Complexity:** Complex

- [ ] Add `import tempfile` at top of engine.py
- [ ] Write tests: normal write verifies `lastCompletedPhase` and `phases.{phase}` timestamps; atomic replacement (verify tmp cleanup); missing `.meta.json` → `ValueError`; corrupt `.meta.json` → `ValueError`; terminal phase (`finish`) sets `status="completed"`; partial write cleanup (mock `json.dump` to raise → verify temp file not on disk after call raises; simplest: `assert not os.path.exists(tmp_path)`)
- [ ] Implement `_write_meta_json_fallback(feature_type_id, phase, state)` per design I4: read current `.meta.json`, update fields, atomic write via `NamedTemporaryFile` + `os.replace()`
- [ ] Ensure try/finally closes fd (`if fd is not None and not fd.closed: fd.close()`) before unlink
- [ ] Note: `state` parameter is used ONLY for `state.mode` when constructing the returned `FeatureWorkflowState`. No other fields from `state` are read — all other data comes from the `.meta.json` file. Do not add other accesses to `state`.

**Done when:** All 6 test scenarios pass. Temp file cleanup verified on failure paths (assert tmp file not on disk).

---

## Phase 3: Scanner Operations (Depends on Phases 1-2)

### Task 3.1: Add `_scan_features_filesystem()` method

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 8
**Depends on:** Task 2.1 (`_read_state_from_meta_json`)
**Complexity:** Moderate

- [ ] Add `import glob` at top of engine.py
- [ ] Write tests: multiple features → correct list; empty dir → empty list; mix of valid and corrupt `.meta.json` files → corrupt ones skipped
- [ ] Implement `_scan_features_filesystem()` per design I5: glob `features/*/.meta.json`, derive `feature_type_id` from dir name, call `_read_state_from_meta_json`

**Done when:** All 3 test scenarios pass. Corrupt files silently skipped.

---

### Task 3.2: Add `_scan_features_by_status()` method

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 9
**Depends on:** Task 1.3 (`_derive_state_from_meta`)
**Complexity:** Moderate

- [ ] Write tests: filter by `"active"` → only active features; filter by `"completed"` → only completed; corrupt files skipped; empty results when no match
- [ ] Implement `_scan_features_by_status(status)` per design I17: glob, read raw JSON, filter by `meta["status"]` BEFORE building `FeatureWorkflowState`, then derive state
- [ ] Note: intentionally does NOT use `_read_state_from_meta_json` — filters at raw JSON level because `FeatureWorkflowState` has no status field

**Done when:** All 4 test scenarios pass. Filtering happens before state derivation.

---

## Phase 4: Public Method Wrapping (Depends on Phases 1-3)

### Task 4.1: Add `get_state()` fallback

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 10
**Depends on:** Tasks 1.2, 2.1
**Complexity:** Moderate

- [ ] Add `import sys` at top of engine.py (for `print(..., file=sys.stderr)`). Note: `import sys` is owned by Task 4.1. Phase 1 tasks (1.2-1.4) do NOT need `sys`.
- [ ] Write tests: probe fails → fallback returns from `.meta.json` with `source="meta_json_fallback"`; probe passes but DB query raises `sqlite3.Error` → secondary defense returns from `.meta.json`; happy path unchanged (existing tests still pass)
- [ ] Wrap `get_state()` per design I7: health probe → proactive skip → `_read_state_from_meta_json`; add `except sqlite3.Error` secondary defense
- [ ] Add stderr logging for both degradation paths

**Done when:** Both fallback paths tested. Happy path tests unmodified and passing.

---

### Task 4.2: Change `transition_phase()` return type + fallback (ATOMIC)

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`, `plugins/iflow/mcp/workflow_state_server.py`
**TDD Step:** 11 (sub-steps a-g)
**Depends on:** Tasks 1.1, 1.2, 4.1
**Complexity:** Complex

**CRITICAL: Sub-steps b through e are a single atomic commit. Do NOT commit after 11b alone.**

- [ ] **11a.** Write new fallback tests (RED): probe fail → `TransitionResponse(degraded=True)`; DB write fail → `TransitionResponse(degraded=True)`
- [ ] **11b.** Change `transition_phase()` return type: wrap results in `TransitionResponse(results=tuple(results), degraded=False)` — existing engine tests now FAIL
- [ ] **11c.** Migrate engine test call sites to unwrap `.results`:
  - Pre-commit grep: `grep -n transition_phase plugins/iflow/hooks/lib/workflow_engine/test_engine.py` to get current line numbers (~22 hits total)
  - Classification: 13 standard assigning sites (add `.results` unwrap, pattern: `results = engine.transition_phase(...).results`), 1 special site (line ~777: `response = engine.transition_phase(...); transition_results = response.results`), 2 `pytest.raises` sites (no change — exception before return), 1 fire-and-forget perf test (no change — return unused), remaining hits are function definitions/comments (no change)
  - **CRITICAL for lines ~1289/1366**: Pattern is `results = engine.transition_phase(...); blocked = [r for r in results ...]` — change to `response = engine.transition_phase(...); results = response.results; blocked = [r for r in results ...]`. These iterate on the value — if unwrap is missed, iteration yields field values not TransitionResult objects.
- [ ] **11d.** Update MCP handler `_process_transition_phase` in `workflow_state_server.py` to unwrap `TransitionResponse.results`; add `from workflow_engine.models import TransitionResponse` import to `workflow_state_server.py`
- [ ] **11e.** Migrate `test_transitioned_uses_all_not_any` monkeypatch to return `TransitionResponse(results=tuple(mixed_results), degraded=False)`; add import at top of `plugins/iflow/mcp/test_workflow_state_server.py`: `from workflow_engine.models import TransitionResponse` (place after existing `from workflow_engine.models import FeatureWorkflowState` import)
- [ ] **COMMIT b-e atomically** — run: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/test_engine.py plugins/iflow/mcp/test_workflow_state_server.py -v`
- [ ] **11f.** Implement degraded-path logic: health probe check, DB write guard, `TransitionResponse(degraded=True)` on failure
- [ ] **11g.** Verification grep: `grep -n 'transition_phase\|\.allowed' plugins/iflow/hooks/lib/workflow_engine/test_engine.py plugins/iflow/mcp/test_workflow_state_server.py` — confirm no unmigrated call sites AND no remaining bare `.allowed` accesses on the response object

**Done when:** All existing tests pass with unwrapped `.results`. New fallback tests pass. Grep verification shows no unmigrated sites.

---

### Task 4.3: Add `complete_phase()` fallback

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 12
**Depends on:** Tasks 1.2, 2.2, 4.1
**Complexity:** Moderate

- [ ] Write tests: DB write fail → `.meta.json` updated with `source="meta_json_fallback"`; probe fail → direct `.meta.json` write; DB write succeeds but read-back fails → derived state with `source="db"` (test via: monkeypatch `db.update_workflow_phase` to succeed, then monkeypatch `db.get_workflow_phase` to raise `sqlite3.Error` — two separate monkeypatches); happy path unchanged. Note: `update_workflow_phase` is a plain SQL UPDATE with no triggers — safe to mock independently.
- [ ] Wrap `complete_phase()` per design I13: probe → `wrote_to_db` flag → secondary defense → `_write_meta_json_fallback`
- [ ] Read-back failure after DB write success → derive state from params (no `.meta.json` write)

**Done when:** All 4 test scenarios pass. Happy path tests unmodified.

---

### Task 4.4: Add `list_by_phase()` fallback

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 13
**Depends on:** Tasks 1.2, 3.1
**Complexity:** Simple

- [ ] Write tests: probe fail → filesystem results via `_scan_features_filesystem` filtered by `current_phase`; DB query raises → secondary defense; happy path unchanged
- [ ] Wrap `list_by_phase()` per design I15: health probe → filesystem scan → filter

**Done when:** Both fallback paths tested. Happy path unchanged.

---

### Task 4.5: Add `list_by_status()` fallback

**File:** `plugins/iflow/hooks/lib/workflow_engine/engine.py`
**TDD Step:** 14
**Depends on:** Tasks 1.2, 3.2
**Complexity:** Simple

- [ ] Write tests: probe fail → filesystem results via `_scan_features_by_status`; happy path unchanged
- [ ] Wrap `list_by_status()` per design I16: health probe → `_scan_features_by_status`; secondary catch → same

**Done when:** Fallback path tested. Happy path unchanged.

---

## Phase 5: MCP Layer Updates (Depends on Phase 4)

### Task 5.1: Add structured error responses

**File:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`
**TDD Step:** 15
**Depends on:** Task 1.5 (`_make_error`)
**Complexity:** Complex

- [ ] Pre-step grep: `grep -n 'startswith\|"Error:\|Internal error' plugins/iflow/mcp/test_workflow_state_server.py` to enumerate all string-format error assertions. This pattern matches: `startswith(` calls (assertion sites), literal `"Error:` strings in assertions, and `Internal error` strings. Expected ~17 assertion sites that need migration. If count differs significantly from ~17, audit the extra/missing hits before proceeding.
- [ ] Add `import sqlite3` to `workflow_state_server.py`
- [ ] Update all 6 `_engine is None` guards to use `_make_error("not_initialized", ...)`
- [ ] Update `_process_*` functions to use `_make_error` for error returns (ValueError, sqlite3.Error, Exception)
- [ ] Update non-exception error paths: `_process_get_phase` None-state check — change from `return f"Feature not found: {feature_type_id}"` to `return _make_error("feature_not_found", f"Feature not found: {feature_type_id}", "Verify feature_type_id format: 'feature:{id}-{slug}'")`
- [ ] Migrate test assertions — specific migrations (all become `data = json.loads(result); assert data["error_type"] == "..."; assert data["error"] is True`):
  - `test_not_found` (line ~144): `error_type: "feature_not_found"`
  - `test_get_phase_none_state_returns_not_found` (line ~765-779): `error_type: "feature_not_found"`
  - Line ~150 (ZeroDivisionError): `error_type: "internal"`
  - Line ~635 (Error:): `error_type: "feature_not_found"`
  - TestErrorClassification block (~lines 791-845): lines ~809/826/845 (`startswith('Internal error:')` → `error_type: "internal"`); lines ~619/635 (`Error:` → `error_type: "invalid_transition"` / `"feature_not_found"`)
  - Line ~516 TestAdversarial catch-all → accept structured JSON
- [ ] Run: `pytest plugins/iflow/mcp/test_workflow_state_server.py -v`

**Done when:** All error-path assertions check JSON structure. All `_engine is None` guards use `_make_error`. Pre-step grep count reconciled.

---

### Task 5.2: Add MCP degradation signal

**File:** `plugins/iflow/mcp/workflow_state_server.py`, `plugins/iflow/mcp/test_workflow_state_server.py`
**TDD Step:** 16 (sub-steps a-b)
**Depends on:** Tasks 4.2, 5.1
**Complexity:** Complex

**Sub-step A — Serialization update:**
- [ ] Write `_serialize_state` degraded-field tests: `source="db"` → `degraded: false`; `source="meta_json_fallback"` → `degraded: true`
- [ ] Update `_serialize_state` to include `degraded = (state.source == "meta_json_fallback")`
- [ ] Migrate `TestSerializeState` and `TestAdversarial` exact key-set assertions to add `degraded` to expected keys

**Sub-step B — Transition response shape + consumer audit:**
- [ ] Consumer audit grep (A): `grep -rn allowed plugins/iflow/skills/ plugins/iflow/commands/ plugins/iflow/hooks/ plugins/iflow/agents/ plugins/iflow/mcp/` — classify hits into 3 categories: Python attribute access (code changes needed), SKILL.md pseudocode (no change), test file JSON parsing (migrated in this task)
- [ ] Consumer audit grep (B): `grep -rn 'transition_phase(' plugins/iflow/ --include='*.py' | grep -v test_` — verify no unexpected Python callers beyond engine.py and workflow_state_server.py
- [ ] Write transition response shape tests: response has `degraded` field, no `allowed` top-level key
- [ ] Update `_process_transition_phase` response shape: drop `allowed` key, add `degraded` per design I14
- [ ] Migrate `test_transition_result_json_has_exact_key_set` (line ~638-653): expected keys `{"transitioned", "results", "degraded"}`
- [ ] Migrate `test_success` in TestProcessTransitionPhase (line ~159-171): remove `data["allowed"]` assertion
- [ ] Update `_process_complete_phase`, `_process_list_*` for degradation field
- [ ] Verification grep: `grep -n "allowed\|key.*set\|keys()\|Feature not found" test_workflow_state_server.py`
- [ ] Run: `pytest plugins/iflow/mcp/test_workflow_state_server.py -v`

**Done when:** All MCP responses include `degraded` field. Consumer audit greps verified. No `allowed` top-level key in transition responses.

---

## Phase 6: Integration Tests (Depends on Phase 5)

### Task 6.1: Add engine integration tests

**File:** `plugins/iflow/hooks/lib/workflow_engine/test_engine.py`
**TDD Step:** 17 (engine portion)
**Depends on:** All Phase 1-5 tasks
**Complexity:** Moderate

- [ ] Full workflow: create state → close DB → `get_state()` → verify fallback returns `source="meta_json_fallback"`
- [ ] Full workflow: create state → close DB → `complete_phase()` → verify `.meta.json` write
- [ ] Full workflow: create state → close DB → `list_by_phase()`/`list_by_status()` → verify filesystem scan results
- [ ] Health probe performance: 1000 iterations `_check_db_health()` < 1ms mean (AC-6). Use in-memory SQLite DB (`EntityDatabase(":memory:")`) for the performance fixture, NOT the `tmp_path` disk-based DB used in other integration tests.
- [ ] Run: `pytest plugins/iflow/hooks/lib/workflow_engine/ -v`

**Done when:** All end-to-end scenarios pass. Performance assertion holds against in-memory DB.

---

### Task 6.2: Add MCP server integration tests

**File:** `plugins/iflow/mcp/test_workflow_state_server.py`
**TDD Step:** 17 (MCP portion)
**Depends on:** All Phase 1-5 tasks
**Complexity:** Moderate

- [ ] Test each MCP tool (`get_phase`, `transition_phase`, `complete_phase`, `list_by_phase`, `list_by_status`) with mocked DB failure → verify `degraded: true` in response
- [ ] Test structured error format for each error type (`db_unavailable`, `feature_not_found`, `invalid_transition`, `internal`, `not_initialized`)
- [ ] Verify all happy-path tests still pass (AC-8)
- [ ] Run: `pytest plugins/iflow/mcp/test_workflow_state_server.py -v`

**Done when:** All degradation and error format tests pass. Happy-path regression suite green.

---

## Dependency Graph

```
Phase 1 (all parallel):
  Task 1.1 ──────┐
  Task 1.2 ────┐ │
  Task 1.3 ──┐ │ │
  Task 1.4 ┐ │ │ │
  Task 1.5 │ │ │ │
             │ │ │ │
Phase 2:     │ │ │ │
  Task 2.1 ◄─┘ │ │  (depends on 1.3)
  Task 2.2 ◄───┘ │  (depends on 1.4)
                  │ │
Phase 3:          │ │
  Task 3.1 ◄─────┘ │  (depends on 2.1)
  Task 3.2 ◄───────┘  (depends on 1.3)

Phase 4:
  Task 4.1 ◄── 1.2, 2.1
  Task 4.2 ◄── 1.1, 1.2, 4.1
  Task 4.3 ◄── 1.2, 2.2, 4.1
  Task 4.4 ◄── 1.2, 3.1
  Task 4.5 ◄── 1.2, 3.2

Phase 5:
  Task 5.1 ◄── 1.5
  Task 5.2 ◄── 4.2, 5.1

Phase 6 (all depend on Phase 5):
  Task 6.1
  Task 6.2
```

## Summary

- **17 tasks** across **6 phases**
- **3 parallel groups**: Phase 1 (5 tasks), Phase 3 (2 tasks), Phase 6 (2 tasks)
- **1 atomic commit boundary**: Task 4.2 sub-steps b-e
- Files modified: `models.py`, `engine.py`, `workflow_state_server.py`, `test_engine.py`, `test_workflow_state_server.py`
