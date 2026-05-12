# Feature 113 — Feature 112 QA-Gate Followups

## Status
- Phase: specify (iter 2)
- Mode: standard
- Source: 11 MED-severity findings filed in `docs/backlog.md` under "From Feature 112 Pre-Release QA Findings (2026-05-12)" section (entries #00391 through #00401)
- Brainstorm: skipped — scope is well-specified by backlog entries with concrete file:line targets and fix descriptions
- Out-of-scope: #00390 (FR-4 alias drop + 30-test migration) and #00389 (`_project_id` lazy global removal)

## Conventions

**Mutation pin:** Throughout this spec, "mutation pin" means a unit test whose pass condition is broken by removing or altering a specific line/kwarg/exception clause. The test serves as a regression guard against future contributors reverting the fix unintentionally. It does NOT imply automated mutation testing (`mutmut` etc.) — each pin is a hand-authored pytest assertion calibrated against a specific code shape.

## Problem Statement

Feature 112 (workspace-identity-cleanup, released as v4.17.1) shipped with 11 MED-severity findings from its pre-release adversarial QA gate. The findings cluster into four themes:

1. **Validation-artifact compliance** (#00391, #00392) — `.qa-gate.json` schema/location drift and `bash-version.log` incomplete format violate the documented AC-9 / AC-12 contracts.
2. **Workspace isolation contract bypass** (#00393, #00397, #00399) — silent fallbacks degrade single-workspace defaults to cross-workspace or orphan-parent under degenerate inputs, violating AC-7 / AC-3c.
3. **Asymmetric workspace_uuid propagation** (#00394, #00395, #00401) — engines and reconcile handlers accept the kwarg but don't thread it through every relevant `db.update_*` write call.
4. **Defensive-coding quality** (#00396, #00398, #00400) — empty-string boundary coverage missing, bare-except handlers swallow `OperationalError`, post-FR-2 happy paths trigger spurious `DeprecationWarning`s.

Total estimated change: ~150-250 LOC + ~15 new tests, no schema migration (Migration 11 column already provides the substrate).

## FR ↔ Backlog Traceability

| FR | Backlog | One-line scope |
|----|---------|----------------|
| FR-1 | #00391 | `.qa-gate.json` canonical schema + location + helper module |
| FR-2 | #00392 | `bash-version.log` 3-line AC-12 format helper script |
| FR-3 | #00393 | `_resolve_list_handler_workspace_filter` 3 path-coverage tests + AC-7 ValueError restoration |
| FR-4 | #00394 | `WorkflowStateEngine` workspace_uuid load-bearing via extended `update_workflow_phase` |
| FR-5 | #00395 | `transition_entity_phase` symmetric workspace_uuid through extended `update_workflow_phase` |
| FR-6 | #00396 | Empty-string boundary tests at workspace_uuid normalization sites |
| FR-7 | #00397 | `_filter_states_by_workspace` narrowed exception handler |
| FR-8 | #00398 | `server_helpers.py` parent-resolution narrowed exception handler |
| FR-9 | #00399 | `_process_create_key_result` missing-parent ValueError |
| FR-10 | #00400 | `entity_status.py` 4 `update_entity` sites conditional-kwarg pattern |
| FR-11 | #00401 | `reconcile_*` MCP handlers thread workspace_uuid through underlying engine fns |

## Functional Requirements

### FR-1 — `.qa-gate.json` reusable emitter + schema compliance (#00391)

**Pre-state:** Feature 112 emitted `.qa-gate.json` to `agent_sandbox/2026-05-12/112-validation/qa-gate.json` (gitignored, wrong directory) with freeform `status: "pass"|"partial"|"deferred"` and evidence-prose. `.gitignore:63` excludes `docs/features/**/.qa-gate.json`.

**Post-state:**

**FR-1.0 (helper module location):** `plugins/pd/hooks/lib/qa_gate/emitter.py` is the canonical home for the QA-gate JSON emitter. Tested at `plugins/pd/hooks/lib/qa_gate/test_emitter.py`. `finish-feature.md` Step 5b uses the emitter via `from qa_gate.emitter import emit_qa_gate`. Module-level is preferred over inline because finish-feature runs this on every future feature (2+ consumers).

**FR-1.1 (status enum validator):** `emit_qa_gate(...)` raises `ValueError` on any per-entry `status` value outside the documented enum:
```
status ∈ {"passed", "deferred", "n_a", "conditional_skipped"}
```

**FR-1.2 (per-entry keys):** Every entry in `ac_results[]` carries:
- `id: str` (e.g., `"AC-1"`)
- `status: str` (one of the enum above)
- `evidence: str` (free-text test path or grep result, ≤500 chars)
- `condition: str` (default `""`; non-empty when `status == "conditional_skipped"`)
- `backlog_ref: str | null` (default `null`; 5-digit backlog ID when applicable)

**FR-1.3 (head_sha idempotency):** Root-level `head_sha` MUST equal `git rev-parse HEAD` at emit time. Re-emission with same HEAD SHA is a no-op (existing feature 112 idempotency contract retained).

**FR-1.4 (gitignore removal):** `.gitignore:63`'s `docs/features/**/.qa-gate.json` line is REMOVED. The QA-gate JSON for each feature becomes committable evidence at `docs/features/{id}-{slug}/.qa-gate.json`. NFR-4 (no new gitignore entries) is preserved; this is an explicit REMOVAL.

**Verification (AC-1):** Feature 113's own `/pd:finish-feature` produces `docs/features/113-feature-112-qa-followups/.qa-gate.json` matching FR-1.1/1.2/1.3. Verified by JSON-shape inspection + validator unit test (`test_emit_qa_gate_rejects_invalid_status`).

### FR-2 — `bash-version.log` three-line format helper (#00392)

**Pre-state:** Feature 112 shipped `bash-version.log` containing only test-hooks.sh stdout (114/114 pass). Missing required lines.

**Post-state:**

**FR-2.0 (helper script):** `plugins/pd/hooks/tests/bash-version-capture.sh` is the canonical capture script. Called from `finish-feature.md` Step 5b (or wherever the AC-12 evidence is produced).

**FR-2.1 (output format):** Three section headers, each with one body block:
```
=== Host bash --version ===
<stdout of `bash --version`>
=== /bin/bash --version ===
<stdout of `/bin/bash --version`>
=== /bin/bash plugins/pd/hooks/tests/test-hooks.sh (exit=<RC>) ===
<tail -20 of test-hooks.sh stdout under explicit /bin/bash>
```

**FR-2.2 (exit code):** Script exits 0 only when the AC-12 line 3 invocation under `/bin/bash` exits 0. Otherwise the script captures the failing tail and exits with the test-hooks.sh exit code.

**FR-2.3 (output path):** Writes to `docs/features/{id}-{slug}/bash-version.log` (same directory as `.qa-gate.json`, committable).

**Verification (AC-2):** `grep -c '^=== ' docs/features/113-feature-112-qa-followups/bash-version.log` returns `3`.

### FR-3 — `_resolve_list_handler_workspace_filter` path coverage + AC-7 restoration (#00393)

**Pre-state:** `plugins/pd/mcp/workflow_state_server.py:1580-1594`. Function has 5 distinct paths; only 2 covered by `TestListFeaturesByDefaultSingleWorkspace`. Three paths silently degrade to cross-workspace:
- `_db is None` returns None (cross-workspace fallback, intentional degraded mode)
- legacy hex with no matching `workspaces.project_id_legacy` row → ValueError caught → returns None
- `project_id == ""` → falls into JOIN-resolve branch → ValueError → returns None

**Post-state:**

**FR-3.0 (entry-point normalization order):** At the top of `_resolve_list_handler_workspace_filter`, BEFORE the existing `project_id == "*"` check:
```python
if project_id == "":
    project_id = None
```
This ensures empty string falls through to the default-workspace branch and does NOT reach FR-3.2's new ValueError raise.

**FR-3.1 (db-None retained, documented):** When `_db is None`: continue to return None (degraded mode — DB unavailable, can't filter). Add explicit comment: `# Degraded-mode: no DB → cross-workspace fallback is intentional, surfaced via _check_db_available upstream`.

**FR-3.2 (invalid legacy hex raises):** When legacy hex doesn't match any `workspaces.project_id_legacy` row: change behavior from silent None to `raise ValueError(f"No workspace found for project_id={project_id!r}")`. Caller MCP handlers (`list_features_by_phase` at workflow_state_server.py:1637 and `list_features_by_status` at the parallel location) wrap the helper call in `try/except ValueError` and return `_make_error(error_type="invalid_project_id", message=str(exc), recovery_hint="Pass project_id='*' for cross-workspace OR omit for current-workspace default")`.

**FR-3.3 (test additions):** Add 3 new tests in `plugins/pd/mcp/test_workflow_state_server.py::TestListFeaturesByDefaultSingleWorkspace`:
- `test_list_features_handler_db_none_returns_empty` (FR-3.1 pin — degraded mode returns []  rather than crashing)
- `test_list_features_handler_invalid_legacy_hex_returns_error` (FR-3.2 pin — asserts `error_type == "invalid_project_id"` JSON)
- `test_list_features_handler_empty_project_id_treated_as_default` (FR-3.0 pin — empty string === None, single-workspace default)

**Verification (AC-3):** `pytest plugins/pd/mcp/test_workflow_state_server.py::TestListFeaturesByDefaultSingleWorkspace -v` shows 5 passing tests (2 existing + 3 new). Mutation pin: removing the FR-3.2 ValueError raise breaks `test_list_features_handler_invalid_legacy_hex_returns_error`.

### FR-4 — `WorkflowStateEngine` workspace_uuid load-bearing forwarding (#00394)

**Pre-state (corrected from iter 1):** Migration 11 ALREADY added `workflow_phases.workspace_uuid` column (database.py:2043-2056) with FK to `workspaces.uuid`, an autofill trigger `wp_autofill_workspace_uuid` (line 2063), and `wp_reject_orphaned_insert` (line 2079). The column EXISTS and is currently populated via trigger from `entities.workspace_uuid` on INSERT. However, `update_workflow_phase` (database.py:4866-4934) does NOT currently expose `workspace_uuid` as an updatable kwarg. `WorkflowStateEngine.transition_phase` (engine.py:78-115) accepts `workspace_uuid` kwarg but never forwards to `db.update_workflow_phase`. `complete_phase` (engine.py:117-194) forwards only when `phase=='finish'` (line 176-177); the intermediate-phase path drops the kwarg.

**Post-state — load-bearing option chosen (option a from spec iter 1, locked):**

**FR-4.1 (extend `update_workflow_phase`):** Add `workspace_uuid: str | None = None` to `update_workflow_phase`'s signature. When provided AND non-None, the implementation:
1. SELECTs the existing row's `workspace_uuid` from `workflow_phases` WHERE `type_id = ?`
2. If existing != provided → raise `ValueError(f"workspace_uuid mismatch for {type_id}: stored={existing!r}, provided={workspace_uuid!r}")`
3. If equal: proceed with normal UPDATE (workspace_uuid column unchanged; not in the UPDATE SET clause since it's immutable post-migration)

When `workspace_uuid is None`: existing behavior preserved (no mismatch check).

This makes the kwarg load-bearing: it acts as a read-side workspace assertion that prevents cross-workspace writes via a misrouted type_id.

**FR-4.2 (forward through engine):** `WorkflowStateEngine.transition_phase` and `complete_phase` forward `workspace_uuid` to every `db.update_workflow_phase` call:
- `engine.py:100-103` (transition_phase's update_workflow_phase): add `workspace_uuid=workspace_uuid`
- `engine.py:166-170` (complete_phase non-terminal update_workflow_phase): add `workspace_uuid=workspace_uuid`

Existing terminal `db.update_entity` forwarding (line 173-174, `phase == "finish"` path) is unchanged.

**FR-4.3 (test additions):** Add 2 tests in `plugins/pd/hooks/lib/workflow_engine/test_engine.py`:
- `test_transition_phase_workspace_uuid_mismatch_raises` — bootstraps two workspaces with same `type_id`, calls `engine.transition_phase(type_id, "design", workspace_uuid=ws_b)` where the row is scoped to ws_a; asserts ValueError raised with mismatch message.
- `test_complete_phase_non_terminal_workspace_uuid_pinned` — same shape for non-terminal complete_phase.

**Verification (AC-4):** `pytest plugins/pd/hooks/lib/workflow_engine/test_engine.py -k 'workspace_uuid' -v` shows 2 new tests passing. Mutation pin (now semantically real): removing `workspace_uuid=workspace_uuid` forwarding at engine.py:100 OR engine.py:166 causes the mismatch tests to silently succeed when they should raise, failing the assertion.

### FR-5 — `transition_entity_phase` symmetric workspace_uuid (#00395)

**Pre-state:** `plugins/pd/hooks/lib/entity_registry/entity_lifecycle.py:178-188` forwards `workspace_uuid` to `db.update_entity` at line 183 but NOT to `db.update_workflow_phase` at line 188.

**Post-state:**

**FR-5.1 (symmetric forwarding):** Once FR-4.1 extends `update_workflow_phase` to accept `workspace_uuid`, `transition_entity_phase` forwards the kwarg to BOTH `db.update_entity` (line 183) AND `db.update_workflow_phase` (line 188). Symmetric scoping via the FR-4.1 mismatch check.

**FR-5.2 (test addition):** Add `test_transition_entity_phase_workspace_uuid_consistent` in `plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py`. Bootstraps two workspaces; calls `transition_entity_phase(db, 'brainstorm:foo', 'promoted', workspace_uuid=ws_a)`. Asserts: (1) ws_a's entity status updated, (2) ws_a's workflow_phase row updated, (3) ws_b's parallel row UNCHANGED (no cross-workspace leak), (4) calling with `workspace_uuid=ws_b` against a ws_a row raises FR-4.1's ValueError.

**Verification (AC-5):** `pytest plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py::test_transition_entity_phase_workspace_uuid_consistent -v` → 1 test passes. Mutation pin: removing the kwarg from EITHER `db.update_entity` OR `db.update_workflow_phase` call inside `transition_entity_phase` causes the corresponding assertion in the test to fail.

### FR-6 — Empty-string boundary coverage (#00396)

**Pre-state:** No test exercises `_workspace_uuid == ""` at any of the 14 MCP write sites. (`project_id == ""` is covered by FR-3.0+FR-3.3 above.)

**Post-state:**

**FR-6.1 (representative write-site test):** Add `test_init_feature_state_unset_workspace_global_falls_back_to_project_id` in `plugins/pd/mcp/test_workflow_state_server.py`:
- Sets `wss._workspace_uuid = ""` (unset state)
- Calls `init_feature_state(...)`
- Asserts the registered entity has `workspace_uuid == _UNKNOWN_WORKSPACE_UUID` (the canonical unknown workspace, resolved from `project_id="__unknown__"` fallback at server_helpers.py:262)
- Pins the `_workspace_uuid or None` normalization at the kwarg boundary

**FR-6.2 (doc comment):** Add an inline comment at the FIRST `_workspace_uuid or None` occurrence in `workflow_state_server.py` (around line 657):
```python
# Empty-string == unset == None at db.* kwarg boundary; downstream
# defaults to project_id="__unknown__" → _UNKNOWN_WORKSPACE_UUID.
```

**Verification (AC-6):** `pytest -k 'unset_workspace_global' plugins/pd/mcp/test_workflow_state_server.py -v` → 1 test passes. Mutation pin: replacing `_workspace_uuid or None` with `_workspace_uuid` (dropping the `or None`) at workflow_state_server.py:657 causes the FK constraint to fail on empty-string workspace_uuid, breaking the test.

### FR-7 — Narrow `_filter_states_by_workspace` exception handler (#00397)

**Pre-state:** `plugins/pd/mcp/workflow_state_server.py:1614-1615` catches `(json.JSONDecodeError, Exception)`. Exception is the base; JSONDecodeError redundant. Bare-except swallows `sqlite3.OperationalError` and returns unfiltered cross-workspace JSON silently.

**Post-state:**

**FR-7.1 (narrow except):** Replace `except (json.JSONDecodeError, Exception):` with:
```python
except json.JSONDecodeError:
    return results_json  # malformed JSON from engine — return as-is
except sqlite3.OperationalError as exc:
    return _make_error("db_unavailable", str(exc), "Database temporarily unavailable; retry shortly")
```
All other exceptions PROPAGATE (no `except Exception` clause).

**FR-7.2 (test additions):** Add 2 tests in `plugins/pd/mcp/test_workflow_state_server.py`:
- `test_filter_states_db_error_returns_error_json` — mock `_db.get_entity` to raise `sqlite3.OperationalError`; assert `_make_error` JSON shape returned.
- `test_filter_states_unexpected_error_propagates` — mock `_db.get_entity` to raise `RuntimeError("unexpected")`; assert RuntimeError propagates out of the helper (`pytest.raises(RuntimeError)`).

**Verification (AC-7):** `pytest -k 'filter_states_' plugins/pd/mcp/test_workflow_state_server.py -v` → 2 new tests pass. Mutation pin: broadening to `except Exception` causes the RuntimeError propagation test to fail (test expects raise, would-be-broadened handler catches and returns the unfiltered JSON). `grep -nE 'except.*Exception' plugins/pd/mcp/workflow_state_server.py | grep -v '^[^:]+:#'` returns 0 matches at the touched lines.

### FR-8 — Narrow `server_helpers.py` parent resolution exception handler (#00398)

**Pre-state:** `plugins/pd/hooks/lib/entity_registry/server_helpers.py:248-255` bare-except during parent_type_id → parent_uuid resolution. Swallows all exceptions including `OperationalError`, registers orphan entity silently with no caller signal.

**Post-state:**

**FR-8.1 (narrow except):** Replace bare `except Exception:` with:
```python
except sqlite3.OperationalError as exc:
    print(
        f"server_helpers: parent resolution failed under DB error: {exc} "
        f"— registering as orphan",
        file=sys.stderr,
    )
    # Fall through with parent_uuid=None
```
Other exception types (ValueError, KeyError, etc.) PROPAGATE to caller.

**FR-8.2 (test additions):** Add 2 tests in `plugins/pd/hooks/lib/entity_registry/test_server_helpers.py`:
- `test_register_entity_parent_resolution_db_error_orphans_with_warning` — mock `db.get_entity` to raise `sqlite3.OperationalError`; capture stderr; assert entity registered with `parent_uuid=None` AND stderr contains the warning text.
- `test_register_entity_parent_resolution_unexpected_error_propagates` — mock to raise `RuntimeError`; assert propagation.

**Verification (AC-8):** `pytest -k 'parent_resolution_' plugins/pd/hooks/lib/entity_registry/test_server_helpers.py -v` → 2 new tests pass. Mutation pin: broadening to `except Exception` OR removing the stderr warning causes one of the tests to fail.

### FR-9 — `_process_create_key_result` missing-parent surfacing (#00399)

**Pre-state:** `plugins/pd/mcp/entity_server.py:449-450`. If `db.get_entity(parent_type_id)` returns None (parent doesn't exist), `parent_uuid` silently stays None and the KR registers without a parent — violating AC-3c (canonical-parent_uuid contract requires explicit linkage).

**Post-state:**

**FR-9.1 (explicit check):** Add explicit check after `parent_entity = db.get_entity(parent_type_id)`:
```python
if parent_entity is None:
    raise ValueError(f"Parent entity not found: {parent_type_id!r}")
```
The MCP `create_key_result` tool catches this ValueError at entity_server.py:1129-1130 (existing `except Exception` clause) and returns the error JSON. No new error-path code needed at the MCP layer.

**FR-9.2 (test addition):** Add `test_create_key_result_missing_parent_raises` in `plugins/pd/hooks/lib/entity_registry/test_entity_server.py`:
- Bootstrap DB without registering the parent objective
- Call `_process_create_key_result(db, parent_type_id="objective:nonexistent", ...)`
- Assert `ValueError` raised with the expected message

**Verification (AC-9):** `pytest -k 'create_key_result_missing_parent' plugins/pd/hooks/lib/entity_registry/test_entity_server.py -v` → 1 test passes. Mutation pin: removing the `if parent_entity is None: raise ValueError(...)` check causes orphan KR registration; the test fails.

### FR-10 — Conditional kwarg pattern at `entity_status.py` 4 `update_entity` sites (#00400)

**Pre-state (verified at iter 2):** `plugins/pd/hooks/lib/reconciliation_orchestrator/entity_status.py` has 6 `register_entity`/`update_entity` call sites:
- Line 47 (`update_entity` in `_sync_meta_json_entities` archive branch): passes BOTH `project_id` AND `workspace_uuid` UNCONDITIONALLY — **TARGET**
- Line 72 (`update_entity` in `_sync_meta_json_entities` status-change branch): same — **TARGET**
- Line 168-176 (`register_entity` in `_sync_brainstorm_entities`): ALREADY uses conditional pattern at line 175 — no change needed
- Line 189 (`update_entity` in `_sync_brainstorm_entities` archive branch): passes BOTH UNCONDITIONALLY — **TARGET**
- Line 309-317 (`register_entity` in `_sync_backlog_md_entities`): ALREADY uses conditional pattern at line 316 — no change needed
- Line 320 (`update_entity` in `_sync_backlog_md_entities` status-change branch): passes BOTH UNCONDITIONALLY — **TARGET**

**Post-state:**

**FR-10.1 (apply conditional pattern at 4 sites):** Lines 47, 72, 189, 320 each change `project_id=project_id, workspace_uuid=workspace_uuid` → `project_id=project_id if workspace_uuid is None else None, workspace_uuid=workspace_uuid`. Pattern matches the already-correct register_entity sites at lines 175 and 316.

**FR-10.2 (test addition):** Add `test_sync_entity_statuses_no_deprecation_warning_on_happy_path` in `plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py`:
- Bootstrap DB with a real workspace_uuid populated
- Write a feature .meta.json that triggers a status change (forcing the line-72 path)
- Call `sync_entity_statuses(db, ..., workspace_uuid=<real-uuid>)`
- Wrap in `warnings.catch_warnings()` + `simplefilter('error', DeprecationWarning)`
- Assert no DeprecationWarning raised

Parametrize to also exercise the archive branch (line 47), the brainstorm archive (line 189), and the backlog status change (line 320). 4 sub-tests, one per fixed site.

**Verification (AC-10):** `pytest -k 'no_deprecation_warning' plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py -v` → 4 parametrized sub-tests pass. Mutation pin: removing the conditional from ANY ONE of the 4 sites re-introduces the DeprecationWarning for the matching parametrized case.

### FR-11 — `reconcile_*` MCP handlers thread workspace_uuid (#00401)

**Pre-state:** `plugins/pd/mcp/workflow_state_server.py:1688-1712` — `reconcile_apply`, `reconcile_frontmatter`, `reconcile_status` MCP handlers do not forward `_workspace_uuid` to their `_process_*` helpers. Per handler-audit.md classification (`read+write`), they should.

**Post-state — option (a) chosen and locked: thread workspace_uuid through reconciliation:**

**FR-11.1 (extend `apply_workflow_reconciliation`):** Add `workspace_uuid: str | None = None` kwarg to `apply_workflow_reconciliation(...)` in `workflow_engine/reconciliation.py`. Forward to every `db.update_entity` / `db.upsert_workflow_phase` call inside its body (concrete call sites identified during design phase).

**FR-11.2 (extend `scan_all`):** Add `workspace_uuid: str | None = None` kwarg to `scan_all(...)` in `entity_registry/frontmatter_sync.py`. Forward to every `db.update_entity` call inside. (Note: existing `ingest_header` already accepts the kwarg per feature 112 / FR-2.)

**FR-11.3 (extend `_process_reconcile_status`):** Add `workspace_uuid: str | None = None` kwarg. Forward to underlying engine calls.

**FR-11.4 (MCP handler forwarding):** `reconcile_apply`, `reconcile_frontmatter`, and `reconcile_status` MCP handlers each pass `workspace_uuid=_workspace_uuid or None` to their `_process_*` helpers.

**FR-11.5 (test additions):** Add 3 tests in `plugins/pd/mcp/test_workflow_state_server.py`:
- `test_reconcile_apply_forwards_workspace_uuid` — bootstrap, set `wss._workspace_uuid`, call `reconcile_apply()`, mock `apply_workflow_reconciliation` to capture kwarg; assert received workspace_uuid.
- `test_reconcile_frontmatter_forwards_workspace_uuid` — same shape for frontmatter.
- `test_reconcile_status_forwards_workspace_uuid` — same shape for status.

**Verification (AC-11):** `pytest -k 'reconcile_.*_forwards_workspace_uuid' plugins/pd/mcp/test_workflow_state_server.py -v` → 3 new tests pass. Mutation pin: removing `workspace_uuid=_workspace_uuid or None` from any of the 3 handler bodies fails the corresponding test.

## Acceptance Criteria

**AC-1:** `.qa-gate.json` for feature 113 located at `docs/features/113-feature-112-qa-followups/.qa-gate.json` (committable; FR-1.4 removed gitignore line). Validator (`plugins/pd/hooks/lib/qa_gate/emitter.py::emit_qa_gate`) accepts only the 4-value status enum; per-entry `condition` and `backlog_ref` keys present. `head_sha` matches `git rev-parse HEAD`. Validator unit test `test_emit_qa_gate_rejects_invalid_status` raises ValueError for status outside the enum.

**AC-2:** `bash-version.log` for feature 113 contains exactly 3 `=== ... ===` section headers (host bash, /bin/bash, /bin/bash test-hooks.sh exit code). `grep -c '^=== ' bash-version.log` returns `3`.

**AC-3:** `pytest plugins/pd/mcp/test_workflow_state_server.py::TestListFeaturesByDefaultSingleWorkspace -v` → 5 tests pass (2 existing + 3 new from FR-3.3). Invalid-legacy-hex test asserts `_make_error` JSON with `error_type="invalid_project_id"`.

**AC-4:** `pytest plugins/pd/hooks/lib/workflow_engine/test_engine.py -k 'workspace_uuid' -v` → 2 new tests pass. Mismatch test raises FR-4.1's ValueError when invoked with a workspace_uuid not matching the existing workflow_phases row.

**AC-5:** `pytest plugins/pd/hooks/lib/entity_registry/test_entity_lifecycle.py::test_transition_entity_phase_workspace_uuid_consistent -v` → 1 test passes. Asserts symmetric workspace_uuid propagation across both `db.update_entity` and `db.update_workflow_phase` calls inside `transition_entity_phase`.

**AC-6:** `pytest -k 'unset_workspace_global' plugins/pd/mcp/test_workflow_state_server.py -v` → 1 test passes. Mutation: removing `or None` from `_workspace_uuid or None` at workflow_state_server.py:657 fails the test (FK constraint failure on empty-string workspace_uuid).

**AC-7:** `pytest -k 'filter_states_' plugins/pd/mcp/test_workflow_state_server.py -v` → 2 new tests pass. Behavioral pin: `OperationalError` → `_make_error` JSON; `RuntimeError` → propagates (the narrow-except contract). Structural pin: `grep -nE 'except.*Exception' plugins/pd/mcp/workflow_state_server.py:1614-1620` returns 0 matches.

**AC-8:** `pytest -k 'parent_resolution_' plugins/pd/hooks/lib/entity_registry/test_server_helpers.py -v` → 2 new tests pass. Behavioral pin: `OperationalError` → orphan with stderr warning; `RuntimeError` → propagates.

**AC-9:** `pytest -k 'create_key_result_missing_parent' plugins/pd/hooks/lib/entity_registry/test_entity_server.py -v` → 1 test passes. Mutation: removing the `if parent_entity is None: raise ValueError(...)` check fails the test (test expects raise; without the check, orphan KR registers).

**AC-10:** `pytest -k 'no_deprecation_warning' plugins/pd/hooks/lib/reconciliation_orchestrator/test_entity_status.py -v` → 4 parametrized sub-tests pass (one per fixed site at lines 47, 72, 189, 320). Wrapped in `simplefilter('error', DeprecationWarning)`.

**AC-11:** `pytest -k 'reconcile_.*_forwards_workspace_uuid' plugins/pd/mcp/test_workflow_state_server.py -v` → 3 new tests pass. Mutation pin: removing `workspace_uuid=_workspace_uuid or None` from any of the 3 MCP handler bodies fails the corresponding test.

**AC-12 (regression baseline, pinned):** Per NFR-2 below, a baseline is captured at the feature branch root commit and stored at `agent_sandbox/{date}/113-validation/baseline.log`. AC-12 is satisfied iff post-implementation full pytest run shows no test_id transitioning from pass→fail vs the baseline log. Net-new failures = 0. New tests added by FR-3 through FR-11 (~15+ tests) all pass.

**AC-13 (dogfood test for FR-1):** Feature 113's own `/pd:finish-feature` Step 5b QA gate produces `.qa-gate.json` matching FR-1.1/1.2/1.3 (validates against the enum + per-entry keys schema). Confirms the new emitter works end-to-end against feature 113's own diff.

## Non-Functional Requirements

**NFR-1 (no schema migration):** This feature does NOT introduce a Migration 12. Migration 11's `workflow_phases.workspace_uuid` column is the substrate for FR-4.1's read-side mismatch check; no new column needed.

**NFR-2 (pinned regression baseline):** Before any FR commit lands, capture a baseline via:
```bash
mkdir -p agent_sandbox/$(date +%Y-%m-%d)/113-validation
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/{hooks/lib,mcp} --tb=line 2>&1 > agent_sandbox/$(date +%Y-%m-%d)/113-validation/baseline.log
```
AC-12 is satisfied iff post-implementation `diff <(grep '^FAILED' baseline.log | sort) <(grep '^FAILED' final.log | sort)` shows ZERO new lines added.

**NFR-3 (no public API breakage):** All MCP tool signatures remain backward-compatible. `update_workflow_phase` gains a new optional `workspace_uuid` kwarg (default None preserves existing behavior). `register_entity` still accepts both `workspace_uuid` and `project_id`; FR-10's conditional pattern only changes WHICH gets sent.

**NFR-4 (gitignore minimization):** FR-1.4 REMOVES `docs/features/**/.qa-gate.json` from `.gitignore:63`. No new gitignore entries introduced.

**NFR-5 (per-method incremental rollout):** Following feature 108/112's pattern, each FR ships as 1-2 commits with its own test verification. Dependency-aware implementation order:
1. **FR-1 + FR-2** (validation artifacts) — unblocks AC-13 dogfood; independent of code changes
2. **FR-3.0 + FR-7 + FR-8 + FR-9** (defensive coding, narrowed excepts, single-file fixes) — independent
3. **FR-3.2 + FR-3.3 + FR-6** (workspace filter; FR-6 depends on FR-3.0 entry-point normalization)
4. **FR-10** (entity_status conditional pattern sweep)
5. **FR-4.1 first** (extend `update_workflow_phase` signature with workspace_uuid + mismatch check)
6. **FR-4.2 + FR-4.3 + FR-5 + FR-5.2** (engine + lifecycle forwarding — depend on FR-4.1's extended signature)
7. **FR-11** (reconcile threading — extends helper signatures, last because it depends on stable update_workflow_phase shape)

**NFR-6 (memory + retro hygiene):** Following retro patterns from feature 112, capture learnings via `store_memory` MCP during review iterations. Anti-patterns surfaced by this feature's own QA gate become input for future spec authoring.

## Out of Scope

- **#00390** (FR-4 alias drop + ~30-test-site migration) — separate sprint, large structural refactor.
- **#00389** (`_project_id` lazy global removal in entity_server.py:55,218,531 with 48 call sites) — separate sprint, large structural refactor.
- **F6 uuid7 adoption** (backlog #00359) — gated on Python 3.14+ pyproject floor.
- **Migration 12** — no new schema column; FR-4.1 uses Migration 11's existing column.
- **Documentation tier scaffolding** — YOLO Skip remains the norm.

## Verification Plan Summary

| AC | Verification method | Test path |
|----|---------------------|-----------|
| AC-1 | JSON shape + validator unit test | `qa_gate/test_emitter.py::test_emit_qa_gate_rejects_invalid_status` |
| AC-2 | grep section headers | `bash-version.log` |
| AC-3 | pytest 5 tests + ValueError pin | `test_workflow_state_server.py` |
| AC-4 | pytest 2 tests + mismatch ValueError pin | `test_engine.py` |
| AC-5 | pytest 1 test + symmetric propagation pin | `test_entity_lifecycle.py` |
| AC-6 | pytest 1 test + or-None mutation pin | `test_workflow_state_server.py` |
| AC-7 | pytest 2 tests (Operational + Runtime) + grep | `test_workflow_state_server.py` |
| AC-8 | pytest 2 tests + stderr capture | `test_server_helpers.py` |
| AC-9 | pytest 1 test + missing-parent check pin | `test_entity_server.py` |
| AC-10 | pytest 4 parametrized + DeprecationWarning capture | `test_entity_status.py` |
| AC-11 | pytest 3 tests (one per reconcile_* handler) | `test_workflow_state_server.py` |
| AC-12 | full plugin pytest, diff against pinned baseline | `agent_sandbox/{date}/113-validation/` |
| AC-13 | dogfood emit at finish-feature | feature 113's own `.qa-gate.json` |

## Cross-References

- Source backlog section: `docs/backlog.md` "From Feature 112 Pre-Release QA Findings (2026-05-12)"
- Feature 112 spec for AC-7/AC-3c/AC-9/AC-12 baseline: `docs/features/112-workspace-identity-cleanup/spec.md`
- Feature 112 design for handler-audit classification: `docs/features/112-workspace-identity-cleanup/design.md`
- Migration 11 schema (workflow_phases.workspace_uuid): `plugins/pd/hooks/lib/entity_registry/database.py:2041-2092`
- `update_workflow_phase` current signature: `plugins/pd/hooks/lib/entity_registry/database.py:4866-4934`
- Established per-method incremental rollout pattern: feature 108 retro + feature 112 retro

## Open Questions

None. All FRs are concrete with file:line targets and binary test verification. The two iter-1 deferrals (FR-1.4 gitignore, FR-4.2 option a/b, FR-11.1 a/b) are now locked at spec time.
