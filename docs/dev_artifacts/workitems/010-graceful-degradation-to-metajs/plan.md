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
- Note: tuple chosen over list for frozen dataclass consistency; `json.dumps` produces identical JSON arrays from both types, so no serialization impact on downstream consumers.
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
- Extract phase derivation logic from `_hydrate_from_meta_json` (lines 255-283) into new `_derive_state_from_meta(meta, feature_type_id, source)` method. The extraction covers phase derivation logic ONLY. The file-reading and exception handling in `_hydrate_from_meta_json` (lines 249-253, catching only `json.JSONDecodeError`) must NOT be modified. `_read_state_from_meta_json` (item 2.1) has its own file-reading logic that additionally catches `OSError`.
- Refactor `_hydrate_from_meta_json` to delegate to `_derive_state_from_meta` (per design I3b)
- Add `source` parameter to `_derive_state_from_meta` (default `"meta_json"`)
- Pre-step grep: `grep -n '_hydrate_from_meta_json' plugins/iflow/hooks/lib/workflow_engine/test_engine.py` to enumerate all ~14 test sites (primary class ~lines 268-413, plus distant tests in TestDeepenedAdversarial ~line 1325 and TestDeepenedMutationMindset-adjacent ~lines 1617, 1667). Confirm all pass before proceeding.
- Tests: existing `_hydrate_from_meta_json` tests MUST still pass (regression). Add direct `_derive_state_from_meta` tests for active/completed/unknown status paths. Add explicit test for default `source="meta_json"` parameter value.

**1.4 — `_iso_now()` helper (I11)**
- File: `workflow_engine/engine.py`
- Module-level function (not a method)
- Add `from datetime import datetime, timezone` at top of engine.py (top-level, overriding design I11's deferred import for consistency with plan import policy)
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
- Return `None` on `FileNotFoundError`, `json.JSONDecodeError`, `OSError`. Note: `_read_state_from_meta_json` catches `OSError` in addition to `json.JSONDecodeError` because it is a fallback path that must never raise — any filesystem error returns `None`. By contrast, `_hydrate_from_meta_json` only catches `json.JSONDecodeError` because `OSError` would indicate a more serious issue that should propagate when DB is available. Do not "fix" this asymmetry.
- Tests: valid .meta.json → correct state; missing file → None; corrupt JSON → None; active/completed/unknown status variants

**2.2 — `_write_meta_json_fallback()` (C3 / I4)**
- File: `workflow_engine/engine.py`
- Depends on: 1.4 (`_iso_now`)
- Read current .meta.json, update `lastCompletedPhase`, `phases.{phase}` timestamps, `status` if finishing
- Atomic write: `NamedTemporaryFile(delete=False)` → `json.dump()` → `fd.close()` → `os.replace()`. Use try/finally to ensure temp file fd is closed AND unlinked on any failure (including `json.dump` raising mid-write). The finally block must explicitly close fd (`if fd is not None and not fd.closed: fd.close()`) before unlink to avoid leaking file descriptors on partial-write failures. Note: `fd.close()` flushes Python and OS buffers; explicit `flush()`+`fsync()` omitted to match design I4 code — crash-consistency guarantees are unnecessary for a single-user CLI tool where fallback data is ephemeral (reconciled by feature 011).
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
- Glob, read raw JSON, filter by `meta["status"]`, then derive state. This method intentionally reads .meta.json directly rather than calling `_read_state_from_meta_json` because it must filter by `meta["status"]` BEFORE building FeatureWorkflowState (which has no status field). Do not refactor to use `_read_state_from_meta_json` + post-filter.
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
- **Unwrap pattern:** Common case: `response = engine.transition_phase(type_id, 'design'); results = response.results`. For line ~777: `response = engine.transition_phase(type_id, 'design'); transition_results = response.results`.
- **Existing ENGINE test migration (ATOMIC with return type change — ~17 call sites in test_engine.py):**
  - 13 standard assigning call sites by line number: 605, 622, 640, 659, 954, 1048, 1059, 1125, 1289, 1366, 1452, 1511, 1532 (all `results = engine.transition_phase(...)` → unwrap via `response = engine.transition_phase(...); results = response.results`)
  - **Downstream iteration risk:** Lines 1289 and 1366 iterate over `results` immediately after the call (`blocked = [r for r in results if not r.allowed]`). After unwrapping to `results = response.results`, verify the list comprehension iterates on the tuple, not the response object.
  - 1 special site at line ~777 (`test_returns_same_results_as_transition`): does `transition_results = engine.transition_phase(...)` then `len(transition_results)` and `zip(validate_results, transition_results)`. After migration: `response = engine.transition_phase(...); transition_results = response.results`. `len()` works on tuples. `validate_prerequisites()` returns `list[TransitionResult]` while `TransitionResponse.results` is `tuple[TransitionResult, ...]` — `zip()` works across both types. Do NOT add type equality assertions.
  - 2 call sites inside `pytest.raises` — no unwrapping needed (exception raised before return)
  - 1 fire-and-forget perf test at line ~1704 — no unwrapping needed (return value unused)
  - Pre-commit grep: `grep -n 'transition_phase' plugins/iflow/hooks/lib/workflow_engine/test_engine.py` to verify all sites migrated.
  - **Grep count reconciliation:** grep returns ~22 hits for `transition_phase`. Classify every hit: (a) 13 standard assigning sites needing unwrap (lines above), (b) 1 special-case site (line ~777), (c) 2 inside `pytest.raises` — no change, (d) 1 fire-and-forget perf test (line ~1704) — no change (measures wall-clock duration, does not inspect return value; TransitionResponse wrapping overhead is sub-microsecond, within AC-6 bounds), (e) remaining hits are test function NAMES (e.g., `def test_transition_phase_...`) and class docstrings — not call sites, no change needed. Total actionable: 13 + 1 + 2 + 1 = 17 call sites. All others are definitions/comments.
- **MCP handler update (ATOMIC with return type change):** Update `_process_transition_phase` in `workflow_state_server.py` to unwrap `TransitionResponse.results` — the handler currently iterates directly over the return value (`all(r.allowed for r in results)`), which would fail on a `TransitionResponse` dataclass. Add `from workflow_engine.models import TransitionResponse` import. Also migrate `test_transitioned_uses_all_not_any` (line ~716-740): monkeypatches `seeded_engine.transition_phase` to return bare `list[TransitionResult]` — must update to return `TransitionResponse(results=tuple(mixed_results), degraded=False)`. Add `TransitionResponse` import to test file.
- Tests: normal → `TransitionResponse(degraded=False)`; DB write fail → `degraded=True`; probe fail → skip DB write, results still valid; all existing engine tests AND MCP transition tests pass with unwrapped results

**4.3 — `complete_phase()` fallback (I13)**
- File: `workflow_engine/engine.py`
- Depends on: 1.2 (health probe), 2.2 (write fallback), 4.1 (get_state)
- Add probe → `wrote_to_db` flag pattern → secondary defense → `_write_meta_json_fallback`
- Read-back failure after successful DB write → derive state from params (no .meta.json write). Note: `update_workflow_phase` is a plain SQL UPDATE with no triggers or side effects — a successful `update_workflow_phase` call guarantees the row is updated, so deriving state from params after a read-back failure is safe.
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
- Add `import sqlite3` for type-specific catches. This is a third-layer defense: (1) engine health probe, (2) engine try/except, (3) MCP handler catch. If the engine has a bug and misses a catch path, the MCP handler provides a structured error instead of an opaque "Internal error" string. Note: this catch is additive — no existing tests currently pass `sqlite3.Error` through the engine layer, so adding `except sqlite3.Error` introduces no behavioral change for passing tests.
- Pre-step grep: `grep -n 'startswith\|"Error:\|Internal error' plugins/iflow/mcp/test_workflow_state_server.py` to enumerate all string-format assertions before beginning migration.
- Tests: update existing error-path assertions to check JSON structure; verify all error types. Specific migrations:
  - `test_not_found` (line ~144): update from plain string to structured JSON with `error_type: "feature_not_found"`
  - `test_get_phase_none_state_returns_not_found` (line ~765-779): update from plain string to structured JSON with `error_type: "feature_not_found"`
  - Line ~150 (`result.startswith('Internal error: ZeroDivisionError:')` in TestProcessGetPhase): update to assert structured JSON with `error_type: "internal"`
  - Line ~635 (`result.startswith('Error:')` in TestProcessCompletePhase): update to assert structured JSON with `error_type: "feature_not_found"`
  - Note: lines ~171/740 assertions on `data['allowed']` top-level key are handled by 5.2 Sub-step B (cross-reference — not a 5.1 concern)
  - **TestErrorClassification block (~lines 791-845):** Lines ~809, ~826, ~845 assert `startswith('Internal error:')` for ValueError paths → update to structured JSON with `error_type: "internal"`. Lines ~619, ~635 assert `startswith('Error:')` for user-facing errors → update to structured JSON with `error_type: "invalid_transition"` or `"feature_not_found"`. Line ~516 in TestAdversarial is a catch-all accepting either prefix → update to accept structured JSON.
  - **Full scope:** The pre-step grep is expected to surface ~17 assertion sites (6 named above + TestErrorClassification block ~5 + remaining `_engine is None` guards 6). If grep returns a different count, audit the difference before proceeding — do not assume unlisted sites are safe to skip. All hits must be migrated to structured JSON format. The specific migrations above cover the non-obvious cases; remaining sites follow the same pattern (prefix string → structured JSON with appropriate `error_type`).

**5.2 — MCP degradation signal (C7 / I10)**
- File: `mcp/workflow_state_server.py`
- Depends on: 4.2 (TransitionResponse + MCP handler already updated), 5.1 (structured errors)
- Note: `TransitionResponse` import and `_process_transition_phase` unwrap already done in 4.2. This step adds serialization changes and the remaining handler updates.
- **Sub-step A — Serialization update:** Update `_serialize_state` to include `degraded = (state.source == "meta_json_fallback")`; migrate `TestSerializeState` and `TestAdversarial` exact key-set assertions to add `degraded` to expected keys
- **Sub-step B — Transition response shape:** Update `_process_transition_phase` response shape — per design I14, response drops `allowed` key (uses `results` from `TransitionResponse`), adds `degraded` field. **Consumer audit (two greps):** (A) `grep -rn '"allowed"\|data\[.allowed.\]' plugins/iflow/skills/ plugins/iflow/commands/ plugins/iflow/hooks/ plugins/iflow/agents/ plugins/iflow/mcp/` — classify grep hits: (1) hooks/ Python files are attribute accesses on `TransitionResult` dataclass fields (`r.allowed`), not MCP JSON key accesses — no changes needed; (2) SKILL.md files (e.g., `skills/workflow-state/SKILL.md`) use `{ allowed: false }` as pseudocode documentation, not MCP JSON consumers — no changes needed; (3) only grep hits in test files parsing JSON responses (e.g., `data["allowed"]`) require updates. (B) `grep -rn 'transition_phase(' plugins/iflow/ --include='*.py' | grep -v test_` — enumerate all non-test Python call sites of `transition_phase()`. Expected hits: engine.py definition (no change), workflow_state_server.py handler (already updated in 4.2). If any other non-test Python file calls `transition_phase()`, it must be updated to unwrap `TransitionResponse`. Update `_process_complete_phase`, `_process_list_*` for degradation field.
- **Existing MCP test migration (ATOMIC with serialization changes):**
  - `TestSerializeState` and `TestAdversarial` exact key-set assertions must add `degraded` to expected keys
  - `test_transition_result_json_has_exact_key_set` (line ~638-653): expected key set changes from `{"allowed", "results", "transitioned"}` to `{"transitioned", "results", "degraded"}`
  - `test_success` in TestProcessTransitionPhase (line ~159-171): asserts `data["allowed"] is True` — update to match new response shape (no `allowed` key)
  - Transition response shape tests (assertions on `data['allowed']`) must be updated per I14 — replace `allowed` with new response shape
  - `test_not_found` (line ~144): already migrated to structured JSON in 5.1 — verify still passes
  - `test_get_phase_none_state_returns_not_found` (line ~765-779): already migrated in 5.1 — verify still passes
  - Note: `test_transitioned_uses_all_not_any` monkeypatch already migrated to `TransitionResponse` in 4.2
  - Grep: `grep -n "allowed\|key.*set\|keys()\|Feature not found" test_workflow_state_server.py` to enumerate all affected assertions
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
11. `transition_phase()` atomic return type change (4.2) — sub-ordered steps:
    **Commit boundary:** Sub-steps b through e are a single atomic commit — do not commit after 11b alone. The test suite will be RED after 11b and must stay unstaged until 11e is complete and all engine + MCP handler tests are GREEN.
    a. Write new fallback tests (RED) — probe fail → `degraded=True`, DB write fail → `degraded=True`
    b. Change `transition_phase()` return type: wrap `results` in `TransitionResponse(results=tuple(results), degraded=False)` — all existing engine tests now FAIL
    c. Migrate ~15 engine test call sites to unwrap `.results` (GREEN) — 13 standard assigning sites add `.results`, 1 special site (line ~777) reassigns `transition_results = response.results`; 2 `pytest.raises` + 1 fire-and-forget unchanged
    d. Update MCP handler `_process_transition_phase` to unwrap `TransitionResponse.results` — prevents iterating dataclass fields
    e. Migrate `test_transitioned_uses_all_not_any` monkeypatch to return `TransitionResponse(results=tuple(mixed_results), degraded=False)` + add import
    f. Implement degraded-path logic (health probe, DB write guard) — new fallback tests now GREEN
    g. Run full suite: `grep -n 'transition_phase\|\.allowed' test_engine.py test_workflow_state_server.py` to verify no unmigrated sites
12. Write `complete_phase()` tests → add wrote_to_db pattern + fallback (4.3)
13. Write `list_by_phase()` fallback tests → add probe + scanner (4.4)
14. Write `list_by_status()` fallback tests → add probe + scanner (4.5)
15. Write structured error tests → update `_process_*` functions (5.1)
16. Write degradation signal tests (5.2) — sub-ordered per 5.2 sub-steps:
    a. (Sub-step A) Write `_serialize_state` degraded-field tests → implement; migrate `TestSerializeState`/`TestAdversarial` key-set assertions to add `degraded`
    b. (Sub-step B) Write transition response shape tests → update `_process_transition_phase` response shape (drop `allowed`, add `degraded`); migrate `test_transition_result_json_has_exact_key_set` and `test_success`; update `_process_complete_phase`/`_process_list_*` for degradation field; run consumer audit grep
    Note: `_process_transition_phase` unwrap and monkeypatch migration already done in step 11.
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

2. **Return type change (4.2):** `transition_phase()` return type changes from `list[TransitionResult]` to `TransitionResponse`. All callers must be updated atomically — engine tests (~17 call sites), MCP handler (`_process_transition_phase`), and MCP test (`test_transitioned_uses_all_not_any`). Run grep for `transition_phase` call sites across BOTH test files before committing.

3. **Error format breaking change (5.1):** Error-path tests in `test_workflow_state_server.py` must be updated before/with the implementation. Existing assertions like `assert "Error:" in result` will break. Update tests first (RED), then implementation (GREEN).

4. **Import ordering (1.2, 1.4, 2.2, 3.1, 4.1-4.5):** Five new imports added to `engine.py`: `sqlite3`, `sys`, `tempfile`, `glob`, `from datetime import datetime, timezone`. All must be top-level (per design — no deferred imports inside function bodies). `sys` is needed for `print(..., file=sys.stderr)` logging in Phase 4 fallback paths. `datetime` is needed by `_iso_now()` (1.4).
