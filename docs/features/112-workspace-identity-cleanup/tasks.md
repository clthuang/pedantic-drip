# Feature 112 — Workspace Identity Cleanup — Tasks

Per spec/design/plan. Each task is 5–15 minutes with a binary DoD.
Acceptance criteria reference IDs from `spec.md`. Per `commitAndComplete`
contract, every task ends with `./validate.sh` green + scoped pytest
green.

**Convention:** `[B]` blocking (must complete before deps run), `[P]`
parallel-safe within a phase.

---

## Phase 0 — Baseline + Pre-checks

### Task 0.1 [B] Capture pytest baseline
**Deps:** none.
**Files touched:** `agent_sandbox/2026-05-12/112-validation/baseline.log` (new).
**Steps:**
1. `mkdir -p agent_sandbox/2026-05-12/112-validation`
2. `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/ --tb=line > agent_sandbox/2026-05-12/112-validation/baseline.log 2>&1 || true`
3. Extract failing test_ids: `grep -E '^FAILED|^ERROR' baseline.log > baseline-failures.txt`

**DoD:** baseline.log exists, non-empty; baseline-failures.txt enumerates pre-existing failures.

### Task 0.2 [B] Design-time migration timing
**Deps:** Task 0.1.
**Files touched:** `agent_sandbox/2026-05-12/112-validation/migration-timing-baseline.log`.
**Steps:** Per design TD-6: write a temporary Python snippet that seeds 500 v10 entities, invokes `MIGRATIONS[11]`, captures wall-clock, deletes the temp DB.

**DoD:** Log file exists with `wall_clock_seconds=<float>`.

### Task 0.3 [B] Decision on perf sub-task
**Deps:** Task 0.2.
**Steps:** Read T0.2 result. If > 5s, append to this tasks.md a new Phase 0.5 with perf tasks; if ≤5s, append note "T0.3 cleared: <X.XX>s ≤ 5s threshold; no perf sub-task needed".

**DoD:** Decision recorded in tasks.md.

### Task 0.4 [P] Re-grep handler-audit verification
**Deps:** none.
**Steps:** Run audit grep per design TD-3:
```
grep -nE 'db\.(register_entity|upsert_workflow_phase|update_entity|list_entities|search_entities|get_entity|search_by_type_id_prefix|set_parent|get_lineage|claim_unknown_entities|next_sequence_value)' plugins/pd/mcp/workflow_state_server.py
```
Compare count vs design-time audit (17 call sites).

**DoD:** Match — proceed. Drift — update handler-audit.md.

---

## Phase A — FR-1 detect_project_id removal

### Task A.1 [B] Migrate task_promotion.py
**File:** `plugins/pd/hooks/lib/workflow_engine/task_promotion.py:18,335`.
**Steps:** Replace `from entity_registry.project_identity import detect_project_id` with `from entity_registry.project_identity import resolve_workspace_uuid`. Replace `_project_id = detect_project_id(...)` with appropriate `resolve_workspace_uuid(...)` per design C1.

**DoD:** `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py` green.

### Task A.2 [P] Migrate doctor/fix_actions.py
**File:** `plugins/pd/hooks/lib/doctor/fix_actions.py:332,334`.
**Steps:** Replace lazy `detect_project_id` import + call with `resolve_workspace_uuid`.

**DoD:** `pytest plugins/pd/hooks/lib/doctor/` green.

### Task A.3 [P] Migrate reconciliation_orchestrator/__main__.py
**File:** `plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py:23,112`.
**Steps:** Import swap + call site swap.

**DoD:** `python -m reconciliation_orchestrator --help` works without ImportError.

### Task A.4 [P] Drop detect_project_id import from entity_server.py
**File:** `plugins/pd/mcp/entity_server.py:28`.
**Steps:** Remove import only. `_project_id` global retention is deferred to Phase D (Task D.3).

**DoD:** `pytest plugins/pd/mcp/` green.

### Task A.5 [P] Drop detect_project_id import from workflow_state_server.py
**File:** `plugins/pd/mcp/workflow_state_server.py:36,213`.
**Steps:** Remove import + caller (line 213). Coordinate with Phase C — `_project_id` lazy global remains for now; FR-2 wiring (Phase C) replaces the assignment with `resolve_workspace_uuid` if still needed at that point.

**DoD:** MCP server boots; `python -c 'from mcp import workflow_state_server'` succeeds.

### Task A.6 [B] Rewrite test_project_identity.py TestDetectProjectId
**File:** `plugins/pd/hooks/lib/entity_registry/test_project_identity.py:68+`.
**Steps:** Rename `TestDetectProjectId` → `TestResolveWorkspaceUuid` (or delete tests that exercised removed behavior). Add `test_resolve_workspace_uuid_env_override` exercising `ENTITY_WORKSPACE_UUID` (AC-2b).

**DoD:** All tests in the class pass post-deletion of `detect_project_id`.

### Task A.7 [P] Retarget test_entity_server.py monkeypatch
**File:** `plugins/pd/hooks/lib/entity_registry/test_entity_server.py:294,297,316`.
**Steps:** `entity_server.detect_project_id` → `entity_server.resolve_workspace_uuid` (or appropriate equivalent).

**DoD:** `pytest plugins/pd/hooks/lib/entity_registry/test_entity_server.py` green.

### Task A.8 [P] Retarget test_task_promotion.py monkeypatch
**File:** `plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py:30,31,33`.
**Steps:** `_tp_mod.detect_project_id` → `_tp_mod.resolve_workspace_uuid`.

**DoD:** Test fixture loads without AttributeError.

### Task A.9 [B] Delete detect_project_id function (LAST commit of Phase A)
**File:** `plugins/pd/hooks/lib/entity_registry/project_identity.py:499`.
**Deps:** A.1–A.8 must all be complete.
**Steps:** Delete the function. Update module docstring (line 4).

**DoD:** `grep -rn 'detect_project_id' plugins/pd/ --include='*.py'` returns 0 (AC-1). `./validate.sh` + full plugin pytest green vs baseline.

---

## Phase B — FR-3 ENTITY_PROJECT_ID removal (parallel-safe with A)

### Task B.1 [B] Delete env-var read
**File:** `plugins/pd/hooks/lib/entity_registry/project_identity.py:512`.
**Steps:** Delete the `os.environ.get("ENTITY_PROJECT_ID")` block. Update module docstring if it references the env var.

**DoD:** `grep -r 'ENTITY_PROJECT_ID' plugins/pd/ --include='*.py'` returns 0 (AC-2).

### Task B.2 [B] Rewrite legacy env-override test
**File:** `plugins/pd/hooks/lib/entity_registry/test_project_identity.py:140`.
**Steps:** Rename `test_detect_project_id_env_override` → `test_resolve_workspace_uuid_env_override`. Assert that `ENTITY_WORKSPACE_UUID=<uuid>` overrides resolution.

**DoD:** Test passes (`pytest -k test_resolve_workspace_uuid_env_override`); AC-2b satisfied.

### Task B.3 [P] CHANGELOG entry
**File:** `CHANGELOG.md` `[Unreleased]` section.
**Steps:** Add under `### Removed`: per NFR-5 #1 text.

**DoD:** CHANGELOG modified; entry present.

---

## Phase C — FR-2 _workspace_uuid wiring

### Task C.1 [B] Reconcile C2b vs handler-audit function checklist
**File:** `docs/features/112-workspace-identity-cleanup/handler-audit.md`.
**Steps:** Append a consolidated function-checklist section merging design C2b's 12 engine functions with the audit's engine-mediated-DB-writes table. Single authoritative list.

**DoD:** New section present; lists each engine function with current signature + post-FR-2 signature + non-MCP caller decision (a/b per C2b).

### Task C.2 [B] Add AC-8 pre-test (TDD red)
**File:** `plugins/pd/mcp/test_workflow_state_server.py`.
**Steps:** Add `test_init_feature_state_scopes_to_active_workspace` per design handler-audit snippet. Comment notes test-only `db._conn` exception per CLAUDE.md.

**DoD:** Test FAILS (red phase) because pre-FR-2 wiring writes via deprecation shim path.

### Task C.3 [B] Engine fn signature: feature_lifecycle.init_feature_state
**File:** `plugins/pd/hooks/lib/workflow_engine/feature_lifecycle.py`.
**Steps:** Add `workspace_uuid: str | None = None` kwarg; forward to `db.register_entity` and `db.upsert_workflow_phase` calls.

**DoD:** `pytest plugins/pd/hooks/lib/workflow_engine/test_feature_lifecycle.py` (or analogous) green.

### Task C.4 [P with C.3] Engine fn: feature_lifecycle.activate_feature
**Steps:** Same pattern.
**DoD:** Same.

### Task C.5 [P] Engine fn: project_lifecycle.init_project_state
**File:** `plugins/pd/hooks/lib/workflow_engine/project_lifecycle.py`.
**DoD:** Same pattern.

### Task C.6 [P] Engine fn: entity_engine.init_entity
**File:** `plugins/pd/hooks/lib/workflow_engine/entity_engine.py`.

### Task C.7 [P] Engine fn: entity_engine.transition_phase

### Task C.8 [P] Engine fn: engine.complete_phase
**File:** `plugins/pd/hooks/lib/workflow_engine/engine.py`.

### Task C.9 [P] Engine fn: engine.transition

### Task C.10 [P] Engine fn: task_promotion.promote_task
**File:** `plugins/pd/hooks/lib/workflow_engine/task_promotion.py`.

### Task C.11 [P] Engine fn: phase_events.record_backward_event

### Task C.12 [P] Engine fn: reconciliation.reconcile_apply

### Task C.13 [P] Engine fn: frontmatter_sync.sync_frontmatter

### Task C.14 [P] Engine fn: reconciliation_orchestrator.entity_status.reconcile_status

### Task C.15 [B] workflow_state_server.py handler wiring
**File:** `plugins/pd/mcp/workflow_state_server.py`.
**Deps:** C.3–C.14 complete (engine signatures ready).
**Steps:** For each `@mcp.tool()` per handler-audit table, add `workspace_uuid=_workspace_uuid or None` to every db write call. Update read handlers (`list_features_by_phase`, `list_features_by_status`) to pass single-workspace filter unless `project_id="*"`.

**DoD:** AC-7 grep passes (every write call has the kwarg); AC-8 test passes (TDD green).

### Task C.16 [B] Remove TODO(backlog:00361) on _workspace_uuid global
**File:** `plugins/pd/mcp/workflow_state_server.py:99-111`.
**Steps:** Delete the TODO comment block on the lazy global.

**DoD:** Comment removed; global retains its declaration line.

### Task C.17 [P] CHANGELOG entry for list_features_by_* default change
**File:** `CHANGELOG.md`.
**Steps:** Add NFR-5 #4 entry under `### Changed`.

**DoD:** Entry present.

---

## Phase D — FR-6 project_id rendering + _project_id removal

### Task D.1 [B] session-start.sh:129 meta read
**File:** `plugins/pd/hooks/session-start.sh`.
**Steps:** Replace `meta.get('project_id', '')` with `meta.get('workspace_uuid', '')`.

**DoD:** `bash plugins/pd/hooks/tests/test-hooks.sh` green.

### Task D.2 [B] session-start.sh:463-485 render
**File:** `plugins/pd/hooks/session-start.sh`.
**Steps:** Declare `workspace_uuid_short="${WORKSPACE_UUID:0:8}"` before the context heredoc. Replace `${project_id}-${project_slug}` with `${workspace_uuid_short}-${project_slug}`.

**DoD:** AC-5b grep passes (`grep -n 'workspace_uuid_short' plugins/pd/hooks/session-start.sh` returns hit in 460–490 range); hook tests green.

### Task D.3 [B] Drop _project_id from entity_server.py
**File:** `plugins/pd/mcp/entity_server.py:55,218,531`.
**Deps:** A.4 (import already dropped).
**Steps:**
1. Delete `_project_id: str = ""` declaration (line 55).
2. Delete `_project_id = detect_project_id(...)` assignment (line 218; should already be gone post-A.4 if import was the only reason — verify).
3. Replace `_project_id` usages at line 531 (and any other) with `_workspace_uuid` only.

**DoD:** AC-6 narrowed grep passes; AC-5 grep passes; `pytest plugins/pd/mcp/` green.

### Task D.4 [P] Verified Behavior matrix check
**File:** `agent_sandbox/2026-05-12/112-validation/bash-version.log` (new).
**Steps:** Run the TD-5 inputs against `/bin/bash` (3.2) and host bash; record outputs. If divergence found, surface as inline note.

**DoD:** Matrix verified or divergence documented.

### Task D.5 [P] CHANGELOG entry
**File:** `CHANGELOG.md`.
**Steps:** NFR-5 #3 entry under `### Changed`.

**DoD:** Entry present.

---

## Phase E — FR-4 parent_type_id kwarg drop (HEAVIEST)

### Task E.0a [B] Verify MCP path for .meta.json rewrite
**Deps:** Phase D close.
**Steps:** Test `update_entity` against a sample .meta.json with `parent_type_id` key — does it support metadata-replace semantics? Document in commit body.

**DoD:** Decision recorded; chosen path identified.

### Task E.1 [B] Production caller: mcp/entity_server.py kwargs
**File:** `plugins/pd/mcp/entity_server.py:435,449,561,1119,1126`.
**Steps:** For each call, pre-resolve via `db.resolve_ref(parent_type_id_str)` if needed (or accept caller's parent_uuid directly); pass `parent_uuid=` only.

**DoD:** Scoped pytest green; runtime smoke test (register_entity via MCP).

### Task E.2 [B] Production caller: workflow_engine/task_promotion.py:346
**Steps:** Same pattern.

### Task E.3 [B] Production caller: workflow_engine/reconciliation.py:50,314,331
**Steps:** Batch-resolve at function entry (R-1 mitigation per design C5).

### Task E.4 [B] Production caller: entity_registry/server_helpers.py:262,439,457
**Steps:** Same.

### Task E.5 [B] Production caller: entity_registry/frontmatter_inject.py:227,236
**Steps:** Same; address both kwarg and dict-key forms.

### Task E.6 [B] Production caller: entity_registry/frontmatter_sync.py (10 hits)
**Steps:** Heaviest file; batch-resolve at sync entry; dict-key rewrites.

### Task E.7a [B] Drop SELECT JOIN aliases in database.py
**File:** `plugins/pd/hooks/lib/entity_registry/database.py:2995,3595,3647,4567`.
**Steps:** Drop the `p.type_id AS parent_type_id` alias from each SELECT.

**DoD:** `pytest plugins/pd/hooks/lib/entity_registry/` green (downstream readers updated in TE.7b).

### Task E.7b [B] Update downstream readers
**Deps:** E.7a, E.3, E.6.
**Files:** Per design C3b table.
**Steps:** Switch readers to `parent_uuid` + on-demand resolve_ref.

**DoD:** All affected tests green.

### Task E.8 [B] Delete parent_type_id kwarg + alias block (LAST commit before E.9)
**File:** `plugins/pd/hooks/lib/entity_registry/database.py:3343-3445`.
**Deps:** E.1–E.7b complete.
**Steps:** Delete `parent_type_id: str | None = None` from `register_entity` signature; delete lines 3420-3445 (alias block); same for `register_entities_batch`.

**DoD:** AC-3, AC-3b, AC-3c grep all pass.

### Task E.10a [B] Audit .meta.json on-disk hits
**Steps:** `grep -rn 'parent_type_id' docs/features/ docs/projects/ --include='*.json'` → save to file.

**DoD:** Audit file exists.

### Task E.10b [B] MCP-path rewrite (PRIMARY)
**Steps:** Per affected file, call `update_entity` to swap `parent_type_id` for `parent_uuid` in metadata.

**DoD:** Post-rewrite grep returns 0; affected files touched per audit list.

### Task E.10c [P] Contingency: rewrite script (if MCP insufficient)
**File:** `agent_sandbox/2026-05-12/112-validation/meta-json-rewrite.py`.
**Steps:** Only if E.0a or E.10b fails; author script using guard-fallback pattern.

**DoD:** Script exists; rewrite logged.

### Task E.11 [P] CHANGELOG entry
**File:** `CHANGELOG.md`.
**Steps:** NFR-5 #2 entry.

**DoD:** Entry present.

---

## Phase F — FR-5 markdown sweep

### Task F.1 [P] commands/create-feature.md
**File:** `plugins/pd/commands/create-feature.md` (6 hits at 194,211-214,224).
**Steps:** Rewrite prose per design C4 — `parent_uuid` + db.resolve_ref preamble.

**DoD:** No hit on line range; AC-4 closer.

### Task F.2 [P] commands/secretary.md (6 hits)

### Task F.3 [P] commands/create-project.md (2 hits)

### Task F.4 [P] skills/brainstorming/SKILL.md (2 hits)

### Task F.5 [P] skills/decomposing/SKILL.md (1 hit)

### Task F.6 [B] AC-4 verification
**Deps:** F.1–F.5.
**Steps:** Run `grep -rn 'parent_type_id' plugins/pd/commands/ plugins/pd/skills/ --include='*.md'`.

**DoD:** 0 hits.

---

## Phase G — FR-7 Phase H validation + .qa-gate.json

### Task G.1 [B] Add _seed_v10_entities helper
**File:** `plugins/pd/hooks/lib/entity_registry/test_database.py`.
**Steps:** Helper per design C6 — deterministic UUIDs, 5th-row parent edges.

**DoD:** Helper added; can be invoked in isolation.

### Task G.2 [B] Add test_migration_11_runtime
**Steps:** 500-row dataset; assert <30s; emit `pytest.warns` if >2s.

**DoD:** AC-11 satisfied; test passes on local machine.

### Task G.3 [P with G.2] Add test_migration_11_stress_benchmark
**Steps:** 10k-row; `@pytest.mark.benchmark`.

**DoD:** Test exists; not in default pytest invocation.

### Task G.4 [P] Capture per-package pytest logs
**Steps:** Run each package suite individually; tee to log files.

**DoD:** All AC-10 files exist; AC-14 NFR-2 diff check shows no net-new failures.

### Task G.5 [P] Capture hook + validate logs

### Task G.6 [P] Capture bash-version.log (3-line AC-12)

### Task G.7 [B] Author .qa-gate.json (41 entries per AC-9)
**Deps:** G.1–G.6.

**DoD:** Validator (`python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert len(d)==41'`) passes.

### Task G.8 [B] NFR-2 diff check
**Deps:** G.4.

### Task G.9 [B] AC-16 backlog annotation
**File:** `docs/backlog.md` entries #00360–#00366.
**Steps:** Append `(fixed in feature:112-workspace-identity-cleanup)`.

**DoD:** All 7 entries annotated.

### Task G.10 [B] AC-17 MED reconciliation (deferred to retro.md)
**Steps:** Per MED #00367–#00388, record (a)/(b)/(c) per AC-17 rubric.

**DoD:** Notes recorded in retro outline; final retro.md authored in /pd:finish-feature.

---

## Total tasks: ~50 across 8 phases.
