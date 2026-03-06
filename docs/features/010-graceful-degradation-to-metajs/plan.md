# Plan: Graceful Degradation to .meta.json

## Plan-Phase Decision Resolution

### Probe busy_timeout (from Design Open Items)

**Decision:** Accept inherited 5s bound. Do NOT implement 100ms probe-specific timeout.

**Reasoning:** PRAGMA save/restore requires try/finally wrapping around the probe (save old value, set 100ms, SELECT 1, restore in finally block, catch PRAGMA failures). This exceeds the 10-line threshold defined in the design and introduces error-handling complexity for the restore path. The 5s worst case only triggers on contended DBs in a single-user CLI tool — rare in practice. Add a code comment documenting the accepted bound.

---

## Implementation Order

### Phase 1: Foundation (No Dependencies)

These items have zero interdependencies and can be implemented in any order within the phase.

**1.1 — `TransitionResponse` dataclass (C5)**
- File: `workflow_engine/models.py`
- Add `TransitionResponse` frozen dataclass with `results: tuple[TransitionResult, ...]` and `degraded: bool`
- Update `source` field comment to include `"meta_json_fallback"` as valid value
- Add `import` for dataclass if not present
- Tests: unit test construction, frozen enforcement, field access

**1.2 — `_check_db_health()` method (C1)**
- File: `workflow_engine/engine.py`
- Add private method to `WorkflowStateEngine`
- Guard `self.db._conn is None` → `False` (defensive future-proofing — EntityDatabase.close() doesn't currently null `_conn`, but guard prevents NPE if behavior changes)
- Execute `SELECT 1`, catch `sqlite3.Error` → `False`
- Add code comment: `# NOTE: busy_timeout is inherited from EntityDatabase (5s). Accepted product decision — see design C1 NFR-1 interaction.`
- Add `import sqlite3` at top of engine.py
- Tests: probe on healthy DB → True; probe with mocked `_conn = None` → False (defensive guard); probe after `db.close()` raising `sqlite3.ProgrammingError` → False (real-world failure mode); probe with generic `sqlite3.Error` → False

**1.3 — `_derive_state_from_meta()` extraction (TD-3)**
- File: `workflow_engine/engine.py`
- Extract phase derivation logic from `_hydrate_from_meta_json` (lines 255-283) into new `_derive_state_from_meta(meta, feature_type_id, source)` method
- Refactor `_hydrate_from_meta_json` to delegate to `_derive_state_from_meta` (per design I3b)
- Add `source` parameter to `_derive_state_from_meta` (default `"meta_json"`)
- Tests: existing `_hydrate_from_meta_json` tests MUST still pass (regression). Add direct `_derive_state_from_meta` tests for active/completed/unknown status paths. Add explicit test for default `source="meta_json"` parameter value.

**1.4 — `_iso_now()` helper (I11)**
- File: `workflow_engine/engine.py`
- Module-level function (not a method)
- Returns ISO 8601 with local timezone offset
- Tests: verify output format matches `.meta.json` convention

**1.5 — `_make_error()` helper (C6 / I9)**
- File: `mcp/workflow_state_server.py`
- Add module-level function returning JSON string with `error`, `error_type`, `message`, `recovery_hint`
- Tests: verify JSON structure, verify all error_type values produce valid JSON

### Phase 2: Filesystem Operations (Depends on Phase 1)

**2.1 — `_read_state_from_meta_json()` (C2 / I2)**
- File: `workflow_engine/engine.py`
- Depends on: 1.3 (`_derive_state_from_meta`)
- Extract slug, construct path, read JSON, delegate to `_derive_state_from_meta` with `source="meta_json_fallback"`
- Return `None` on `FileNotFoundError`, `json.JSONDecodeError`, `OSError`
- Tests: valid .meta.json → correct state; missing file → None; corrupt JSON → None; active/completed/unknown status variants

**2.2 — `_write_meta_json_fallback()` (C3 / I4)**
- File: `workflow_engine/engine.py`
- Depends on: 1.4 (`_iso_now`)
- Read current .meta.json, update `lastCompletedPhase`, `phases.{phase}` timestamps, `status` if finishing
- Atomic write: `NamedTemporaryFile(delete=False)` + `os.replace()`. Use try/finally to ensure temp file fd is closed AND unlinked on any failure (including `json.dump` raising mid-write)
- Raise `ValueError` on unreadable .meta.json
- Add `import tempfile` at top of engine.py
- Tests: normal write; atomic replacement (verify tmp cleanup); missing .meta.json → ValueError; corrupt .meta.json → ValueError; terminal phase sets `status="completed"`; partial write cleanup (mock `json.dump` to raise → verify temp file is removed)

### Phase 3: Scanner Operations (Depends on Phases 1-2)

**3.1 — `_scan_features_filesystem()` (C4 / I5)**
- File: `workflow_engine/engine.py`
- Depends on: 2.1 (`_read_state_from_meta_json`)
- Glob `features/*/.meta.json`, derive `feature_type_id` from dir name, call `_read_state_from_meta_json`
- Add `import glob` at top of engine.py (top-level, not deferred)
- Tests: multiple features; empty dir; mix of valid and corrupt .meta.json files

**3.2 — `_scan_features_by_status()` (C8 / I17)**
- File: `workflow_engine/engine.py`
- Depends on: 1.3 (`_derive_state_from_meta`) — note: does NOT depend on 2.1; could execute in Phase 2, but grouped here for logical coherence with 3.1
- Glob, read raw JSON, filter by `meta["status"]`, then derive state
- Tests: filter active; filter completed; corrupt files skipped; empty results

### Phase 4: Public Method Wrapping (Depends on Phases 1-3)

Wire fallback paths into existing public methods. Each method gets:
(a) health probe at entry, (b) proactive skip when unhealthy, (c) secondary catch for mid-operation failures.

**4.1 — `get_state()` fallback (I7)**
- File: `workflow_engine/engine.py`
- Depends on: 1.2 (health probe), 2.1 (filesystem reader)
- Add probe → proactive skip → `_read_state_from_meta_json`
- Add `except sqlite3.Error` → secondary defense → `_read_state_from_meta_json`
- stderr logging for both paths
- Tests: probe fails → fallback returns from .meta.json; probe passes but DB query raises → secondary defense; happy path unchanged

**4.2 — `transition_phase()` return type change + fallback (I8 / I12)**
- File: `workflow_engine/engine.py`
- Depends on: 1.1 (TransitionResponse), 1.2 (health probe), 4.1 (get_state)
- Change return type from `list[TransitionResult]` to `TransitionResponse`
- Add probe → `degraded` tracking → catch DB write failure → `TransitionResponse(degraded=True)`
- Gate evaluation unchanged (pure logic, no DB dependency)
- **Existing test migration (ATOMIC with return type change):**
  - Engine tests (~14 call sites in `test_engine.py`): all tests calling `transition_phase()` must unwrap `TransitionResponse.results` instead of receiving bare `list[TransitionResult]`. Grep for `transition_phase(` in test_engine.py to enumerate.
  - MCP handler `_process_transition_phase` in `workflow_state_server.py`: must unwrap `TransitionResponse` and serialize `degraded` field.
  - MCP tests (~3 call sites in `test_workflow_state_server.py`): assertions on transition response shape must account for new `degraded` field.
  - Run grep: `grep -n 'transition_phase\|\.allowed' test_engine.py test_workflow_state_server.py` before committing to catch all sites.
- Tests: normal → `TransitionResponse(degraded=False)`; DB write fail → `degraded=True`; probe fail → skip DB write, results still valid; all existing transition tests pass with unwrapped results

**4.3 — `complete_phase()` fallback (I13)**
- File: `workflow_engine/engine.py`
- Depends on: 1.2 (health probe), 2.2 (write fallback), 4.1 (get_state)
- Add probe → `wrote_to_db` flag pattern → secondary defense → `_write_meta_json_fallback`
- Read-back failure after successful DB write → derive state from params (no .meta.json write)
- Tests: DB write fail → .meta.json updated; probe fail → direct .meta.json write; DB write + read-back fail → derived state with source="db"; happy path unchanged

**4.4 — `list_by_phase()` fallback (I15)**
- File: `workflow_engine/engine.py`
- Depends on: 1.2 (health probe), 3.1 (filesystem scanner)
- Add probe → filesystem scan → filter by `current_phase`
- Tests: probe fail → filesystem results; DB query fail → secondary defense; happy path unchanged

**4.5 — `list_by_status()` fallback (I16)**
- File: `workflow_engine/engine.py`
- Depends on: 1.2 (health probe), 3.2 (status scanner)
- Add probe → `_scan_features_by_status`; secondary catch → same
- Tests: probe fail → filesystem results; happy path unchanged

### Phase 5: MCP Layer Updates (Depends on Phase 4)

**5.1 — Structured error responses (C6)**
- File: `mcp/workflow_state_server.py`
- Depends on: 1.5 (_make_error)
- Update all `_process_*` functions to use `_make_error` for error returns
- Update all 6 `_engine is None` guards to use `_make_error("not_initialized", ...)`
- Update non-exception error paths (e.g., `_process_get_phase` None-state check)
- Add `import sqlite3` for type-specific catches
- Tests: update existing error-path assertions to check JSON structure; verify all error types

**5.2 — MCP degradation signal (C7 / I10)**
- File: `mcp/workflow_state_server.py`
- Depends on: 4.2 (TransitionResponse), 5.1 (structured errors)
- Add `from workflow_engine.models import TransitionResponse` import
- Update `_serialize_state` to include `degraded = (state.source == "meta_json_fallback")`
- Update `_process_transition_phase` to unwrap `TransitionResponse` — per design I14, response drops `allowed` key (uses `results` from `TransitionResponse`)
- Update `_process_complete_phase`, `_process_list_*` for degradation field
- **Existing test migration (ATOMIC with serialization changes):**
  - `TestSerializeState` and `TestAdversarial` exact key-set assertions must add `degraded` to expected keys
  - Transition response shape tests (assertions on `data['allowed']`) must be updated per I14 — replace `allowed` with new response shape
  - Grep: `grep -n "allowed\|key.*set\|keys()" test_workflow_state_server.py` to enumerate all affected assertions
- Tests: normal responses have `degraded: false`; fallback responses have `degraded: true`; transition responses include degraded field

### Phase 6: Integration Tests (Depends on Phase 5)

**6.1 — End-to-end degradation scenarios**
- File: `workflow_engine/test_engine.py` (extend)
- Full workflow: create state → close DB → get_state → verify fallback
- Full workflow: create state → close DB → complete_phase → verify .meta.json write
- Full workflow: create state → close DB → list operations → verify filesystem scan
- Health probe performance: 1000 iterations < 1ms mean (AC-6)

**6.2 — MCP server degradation tests**
- File: `mcp/test_workflow_state_server.py` (extend)
- Test each MCP tool with mocked DB failure → verify `degraded: true`
- Test structured error format for each error type
- Verify happy-path tests still pass (AC-8)

---

## Dependency Graph

```
Phase 1 (parallel):
  1.1 TransitionResponse ─────────────────┐
  1.2 _check_db_health ──────────────────┐│
  1.3 _derive_state_from_meta ──────────┐││
  1.4 _iso_now ────────────────────────┐│││
  1.5 _make_error ────────────────────┐││││
                                      │││││
Phase 2 (depends on 1.3, 1.4):       │││││
  2.1 _read_state_from_meta_json ◄────┘│┘││
  2.2 _write_meta_json_fallback ◄──────┘ ││
                                         ││
Phase 3 (depends on 2.1, 1.3):          ││
  3.1 _scan_features_filesystem          ││
  3.2 _scan_features_by_status           ││
                                         ││
Phase 4 (depends on 1-3):               ││
  4.1 get_state() fallback               ││
  4.2 transition_phase() ◄───────────────┘│
  4.3 complete_phase()                    │
  4.4 list_by_phase()                     │
  4.5 list_by_status()                    │
                                          │
Phase 5 (depends on 4, 1.5):             │
  5.1 structured errors ◄────────────────┘
  5.2 MCP degradation signal

Phase 6 (depends on 5):
  6.1 engine integration tests
  6.2 MCP server integration tests
```

## TDD Order

Each item is implemented RED → GREEN → REFACTOR.

**Dependency note:** Steps 10-14 (Phase 4) write tests that exercise fallback paths. These tests depend on Phase 1-3 implementations being GREEN — the fallback methods (`_read_state_from_meta_json`, `_write_meta_json_fallback`, scanners) must exist and pass their own tests before Phase 4 tests can run. Steps 1-9 are strict prerequisites.

1. Write `TransitionResponse` tests → implement dataclass (1.1)
2. Write `_check_db_health` tests → implement probe (1.2)
3. Write `_derive_state_from_meta` tests → extract method, verify `_hydrate_from_meta_json` still passes (1.3)
4. Write `_iso_now` tests → implement helper (1.4)
5. Write `_make_error` tests → implement helper (1.5)
6. Write `_read_state_from_meta_json` tests → implement reader (2.1)
7. Write `_write_meta_json_fallback` tests → implement writer (2.2)
8. Write `_scan_features_filesystem` tests → implement scanner (3.1)
9. Write `_scan_features_by_status` tests → implement scanner (3.2)
10. Write `get_state()` fallback tests → wrap with probe + catch (4.1)
11. Write `transition_phase()` tests → change return type + add fallback + **migrate ~14 existing engine tests and ~3 MCP tests atomically** (4.2)
12. Write `complete_phase()` tests → add wrote_to_db pattern + fallback (4.3)
13. Write `list_by_phase()` fallback tests → add probe + scanner (4.4)
14. Write `list_by_status()` fallback tests → add probe + scanner (4.5)
15. Write structured error tests → update `_process_*` functions (5.1)
16. Write degradation signal tests → update serialization + handlers + **migrate existing key-set and response shape assertions** (5.2)
17. Write integration tests → end-to-end scenarios (6.1, 6.2)

## Files Modified

| File | Phase | Change Type |
|------|-------|-------------|
| `plugins/iflow/hooks/lib/workflow_engine/models.py` | 1.1 | Add `TransitionResponse`, update source comment |
| `plugins/iflow/hooks/lib/workflow_engine/engine.py` | 1.2-4.5 | Add C1-C4, C8 methods; extract helper; wrap public methods; add imports |
| `plugins/iflow/mcp/workflow_state_server.py` | 5.1-5.2 | Add `_make_error`; structured errors; degradation signals; update handlers |
| `plugins/iflow/hooks/lib/workflow_engine/test_engine.py` | 1-6 | Tests for all engine changes |
| `plugins/iflow/mcp/test_workflow_state_server.py` | 5-6 | Update error assertions; add degradation tests |

## Risk Mitigations During Implementation

1. **Regression guard (1.3):** Run full existing test suite after `_derive_state_from_meta` extraction to catch any behavioral drift. The extraction is mechanical but the phase derivation logic has edge cases (unknown status, missing `lastCompletedPhase`, `ValueError` from `_next_phase_value`).

2. **Return type change (4.2):** `transition_phase()` return type changes from `list[TransitionResult]` to `TransitionResponse`. All callers must be updated atomically — both engine callers and MCP handler. Run grep for `transition_phase` call sites before committing.

3. **Error format breaking change (5.1):** Error-path tests in `test_workflow_state_server.py` must be updated before/with the implementation. Existing assertions like `assert "Error:" in result` will break. Update tests first (RED), then implementation (GREEN).

4. **Import ordering (1.2, 2.2, 3.1, 4.1-4.5):** Four new imports added to `engine.py`: `sqlite3`, `sys`, `tempfile`, `glob`. All must be top-level (per design — no deferred imports inside function bodies). `sys` is needed for `print(..., file=sys.stderr)` logging in Phase 4 fallback paths.
