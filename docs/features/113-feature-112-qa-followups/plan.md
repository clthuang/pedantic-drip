# Feature 113 — Implementation Plan (iter 2)

## Status
- Phase: create-plan (iter 2)
- Mode: standard
- Spec: `docs/features/113-feature-112-qa-followups/spec.md`
- Design: `docs/features/113-feature-112-qa-followups/design.md`

## Overview

Surgical changes across 7 source files, 2 new modules, 8 test-file extensions, 1 new test file. Per-method incremental rollout (NFR-5): each FR ships as Tests+X (RED) → Impl+X (GREEN) pair, with explicit RED-test authoring BEFORE the corresponding implementation step. Baseline captured before any code commit, AC-12 diff at the end.

**Conventions (iter 2):**
- `Tests+X` = step authors failing tests (RED). Must commit-or-stage the failing tests before the Impl step. Verification: `pytest -k '<keyword>' -v` shows the new tests failing for the right reason.
- `Impl+X` = step implements the source change (GREEN). Verification: same pytest invocation now passes.
- `[P]` = parallel-safe with siblings in the same PI (no shared file).
- `[S:<file>]` = serializes on the named file (cannot dispatch to a parallel worktree concurrently with a sibling touching the same file).
- `[B]` = blocker for downstream PIs.
- `→ AC-N` = acceptance criterion satisfied.

**Test-count canonical source:** Verification Plan Summary table in spec.md. Approximately 20 unique test functions, ~26 parametrized cases. Each PI lists its delta against that table.

## Implementation Order (per NFR-5)

```
PI-0   Baseline capture (NFR-2, artifact-only)
   │
   ├── PI-1   Validation artifacts (parallel safe across files)
   │   ├── Tests+1 → Impl+1 (qa_gate/emitter.py)
   │   └── Tests+2 → Impl+2 (bash-version-capture.sh)
   │
   ├── PI-2   Defensive fixes (FR-3.0, FR-7, FR-8, FR-9 — parallel-safe across files; serialize on test_workflow_state_server.py)
   │   ├── Tests+3.0 → Impl+3.0
   │   ├── Tests+7  → Impl+7    [S:test_workflow_state_server.py with PI-2a]
   │   ├── Tests+8  → Impl+8
   │   └── Tests+9  → Impl+9
   │
   ├── PI-3   Workspace filter + boundary (depends on PI-2 FR-3.0; serializes on test_workflow_state_server.py)
   │   ├── Tests+3.2 → Impl+3.2  [S:test_workflow_state_server.py with PI-2, PI-3b]
   │   └── Tests+6  → Impl+6     [S:test_workflow_state_server.py]
   │
   ├── PI-4   entity_status sweep (independent)
   │   └── Tests+10 → Impl+10
   │
   ├── PI-5   FR-4.1 anchor (blocks PI-6, PI-7)
   │   └── Tests+4.1 → Impl+4.1
   │
   ├── PI-6   Engine + lifecycle forwarding (depends on PI-5)
   │   ├── Tests+4.2 → Impl+4.2
   │   └── Tests+5  → Impl+5
   │
   ├── PI-7   Reconcile threading (depends on PI-5)
   │   ├── Tests+11.1/11.2 → Impl+11.1/11.2 (lib extensions)
   │   └── Tests+11.3/4/5 → Impl+11.3/4/5 (MCP + test additions)
   │
   └── PI-8   Regression + dogfood (depends on all)
       ├── Final pytest pass + baseline diff (AC-12)
       ├── CHANGELOG entries
       ├── Pre-finish sanity check
       └── AC-13 dogfood at /pd:finish-feature (verifies emitter end-to-end)
```

## Plan Items

### PI-0 — Baseline capture (NFR-2)

**Goal:** Capture pre-implementation regression baseline at feature branch root commit.

**Steps:**
1. `mkdir -p agent_sandbox/$(date +%Y-%m-%d)/113-validation`
2. Run full pytest: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/{hooks/lib,mcp} --tb=line > agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log 2>&1 || true`
3. Record `BASELINE_FAIL_COUNT=$(grep -c '^FAILED' agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log)` for later diff.

**Verification:** Baseline log file present with `^FAILED` rows captured.

**Dependencies:** None.

**Commits:** 0 (artifact-only; baseline log lives in gitignored `agent_sandbox/`).

### PI-1 — Validation artifacts (FR-1 + FR-2)

**Goal:** Land canonical `.qa-gate.json` schema + reusable emitter + `bash-version-capture.sh` helper.

**Work pairs:**

#### Tests+1 (RED) — qa_gate emitter tests
- Create `plugins/pd/hooks/lib/qa_gate/__init__.py` exporting `STATUS_ENUM` placeholder (`frozenset()` empty initially)
- Create `plugins/pd/hooks/lib/qa_gate/emitter.py` stub: `def emit_qa_gate(*args, **kwargs): raise NotImplementedError`
- Create `plugins/pd/hooks/lib/qa_gate/test_emitter.py` with 5 failing tests:
  - `test_emit_qa_gate_rejects_invalid_status`
  - `test_emit_qa_gate_requires_id_status_evidence`
  - `test_emit_qa_gate_rejects_evidence_over_500_chars`
  - `test_emit_qa_gate_rejects_conditional_skipped_with_empty_condition`
  - `test_emit_qa_gate_head_sha_idempotent`
- **RED verification:** `pytest plugins/pd/hooks/lib/qa_gate/test_emitter.py -v` → all 5 fail with NotImplementedError.

#### Impl+1 (GREEN) — qa_gate emitter implementation + .gitignore removal
- Populate `STATUS_ENUM = frozenset({"passed", "deferred", "n_a", "conditional_skipped"})`
- Implement `emit_qa_gate(...)` per design I1
- Remove `.gitignore:63` line `docs/features/**/.qa-gate.json` (FR-1.4)
- **GREEN verification:** `pytest plugins/pd/hooks/lib/qa_gate/test_emitter.py -v` → all 5 pass. `grep -n 'docs/features/\*\*/.qa-gate.json' .gitignore` returns 0 matches. → AC-1 (partial; AC-13 dogfood at PI-8 completes)

#### Tests+2 (RED) — bash-version-capture self-test
- Create test stub `plugins/pd/hooks/tests/test_bash_version_capture.sh` (or inline pytest equivalent) asserting:
  - Script exists and is executable
  - Running it produces 3 `=== ... ===` headers in output
- **RED verification:** First-pass — script doesn't exist; test fails with file-not-found.

#### Impl+2 (GREEN) — bash-version-capture.sh script
- Create `plugins/pd/hooks/tests/bash-version-capture.sh` per design I10 (with `trap '' PIPE` + `{ ...; } 2>/dev/null || true` wrappers, no `set -e`)
- `chmod +x` the script
- **GREEN verification:** `bash plugins/pd/hooks/tests/bash-version-capture.sh > /tmp/bv.log 2>&1`; `grep -c '^=== ' /tmp/bv.log` returns 3. → AC-2

**Commits:** 2 (Impl+1, Impl+2; the Tests+ commits can be folded into the same commit IF the RED state is verified locally and noted in the commit message).

**Dependencies:** None.

### PI-2 — Defensive fixes (FR-3.0, FR-7, FR-8, FR-9)

**Goal:** Land defensive code-quality fixes — workspace filter entry-point normalization, narrow exception handlers, missing-parent ValueError.

**Serialization note:** PI-2a (FR-3.0) and PI-2b (FR-7) both touch `test_workflow_state_server.py` and must serialize on that file (no parallel worktree dispatch on this test module). PI-2c (FR-8) and PI-2d (FR-9) touch separate test files (`test_server_helpers.py`, `test_entity_server.py`) and ARE parallel-safe with each other.

**Work pairs:**

#### Tests+3.0 (RED) — empty-string normalization test
- In `plugins/pd/mcp/test_workflow_state_server.py::TestListFeaturesByDefaultSingleWorkspace`, add `test_list_features_handler_empty_project_id_treated_as_default`
  - Sets `_workspace_uuid` to a known value; calls `list_features_by_phase(phase="design", project_id="")`; asserts results scoped to that workspace
- **RED verification:** Test fails today because helper falls into JOIN-resolve branch and returns None (cross-workspace).

#### Impl+3.0 (GREEN) — workspace_filter entry-point normalization
- In `workflow_state_server.py:_resolve_list_handler_workspace_filter`, BEFORE the `== "*"` check, add `if project_id == "": project_id = None`
- Add comment for FR-3.1's `_db is None` retain branch (per design I5)
- **GREEN verification:** Above test passes. → AC-3 partial (1 of 4 new tests)

#### Tests+7 (RED) — _filter_states_by_workspace narrow except [S:test_workflow_state_server.py]
- In `test_workflow_state_server.py`, add 2 tests:
  - `test_filter_states_db_error_returns_error_json` — mock `_db.get_entity` to raise `sqlite3.OperationalError`; assert `_make_error` JSON returned
  - `test_filter_states_unexpected_error_propagates` — mock to raise `RuntimeError`; assert `pytest.raises(RuntimeError)`
- **RED verification:** Both fail today (current bare-except swallows RuntimeError; DB-error path returns unfiltered JSON, not `_make_error`).

#### Impl+7 (GREEN) — narrow _filter_states_by_workspace except
- Replace `except (json.JSONDecodeError, Exception):` at workflow_state_server.py:1614-1615 with split clauses per design I6
- **GREEN verification:** Tests+7's 2 tests pass. `grep -nE 'except.*Exception' plugins/pd/mcp/workflow_state_server.py | awk -F: '$2 >= 1614 && $2 <= 1620'` returns 0 lines. → AC-7

#### Tests+8 (RED) — server_helpers parent-resolution narrow except
- Verify `import sys` is added at top of `server_helpers.py` (currently NOT imported per iter 2 pre-check — only `json, os, sqlite3` imported). The Impl+8 step adds the import.
- In `plugins/pd/hooks/lib/entity_registry/test_server_helpers.py`, add 2 tests:
  - `test_register_entity_parent_resolution_db_error_orphans_with_warning` — mock `db.get_entity` to raise `sqlite3.OperationalError`; use `capsys`; assert entity registered with `parent_uuid=None` AND stderr contains the warning text
  - `test_register_entity_parent_resolution_unexpected_error_propagates` — mock to raise `RuntimeError`; assert propagation
- **RED verification:** Both fail today (current `except Exception` swallows both).

#### Impl+8 (GREEN) — narrow server_helpers.py parent-resolution except
- Add `import sys` to top of `server_helpers.py` (currently absent; verified at iter 2)
- Confirm `import sqlite3` is present (verified at iter 2: line 10)
- Replace `except Exception:` at server_helpers.py:248-255 with `except sqlite3.OperationalError as exc:` block per design I6
- **GREEN verification:** Tests+8's tests pass. → AC-8

#### Tests+9 (RED) — _process_create_key_result missing-parent ValueError
- Verify current `entity_server.py:450` is the silent-orphan ternary `parent_uuid = parent_entity["uuid"] if parent_entity else None` (pre-checked at iter 2 — confirmed).
- In `plugins/pd/hooks/lib/entity_registry/test_entity_server.py` (existing file that already imports MCP entity_server via sys.path injection at lines 12-14), add `test_create_key_result_missing_parent_raises`
  - Bootstrap DB without parent objective; call `_process_create_key_result(...)`; assert `ValueError` raised with message matching `"Parent entity not found"`
- **RED verification:** Test fails today (silent orphan; no ValueError raised; current ternary makes parent_uuid=None and proceeds).

#### Impl+9 (GREEN) — explicit missing-parent ValueError raise
- Per design I7: add `if parent_entity is None: raise ValueError(f"Parent entity not found: {parent_type_id!r}")` BEFORE the parent_uuid assignment; simplify line 450 to `parent_uuid = parent_entity["uuid"]`
- **GREEN verification:** Tests+9's test passes. → AC-9

**Commits:** 4 (Impl+3.0, Impl+7, Impl+8, Impl+9).

**Dependencies:** None internal.

### PI-3 — Workspace filter ValueError + empty-string boundary (FR-3.2/3.3, FR-6)

**Goal:** Complete workspace_filter narrowing (raise on invalid hex) + empty-string boundary tests pinning `_workspace_uuid or None` MCP idiom.

**Serialization note:** Both Tests+3.2 and Tests+6 touch `test_workflow_state_server.py`; serialize. Both depend on PI-2a's FR-3.0 entry-point normalization being in place.

**Work pairs:**

#### Tests+3.2 (RED) — invalid-hex ValueError caller wrappers
- In `test_workflow_state_server.py`, add 3 new tests:
  - `test_list_features_handler_db_none_returns_empty` (FR-3.1 pin — degraded mode returns empty/None rather than crashing)
  - `test_list_features_by_phase_invalid_legacy_hex_returns_error` — calls `list_features_by_phase(phase="design", project_id="ffffffffffff")`; asserts JSON has `error_type="invalid_project_id"`
  - `test_list_features_by_status_invalid_legacy_hex_returns_error` — same shape for `list_features_by_status`
- **RED verification:** All 3 fail today (current helper returns None silently on invalid hex).

#### Impl+3.2 (GREEN) — raise ValueError + caller wrappers
- Modify `_resolve_list_handler_workspace_filter` to raise `ValueError(f"No workspace found for project_id={project_id!r}")` on no-matching-row
- Wrap `list_features_by_phase` at workflow_state_server.py:1619 and `list_features_by_status` at :1643 in `try/except ValueError` returning `_make_error(error_type="invalid_project_id", ...)` per design TD-6
- **GREEN verification:** Tests+3.2's 3 tests pass; combined with PI-2a's 1 test = 4 new from FR-3.3. → AC-3 (6 tests total)

#### Tests+6 (RED) — empty-string normalization boundary pins
- In `test_workflow_state_server.py`, add parametrized test `test_workspace_uuid_empty_string_normalized_to_none`:
  - Param 1 (`init_feature_state`): set `wss._workspace_uuid = ""`; call `init_feature_state(...)`; assert entity registered with `workspace_uuid == _UNKNOWN_WORKSPACE_UUID` (exercises line 1280)
  - Param 2 (`transition_phase`): set `wss._workspace_uuid = ""`; call `transition_phase(...)`; assert state row's workspace_uuid (exercises line 657)
- **RED verification:** Tests fail today only if `or None` is removed first (since `or None` already produces correct behavior); pre-impl assertion: tests PASS today (current code is correct). Comment tests as "Behavior pin — passes today; removing `or None` should fail them" — these are mutation-pin tests, NOT change-detection tests.

#### Impl+6 (GREEN) — FR-6.2 inline doc comments at lines 657 + 1280
- Add `# Empty-string == unset == None at db.* kwarg boundary; downstream defaults to project_id="__unknown__" → _UNKNOWN_WORKSPACE_UUID.` comment at workflow_state_server.py:657 AND at line 1280
- **GREEN verification:** Tests+6's 2 parametrized sub-tests pass (they already passed in RED — Impl+6 is documentation only). → AC-6

##### PI-3.MUT — Mutation-pin observability gate (AC-6 fallback enforcement)
- **MUST execute before Impl+6 commit lands.**
- Procedure:
  1. Temporarily edit `workflow_state_server.py:1280`: change `workspace_uuid=_workspace_uuid or None` → `workspace_uuid=_workspace_uuid`
  2. Run `pytest plugins/pd/mcp/test_workflow_state_server.py -k 'workspace_uuid_empty_string_normalized_to_none and init_feature_state' -v`
  3. Capture the assertion failure mode (FK constraint, validation error, etc.)
  4. Revert the mutation
  5. Repeat for line 657 (transition_phase sub-test)
  6. If the failure mode is NOT FK-or-equivalent observable error, update AC-6 spec text in the Impl+6 commit body
- **Gate condition:** Both sub-tests must fail with observable assertion errors when their `or None` is removed. If a sub-test SILENTLY PASSES after the mutation, that mutation pin is vacuous — open a spec amendment commit before Impl+6 lands.

**Commits:** 2 (Impl+3.2, Impl+6), plus PI-3.MUT verification (documented in Impl+6 commit body).

**Dependencies:** PI-2a (FR-3.0 entry-point normalization).

### PI-4 — entity_status conditional-kwarg sweep (FR-10)

**Goal:** Eliminate `DeprecationWarning` on post-FR-2 happy paths at 4 update_entity sites.

**Work pair:**

#### Tests+10 (RED) — parametrized no-DeprecationWarning test
- In `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`, add parametrized `test_sync_entity_statuses_no_deprecation_warning_on_happy_path` covering 4 sites (lines 47, 72, 189, 320):
  - Each parametrize case: bootstrap DB with real workspace_uuid via `bootstrap_test_workspace()`; trigger the specific path; call `sync_entity_statuses(db, ..., workspace_uuid=ws_a)`; wrap in `warnings.catch_warnings()` + `simplefilter('error', DeprecationWarning)` (scoped per design R6 critical note); assert no DeprecationWarning fires
  - Fallback to `recwarn` fixture if catch_warnings has filter-bleed (per design R6)
- **RED verification:** All 4 sub-tests fail today — DeprecationWarning fires at lines 47/72/189/320 (per FR-10 pre-state).

#### Impl+10 (GREEN) — apply conditional pattern at 4 sites
- Modify `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py` at lines 47, 72, 189, 320 per design I8:
  - Change `project_id=project_id, workspace_uuid=workspace_uuid` → `project_id=project_id if workspace_uuid is None else None, workspace_uuid=workspace_uuid`
- Verify lines 175 and 316 unchanged (already correct per spec FR-10 pre-state).
- **GREEN verification:** Tests+10's 4 sub-tests pass. `grep -nE 'project_id=project_id if workspace_uuid is None' plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py | wc -l` returns 6 (4 new + 2 existing). → AC-10

**Commits:** 1 (Impl+10).

**Dependencies:** None.

### PI-5 — FR-4.1 anchor (`update_workflow_phase` workspace_uuid)

**Goal:** Land the load-bearing kwarg + mismatch check + column-immutability test. Blocks PI-6 and PI-7.

**Work pair:**

#### Tests+4.1 (RED) — direct database-layer tests
- In `plugins/pd/hooks/lib/entity_registry/test_database.py`, add 2 new tests:
  - `test_update_workflow_phase_workspace_uuid_mismatch_raises_value_error` (NEW per iter-1 review B2):
    - Bootstrap workflow_phases row with workspace_uuid=ws_a
    - Call `db.update_workflow_phase(type_id, workspace_uuid=ws_b, workflow_phase="design")` directly (NOT via engine)
    - Assert `pytest.raises(ValueError, match="workspace_uuid mismatch")` triggers
    - Pins FR-4.1's own mismatch check at the database layer, independent of engine forwarding
  - `test_update_workflow_phase_does_not_mutate_workspace_uuid_column`:
    - Bootstrap workflow_phases row with workspace_uuid=ws_a
    - Pre-update SELECT: capture workspace_uuid
    - Call `db.update_workflow_phase(type_id, workspace_uuid=ws_a, workflow_phase="design")`
    - Post-update SELECT: assert workspace_uuid byte-identical
- **RED verification:** Mismatch test fails today (TypeError: unexpected kwarg `workspace_uuid`). Column-immutability test cannot run today (same TypeError).

#### Impl+4.1 (GREEN) — extend update_workflow_phase signature
- Modify `plugins/pd/hooks/lib/entity_registry/database.py:4866-4944` per design I2:
  - Add `workspace_uuid: str | None = None` to signature (after the `_UNSET`-sentinel kwargs)
  - When non-None: `SELECT workspace_uuid FROM workflow_phases WHERE type_id = ?`; raise `ValueError(f"workspace_uuid mismatch for {type_id}: stored={existing!r}, provided={workspace_uuid!r}")` on mismatch
  - Do NOT add `workspace_uuid` to UPDATE SET clause
- **GREEN verification:** Both Tests+4.1 tests pass. Existing tests with no workspace_uuid kwarg still pass. → AC-4 partial (2 of 5 tests)

**Commits:** 1 (Impl+4.1).

**Dependencies:** None.

**Spec amendment commit:** Update spec FR-4.3 + AC-4 from "3 engine tests + 1 database test = 4" to "3 engine tests + 2 database tests = 5" (adds the new direct mismatch test). Apply in same commit as Impl+4.1.

### PI-6 — Engine + lifecycle forwarding (FR-4.2/4.3 + FR-5/5.2)

**Goal:** Make the FR-4.1 mismatch check load-bearing across all transition_phase/complete_phase/transition_entity_phase call paths.

**Work pairs:**

#### Tests+4.2 (RED) — engine-level mismatch tests
- In `plugins/pd/hooks/lib/workflow_engine/test_engine.py`, add 3 new tests:
  - `test_transition_phase_workspace_uuid_mismatch_raises`:
    - Use `bootstrap_test_workspace()` to create ws_a, ws_b
    - Create workflow_phases row scoped to ws_a
    - Call `engine.transition_phase(type_id, "design", workspace_uuid=ws_b)`
    - Assert `pytest.raises(ValueError, match="workspace_uuid mismatch")` (specific shape per design C4)
  - `test_complete_phase_non_terminal_workspace_uuid_pinned` — same shape, non-terminal complete_phase
  - `test_complete_phase_terminal_workspace_uuid_pinned` — same shape, `phase == "finish"` path
- **RED verification:** All 3 fail today — engine.py doesn't forward `workspace_uuid` to `update_workflow_phase`, so the mismatch is never checked. (Pre-PI-6a: tests should fail with "transition succeeded without ValueError".)

#### Impl+4.2 (GREEN) — engine forwarding
- Modify `plugins/pd/hooks/lib/workflow_engine/engine.py`:
  - Line 100-103 (`transition_phase`'s `db.update_workflow_phase` call): add `workspace_uuid=workspace_uuid`
  - Line 166-170 (`complete_phase`'s non-terminal `db.update_workflow_phase` call): add `workspace_uuid=workspace_uuid`
- **GREEN verification:** Tests+4.2's 3 tests pass. → AC-4 partial (3 more, 5 total)

##### PI-6a.MUT — Engine except-clause non-swallow verification (design C4 contract)
- **MUST execute before Impl+4.2 commit lands.**
- Procedure:
  1. Temporarily widen `engine.py`'s `except sqlite3.Error` at lines 105 + 178 to `except (sqlite3.Error, ValueError):`
  2. Run `pytest plugins/pd/hooks/lib/workflow_engine/test_engine.py -k 'workspace_uuid_mismatch' -v`
  3. Confirm all 3 tests FAIL (ValueError now swallowed by widened except)
  4. Revert the widening
  5. Re-run tests — confirm all 3 PASS
- **Gate condition:** Engine-level mismatch tests must fail when except is widened to catch ValueError; pass when except is narrow. Document the procedure outcome in the Impl+4.2 commit body.

#### Tests+5 (RED) — transition_entity_phase symmetric forwarding test
- In `plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py`, add `test_transition_entity_phase_workspace_uuid_consistent`:
  - Bootstrap two workspaces via `bootstrap_test_workspace()`
  - Call `transition_entity_phase(db, 'brainstorm:foo', 'promoted', workspace_uuid=ws_a)`
  - Assert: (1) ws_a's entity status updated, (2) ws_a's workflow_phase row updated, (3) ws_b's parallel row UNCHANGED, (4) calling with `workspace_uuid=ws_b` against ws_a row raises FR-4.1 ValueError
- **RED verification:** Test fails today — current entity_lifecycle.py:193 doesn't forward workspace_uuid; the mismatch check is never invoked.

#### Impl+5 (GREEN) — entity_lifecycle.py kwarg dict extension
- Modify `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py:185-193` per design I4 (unconditional):
  - Add `"workspace_uuid": workspace_uuid` to the `update_kwargs` dict literal
- **GREEN verification:** Tests+5's test passes. → AC-5

**Commits:** 2 (Impl+4.2, Impl+5), plus PI-6a.MUT verification noted in Impl+4.2 commit body.

**Dependencies:** PI-5.

### PI-7 — Reconcile workspace_uuid threading (FR-11)

**Goal:** Thread workspace_uuid through reconcile_apply / reconcile_frontmatter / reconcile_status.

**Work pairs:**

#### Tests+11.1/11.2 (RED) — internal-forwarding + scope-scan tests
- In `plugins/pd/hooks/lib/workflow_engine/test_reconciliation.py`, add 2 tests:
  - `test_apply_workflow_reconciliation_forwards_workspace_uuid_to_update_workflow_phase_meta_ahead`:
    - Bootstrap meta_json_ahead row; call apply with `workspace_uuid=ws_a`; mock `db.update_workflow_phase`; assert mock received `workspace_uuid=ws_a` kwarg (pins reconciliation.py:374)
  - `test_apply_workflow_reconciliation_forwards_workspace_uuid_to_update_workflow_phase_kanban_drift`:
    - Same shape, kanban-only-drift row (pins reconciliation.py:462)
- In `plugins/pd/hooks/lib/entity_registry/test_frontmatter_sync.py`, add 2 tests:
  - `test_scan_all_scopes_to_workspace`:
    - Bootstrap two workspaces with features; call `scan_all(db, artifacts_root, workspace_uuid=ws_a)`; assert reports cover ONLY ws_a's features
  - `test_scan_all_default_unscoped_returns_all_workspace_features` (NFR-3 regression pin per design R3):
    - Same fixture; call `scan_all(db, artifacts_root)` with NO workspace_uuid kwarg; assert reports cover BOTH workspaces
- **RED verification:** All 4 tests fail today — `apply_workflow_reconciliation` and `scan_all` don't currently accept workspace_uuid kwarg (TypeError on call).

#### Impl+11.1/11.2 (GREEN) — lib extensions
- Modify `plugins/pd/hooks/lib/workflow_engine/reconciliation.py:756`:
  - Add `workspace_uuid: str | None = None` kwarg to `apply_workflow_reconciliation`
  - Merge into kwargs dict at lines 367-374 per design I9: `kwargs["workspace_uuid"] = workspace_uuid` BEFORE `db.update_workflow_phase(feature_type_id, **kwargs)`
  - Add `workspace_uuid=workspace_uuid` to `db.update_workflow_phase` call at line 462
- Modify `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py:543`:
  - Add `workspace_uuid: str | None = None` kwarg to `scan_all`
  - Forward to `db.list_entities(entity_type="feature", workspace_uuid=workspace_uuid)` at line 570
- **GREEN verification:** Tests+11.1/11.2's 4 tests pass. → AC-11 partial

#### Tests+11.3/4/5 (RED) — MCP boundary forwarding tests
- In `plugins/pd/mcp/test_workflow_state_server.py`, add 3 boundary tests:
  - `test_reconcile_apply_forwards_workspace_uuid` — set `wss._workspace_uuid = ws_a`; mock `apply_workflow_reconciliation`; call async `reconcile_apply()`; assert mock received `workspace_uuid=ws_a` kwarg
  - `test_reconcile_frontmatter_forwards_workspace_uuid` — same shape; mock `scan_all`
  - `test_reconcile_status_forwards_workspace_uuid` — same shape
- **RED verification:** All 3 fail today — MCP handlers don't forward `_workspace_uuid`.

#### Impl+11.3/4/5 (GREEN) — MCP handler forwarding
- Modify `plugins/pd/mcp/workflow_state_server.py`:
  - Line 1189 `_process_reconcile_apply`: accept and forward `workspace_uuid`
  - Line 1223 `_process_reconcile_frontmatter`: accept and forward to `scan_all`
  - Line 1366 `_process_reconcile_status`: accept and forward to `scan_all` at line 1381
  - Lines 1678, 1694, 1705 (async handlers): pass `workspace_uuid=_workspace_uuid or None`
- **GREEN verification:** Tests+11.3/4/5's 3 tests pass. Total 7 tests for AC-11. → AC-11

**Commits:** 2 (Impl+11.1/11.2 lib, Impl+11.3/4/5 MCP+tests).

**Dependencies:** PI-5.

### PI-8 — Regression + dogfood + cleanup

**Goal:** Verify zero regressions (AC-12), CHANGELOG, dogfood AC-13.

#### PI-8a — Final pytest run
```bash
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/{hooks/lib,mcp} --tb=line > agent_sandbox/$(date +%Y-%m-%d)/113-validation/final.log 2>&1 || true
```

#### PI-8b — AC-12 baseline diff
```bash
diff <(grep '^FAILED' agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log | sort) \
     <(grep '^FAILED' agent_sandbox/$(date +%Y-%m-%d)/113-validation/final.log | sort)
```
**Done:** Output empty (no net-new failures). → AC-12

#### PI-8c — CHANGELOG update
Add to `[Unreleased]` section, one bullet per FR (FR-1 through FR-11). Note `.gitignore:63` removal under "Removed".

#### PI-8d — AC-13 dogfood at finish-feature
- Runs as part of `/pd:finish-feature` Step 5b (the standard QA gate emit). Required check: AFTER `/pd:finish-feature` runs, verify:
  - `ls docs/features/113-feature-112-qa-followups/.qa-gate.json` exists (committable post-FR-1.4)
  - JSON-shape check: `python -c "import json, subprocess; d=json.load(open('docs/features/113-feature-112-qa-followups/.qa-gate.json')); head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(); assert set(d.keys()) >= {'feature','head_sha','gate_run_at','ac_results','decision','reviewers'}, d.keys(); assert d['head_sha']==head, (d['head_sha'],head); print('AC-13 OK')"`
  - All `ac_results[]` entries have valid status from `STATUS_ENUM`
- **Done:** Above Python check prints `AC-13 OK`. → AC-13

#### PI-8e — Pre-finish sanity check
- `grep -nE 'docs/features/\*\*/.qa-gate.json' .gitignore` returns 0 matches (FR-1.4 confirmation)
- Test count delta: `pytest --co -q plugins/pd/ 2>/dev/null | wc -l` minus baseline-collected count is approximately matching the Verification Plan Summary sum. Not a hard gate — informational only; AC-12 is the real regression gate.

**Commits:** 1 (CHANGELOG + verification log noted in commit body).

**Dependencies:** All prior PIs.

## Total Commit Count

| PI | Commits | Notes |
|----|---------|-------|
| PI-0 | 0 | Artifact-only |
| PI-1 | 2 | Impl+1, Impl+2 (Tests+ folded in commit messages) |
| PI-2 | 4 | Impl+3.0, Impl+7, Impl+8, Impl+9 |
| PI-3 | 2 | Impl+3.2, Impl+6 |
| PI-4 | 1 | Impl+10 |
| PI-5 | 1 | Impl+4.1 (includes spec amendment for AC-4 5-test count) |
| PI-6 | 2 | Impl+4.2 (with PI-6a.MUT), Impl+5 |
| PI-7 | 2 | Impl+11.1/11.2 lib, Impl+11.3/4/5 MCP |
| PI-8 | 1 | CHANGELOG + dogfood verification |
| **Total** | **15** | Per-method incremental rollout (NFR-5) |

## Risk Tracking (from design)

| Risk | Mitigation | PI activation |
|------|------------|---------------|
| R1 mismatch ValueError breaks call sites | NFR-3 grep audit (12 callers, none pass kwarg today) | PI-5/6/7 |
| R2 FR-6 mutation pin vacuous | PI-3.MUT mutation-observability gate before Impl+6 commit | PI-3 |
| R3 scan_all default behavior change | `test_scan_all_default_unscoped_returns_all_workspace_features` regression pin | PI-7 |
| R4 qa_gate schema breaks older features | TD-8 scopes migration as out-of-scope | PI-1 |
| R5 transient inconsistency between commits | AC-12 baseline diff catches any regression | PI-0/PI-8 |
| R6 catch_warnings filter bleed | `recwarn` fixture fallback; scoped context manager | PI-4 |
| R7 spec test count drift | Verification Plan Summary table is source of truth; spec amendment commits when count changes (e.g., PI-5's +1 for direct mismatch test) | All |

## Acceptance Criteria Mapping

| AC | Tests added by | Impl by | Test path |
|----|----------------|---------|-----------|
| AC-1 | Tests+1 | Impl+1 | `qa_gate/test_emitter.py` (5 unit tests) |
| AC-2 | Tests+2 | Impl+2 | `bash plugins/pd/hooks/tests/bash-version-capture.sh` + grep |
| AC-3 | Tests+3.0 + Tests+3.2 | Impl+3.0 + Impl+3.2 | `test_workflow_state_server.py::TestListFeaturesByDefaultSingleWorkspace` (6 tests) |
| AC-4 | Tests+4.1 + Tests+4.2 | Impl+4.1 + Impl+4.2 | `test_database.py` (2) + `test_engine.py` (3) = 5 tests |
| AC-5 | Tests+5 | Impl+5 | `test_entity_lifecycle.py` (1) |
| AC-6 | Tests+6 | Impl+6 + PI-3.MUT | `test_workflow_state_server.py` (2 parametrized) |
| AC-7 | Tests+7 | Impl+7 | `test_workflow_state_server.py` (2 — filter_states_) |
| AC-8 | Tests+8 | Impl+8 | `test_server_helpers.py` (2 — parent_resolution_) |
| AC-9 | Tests+9 | Impl+9 | `test_entity_server.py` (1) |
| AC-10 | Tests+10 | Impl+10 | `test_entity_status.py` (4 parametrized) |
| AC-11 | Tests+11.1/11.2/11.3/4/5 | Impl+11.1/11.2 + Impl+11.3/4/5 | `test_workflow_state_server.py` (3) + `test_reconciliation.py` (2) + `test_frontmatter_sync.py` (2) = 7 tests |
| AC-12 | Baseline at PI-0 | Diff at PI-8b | `agent_sandbox/{date}/113-validation/` |
| AC-13 | Dogfood at PI-8d | Run /pd:finish-feature | feature 113's own `.qa-gate.json` |

**Spec amendment in PI-5:** AC-4 count changes from 4 → 5 (adds direct database-layer mismatch test per iter-1 reviewer B2).

## Out of Scope (recap)

- Migration 12, #00390, #00389, #00359, documentation tier scaffolding

## Cross-References

- Spec: `docs/features/113-feature-112-qa-followups/spec.md`
- Design: `docs/features/113-feature-112-qa-followups/design.md`
- NFR-5 dependency order: spec §NFR-5 + design Components preamble
