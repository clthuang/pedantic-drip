# Feature 113 — Tasks (iter 2, TDD-ordered)

Discrete 5-15 min tasks paired Tests+X (RED) → Impl+X (GREEN) per NFR-5. Each task has explicit acceptance criteria (binary pass/fail).

**Legend:**
- `[P]` = parallel-safe with siblings (no shared file)
- `[S:<file>]` = serializes on the named file (no concurrent dispatch)
- `[B]` = blocker for downstream PIs
- `→ AC-N` = acceptance criterion satisfied
- `RED` = test must be failing before this task's commit
- `GREEN` = implementation must make the prior RED test pass

---

## PI-0 — Baseline capture (NFR-2)

### T0.1 — Create validation artifacts directory
```bash
mkdir -p agent_sandbox/$(date +%Y-%m-%d)/113-validation
```
**Done:** Directory exists.
**Time:** 1 min.

### T0.2 — Capture pre-implementation pytest baseline
```bash
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/{hooks/lib,mcp} --tb=line > agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log 2>&1 || true
```
Record `BASELINE_FAIL_COUNT=$(grep -c '^FAILED' agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log)`.
**Done:** baseline.log exists; FAILED count recorded in a notes file.
**Time:** 5-10 min (pytest run).
**Dependencies:** T0.1.

---

## PI-1 — Validation artifacts (FR-1 + FR-2)

### T1a.1 — Tests+1 RED: scaffold + 5 failing tests
- Create `plugins/pd/hooks/lib/qa_gate/__init__.py` (empty `frozenset()` for STATUS_ENUM placeholder)
- Create `plugins/pd/hooks/lib/qa_gate/emitter.py` stub: `def emit_qa_gate(*args, **kwargs): raise NotImplementedError`
- Create `plugins/pd/hooks/lib/qa_gate/test_emitter.py` with 5 test functions:
  - `test_emit_qa_gate_rejects_invalid_status`
  - `test_emit_qa_gate_requires_id_status_evidence`
  - `test_emit_qa_gate_rejects_evidence_over_500_chars`
  - `test_emit_qa_gate_rejects_conditional_skipped_with_empty_condition`
  - `test_emit_qa_gate_head_sha_idempotent`
**Done (RED):** `pytest plugins/pd/hooks/lib/qa_gate/test_emitter.py -v` → all 5 fail with NotImplementedError.
**Time:** 15 min.

### T1a.2 [B] — Impl+1 GREEN: emitter + .gitignore removal
- Populate `STATUS_ENUM = frozenset({"passed", "deferred", "n_a", "conditional_skipped"})`
- Implement `emit_qa_gate(...)` per design I1 (validation + idempotency + JSON write)
- Remove `.gitignore:63` line `docs/features/**/.qa-gate.json`
**Done (GREEN):** `pytest plugins/pd/hooks/lib/qa_gate/test_emitter.py -v` → all 5 pass. `grep -n 'docs/features/\*\*/.qa-gate.json' .gitignore` → 0 matches. → AC-1 partial
**Time:** 20 min.
**Dependencies:** T1a.1.

### T1a.3 — Commit PI-1a
```bash
git add plugins/pd/hooks/lib/qa_gate/ .gitignore
git commit -m "feat(113/FR-1): qa_gate/emitter.py canonical schema + remove gitignore"
```
**Time:** 2 min.

### T1b.1 [P] — Tests+2 RED: bash-version-capture validation
- In `plugins/pd/hooks/tests/test-hooks.sh` (or as a Python pytest in a suitable location), add a sub-test asserting:
  - File `plugins/pd/hooks/tests/bash-version-capture.sh` exists and is executable
  - Running it produces 3 lines matching `^=== `
**Done (RED):** Test fails — script doesn't exist yet.
**Time:** 5 min.

### T1b.2 — Impl+2 GREEN: bash-version-capture.sh
- Create script per design I10 with `trap '' PIPE`, `set -u`, `{ ...; } 2>/dev/null || true` wrappers
- `chmod +x plugins/pd/hooks/tests/bash-version-capture.sh`
**Done (GREEN):** `bash plugins/pd/hooks/tests/bash-version-capture.sh > /tmp/bv.log 2>&1`; `grep -c '^=== ' /tmp/bv.log` returns 3. → AC-2
**Time:** 8 min.
**Dependencies:** T1b.1.

### T1b.3 — Commit PI-1b
```bash
git add plugins/pd/hooks/tests/bash-version-capture.sh plugins/pd/hooks/tests/test-hooks.sh
git commit -m "feat(113/FR-2): bash-version-capture.sh AC-12 evidence helper"
```
**Time:** 2 min.

---

## PI-2 — Defensive fixes (FR-3.0, FR-7, FR-8, FR-9)

### T2a.1 [S:test_workflow_state_server.py] — Tests+3.0 RED
In `plugins/pd/mcp/test_workflow_state_server.py::TestListFeaturesByDefaultSingleWorkspace`, add `test_list_features_handler_empty_project_id_treated_as_default`. Set `_workspace_uuid` to a known value; call `list_features_by_phase(phase="design", project_id="")`; assert results scoped to that workspace.
**Done (RED):** Test fails — current helper falls into JOIN-resolve and returns None.
**Time:** 10 min.

### T2a.2 — Impl+3.0 GREEN
In `workflow_state_server.py:_resolve_list_handler_workspace_filter` top, BEFORE `== "*"` check, add `if project_id == "": project_id = None`. Add comment for `_db is None` retain branch per design I5.
**Done (GREEN):** T2a.1's test passes. → AC-3 partial (1 of 4 new)
**Time:** 5 min.
**Dependencies:** T2a.1.

### T2a.3 — Commit PI-2a
```bash
git add plugins/pd/mcp/workflow_state_server.py plugins/pd/mcp/test_workflow_state_server.py
git commit -m "feat(113/FR-3.0): empty-string project_id normalization at workspace_filter entry"
```
**Time:** 2 min.

### T2b.1 [S:test_workflow_state_server.py] — Tests+7 RED
In `test_workflow_state_server.py`, add 2 tests:
- `test_filter_states_db_error_returns_error_json` (mock `_db.get_entity` → `sqlite3.OperationalError`; assert `_make_error` JSON)
- `test_filter_states_unexpected_error_propagates` (mock → `RuntimeError`; assert `pytest.raises(RuntimeError)`)
**Done (RED):** Both fail today (bare-except swallows RuntimeError; OperationalError path returns unfiltered JSON).
**Time:** 12 min.
**Dependencies:** T2a.3 (serializes on test_workflow_state_server.py).

### T2b.2 — Impl+7 GREEN
Replace `except (json.JSONDecodeError, Exception):` at workflow_state_server.py:1614-1615 with split clauses per design I6.
**Done (GREEN):** T2b.1's tests pass. `grep -nE 'except.*Exception' plugins/pd/mcp/workflow_state_server.py | awk -F: '$2 >= 1614 && $2 <= 1620'` returns 0. → AC-7
**Time:** 5 min.
**Dependencies:** T2b.1.

### T2b.3 — Commit PI-2b
```bash
git add plugins/pd/mcp/workflow_state_server.py plugins/pd/mcp/test_workflow_state_server.py
git commit -m "feat(113/FR-7): narrow _filter_states_by_workspace except clause"
```
**Time:** 2 min.

### T2c.1 [P] — Tests+8 RED
In `plugins/pd/hooks/lib/entity_registry/test_server_helpers.py`, add:
- `test_register_entity_parent_resolution_db_error_orphans_with_warning` — mock `db.get_entity` → `sqlite3.OperationalError`; use `capsys`; assert entity registers with `parent_uuid=None` AND stderr contains "server_helpers: parent resolution failed"
- `test_register_entity_parent_resolution_unexpected_error_propagates` — mock → `RuntimeError`; assert propagation
**Done (RED):** Both fail today (bare-except swallows both).
**Time:** 12 min.

### T2c.2 — Impl+8 GREEN: add import sys + narrow except
- Add `import sys` to top of `server_helpers.py` (currently absent — verified at iter 2; `sqlite3` already imported at line 10)
- Replace `except Exception:` at lines 248-255 with `except sqlite3.OperationalError as exc:` block per design I6
**Done (GREEN):** T2c.1's tests pass. → AC-8
**Time:** 8 min.
**Dependencies:** T2c.1.

### T2c.3 — Commit PI-2c
```bash
git add plugins/pd/hooks/lib/entity_registry/server_helpers.py plugins/pd/hooks/lib/entity_registry/test_server_helpers.py
git commit -m "feat(113/FR-8): narrow server_helpers parent resolution except + import sys"
```
**Time:** 2 min.

### T2d.1 [P] — Tests+9 RED
In `plugins/pd/hooks/lib/entity_registry/test_entity_server.py` (existing file with sys.path injection at lines 12-14 importing MCP entity_server), add `test_create_key_result_missing_parent_raises`:
- Bootstrap DB without parent objective
- Call `_process_create_key_result(...)`
- Assert `pytest.raises(ValueError, match="Parent entity not found")` triggers
**Done (RED):** Test fails — current ternary at line 450 silently sets parent_uuid=None.
**Time:** 10 min.

### T2d.2 — Impl+9 GREEN
Per design I7: in entity_server.py:449-450, add `if parent_entity is None: raise ValueError(f"Parent entity not found: {parent_type_id!r}")` BEFORE the assignment; change line 450 to `parent_uuid = parent_entity["uuid"]`.
**Done (GREEN):** T2d.1's test passes. → AC-9
**Time:** 5 min.
**Dependencies:** T2d.1.

### T2d.3 — Commit PI-2d
```bash
git add plugins/pd/mcp/entity_server.py plugins/pd/hooks/lib/entity_registry/test_entity_server.py
git commit -m "feat(113/FR-9): _process_create_key_result missing-parent ValueError"
```
**Time:** 2 min.

---

## PI-3 — Workspace filter ValueError + empty-string boundary (FR-3.2/3.3, FR-6)

### T3a.1 [S:test_workflow_state_server.py] — Tests+3.2 RED
In `test_workflow_state_server.py`, add 3 tests:
- `test_list_features_handler_db_none_returns_empty` (FR-3.1 pin)
- `test_list_features_by_phase_invalid_legacy_hex_returns_error` (calls with `project_id="ffffffffffff"`; asserts `error_type="invalid_project_id"`)
- `test_list_features_by_status_invalid_legacy_hex_returns_error` (same shape, list_features_by_status)
**Done (RED):** All 3 fail today (helper returns None silently; no error JSON).
**Time:** 15 min.
**Dependencies:** T2b.3 (serializes on test_workflow_state_server.py).

### T3a.2 — Impl+3.2 GREEN
- Modify `_resolve_list_handler_workspace_filter` to raise `ValueError(f"No workspace found for project_id={project_id!r}")` on no-matching-row
- Wrap `list_features_by_phase` at workflow_state_server.py:1619 and `list_features_by_status` at :1643 with `try/except ValueError → _make_error(error_type="invalid_project_id", ...)`
**Done (GREEN):** T3a.1's 3 tests pass. Total with T2a.2's test = 4 new from FR-3.3. → AC-3 (6 tests total)
**Time:** 10 min.
**Dependencies:** T3a.1.

### T3a.3 — Commit PI-3a
```bash
git add plugins/pd/mcp/workflow_state_server.py plugins/pd/mcp/test_workflow_state_server.py
git commit -m "feat(113/FR-3.2): invalid project_id raises; handlers return _make_error JSON"
```
**Time:** 2 min.

### T3b.1 [S:test_workflow_state_server.py] — Tests+6 RED
In `test_workflow_state_server.py`, add parametrized `test_workspace_uuid_empty_string_normalized_to_none`:
- Param 1 (`init_feature_state`): exercises line 1280
- Param 2 (`transition_phase`): exercises line 657

Each: set `wss._workspace_uuid = ""`; call entry-point with valid args; assert resolved entity/state has `workspace_uuid == _UNKNOWN_WORKSPACE_UUID`.
**Done (RED, expected PASS today):** Both sub-tests pass today (current code is correct with `or None`). RED-state instead asserted via PI-3.MUT below.
**Time:** 15 min.
**Dependencies:** T3a.3.

### T3b.2 — PI-3.MUT: Mutation-pin observability gate
**Procedure (manual, MUST execute before T3b.3 commit):**
1. `cp plugins/pd/mcp/workflow_state_server.py /tmp/wss.bak` (backup)
2. Edit line 1280: change `workspace_uuid=_workspace_uuid or None` → `workspace_uuid=_workspace_uuid`
3. Run `pytest plugins/pd/mcp/test_workflow_state_server.py -k 'workspace_uuid_empty_string_normalized_to_none and init_feature_state' -v`
4. Capture: PASS or FAIL with observable assertion error?
5. Restore: `cp /tmp/wss.bak plugins/pd/mcp/workflow_state_server.py`
6. Repeat steps 2-5 for line 657 (transition_phase sub-test)

**Gate condition:**
- If both mutations cause observable test failures → AC-6 mutation pins are valid; proceed
- If either mutation results in silent test PASS → that mutation pin is vacuous; halt and amend the AC-6 spec text to describe the actual fail mode (or remove the vacuous pin from the spec) in the same Impl+6 commit
**Done:** Captured failure modes for both lines; documented in T3b.3 commit message body.
**Time:** 10 min.
**Dependencies:** T3b.1.

### T3b.3 — Impl+6 GREEN: add FR-6.2 inline doc comments
- Add `# Empty-string == unset == None at db.* kwarg boundary; downstream defaults to project_id="__unknown__" → _UNKNOWN_WORKSPACE_UUID.` at workflow_state_server.py:657 AND at line 1280
- Verify both T3b.1 sub-tests still pass (Impl+6 is documentation only)
**Done (GREEN):** Both sub-tests pass; PI-3.MUT outcome documented in commit body. → AC-6
**Time:** 5 min.
**Dependencies:** T3b.2.

### T3b.4 — Commit PI-3b
```bash
git add plugins/pd/mcp/workflow_state_server.py plugins/pd/mcp/test_workflow_state_server.py
git commit -m "feat(113/FR-6): empty-string workspace_uuid normalization tests + doc comments

PI-3.MUT verification: removing 'or None' at line 1280 fails init_feature_state sub-test
with <captured error mode>; removing at line 657 fails transition_phase sub-test with
<captured error mode>. Both mutation pins observable."
```
**Time:** 2 min.

---

## PI-4 — entity_status conditional-kwarg sweep (FR-10)

### T4.1 — Tests+10 RED: parametrized no-DeprecationWarning test
In `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`, add parametrized `test_sync_entity_statuses_no_deprecation_warning_on_happy_path`. 4 sub-tests, one per fixed site:
- Site 47 (`_sync_meta_json_entities` archive)
- Site 72 (`_sync_meta_json_entities` status-change)
- Site 189 (`_sync_brainstorm_entities` archive)
- Site 320 (`_sync_backlog_md_entities` status-change)

Each: bootstrap real workspace_uuid via `bootstrap_test_workspace()`; trigger site-specific state; call `sync_entity_statuses(db, ..., workspace_uuid=ws_a)`; wrap in `warnings.catch_warnings()` + `simplefilter('error', DeprecationWarning)` per design R6 (scoped to the call, NOT module-level); assert no DeprecationWarning fires.

If catch_warnings filter-bleeds: switch implementation to `recwarn` fixture per design R6 fallback.
**Done (RED):** All 4 sub-tests fail today — DeprecationWarning fires at each site per FR-10 pre-state.
**Time:** 25 min.

### T4.2 — Impl+10 GREEN: apply conditional pattern at 4 sites
Modify `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py` at lines 47, 72, 189, 320:
Change `project_id=project_id, workspace_uuid=workspace_uuid` → `project_id=project_id if workspace_uuid is None else None, workspace_uuid=workspace_uuid`.
**Done (GREEN):** T4.1's 4 sub-tests pass. `grep -nE 'project_id=project_id if workspace_uuid is None' plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py | wc -l` returns 6 (4 new + 2 existing at lines 175, 316). → AC-10
**Time:** 8 min.
**Dependencies:** T4.1.

### T4.3 — Commit PI-4
```bash
git add plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py
git commit -m "feat(113/FR-10): entity_status conditional-kwarg pattern at 4 sites"
```
**Time:** 2 min.

---

## PI-5 — FR-4.1 anchor

### T5.1 [B] — Tests+4.1 RED: direct database-layer tests
In `plugins/pd/hooks/lib/entity_registry/test_database.py`, add 2 tests:
- `test_update_workflow_phase_workspace_uuid_mismatch_raises_value_error`:
  - Bootstrap workflow_phases row with `workspace_uuid=ws_a` (via `bootstrap_test_workspace()`)
  - Call `db.update_workflow_phase(type_id, workspace_uuid=ws_b, workflow_phase='design')`
  - Assert `pytest.raises(ValueError, match="workspace_uuid mismatch")`
- `test_update_workflow_phase_does_not_mutate_workspace_uuid_column`:
  - Bootstrap workflow_phases row with workspace_uuid=ws_a
  - Pre-update SELECT: capture workspace_uuid
  - Call `db.update_workflow_phase(type_id, workspace_uuid=ws_a, workflow_phase='design')`
  - Post-update SELECT: assert workspace_uuid byte-identical
**Done (RED):** Both fail today — `db.update_workflow_phase` doesn't accept `workspace_uuid` kwarg (TypeError).
**Time:** 15 min.

### T5.2 [B] — Impl+4.1 GREEN: extend signature + mismatch check
Modify `plugins/pd/hooks/lib/entity_registry/database.py:4866-4944` per design I2:
- Add `workspace_uuid: str | None = None` to signature
- When non-None: `SELECT workspace_uuid FROM workflow_phases WHERE type_id = ?`; raise `ValueError(f"workspace_uuid mismatch for {type_id}: stored={existing!r}, provided={workspace_uuid!r}")` on mismatch
- Do NOT add workspace_uuid to UPDATE SET clause
**Done (GREEN):** T5.1's 2 tests pass. Existing tests still pass. → AC-4 partial (2 of 5)
**Time:** 20 min.
**Dependencies:** T5.1.

### T5.3 — Commit PI-5 (with spec amendment)
```bash
git add plugins/pd/hooks/lib/entity_registry/database.py plugins/pd/hooks/lib/entity_registry/test_database.py docs/features/113-feature-112-qa-followups/spec.md
git commit -m "feat(113/FR-4.1): update_workflow_phase workspace_uuid read-side assertion (+spec AC-4: 5 tests)"
```
Note: spec.md amendment (FR-4.3 + AC-4 5-test count) lands in this commit per plan-reviewer iter-1 B2.
**Time:** 3 min.

---

## PI-6 — Engine + lifecycle forwarding

### T6a.1 — Tests+4.2 RED: engine-level mismatch tests
In `test_engine.py`, add 3 tests:
- `test_transition_phase_workspace_uuid_mismatch_raises`:
  - Bootstrap 2 workspaces via `bootstrap_test_workspace()`
  - Create workflow_phases row scoped to ws_a
  - `with pytest.raises(ValueError, match="workspace_uuid mismatch"): engine.transition_phase(type_id, "design", workspace_uuid=ws_b)`
- `test_complete_phase_non_terminal_workspace_uuid_pinned` (same shape, non-terminal)
- `test_complete_phase_terminal_workspace_uuid_pinned` (same shape, `phase == "finish"`)
**Done (RED):** All 3 fail today — engine doesn't forward workspace_uuid, mismatch never checked.
**Time:** 20 min.
**Dependencies:** T5.3.

### T6a.2 — PI-6a.MUT: engine except-clause non-swallow verification
**Procedure (manual, MUST execute before T6a.4 commit):**
1. `cp plugins/pd/hooks/lib/workflow_engine/engine.py /tmp/engine.bak`
2. Temporarily widen except at lines 105 + 178: `except sqlite3.Error:` → `except (sqlite3.Error, ValueError):`
3. Run `pytest plugins/pd/hooks/lib/workflow_engine/test_engine.py -k 'workspace_uuid_mismatch or workspace_uuid_pinned' -v`
4. Confirm all 3 tests FAIL (ValueError swallowed)
5. Restore: `cp /tmp/engine.bak plugins/pd/hooks/lib/workflow_engine/engine.py`
6. Re-run tests — confirm all 3 PASS

**Gate condition:** Tests fail when except is widened to catch ValueError; pass when except is narrow.
**Done:** Procedure outcomes captured for commit body.
**Time:** 8 min.
**Dependencies:** T6a.1.

### T6a.3 — Impl+4.2 GREEN: forward workspace_uuid at engine.py
Modify `plugins/pd/hooks/lib/workflow_engine/engine.py`:
- Line 100-103 (transition_phase): add `workspace_uuid=workspace_uuid` to `db.update_workflow_phase` call
- Line 166-170 (complete_phase non-terminal): same
**Done (GREEN):** T6a.1's 3 tests pass. → AC-4 partial (3 more, 5 total)
**Time:** 5 min.
**Dependencies:** T6a.1, T6a.2 (mutation gate).

### T6a.4 — Commit PI-6a
```bash
git add plugins/pd/hooks/lib/workflow_engine/engine.py plugins/pd/hooks/lib/workflow_engine/test_engine.py
git commit -m "feat(113/FR-4.2): engine.py workspace_uuid forwarding + mismatch tests

PI-6a.MUT verification: widening except sqlite3.Error → except (sqlite3.Error, ValueError)
fails all 3 mismatch tests as expected. Narrow except keeps tests passing."
```
**Time:** 3 min.

### T6b.1 — Tests+5 RED: transition_entity_phase symmetric forwarding test
In `plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py`, add `test_transition_entity_phase_workspace_uuid_consistent`:
- Bootstrap 2 workspaces
- Call `transition_entity_phase(db, 'brainstorm:foo', 'promoted', workspace_uuid=ws_a)`
- Assert: (1) ws_a entity status updated, (2) ws_a workflow_phase row updated, (3) ws_b parallel row UNCHANGED, (4) calling with `workspace_uuid=ws_b` against ws_a row raises FR-4.1 ValueError
**Done (RED):** Test fails today — entity_lifecycle.py:193 doesn't forward workspace_uuid.
**Time:** 18 min.
**Dependencies:** T5.3.

### T6b.2 — Impl+5 GREEN: entity_lifecycle.py kwarg dict extension
Modify `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py:185-193` per design I4 (unconditional):
Add `"workspace_uuid": workspace_uuid` to the `update_kwargs` dict.
**Done (GREEN):** T6b.1's test passes. → AC-5
**Time:** 3 min.
**Dependencies:** T6b.1.

### T6b.3 — Commit PI-6b
```bash
git add plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py
git commit -m "feat(113/FR-5): transition_entity_phase symmetric workspace_uuid forwarding"
```
**Time:** 2 min.

---

## PI-7 — Reconcile workspace_uuid threading

### T7a.1 — Tests+11.1/11.2 RED: internal-forwarding + scope-scan tests
In `plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py`, add 2 tests:
- `test_apply_workflow_reconciliation_forwards_workspace_uuid_to_update_workflow_phase_meta_ahead`:
  - Bootstrap meta_json_ahead row
  - Mock `db.update_workflow_phase`
  - Call `apply_workflow_reconciliation(engine, db, artifacts_root, workspace_uuid=ws_a)`
  - Assert mock received `workspace_uuid=ws_a` kwarg
- `test_apply_workflow_reconciliation_forwards_workspace_uuid_to_update_workflow_phase_kanban_drift`:
  - Same shape, kanban-only-drift row

In `plugins/pd/hooks/lib/entity_registry/test_frontmatter_sync.py`, add 2 tests:
- `test_scan_all_scopes_to_workspace`:
  - Bootstrap 2 workspaces with features
  - Call `scan_all(db, artifacts_root, workspace_uuid=ws_a)`
  - Assert reports cover ONLY ws_a's features
- `test_scan_all_default_unscoped_returns_all_workspace_features` (NFR-3 regression pin):
  - Same fixture; call `scan_all(db, artifacts_root)` (no kwarg)
  - Assert reports cover BOTH workspaces
**Done (RED):** All 4 fail today — `apply_workflow_reconciliation` and `scan_all` don't accept workspace_uuid (TypeError).
**Time:** 25 min.
**Dependencies:** T5.3.

### T7a.2 — Impl+11.1 GREEN: extend apply_workflow_reconciliation
Modify `plugins/pd/hooks/lib/workflow_engine/reconciliation.py:756`:
- Add `workspace_uuid: str | None = None` kwarg to signature
- At lines 367-374: merge into kwargs dict per design I9 (`kwargs["workspace_uuid"] = workspace_uuid` BEFORE `db.update_workflow_phase(feature_type_id, **kwargs)`)
- At line 462: add `workspace_uuid=workspace_uuid` to single-kwarg call
**Done:** T7a.1's reconciliation tests (2 of 4) pass.
**Time:** 10 min.
**Dependencies:** T7a.1.

### T7a.3 — Impl+11.2 GREEN: extend scan_all
Modify `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py:543`:
- Add `workspace_uuid: str | None = None` kwarg to signature
- At line 570: forward to `db.list_entities(entity_type="feature", workspace_uuid=workspace_uuid)`
**Done:** T7a.1's frontmatter_sync tests (2 of 4) pass. All 4 RED tests now GREEN.
**Time:** 5 min.
**Dependencies:** T7a.1.

### T7a.4 — Commit PI-7a
```bash
git add plugins/pd/hooks/lib/workflow_engine/reconciliation.py plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py plugins/pd/hooks/lib/entity_registry/test_frontmatter_sync.py
git commit -m "feat(113/FR-11.1-2): apply_workflow_reconciliation + scan_all workspace_uuid kwargs"
```
**Time:** 2 min.

### T7b.1 [S:test_workflow_state_server.py] — Tests+11.3/4/5 RED: MCP boundary tests
In `test_workflow_state_server.py`, add 3 boundary tests:
- `test_reconcile_apply_forwards_workspace_uuid`: set `wss._workspace_uuid = ws_a`; mock `apply_workflow_reconciliation`; call async `reconcile_apply()`; assert mock received `workspace_uuid=ws_a`
- `test_reconcile_frontmatter_forwards_workspace_uuid`: same shape; mock `scan_all`
- `test_reconcile_status_forwards_workspace_uuid`: same shape
**Done (RED):** All 3 fail today — MCP handlers don't forward `_workspace_uuid`.
**Time:** 18 min.
**Dependencies:** T7a.4, T3b.4 (serializes on test_workflow_state_server.py).

### T7b.2 — Impl+11.3/4/5 GREEN: MCP handler forwarding
Modify `plugins/pd/mcp/workflow_state_server.py`:
- Line 1189 `_process_reconcile_apply`: accept and forward `workspace_uuid` to `apply_workflow_reconciliation`
- Line 1223 `_process_reconcile_frontmatter`: accept and forward to `scan_all`
- Line 1366 `_process_reconcile_status`: accept and forward to `scan_all` at line 1381
- Lines 1678, 1694, 1705 (async handlers): pass `workspace_uuid=_workspace_uuid or None`
**Done (GREEN):** T7b.1's 3 tests pass. Total 7 tests for AC-11. → AC-11
**Time:** 12 min.
**Dependencies:** T7b.1.

### T7b.3 — Commit PI-7b
```bash
git add plugins/pd/mcp/workflow_state_server.py plugins/pd/mcp/test_workflow_state_server.py
git commit -m "feat(113/FR-11.3-5): reconcile_* MCP handlers workspace_uuid forwarding + boundary tests"
```
**Time:** 2 min.

---

## PI-8 — Regression + dogfood + cleanup

### T8.1 — Final pytest run
```bash
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/{hooks/lib,mcp} --tb=line > agent_sandbox/$(date +%Y-%m-%d)/113-validation/final.log 2>&1 || true
```
**Done:** final.log exists.
**Time:** 5-10 min.

### T8.2 — AC-12 baseline diff
```bash
diff <(grep '^FAILED' agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log | sort) \
     <(grep '^FAILED' agent_sandbox/$(date +%Y-%m-%d)/113-validation/final.log | sort)
```
**Done:** Output empty (no net-new failures). → AC-12
**Time:** 2 min.

### T8.3 — CHANGELOG update
Add `[Unreleased]` entries, one bullet per FR (FR-1 through FR-11). Note `.gitignore:63` removal under "Removed".
**Done:** All 12 entries present.
**Time:** 10 min.

### T8.4 — Pre-finish sanity check
- `grep -nE 'docs/features/\*\*/.qa-gate.json' .gitignore` → 0 matches (FR-1.4 confirmation)
**Done:** Check passes.
**Time:** 1 min.

### T8.5 — Commit PI-8
```bash
git add CHANGELOG.md
git commit -m "docs(113): CHANGELOG entries for feature 112 QA-followup fixes

AC-12 baseline diff: empty (no net-new failures).
Baseline FAIL count: $BASELINE_FAIL_COUNT; final FAIL count: $FINAL_FAIL_COUNT.
"
```
**Time:** 2 min.

### T8.6 — AC-13 dogfood verification (runs at /pd:finish-feature)
After `/pd:finish-feature` Step 5b emits the gate JSON, verify:
```python
python -c "
import json, subprocess
d = json.load(open('docs/features/113-feature-112-qa-followups/.qa-gate.json'))
head = subprocess.check_output(['git','rev-parse','HEAD']).decode().strip()
assert set(d.keys()) >= {'feature','head_sha','gate_run_at','ac_results','decision','reviewers'}, d.keys()
assert d['head_sha'] == head, (d['head_sha'], head)
STATUS_ENUM = {'passed', 'deferred', 'n_a', 'conditional_skipped'}
for r in d['ac_results']:
    assert r['status'] in STATUS_ENUM, r
print('AC-13 OK')
"
```
**Done:** Prints `AC-13 OK`. → AC-13
**Time:** 5 min.
**Dependencies:** T8.5.

---

## Total Effort Estimate

| PI | # Tasks | Est. Duration |
|----|---------|----------------|
| PI-0 | 2 | 10 min |
| PI-1 | 6 | 50 min |
| PI-2 | 11 | 70 min |
| PI-3 | 7 | 60 min |
| PI-4 | 3 | 35 min |
| PI-5 | 3 | 40 min |
| PI-6 | 7 | 65 min |
| PI-7 | 7 | 75 min |
| PI-8 | 6 | 35 min |
| **Total** | **52** | **~7 hours** |

## Test Count Reconciliation

Per spec Verification Plan Summary (canonical source):
- AC-1: 5 tests (in qa_gate/test_emitter.py)
- AC-2: 1 script execution
- AC-3: 4 new tests
- AC-4: 5 new tests
- AC-5: 1 new test
- AC-6: 2 parametrized sub-tests
- AC-7: 2 new tests
- AC-8: 2 new tests
- AC-9: 1 new test
- AC-10: 4 parametrized sub-tests
- AC-11: 7 new tests
- AC-12: regression baseline diff (no new test)
- AC-13: dogfood verification (Python snippet)

**Total new test functions ≈ 33** (counting parametrized as separate sub-tests). Some collapse to ~17 unique test functions when parametrize is collapsed to 1.

## Cross-References

- Plan: `docs/features/113-feature-112-qa-followups/plan.md`
- Design: `docs/features/113-feature-112-qa-followups/design.md`
- Spec: `docs/features/113-feature-112-qa-followups/spec.md`
