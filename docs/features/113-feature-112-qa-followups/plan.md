# Feature 113 — Implementation Plan

## Status
- Phase: create-plan
- Mode: standard
- Spec: `docs/features/113-feature-112-qa-followups/spec.md`
- Design: `docs/features/113-feature-112-qa-followups/design.md`

## Overview

Surgical changes across 7 source files, 2 new modules, 8 test-file extensions, 1 new test file. Per-method incremental rollout (NFR-5): each FR ships as 1-2 commits with its own test verification. Baseline captured before any code commit, AC-12 diff at the end.

**Implementation order** (per spec NFR-5 + design Components preamble):

```
PI-0   (setup)            Baseline capture (NFR-2) — single one-shot run, no FR
   │
   ├── PI-1   (validation artifacts, parallel safe)
   │   ├── FR-1 (C1: qa_gate/emitter.py + .gitignore:63 removal)
   │   └── FR-2 (C2: bash-version-capture.sh)
   │
   ├── PI-2   (defensive fixes, parallel safe)
   │   ├── FR-3.0 only (entry-point normalization at workspace_filter)
   │   ├── FR-7   (C6 part 1: narrow _filter_states_by_workspace except)
   │   ├── FR-8   (C6 part 2: narrow server_helpers.py except)
   │   └── FR-9   (C7: missing-parent ValueError)
   │
   ├── PI-3   (workspace filter completion, depends on PI-2 FR-3.0)
   │   ├── FR-3.2 + 3.3 (invalid hex raises, caller wrappers)
   │   └── FR-6   (empty-string boundary tests, depends on FR-3.0)
   │
   ├── PI-4   (entity_status sweep, independent of others)
   │   └── FR-10  (C8: conditional kwarg pattern, 4 sites)
   │
   ├── PI-5   (workspace_uuid load-bearing anchor)
   │   └── FR-4.1 (C3: extend update_workflow_phase signature) — BLOCKS PI-6, PI-7
   │
   ├── PI-6   (engine + lifecycle forwarding, depends on PI-5)
   │   ├── FR-4.2 + 4.3 (engine.py call sites)
   │   └── FR-5.1 + 5.2 (entity_lifecycle.py call site)
   │
   ├── PI-7   (reconcile threading, depends on PI-5)
   │   └── FR-11 (C9: apply_workflow_reconciliation + scan_all + handlers)
   │
   └── PI-8   (regression + cleanup)
       ├── Final pytest pass, baseline diff (AC-12)
       └── CHANGELOG + .gitignore:63 removal verification
```

## Plan Items

### PI-0 — Baseline capture (NFR-2)

**Goal:** Capture pre-implementation regression baseline at feature branch root commit.

**Steps:**
1. `mkdir -p agent_sandbox/$(date +%Y-%m-%d)/113-validation`
2. Run full pytest: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/{hooks/lib,mcp} --tb=line > agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log 2>&1` (exit code captured)
3. Verify baseline file exists and is non-empty.

**Verification:** Baseline log file present with `^FAILED` rows captured for diff comparison at PI-8.

**Dependencies:** None.

**Estimated commits:** 0 (artifact-only; baseline log lives in gitignored `agent_sandbox/`).

### PI-1 — Validation artifacts (FR-1 + FR-2)

**Goal:** Land canonical `.qa-gate.json` schema + reusable emitter + `bash-version-capture.sh` helper. Establishes evidence-emission contracts BEFORE feature 113's own QA gate runs (AC-13 dogfood prerequisite).

**Work items:**

**PI-1a — `qa_gate/` package (FR-1, component C1)**
- Create `plugins/pd/hooks/lib/qa_gate/__init__.py` (package marker, exports `STATUS_ENUM`)
- Create `plugins/pd/hooks/lib/qa_gate/emitter.py` (`emit_qa_gate(...)`, see design I1)
- Create `plugins/pd/hooks/lib/qa_gate/test_emitter.py` (validator unit test, `test_emit_qa_gate_rejects_invalid_status`)
- Remove `.gitignore:63` line `docs/features/**/.qa-gate.json` (FR-1.4)
- Run new tests; confirm pass

**PI-1b — `bash-version-capture.sh` (FR-2, component C2)**
- Create `plugins/pd/hooks/tests/bash-version-capture.sh` per design I10 (with `trap '' PIPE` + `{ ...; } 2>/dev/null || true` wrappers)
- `chmod +x` the script
- Run script in isolation; confirm 3-section output format matches FR-2.1

**Verification:**
- `pytest plugins/pd/hooks/lib/qa_gate/test_emitter.py -v` → all pass
- `bash plugins/pd/hooks/tests/bash-version-capture.sh > /tmp/bv.log && grep -c '^=== ' /tmp/bv.log` returns 3
- `git diff .gitignore` shows line 63 removed

**Dependencies:** None (greenfield).

**Estimated commits:** 2 (one per work item).

### PI-2 — Defensive fixes (FR-3.0, FR-7, FR-8, FR-9)

**Goal:** Land single-file defensive code quality fixes — independent of each other, parallel-safe.

**Work items:**

**PI-2a — FR-3.0 entry-point normalization (workflow_state_server.py:1563-1594)**
- At the top of `_resolve_list_handler_workspace_filter`, BEFORE the existing `== "*"` check, add: `if project_id == "": project_id = None`
- Add explicit comment to FR-3.1 retain branch (`# Degraded-mode: ...`)
- Add unit test `test_list_features_handler_empty_project_id_treated_as_default` to confirm empty-string treated as default
- Note: FR-3.2 and FR-3.3 deferred to PI-3 (needs FR-3.0 normalization in place first)

**PI-2b — FR-7 narrow `_filter_states_by_workspace` except (workflow_state_server.py:1614-1615, component C6)**
- Replace `except (json.JSONDecodeError, Exception):` with two narrow except clauses per design I6
- Verify `sqlite3` is imported at workflow_state_server.py (it is, at line 11)
- Verify `_make_error` is in scope (defined at line 485)
- Add 2 tests: `test_filter_states_db_error_returns_error_json`, `test_filter_states_unexpected_error_propagates`

**PI-2c — FR-8 narrow server_helpers.py except (server_helpers.py:248-255, component C6)**
- Replace `except Exception:` with `except sqlite3.OperationalError as exc:` + stderr warning per design I6
- Verify `import sys` at top of server_helpers.py (verify and add if missing)
- Verify `import sqlite3` (verify and add if missing)
- Add 2 tests: `test_register_entity_parent_resolution_db_error_orphans_with_warning`, `test_register_entity_parent_resolution_unexpected_error_propagates`

**PI-2d — FR-9 missing-parent ValueError (entity_server.py:449-450, component C7)**
- Verify current line 450 is `parent_uuid = parent_entity["uuid"] if parent_entity else None` (the silent-orphan ternary)
- Replace with explicit check per design I7
- Add test `test_create_key_result_missing_parent_raises` in `plugins/pd/hooks/lib/entity_registry/test_entity_server.py` (per spec FR-9.2 inline note)

**Verification:**
- `pytest plugins/pd/mcp/test_workflow_state_server.py -k 'empty_project_id or filter_states_' -v` → all pass
- `pytest plugins/pd/hooks/lib/entity_registry/test_server_helpers.py -k 'parent_resolution_' -v` → all pass
- `pytest plugins/pd/hooks/lib/entity_registry/test_entity_server.py -k 'create_key_result_missing_parent' -v` → 1 pass

**Dependencies:** None (each work item independent).

**Estimated commits:** 4 (one per FR).

### PI-3 — Workspace filter ValueError + empty-string boundary (FR-3.2/3.3, FR-6)

**Goal:** Complete the workspace filter narrowing (raise on invalid hex) + add empty-string boundary tests pinning the `_workspace_uuid or None` MCP idiom.

**Work items:**

**PI-3a — FR-3.2 raise ValueError on invalid hex + FR-3.3 caller wrappers**
- Modify `_resolve_list_handler_workspace_filter` to raise `ValueError` on no-matching-row
- Wrap `list_features_by_phase` (workflow_state_server.py:1619) call to helper with `try/except ValueError → _make_error`
- Wrap `list_features_by_status` (workflow_state_server.py:1643) with same wrapper
- Add 3 new tests (FR-3.3): `test_list_features_handler_db_none_returns_empty`, `test_list_features_by_phase_invalid_legacy_hex_returns_error`, `test_list_features_by_status_invalid_legacy_hex_returns_error` (the 4th, `test_list_features_handler_empty_project_id_treated_as_default`, already exists from PI-2a)

**PI-3b — FR-6 empty-string boundary tests**
- Add `test_workspace_uuid_empty_string_normalized_to_none` parametrized across 2 entry points:
  - param 1: `init_feature_state` exercises `_workspace_uuid or None` at workflow_state_server.py:1280
  - param 2: `transition_phase` exercises `_workspace_uuid or None` at workflow_state_server.py:657
- For each: set `wss._workspace_uuid = ""`, call entry-point, assert resolved to `_UNKNOWN_WORKSPACE_UUID`
- Add inline FR-6.2 comment at BOTH lines 657 and 1280
- Pre-impl verification per AC-6 fallback: remove `or None` at one line, run test, confirm failure mode is FK-or-equivalent observable error

**Verification:**
- `pytest plugins/pd/mcp/test_workflow_state_server.py::TestListFeaturesByDefaultSingleWorkspace -v` → 6 pass (2 existing + 4 new per FR-3.3)
- `pytest plugins/pd/mcp/test_workflow_state_server.py -k 'workspace_uuid_empty_string_normalized_to_none' -v` → 2 parametrized sub-tests pass

**Dependencies:** PI-2a (FR-3.0 entry-point normalization must land first so empty-string falls through correctly).

**Estimated commits:** 2 (FR-3 completion + FR-6).

### PI-4 — `entity_status.py` conditional-kwarg sweep (FR-10)

**Goal:** Eliminate `DeprecationWarning` on post-FR-2 happy paths.

**Work items:**

**PI-4a — Apply conditional pattern at 4 sites (component C8)**
- Edit `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py` at lines 47, 72, 189, 320 per design I8
- Verify lines 175 and 316 unchanged (already correct)
- Add parametrized test `test_sync_entity_statuses_no_deprecation_warning_on_happy_path` covering all 4 sites
- Use `warnings.catch_warnings()` + `simplefilter('error', DeprecationWarning)` per design R6 (scoped to test body — see design R6 critical note)
- Fallback to `recwarn` fixture if catch_warnings approach has filter-bleed issues

**Verification:**
- `pytest plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py -k 'no_deprecation_warning' -v` → 4 parametrized sub-tests pass

**Dependencies:** None (independent sweep).

**Estimated commits:** 1.

### PI-5 — `update_workflow_phase` signature extension (FR-4.1, anchor)

**Goal:** Land the load-bearing kwarg + mismatch check. This is the dependency anchor for PI-6 and PI-7.

**Work items:**

**PI-5a — Extend `update_workflow_phase` (component C3)**
- Modify `plugins/pd/hooks/lib/entity_registry/database.py:4866-4944` per design I2
- Add `workspace_uuid: str | None = None` to signature
- When non-None: `SELECT workspace_uuid FROM workflow_phases WHERE type_id = ?`; raise `ValueError(f"workspace_uuid mismatch for {type_id}: stored={existing!r}, provided={workspace_uuid!r}")` on mismatch
- Do NOT add `workspace_uuid` to UPDATE SET clause (immutable post-Migration-11)
- Add test `test_update_workflow_phase_does_not_mutate_workspace_uuid_column` in test_database.py per design TD-7 (pre/post SELECT pattern from test_frontmatter_sync.py:1768-1795)

**Verification:**
- `pytest plugins/pd/hooks/lib/entity_registry/test_database.py -k 'does_not_mutate_workspace_uuid' -v` → 1 pass

**Dependencies:** None.

**Estimated commits:** 1.

### PI-6 — Engine + lifecycle forwarding (FR-4.2/4.3 + FR-5/5.2)

**Goal:** Make the FR-4.1 mismatch check load-bearing across all transition_phase/complete_phase/transition_entity_phase call paths.

**Work items:**

**PI-6a — Engine forwarding (FR-4.2, component C4)**
- Modify `plugins/pd/hooks/lib/workflow_engine/engine.py`:
  - Line 100-103: `transition_phase`'s `update_workflow_phase` call adds `workspace_uuid=workspace_uuid`
  - Line 166-170: `complete_phase`'s non-terminal `update_workflow_phase` call adds `workspace_uuid=workspace_uuid`
- Add 3 new tests in `test_engine.py`:
  - `test_transition_phase_workspace_uuid_mismatch_raises` (use `pytest.raises(ValueError, match="workspace_uuid mismatch")` per design C4)
  - `test_complete_phase_non_terminal_workspace_uuid_pinned`
  - `test_complete_phase_terminal_workspace_uuid_pinned`
- Pre-impl verification per design C4: temporarily widen the engine's except to `(sqlite3.Error, ValueError)` and confirm the mismatch tests FAIL; revert before committing.

**PI-6b — Entity lifecycle forwarding (FR-5.1/5.2, component C4)**
- Modify `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py:185-193` per design I4
  - Unconditional add: `update_kwargs["workspace_uuid"] = workspace_uuid`
- Add test `test_transition_entity_phase_workspace_uuid_consistent` in `test_entity_lifecycle.py` per spec FR-5.2
  - Bootstrap two workspaces; assert symmetric propagation; assert cross-workspace mismatch raises ValueError

**Verification:**
- `pytest plugins/pd/hooks/lib/workflow_engine/test_engine.py -k 'workspace_uuid' -v` → 3 new tests pass
- `pytest plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py::test_transition_entity_phase_workspace_uuid_consistent -v` → 1 pass

**Dependencies:** PI-5 (FR-4.1's extended signature).

**Estimated commits:** 2 (one per FR cluster).

### PI-7 — Reconcile workspace_uuid threading (FR-11)

**Goal:** Thread workspace_uuid through reconcile_apply / reconcile_frontmatter / reconcile_status.

**Work items:**

**PI-7a — Library extensions (FR-11.1, FR-11.2, component C9)**
- Modify `plugins/pd/hooks/lib/workflow_engine/reconciliation.py:756` — add `workspace_uuid` kwarg to `apply_workflow_reconciliation`. Merge into kwargs dict per design I9 (avoid `**kwargs, workspace_uuid=...` syntax).
- Modify `plugins/pd/hooks/lib/entity_registry/frontmatter_sync.py:543` — add `workspace_uuid` kwarg to `scan_all`. Forward to `db.list_entities` at line 570.

**PI-7b — MCP handler forwarding (FR-11.3, FR-11.4)**
- Modify `plugins/pd/mcp/workflow_state_server.py:1189` — `_process_reconcile_apply` accepts and forwards `workspace_uuid`
- Modify `plugins/pd/mcp/workflow_state_server.py:1223` — `_process_reconcile_frontmatter` accepts and forwards to `scan_all`
- Modify `plugins/pd/mcp/workflow_state_server.py:1366` — `_process_reconcile_status` accepts and forwards to `scan_all`
- Modify async handlers at lines 1678, 1694, 1705 — pass `workspace_uuid=_workspace_uuid or None`

**PI-7c — Test additions (FR-11.5)**
- Add 3 boundary-pin tests in `test_workflow_state_server.py`:
  - `test_reconcile_apply_forwards_workspace_uuid`
  - `test_reconcile_frontmatter_forwards_workspace_uuid`
  - `test_reconcile_status_forwards_workspace_uuid`
- Add 2 internal-forwarding tests in `test_reconciliation.py`:
  - `test_apply_workflow_reconciliation_forwards_workspace_uuid_to_update_workflow_phase_meta_ahead`
  - `test_apply_workflow_reconciliation_forwards_workspace_uuid_to_update_workflow_phase_kanban_drift`
- Add 2 scope-scan tests in `test_frontmatter_sync.py`:
  - `test_scan_all_scopes_to_workspace`
  - `test_scan_all_default_unscoped_returns_all_workspace_features` (NFR-3 backward-compat regression pin)

**Verification:**
- `pytest -k 'reconcile_.*_forwards_workspace_uuid or apply_workflow_reconciliation_forwards or scan_all_scopes_to_workspace or scan_all_default_unscoped' plugins/pd/{mcp,hooks/lib}/ -v` → 7 new tests pass

**Dependencies:** PI-5 (FR-4.1's stable update_workflow_phase signature).

**Estimated commits:** 2 (lib extensions + MCP/test additions).

### PI-8 — Regression + cleanup

**Goal:** Verify zero regressions (AC-12) and finalize CHANGELOG.

**Work items:**

**PI-8a — Final pytest run + baseline diff**
- Run full pytest: `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/{hooks/lib,mcp} --tb=line > agent_sandbox/$(date +%Y-%m-%d)/113-validation/final.log 2>&1`
- Diff against baseline: `diff <(grep '^FAILED' agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log | sort) <(grep '^FAILED' agent_sandbox/$(date +%Y-%m-%d)/113-validation/final.log | sort)`
- AC-12 satisfied iff ZERO new FAILED lines

**PI-8b — CHANGELOG update**
- Add entries to `[Unreleased]` section of CHANGELOG.md, one bullet per FR (FR-1 through FR-11)
- Note .gitignore:63 removal under "Removed"

**PI-8c — Pre-finish sanity check**
- Confirm `.gitignore:63` is removed (`grep -n 'qa-gate' .gitignore` returns no match for `docs/features/**`)
- Confirm new test count matches AC summaries (`pytest --co -q plugins/pd/ | wc -l` delta vs baseline ≈ +20)

**Verification:**
- `diff` output empty (no new failures)
- `git diff HEAD~N CHANGELOG.md` shows all 11 FR entries

**Dependencies:** All prior PIs.

**Estimated commits:** 1.

## Total Commit Count

| PI | Commits | Notes |
|----|---------|-------|
| PI-0 | 0 | Artifact-only, no source change |
| PI-1 | 2 | qa_gate + bash-version-capture |
| PI-2 | 4 | FR-3.0, FR-7, FR-8, FR-9 |
| PI-3 | 2 | FR-3 completion + FR-6 |
| PI-4 | 1 | FR-10 sweep |
| PI-5 | 1 | FR-4.1 anchor |
| PI-6 | 2 | FR-4.2/4.3 + FR-5/5.2 |
| PI-7 | 2 | FR-11 lib + MCP/tests |
| PI-8 | 1 | CHANGELOG + verification |
| **Total** | **15** | Per-method incremental rollout (NFR-5) |

## Risk Tracking (from design)

| Risk | Mitigation | PI where activated |
|------|------------|---------------------|
| R1 mismatch ValueError breaks call sites | Audit-grep + NFR-3 narrowing — verified zero current callers pass workspace_uuid | PI-5, PI-6, PI-7 |
| R2 FR-6 mutation pin vacuous | AC-6 fallback clause + pre-impl manual verification | PI-3b |
| R3 scan_all default behavior change | Regression pin test `test_scan_all_default_unscoped_returns_all_workspace_features` | PI-7c |
| R4 qa_gate schema breaks older features | TD-8 scopes migration as out-of-scope | PI-1a |
| R5 transient inconsistency between PIs | AC-12 baseline diff catches any regression | PI-0 baseline + PI-8 diff |
| R6 DeprecationWarning suppression pattern bleed | `catch_warnings` context-manager-scoped; `recwarn` fallback | PI-4 |
| R7 spec test count drift during impl | Verification Plan Summary is source of truth; patch in same commit | All PIs |

## Acceptance Criteria Mapping

| AC | Verified by PI | Test path |
|----|----------------|-----------|
| AC-1 | PI-1a | `qa_gate/test_emitter.py::test_emit_qa_gate_rejects_invalid_status` + dogfood at PI-8 |
| AC-2 | PI-1b | `bash plugins/pd/hooks/tests/bash-version-capture.sh` + grep |
| AC-3 | PI-2a + PI-3a | `test_workflow_state_server.py::TestListFeaturesByDefaultSingleWorkspace` |
| AC-4 | PI-5 + PI-6a | `test_database.py` + `test_engine.py` |
| AC-5 | PI-6b | `test_entity_lifecycle.py` |
| AC-6 | PI-3b | `test_workflow_state_server.py` (2 parametrized) |
| AC-7 | PI-2b | `test_workflow_state_server.py` (filter_states_) |
| AC-8 | PI-2c | `test_server_helpers.py` (parent_resolution_) |
| AC-9 | PI-2d | `test_entity_server.py` |
| AC-10 | PI-4 | `test_entity_status.py` (no_deprecation_warning) |
| AC-11 | PI-7c | `test_workflow_state_server.py` + `test_reconciliation.py` + `test_frontmatter_sync.py` |
| AC-12 | PI-0 baseline + PI-8 diff | `agent_sandbox/{date}/113-validation/` |
| AC-13 | PI-8 (dogfood at finish-feature) | feature 113's own `.qa-gate.json` |

## Out of Scope (recap from spec)

- Migration 12, #00390 (FR-4 alias drop), #00389 (`_project_id` removal), #00359 (uuid7), documentation tier scaffolding

## Cross-References

- Spec: `docs/features/113-feature-112-qa-followups/spec.md`
- Design: `docs/features/113-feature-112-qa-followups/design.md`
- NFR-5 dependency order: spec §NFR-5 + design Components preamble
