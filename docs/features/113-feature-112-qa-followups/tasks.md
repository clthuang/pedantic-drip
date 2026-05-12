# Feature 113 — Tasks

Discrete 5-15 min tasks ordered by NFR-5 dependency graph. Each task has explicit acceptance criteria (binary pass/fail).

Legend:
- `[P]` = parallel-safe with siblings in the same PI
- `[B]` = blocker for downstream PIs (gating dependency)
- `→ AC-N` = acceptance criterion satisfied by this task

---

## PI-0 — Baseline capture (NFR-2)

### T0.1 — Create validation artifacts directory
```bash
mkdir -p agent_sandbox/$(date +%Y-%m-%d)/113-validation
```
**Done:** Directory exists, `ls -la` returns it.
**Time:** 1 min.

### T0.2 — Capture pre-implementation pytest baseline
Run from project root:
```bash
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/{hooks/lib,mcp} --tb=line > agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log 2>&1 || true
```
**Done:** `baseline.log` file exists; `grep -c '^FAILED' baseline.log` returns a known number (record it).
**Time:** 5-10 min (pytest run).
**Dependencies:** T0.1.

---

## PI-1 — Validation artifacts (FR-1 + FR-2)

### T1.1 [P] — Scaffold `qa_gate/` package
Create:
- `plugins/pd/hooks/lib/qa_gate/__init__.py` with `STATUS_ENUM = frozenset({"passed", "deferred", "n_a", "conditional_skipped"})`
- `plugins/pd/hooks/lib/qa_gate/emitter.py` skeleton (no body yet) per design I1 signature
- `plugins/pd/hooks/lib/qa_gate/test_emitter.py` skeleton (empty test file with imports)

**Done:** `ls plugins/pd/hooks/lib/qa_gate/` shows 3 files; `pytest plugins/pd/hooks/lib/qa_gate/test_emitter.py --collect-only` exits 0.
**Time:** 5 min.

### T1.2 — Write `test_emit_qa_gate_rejects_invalid_status` (TDD red)
In `test_emitter.py`, write test asserting `emit_qa_gate(...)` raises `ValueError` when an entry's status is `"invalid"`.
**Done:** `pytest plugins/pd/hooks/lib/qa_gate/test_emitter.py -v` shows 1 failure (NotImplementedError or similar — TDD red).
**Time:** 10 min.
**Dependencies:** T1.1.

### T1.3 — Implement `emit_qa_gate` per design I1
Body: validate status enum, validate per-entry keys, resolve head_sha if not provided, compute idempotency, write JSON.
**Done:** T1.2's test now passes. → AC-1 partial
**Time:** 15 min.
**Dependencies:** T1.2.

### T1.4 — Add per-entry key validator tests
Add 3 more tests:
- `test_emit_qa_gate_requires_id_status_evidence` (missing required key raises)
- `test_emit_qa_gate_rejects_evidence_over_500_chars`
- `test_emit_qa_gate_rejects_conditional_skipped_with_empty_condition`

**Done:** All 4 tests in `test_emitter.py` pass.
**Time:** 10 min.
**Dependencies:** T1.3.

### T1.5 — Add head_sha idempotency test
Test: calling `emit_qa_gate` twice with same `head_sha` is a no-op (returns same path, doesn't rewrite).
**Done:** Test passes. → AC-1 partial
**Time:** 5 min.
**Dependencies:** T1.3.

### T1.6 [B] — Remove `.gitignore:63` line
Delete the line `docs/features/**/.qa-gate.json` from `.gitignore`.
**Done:** `grep -n 'qa-gate' .gitignore` returns 0 matches for `docs/features/**`. → AC-1 partial; FR-1.4 satisfied
**Time:** 1 min.
**Dependencies:** None.

### T1.7 — Commit PI-1a (qa_gate package)
```bash
git add plugins/pd/hooks/lib/qa_gate/ .gitignore
git commit -m "feat(113/FR-1): qa_gate/emitter.py canonical schema + remove gitignore"
```
**Done:** Commit lands; pre-commit hooks pass.
**Time:** 2 min.
**Dependencies:** T1.4, T1.5, T1.6.

### T1.8 [P] — Create `bash-version-capture.sh` per design I10
Write the script with `trap '' PIPE`, `set -u`, no `set -e`, and `{ ...; } 2>/dev/null || true` wrappers per design.
**Done:** `bash -n plugins/pd/hooks/tests/bash-version-capture.sh` reports no syntax errors; file is `chmod +x`.
**Time:** 5 min.
**Dependencies:** None.

### T1.9 — Test bash-version-capture.sh end-to-end
Run: `bash plugins/pd/hooks/tests/bash-version-capture.sh > /tmp/bv.log 2>&1`
Verify: `grep -c '^=== ' /tmp/bv.log` returns `3`.
**Done:** Exit code matches the embedded test-hooks.sh result; 3-section format confirmed. → AC-2
**Time:** 3 min.
**Dependencies:** T1.8.

### T1.10 — Commit PI-1b (bash-version-capture.sh)
```bash
git add plugins/pd/hooks/tests/bash-version-capture.sh
git commit -m "feat(113/FR-2): bash-version-capture.sh AC-12 evidence helper"
```
**Done:** Commit lands; hook tests still pass.
**Time:** 2 min.
**Dependencies:** T1.9.

---

## PI-2 — Defensive fixes (FR-3.0, FR-7, FR-8, FR-9)

### T2a.1 [P] — Apply FR-3.0 entry-point normalization
At `workflow_state_server.py:_resolve_list_handler_workspace_filter` top (before `== "*"` check), add `if project_id == "": project_id = None`. Add comment for FR-3.1's `_db is None` retain branch.
**Done:** `grep -n 'project_id == ""' plugins/pd/mcp/workflow_state_server.py` returns the new line.
**Time:** 3 min.

### T2a.2 — Add `test_list_features_handler_empty_project_id_treated_as_default`
TDD pass: test fails before T2a.1 applied (if applied via separate branch), but in linear flow it's already applied. Test asserts: setting `_workspace_uuid` to a known value, calling `list_features_by_phase(phase="design", project_id="")`, expects results scoped to that workspace.
**Done:** `pytest -k 'empty_project_id_treated_as_default' -v` → pass. → AC-3 partial
**Time:** 10 min.
**Dependencies:** T2a.1.

### T2a.3 — Commit PI-2a (FR-3.0)
```bash
git add plugins/pd/mcp/workflow_state_server.py plugins/pd/mcp/test_workflow_state_server.py
git commit -m "feat(113/FR-3.0): empty-string project_id normalization at workspace_filter entry"
```
**Time:** 2 min.

### T2b.1 [P] — Narrow `_filter_states_by_workspace` except (workflow_state_server.py:1614-1615)
Replace `except (json.JSONDecodeError, Exception):` with split clauses per design I6.
**Done:** `grep -nE 'except.*Exception' plugins/pd/mcp/workflow_state_server.py:1614-1620` returns 0 matches.
**Time:** 3 min.

### T2b.2 — Add `test_filter_states_db_error_returns_error_json`
Mock `_db.get_entity` to raise `sqlite3.OperationalError`; assert `_make_error` JSON returned.
**Done:** Test passes. → AC-7 partial
**Time:** 8 min.
**Dependencies:** T2b.1.

### T2b.3 — Add `test_filter_states_unexpected_error_propagates`
Mock `_db.get_entity` to raise `RuntimeError("unexpected")`; assert `pytest.raises(RuntimeError)` triggers.
**Done:** Test passes. → AC-7 partial
**Time:** 5 min.
**Dependencies:** T2b.1.

### T2b.4 — Commit PI-2b (FR-7)
```bash
git add plugins/pd/mcp/workflow_state_server.py plugins/pd/mcp/test_workflow_state_server.py
git commit -m "feat(113/FR-7): narrow _filter_states_by_workspace except clause"
```
**Time:** 2 min.

### T2c.1 [P] — Verify imports in server_helpers.py
Check `plugins/pd/hooks/lib/entity_registry/server_helpers.py` has `import sys` and `import sqlite3` at top; add if missing.
**Done:** Both imports present.
**Time:** 2 min.

### T2c.2 — Narrow server_helpers.py parent resolution except (lines 248-255)
Replace `except Exception:` with `except sqlite3.OperationalError as exc:` block + stderr warning per design I6.
**Done:** `grep -nE 'except Exception' plugins/pd/hooks/lib/entity_registry/server_helpers.py:248-260` returns 0 matches.
**Time:** 5 min.
**Dependencies:** T2c.1.

### T2c.3 — Add `test_register_entity_parent_resolution_db_error_orphans_with_warning`
Mock `db.get_entity` to raise `sqlite3.OperationalError`. Use `capsys` fixture. Assert: entity registers with `parent_uuid=None` AND stderr contains "server_helpers: parent resolution failed".
**Done:** Test passes. → AC-8 partial
**Time:** 10 min.
**Dependencies:** T2c.2.

### T2c.4 — Add `test_register_entity_parent_resolution_unexpected_error_propagates`
Mock `db.get_entity` to raise `RuntimeError`; assert propagation.
**Done:** Test passes. → AC-8 partial
**Time:** 5 min.
**Dependencies:** T2c.2.

### T2c.5 — Commit PI-2c (FR-8)
```bash
git add plugins/pd/hooks/lib/entity_registry/server_helpers.py plugins/pd/hooks/lib/entity_registry/test_server_helpers.py
git commit -m "feat(113/FR-8): narrow server_helpers parent resolution except"
```
**Time:** 2 min.

### T2d.1 [P] — Verify current entity_server.py:450 silent-orphan behavior
Confirm line 450 is `parent_uuid = parent_entity["uuid"] if parent_entity else None`.
**Done:** `sed -n '450p' plugins/pd/mcp/entity_server.py` shows the ternary.
**Time:** 1 min.

### T2d.2 — Replace ternary with explicit ValueError raise
Per design I7: add `if parent_entity is None: raise ValueError(f"Parent entity not found: {parent_type_id!r}")` before the parent_uuid assignment; change line 450 to `parent_uuid = parent_entity["uuid"]`.
**Done:** `grep -A1 'parent_entity = db.get_entity' plugins/pd/mcp/entity_server.py` shows the explicit check.
**Time:** 3 min.
**Dependencies:** T2d.1.

### T2d.3 — Add `test_create_key_result_missing_parent_raises`
In `plugins/pd/hooks/lib/entity_registry/test_entity_server.py` (existing file that already imports MCP entity_server via sys.path injection per spec FR-9.2 inline note), bootstrap DB without parent objective; call `_process_create_key_result(...)`; assert `ValueError` raised.
**Done:** Test passes. → AC-9
**Time:** 10 min.
**Dependencies:** T2d.2.

### T2d.4 — Commit PI-2d (FR-9)
```bash
git add plugins/pd/mcp/entity_server.py plugins/pd/hooks/lib/entity_registry/test_entity_server.py
git commit -m "feat(113/FR-9): _process_create_key_result missing-parent ValueError"
```
**Time:** 2 min.

---

## PI-3 — Workspace filter ValueError + empty-string boundary (FR-3.2/3.3, FR-6)

### T3a.1 — Modify `_resolve_list_handler_workspace_filter` to raise on invalid hex
Replace silent `None` return on no-matching-row with `raise ValueError(f"No workspace found for project_id={project_id!r}")`.
**Done:** `grep -n 'No workspace found for project_id' plugins/pd/mcp/workflow_state_server.py` returns 1 match.
**Time:** 3 min.
**Dependencies:** T2a.3 (FR-3.0 in place).

### T3a.2 — Wrap `list_features_by_phase` caller (workflow_state_server.py:1619)
Add `try/except ValueError` returning `_make_error(error_type="invalid_project_id", ...)` per design TD-6.
**Done:** Verifying by inspection.
**Time:** 5 min.
**Dependencies:** T3a.1.

### T3a.3 — Wrap `list_features_by_status` caller (workflow_state_server.py:1643)
Same wrapper as T3a.2.
**Done:** Verifying by inspection.
**Time:** 5 min.
**Dependencies:** T3a.1.

### T3a.4 — Add `test_list_features_handler_db_none_returns_empty`
Set `_db = None`; call helper; assert returns None or empty list (FR-3.1 pin).
**Done:** Test passes. → AC-3 partial
**Time:** 5 min.

### T3a.5 — Add `test_list_features_by_phase_invalid_legacy_hex_returns_error`
Call `list_features_by_phase(phase="design", project_id="ffffffffffff")` (12-char hex with no matching row); assert returned JSON has `error_type="invalid_project_id"`.
**Done:** Test passes. → AC-3 partial
**Time:** 7 min.
**Dependencies:** T3a.2.

### T3a.6 — Add `test_list_features_by_status_invalid_legacy_hex_returns_error`
Mirror T3a.5 for `list_features_by_status`.
**Done:** Test passes. → AC-3 partial
**Time:** 5 min.
**Dependencies:** T3a.3.

### T3a.7 — Commit PI-3a (FR-3.2/3.3)
```bash
git add plugins/pd/mcp/workflow_state_server.py plugins/pd/mcp/test_workflow_state_server.py
git commit -m "feat(113/FR-3.2): invalid project_id raises ValueError; handlers return _make_error JSON"
```
**Time:** 2 min.

### T3b.1 — Add FR-6.2 inline comments at workflow_state_server.py lines 657 + 1280
Per design I6.2: add `# Empty-string == unset == None at db.* kwarg boundary; downstream defaults to project_id="__unknown__" → _UNKNOWN_WORKSPACE_UUID.` at both lines.
**Done:** `grep -B0 -A0 'Empty-string == unset' plugins/pd/mcp/workflow_state_server.py | wc -l` returns 2.
**Time:** 3 min.

### T3b.2 — Add parametrized test `test_workspace_uuid_empty_string_normalized_to_none`
Two sub-tests:
- param `init_feature_state`: exercises line 1280
- param `transition_phase`: exercises line 657

Each: set `wss._workspace_uuid = ""`, call entry-point, assert entity registered with workspace_uuid == `_UNKNOWN_WORKSPACE_UUID`.
**Done:** Both sub-tests pass.
**Time:** 12 min.

### T3b.3 — Pre-impl mutation pin verification (AC-6 fallback clause)
Manually: temporarily remove `or None` at line 1280, run init_feature_state sub-test, confirm it fails with FK-or-equivalent observable error. Note the actual failure mode in commit message. Revert mutation.
**Done:** Observable error confirmed; AC-6 text updated in same commit if mode differs from FK constraint failure. → AC-6
**Time:** 8 min.
**Dependencies:** T3b.2.

### T3b.4 — Commit PI-3b (FR-6)
```bash
git add plugins/pd/mcp/workflow_state_server.py plugins/pd/mcp/test_workflow_state_server.py
git commit -m "feat(113/FR-6): empty-string workspace_uuid normalization tests + doc comments"
```
**Time:** 2 min.

---

## PI-4 — `entity_status.py` conditional-kwarg sweep (FR-10)

### T4.1 — Apply conditional pattern at 4 sites
Modify `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py` at lines 47, 72, 189, 320 per design I8:
Change `project_id=project_id, workspace_uuid=workspace_uuid` → `project_id=project_id if workspace_uuid is None else None, workspace_uuid=workspace_uuid`.
**Done:** `grep -nE 'project_id=project_id if workspace_uuid is None' plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py | wc -l` returns 6 (4 new + 2 existing at 175, 316).
**Time:** 5 min.

### T4.2 — Add parametrized `test_sync_entity_statuses_no_deprecation_warning_on_happy_path`
4 sub-tests, one per fixed site (47 update_entity meta_json archive, 72 update_entity status-change, 189 update_entity brainstorm archive, 320 update_entity backlog status-change).

Each:
- Bootstrap DB with real workspace_uuid via `bootstrap_test_workspace()`
- Set up the path-specific state (e.g., for line 72, write a meta.json that triggers status change)
- Call `sync_entity_statuses(db, ..., workspace_uuid=ws_a)`
- Wrap in `warnings.catch_warnings()` + `simplefilter('error', DeprecationWarning)` (scoped to call per design R6 critical note)
- Assert no DeprecationWarning fires

If `catch_warnings` filter-bleeds, fallback to `recwarn` fixture per design R6.
**Done:** All 4 sub-tests pass. → AC-10
**Time:** 20 min.
**Dependencies:** T4.1.

### T4.3 — Commit PI-4 (FR-10)
```bash
git add plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py
git commit -m "feat(113/FR-10): entity_status conditional-kwarg pattern at 4 sites"
```
**Time:** 2 min.

---

## PI-5 — `update_workflow_phase` signature extension (FR-4.1)

### T5.1 [B] — Add `workspace_uuid` to `update_workflow_phase` signature
Modify `plugins/pd/hooks/lib/entity_registry/database.py:4866`:
- Add `workspace_uuid: str | None = None` (after the `_UNSET`-sentinel kwargs)
- When non-None: pre-UPDATE SELECT of stored workspace_uuid; raise `ValueError(f"workspace_uuid mismatch for {type_id}: stored={existing!r}, provided={workspace_uuid!r}")` on mismatch
- Do NOT add workspace_uuid to the UPDATE SET parts
**Done:** Method accepts kwarg; running existing tests with kwarg unset still passes. Mismatch case raises ValueError.
**Time:** 15 min.

### T5.2 — Add `test_update_workflow_phase_does_not_mutate_workspace_uuid_column`
In `test_database.py`:
- Bootstrap workflow_phases row with `workspace_uuid=ws_a`
- Pre-update SELECT: capture workspace_uuid
- Call `update_workflow_phase(type_id, workspace_uuid=ws_a, workflow_phase="design")`
- Post-update SELECT: assert workspace_uuid byte-identical
**Done:** Test passes. → AC-4 partial
**Time:** 10 min.
**Dependencies:** T5.1.

### T5.3 — Commit PI-5 (FR-4.1)
```bash
git add plugins/pd/hooks/lib/entity_registry/database.py plugins/pd/hooks/lib/entity_registry/test_database.py
git commit -m "feat(113/FR-4.1): update_workflow_phase workspace_uuid read-side assertion"
```
**Time:** 2 min.

---

## PI-6 — Engine + lifecycle forwarding (FR-4.2/4.3 + FR-5/5.2)

### T6a.1 — Forward `workspace_uuid` at engine.py:100-103 (transition_phase)
Add `workspace_uuid=workspace_uuid` to the `db.update_workflow_phase` call.
**Done:** `grep -A3 'transition_phase' plugins/pd/hooks/lib/workflow_engine/engine.py | grep workspace_uuid` shows the new kwarg.
**Time:** 3 min.
**Dependencies:** T5.3.

### T6a.2 — Forward `workspace_uuid` at engine.py:166-170 (complete_phase non-terminal)
Same shape.
**Done:** Confirming via inspection.
**Time:** 3 min.
**Dependencies:** T5.3.

### T6a.3 — Add `test_transition_phase_workspace_uuid_mismatch_raises`
- Bootstrap two workspaces with `bootstrap_test_workspace()`
- Create a workflow_phases row scoped to ws_a
- Call `engine.transition_phase(type_id, "design", workspace_uuid=ws_b)`
- Assert: `pytest.raises(ValueError, match="workspace_uuid mismatch")` triggers
**Done:** Test passes. → AC-4 partial
**Time:** 15 min.
**Dependencies:** T6a.1.

### T6a.4 — Add `test_complete_phase_non_terminal_workspace_uuid_pinned`
Same shape for non-terminal `complete_phase` call.
**Done:** Test passes. → AC-4 partial
**Time:** 10 min.
**Dependencies:** T6a.2.

### T6a.5 — Add `test_complete_phase_terminal_workspace_uuid_pinned`
For `phase == "finish"` path; verify the terminal `db.update_entity` already-correct forwarding still works.
**Done:** Test passes. → AC-4 partial
**Time:** 10 min.
**Dependencies:** T6a.2.

### T6a.6 — Pre-impl propagation verification (design C4 contract)
Manually: temporarily widen `engine.py`'s `except sqlite3.Error` to `except (sqlite3.Error, ValueError):`. Run T6a.3's test. Confirm it FAILS (ValueError now swallowed). Revert widening before committing.
**Done:** Mutation produces test failure as expected.
**Time:** 5 min.
**Dependencies:** T6a.3, T6a.4, T6a.5.

### T6a.7 — Commit PI-6a (FR-4.2/4.3)
```bash
git add plugins/pd/hooks/lib/workflow_engine/engine.py plugins/pd/hooks/lib/workflow_engine/test_engine.py
git commit -m "feat(113/FR-4.2): engine.py transition_phase + complete_phase workspace_uuid forwarding + mismatch tests"
```
**Time:** 2 min.

### T6b.1 — Add `workspace_uuid` unconditionally to entity_lifecycle.py update_kwargs dict
Modify `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py:185-193`:
Add `"workspace_uuid": workspace_uuid` to the `update_kwargs` dict literal per design I4 (locked unconditional form).
**Done:** `grep -A8 'update_kwargs: dict' plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py | grep workspace_uuid` shows the new entry.
**Time:** 3 min.
**Dependencies:** T5.3.

### T6b.2 — Add `test_transition_entity_phase_workspace_uuid_consistent`
Bootstrap two workspaces; call `transition_entity_phase(db, 'brainstorm:foo', 'promoted', workspace_uuid=ws_a)`. Assert:
1. ws_a's entity status updated
2. ws_a's workflow_phase row updated
3. ws_b's parallel row UNCHANGED
4. Calling with `workspace_uuid=ws_b` against ws_a row raises FR-4.1 ValueError
**Done:** Test passes. → AC-5
**Time:** 15 min.
**Dependencies:** T6b.1, T5.3.

### T6b.3 — Commit PI-6b (FR-5/5.2)
```bash
git add plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py
git commit -m "feat(113/FR-5): transition_entity_phase symmetric workspace_uuid forwarding"
```
**Time:** 2 min.

---

## PI-7 — Reconcile workspace_uuid threading (FR-11)

### T7a.1 — Extend `apply_workflow_reconciliation` signature
Add `workspace_uuid: str | None = None` kwarg to `apply_workflow_reconciliation` at `plugins/pd/hooks/lib/workflow_engine/reconciliation.py:756`.
**Done:** Signature includes kwarg.
**Time:** 3 min.
**Dependencies:** T5.3.

### T7a.2 — Merge workspace_uuid into kwargs dict at reconciliation.py:367-374
Per design I9: `kwargs["workspace_uuid"] = workspace_uuid` BEFORE `db.update_workflow_phase(feature_type_id, **kwargs)`.
**Done:** `grep -B2 'db.update_workflow_phase' plugins/pd/hooks/lib/workflow_engine/reconciliation.py:370-375` shows kwarg assignment.
**Time:** 3 min.
**Dependencies:** T7a.1.

### T7a.3 — Add workspace_uuid kwarg at reconciliation.py:462
Add `workspace_uuid=workspace_uuid` to the single-kwarg `db.update_workflow_phase` call.
**Done:** Inspection.
**Time:** 2 min.
**Dependencies:** T7a.1.

### T7a.4 — Extend `scan_all` signature
Add `workspace_uuid: str | None = None` kwarg at `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py:543`. Forward to `db.list_entities(entity_type="feature", workspace_uuid=workspace_uuid)` at line 570.
**Done:** Signature + forwarding confirmed.
**Time:** 5 min.

### T7a.5 — Commit PI-7a (FR-11.1, FR-11.2 lib extensions)
```bash
git add plugins/pd/hooks/lib/workflow_engine/reconciliation.py plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py
git commit -m "feat(113/FR-11): apply_workflow_reconciliation + scan_all workspace_uuid kwargs"
```
**Time:** 2 min.

### T7b.1 — Extend `_process_reconcile_apply` (workflow_state_server.py:1189)
Accept and forward `workspace_uuid` to `apply_workflow_reconciliation`.
**Done:** Inspection.
**Time:** 3 min.
**Dependencies:** T7a.5.

### T7b.2 — Extend `_process_reconcile_frontmatter` (workflow_state_server.py:1223)
Accept and forward `workspace_uuid` to `scan_all`.
**Done:** Inspection.
**Time:** 3 min.

### T7b.3 — Extend `_process_reconcile_status` (workflow_state_server.py:1366)
Accept and forward `workspace_uuid` to `scan_all` at line 1381.
**Done:** Inspection.
**Time:** 3 min.

### T7b.4 — Update async handlers (workflow_state_server.py:1678, 1694, 1705)
Each handler passes `workspace_uuid=_workspace_uuid or None` to its `_process_*` helper.
**Done:** 3 handler bodies updated.
**Time:** 5 min.

### T7c.1 — Add `test_reconcile_apply_forwards_workspace_uuid`
Set `wss._workspace_uuid = ws_a`; mock `apply_workflow_reconciliation`; call async `reconcile_apply()`; assert mock received `workspace_uuid=ws_a` kwarg.
**Done:** Test passes. → AC-11 partial
**Time:** 10 min.

### T7c.2 — Add `test_reconcile_frontmatter_forwards_workspace_uuid`
Same shape for `reconcile_frontmatter`; mock `scan_all`.
**Done:** Test passes. → AC-11 partial
**Time:** 8 min.

### T7c.3 — Add `test_reconcile_status_forwards_workspace_uuid`
Same shape for `reconcile_status`.
**Done:** Test passes. → AC-11 partial
**Time:** 8 min.

### T7c.4 — Add `test_apply_workflow_reconciliation_forwards_workspace_uuid_to_update_workflow_phase_meta_ahead`
In `plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py`: bootstrap meta_json_ahead row; call apply with `workspace_uuid=ws_a`; mock `db.update_workflow_phase`; assert mock received the kwarg (pins reconciliation.py:374).
**Done:** Test passes. → AC-11 partial
**Time:** 12 min.

### T7c.5 — Add `test_apply_workflow_reconciliation_forwards_workspace_uuid_to_update_workflow_phase_kanban_drift`
Same shape; bootstrap kanban-only-drift row; pins reconciliation.py:462.
**Done:** Test passes. → AC-11 partial
**Time:** 10 min.

### T7c.6 — Add `test_scan_all_scopes_to_workspace`
In `plugins/pd/hooks/lib/entity_registry/test_frontmatter_sync.py`: bootstrap two workspaces with features; call `scan_all(db, artifacts_root, workspace_uuid=ws_a)`; assert reports cover ONLY ws_a's features.
**Done:** Test passes. → AC-11 partial
**Time:** 12 min.

### T7c.7 — Add `test_scan_all_default_unscoped_returns_all_workspace_features`
NFR-3 regression pin: same fixture; call `scan_all(db, artifacts_root)` with NO workspace_uuid kwarg; assert reports cover BOTH workspaces.
**Done:** Test passes. → AC-11 partial (default behavior pin)
**Time:** 8 min.

### T7c.8 — Commit PI-7b/c (FR-11.3/4/5)
```bash
git add plugins/pd/mcp/workflow_state_server.py plugins/pd/mcp/test_workflow_state_server.py plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py plugins/pd/hooks/lib/entity_registry/test_frontmatter_sync.py
git commit -m "feat(113/FR-11): reconcile_* MCP handlers workspace_uuid forwarding + 7 pin tests"
```
**Time:** 2 min.

---

## PI-8 — Regression + cleanup

### T8.1 — Final pytest run
```bash
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/{hooks/lib,mcp} --tb=line > agent_sandbox/$(date +%Y-%m-%d)/113-validation/final.log 2>&1 || true
```
**Done:** `final.log` exists.
**Time:** 5-10 min.

### T8.2 — Baseline diff (AC-12)
```bash
diff <(grep '^FAILED' agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log | sort) \
     <(grep '^FAILED' agent_sandbox/$(date +%Y-%m-%d)/113-validation/final.log | sort)
```
**Done:** Output is empty (no net-new failures). → AC-12
**Time:** 2 min.
**Dependencies:** T8.1.

### T8.3 — Update CHANGELOG.md
Add `[Unreleased]` section entries (or extend the existing one), one bullet per FR:
- FR-1: qa_gate/emitter.py + .gitignore:63 removal
- FR-2: bash-version-capture.sh
- FR-3: workspace filter narrow-fail + caller wrappers
- FR-4: update_workflow_phase workspace_uuid read-side assertion + engine forwarding
- FR-5: transition_entity_phase symmetric forwarding
- FR-6: empty-string workspace_uuid normalization tests
- FR-7: narrow _filter_states_by_workspace except
- FR-8: narrow server_helpers parent resolution except
- FR-9: _process_create_key_result missing-parent ValueError
- FR-10: entity_status conditional-kwarg sweep
- FR-11: reconcile_* handler workspace_uuid threading
- Removed: `docs/features/**/.qa-gate.json` from `.gitignore` (FR-1.4)
**Done:** CHANGELOG.md shows all 12 entries (11 FRs + removal note).
**Time:** 10 min.

### T8.4 — Pre-finish sanity check
- `grep -n 'qa-gate' .gitignore` returns no `docs/features/**` match
- Count of new tests roughly matches AC totals (run `pytest --co -q plugins/pd/ | wc -l` and compare vs baseline)
**Done:** Both checks pass.
**Time:** 3 min.

### T8.5 — Commit PI-8 (CHANGELOG + verification)
```bash
git add CHANGELOG.md
git commit -m "docs(113): CHANGELOG entries for feature 112 QA-followup fixes"
```
**Done:** Commit lands; verification log noted in commit body.
**Time:** 2 min.

---

## Total Effort Estimate

| PI | # Tasks | Est. Duration |
|----|---------|----------------|
| PI-0 | 2 | 10 min |
| PI-1 | 10 | 55 min |
| PI-2 | 14 | 60 min |
| PI-3 | 11 | 60 min |
| PI-4 | 3 | 27 min |
| PI-5 | 3 | 27 min |
| PI-6 | 10 | 80 min |
| PI-7 | 15 | 95 min |
| PI-8 | 5 | 32 min |
| **Total** | **73** | **~7 hours** |

## Cross-References

- Plan: `docs/features/113-feature-112-qa-followups/plan.md`
- Design: `docs/features/113-feature-112-qa-followups/design.md`
- Spec: `docs/features/113-feature-112-qa-followups/spec.md`
