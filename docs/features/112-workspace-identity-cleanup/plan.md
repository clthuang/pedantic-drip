# Feature 112 — Workspace Identity Cleanup — Plan (iter 2)

**Spec:** [`spec.md`](spec.md) — FR-6 narrowed per iter-1 plan review
(see backlog #00389).
**Design:** [`design.md`](design.md) + [`handler-audit.md`](handler-audit.md).
**Approach:** Per-method incremental rollout (NFR-3). 7 FR clusters
sequenced per the dependency graph.

**Iter-1 review fixes incorporated:** scope narrowing on `_project_id`
(backlog #00389), Phase A/D ordering corrected, `.meta.json` rewrite
path = sandbox script (not MCP), Phase G ordering explicit, time
estimates removed (replaced with complexity tiers).

---

## Phase Sequence

```
Phase 0: Baseline + Pre-checks
   ↓
Phase A: FR-1 detect_project_id removal (workflow_engine + doctor + recon-orch + tests)
Phase B: FR-3 ENTITY_PROJECT_ID removal (parallel-safe with A)
   ↓
Phase C: FR-2 _workspace_uuid wiring (workflow_state_server + 12 engine fns)
   ↓
Phase D: FR-6 narrowed — session-start render + entity_server.py:218 swap + workflow_state_server.py:213 caller migration
   ↓
Phase E: FR-4 parent_type_id kwarg drop
   ↓
Phase F: FR-5 markdown sweep (17 hits / 5 files + agents/ audit)
   ↓
Phase G: FR-7 validation artifacts (explicit internal ordering)
```

**Critical ordering correction (iter-1 blocker #2):** `detect_project_id`
import drop in `entity_server.py` and `workflow_state_server.py` is
NOT in Phase A — those two MCP files are handled in Phase D
(narrowed FR-6) which swaps the line-218 / line-213 callers to
`_compute_legacy_project_id` in the same commit as the import drop.
This prevents NameError between phases. Phase A targets only
`workflow_engine/`, `doctor/`, `reconciliation_orchestrator/`, and
test files.

---

## Global Subagent Context

All task commands assume:
- **CWD:** `/Users/terry/projects/pedantic-drip` (project root).
- **Pytest invocation prefix:** `PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m pytest`
- **Validate:** `./validate.sh` (Errors: 0 required for green).
- **Hook tests:** `bash plugins/pd/hooks/tests/test-hooks.sh`.

---

## Phase 0 — Baseline + Pre-checks (Complexity: Simple)

| Task | Deliverable | DoD |
|------|-------------|-----|
| T0.1 | `agent_sandbox/2026-05-12/112-validation/baseline.log` | Full plugin pytest run captured (`<prefix>... plugins/pd/`); failing test_ids extracted to `baseline-failures.txt` |
| T0.2 | `migration-timing-baseline.log` | 500-row Migration 11 wall-clock recorded per design TD-6 |
| T0.3 | Decision note appended to plan.md | If T0.2 > 30s: halt + design-revision; if 5s < T0.2 ≤ 30s: log warning + proceed (test still passes AC-11); if T0.2 ≤ 5s: proceed clean |
| T0.4 | Updated `handler-audit.md` if drift | Re-run audit grep per TD-3; reconcile any count drift |
| T0.5 | Agents/ markdown audit | `grep -rn 'parent_type_id' plugins/pd/agents/` recorded; any hits added to Phase F scope |

**Single commit:** `chore(112): Phase 0 baseline + pre-checks`.

---

## Phase A — FR-1 detect_project_id removal (Complexity: Medium)

**Goal:** Delete `detect_project_id` from `project_identity.py:499` and
migrate 5 non-MCP callers + 3 test files. MCP files
(`entity_server.py:28,218`, `workflow_state_server.py:36,213`) are
handled in Phase D — NOT here.

| Task | File | DoD |
|------|------|-----|
| A.1 | `workflow_engine/task_promotion.py:18,335` | Import → `resolve_workspace_uuid`; call site updated; `<prefix> plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py` green |
| A.2 | `doctor/fix_actions.py:332,334` | Same pattern; `<prefix> plugins/pd/hooks/lib/doctor/` green |
| A.3 | `reconciliation_orchestrator/__main__.py:23,112` | Same pattern; `grep -n detect_project_id plugins/pd/hooks/lib/reconciliation_orchestrator/__main__.py` returns 0 |
| A.4 | `test_project_identity.py` (TestDetectProjectId class) | Rename class + tests to target `resolve_workspace_uuid`; add `test_resolve_workspace_uuid_env_override` (AC-2b) |
| A.5 | `test_entity_server.py:294,297,316` | Monkeypatch → `resolve_workspace_uuid`; full test file green |
| A.6 | `test_task_promotion.py:30,31,33` | Monkeypatch → `resolve_workspace_uuid`; full test file green |
| A.7 | DELETE `detect_project_id` function (LAST commit) | Deps: A.1-A.6 + D.3 (Phase D's MCP-caller migration). After both, `grep -rn 'detect_project_id' plugins/pd/ --include='*.py'` returns 0 (AC-1) |

**Ordering note:** A.7 (final delete) blocks on Phase D.3 too. Until
Phase D lands, `detect_project_id` survives in MCP files.

---

## Phase B — FR-3 ENTITY_PROJECT_ID removal (Complexity: Simple, parallel-safe with A)

| Task | DoD |
|------|-----|
| B.1 | `project_identity.py:512` env-var read deleted; `grep -r 'ENTITY_PROJECT_ID' plugins/pd/ --include='*.py'` returns 0 (AC-2) |
| B.2 | `test_project_identity.py:140` → `test_resolve_workspace_uuid_env_override`; passes (AC-2b) |
| B.3 | CHANGELOG entry per NFR-5 #1 |

Single commit.

---

## Phase C — FR-2 _workspace_uuid wiring + 12 engine fns (Complexity: Complex)

**Goal:** Wire `_workspace_uuid` through `workflow_state_server.py`
tool handlers + 12 engine functions. TDD: AC-8 pre-tests FIRST.

### C.1 Reconcile audit
Append authoritative function-list checklist to `handler-audit.md`,
merging design C2b 12 functions with the audit's engine-mediated-DB
table.

### C.2 TDD red pre-tests (broader than single-handler)
Add pre-tests in `test_workflow_state_server.py` covering
representative handlers from each engine path (per iter-1 task-reviewer
warning):
- `test_init_feature_state_scopes_to_active_workspace` (feature_lifecycle)
- `test_init_project_state_scopes_to_active_workspace` (project_lifecycle)
- `test_transition_entity_phase_scopes_to_active_workspace` (entity_engine)
- `test_record_backward_event_scopes_to_active_workspace` (phase_events)
- `test_promote_task_scopes_to_active_workspace` (task_promotion)

**Assertion pattern (public API, no `db._conn`):**
```python
ws_uuid = bootstrap_test_workspace(db, project_root)
workflow_state_server._workspace_uuid = ws_uuid
workflow_state_server._db = db
workflow_state_server._engine = WorkflowStateEngine(db, "docs")
asyncio.run(workflow_state_server.init_feature_state(...))
entity = db.get_entity(type_id="feature:999-test")
assert entity["workspace_uuid"] == ws_uuid
```

All 5 tests FAIL (red phase).

### C.3-C.14 Engine fn signatures (12 functions)
Each task: add `workspace_uuid: str | None = None` kwarg; forward to
every `db.*` write call inside the function body; grep
`<func_name>\b` across plugins/pd/ for non-MCP callers; per non-MCP
caller pass `workspace_uuid=None` (deprecation shim handles) unless
implementer's commit body justifies explicit migration (AC-15).

| Task | File:function | Test target |
|------|---------------|-------------|
| C.3 | `workflow_engine/feature_lifecycle.py::init_feature_state` | `test_feature_lifecycle.py` green |
| C.4 | `workflow_engine/feature_lifecycle.py::activate_feature` | same |
| C.5 | `workflow_engine/project_lifecycle.py::init_project_state` | `test_project_lifecycle.py` green |
| C.6 | `workflow_engine/entity_engine.py::init_entity` | `test_entity_engine.py` green |
| C.7 | `workflow_engine/entity_engine.py::transition_phase` | same |
| C.8 | `workflow_engine/engine.py::complete_phase` | `test_engine.py` green |
| C.9 | `workflow_engine/engine.py::transition` | same |
| C.10 | `workflow_engine/task_promotion.py::promote_task` | `test_task_promotion.py` green |
| C.11 | `workflow_engine/phase_events.py::record_backward_event` | `test_phase_events.py` green |
| C.12 | `workflow_engine/reconciliation.py::reconcile_apply` | `test_reconciliation.py` green |
| C.13 | `entity_registry/frontmatter_sync.py::sync_frontmatter` | `test_frontmatter_sync.py` green |
| C.14 | `reconciliation_orchestrator/entity_status.py::reconcile_status` | `test_entity_status.py` green |

### C.15 workflow_state_server.py handler wiring
Per handler-audit table, 21 handlers: 6 write + 6 read+write handlers
add `workspace_uuid=_workspace_uuid or None` to every db write call.
Update `list_features_by_phase` and `list_features_by_status` to
default single-workspace (pass `project_id="*"` for cross-workspace).

**DoD:** Each pre-test from C.2 now PASSES (TDD green). AC-7 grep:
every `db.(register_entity|upsert_workflow_phase|update_entity)` call
in `workflow_state_server.py` is on a line with
`workspace_uuid=_workspace_uuid or None` (same line or within 5
lines for multi-line calls).

### C.16 Remove TODO + retain _workspace_uuid global
Delete the TODO(backlog:00361) comment block at
`workflow_state_server.py:99-111`. RETAIN the
`_workspace_uuid: str = ""` declaration. RETAIN `_project_id` global
(deferred per #00389).

### C.17 CHANGELOG entry per NFR-5 #4 (list_features_by_* default change)

---

## Phase D — FR-6 narrowed (Complexity: Medium)

**Goal:** Switch session-start render; swap MCP-file
`detect_project_id` callers to `_compute_legacy_project_id`.

| Task | DoD |
|------|-----|
| D.1 | `session-start.sh:129`: `meta.get('project_id')` → `meta.get('workspace_uuid')`; hook tests green |
| D.2 | `session-start.sh:463-485`: declare `workspace_uuid_short="${WORKSPACE_UUID:0:8}"`; replace `${project_id}-${project_slug}` → `${workspace_uuid_short}-${project_slug}`; AC-5b grep passes |
| D.3 | `entity_server.py:28` import: drop `detect_project_id` from import line; **line 218**: replace `_project_id = detect_project_id(_project_root)` → `_project_id = _compute_legacy_project_id(_project_root)`; add `_compute_legacy_project_id` to import. `pytest plugins/pd/mcp/` green. (`_project_id` lazy global RETAINED per #00389.) |
| D.4 | `workflow_state_server.py:36` import: drop `detect_project_id`; **line 213**: replace `_project_id = detect_project_id(project_root)` → `_project_id = _compute_legacy_project_id(project_root)`; same import swap. MCP server boots; hook tests green. |
| D.5 | Verified Behavior matrix check: run TD-5 inputs against `/bin/bash` (3.2) and host bash; record divergences in `bash-version.log` |
| D.6 | CHANGELOG entry per NFR-5 #3 (session-start render format) |

**After Phase D + Phase A.7:** `detect_project_id` is gone; AC-1
passes.

---

## Phase E — FR-4 parent_type_id kwarg drop (Complexity: Complex)

### E.0 Verify .meta.json rewrite path (iter-1 blocker #3)
Test whether any MCP tool currently rewrites top-level `.meta.json`
frontmatter keys. Specifically:
- Try `update_entity(metadata={...})` against a sample file with
  `parent_type_id` at top level. Confirm it does NOT rewrite the
  on-disk file's top-level keys (only updates DB `metadata` column).
- **Conclusion (expected per design):** PRIMARY path is the sandbox
  script `agent_sandbox/2026-05-12/112-validation/meta-json-rewrite.py`
  using `meta-json-guard.sh` fallback (temporary bootstrap sentinel
  move pattern proven in feature 108 cleanup).

| Task | DoD |
|------|-----|
| E.0 | Empirical test recorded; primary path = sandbox script (CONTINGENCY path is the new PRIMARY per iter-1 review) |

### E.1-E.6 Production callers
Each task: pre-resolve `parent_type_id` to `parent_uuid` via
`db.resolve_ref()` at call site (or batch-resolve at function entry
per design C5 R-1 mitigation); pass `parent_uuid=` only.

| Task | File | DoD |
|------|------|-----|
| E.1 | `mcp/entity_server.py:435,449,561,1119,1126` | `grep -n 'parent_type_id\\s*=' plugins/pd/mcp/entity_server.py` returns 0; `pytest plugins/pd/mcp/` green |
| E.2 | `workflow_engine/task_promotion.py:346` (body — import handled in A.1) | `grep -n parent_type_id plugins/pd/hooks/lib/workflow_engine/task_promotion.py` returns 0 |
| E.3 | `workflow_engine/reconciliation.py:50,314,331` | Batch-resolve at function entry; per-row in-memory lookup; `test_reconciliation.py` green |
| E.4 | `entity_registry/server_helpers.py:262,439,457` | Same; `test_server_helpers.py` green |
| E.5 | `entity_registry/frontmatter_inject.py:227,236` | Same; both kwarg + dict-key forms handled; `test_frontmatter_inject.py` green |
| E.6 | `entity_registry/frontmatter_sync.py` (10 hits at 501,545,548,553,556,658,668,746,756,800) | Heaviest file; batch-resolve at sync entry; dict-key rewrites; `test_frontmatter_sync.py` green |

### E.7 Drop SELECT JOIN aliases + downstream readers (single combined commit)
Merges iter-1 reviewer's E.7a/E.7b split into one atomic change.

**Files:** `database.py:2995,3595,3647,4567` drop
`p.type_id AS parent_type_id` alias; update downstream readers in
same commit:
- `frontmatter_sync.py` (already touched in E.6 — verify dict-key
  reads of synthesized column also switched)
- `reconciliation.py:314` (already touched in E.3 — verify)
- `database.py:4611` export envelope: drop `entity['parent_type_id']
  = row['parent_type_id']` line
- `test_database.py` + `test_server_helpers.py` assertions on
  `entity["parent_type_id"]` rewritten to query parent type_id via
  `db.get_entity_by_uuid(parent_uuid)` follow-up lookup

**DoD:** `pytest plugins/pd/hooks/lib/entity_registry/` green
(atomic — drops + readers in one commit).

### E.8 Delete parent_type_id kwarg + alias block (LAST code commit of Phase E)
**Deps:** E.1-E.7 complete.
Delete `parent_type_id: str | None = None` from `register_entity`
signature (db.py:3354) AND alias block (db.py:3420-3445); same for
`register_entities_batch`. Delete `import warnings` if no other
caller uses it.

**DoD (inline AC verification):**
- `grep -nE 'parent_type_id\\s*=' plugins/pd/ --include='*.py' | grep -vE '^[^:]+:[^:]+:\\s*#'` returns 0 production hits (AC-3)
- `grep -rnE "['\"]parent_type_id['\"]" plugins/pd/ --include='*.py' | grep -vE '^[^:]+:[^:]+:\\s*#'` returns 0 production hits (AC-3b)
- `grep -n 'parent_type_id' plugins/pd/hooks/lib/entity_registry/database.py` returns hits only inside historical Migration-8/9/10/11 bodies (AC-3c)

### E.9 .meta.json schema bump
| Sub | DoD |
|-----|-----|
| E.9a Audit | `grep -rn 'parent_type_id' docs/features/ docs/projects/ docs/brainstorms/ --include='*.json'` → save list |
| E.9b PRIMARY rewrite script | `agent_sandbox/2026-05-12/112-validation/meta-json-rewrite.py` authored; each affected .meta.json rewritten via guard-fallback (temp move bootstrap sentinel, edit, restore). Log: `meta-json-rewrite.log` |
| E.9c Post-rewrite verify | Audit grep returns 0; affected file count matches E.9a |

### E.10 CHANGELOG entry per NFR-5 #2

---

## Phase F — FR-5 markdown sweep (Complexity: Simple)

| Task | File:lines | DoD |
|------|------------|-----|
| F.1 | `plugins/pd/commands/create-feature.md` lines 194,211-214,224 | Rewrite each kwarg-form code block to `parent_uuid=<uuid-via-db.resolve_ref()>` + 1-line preamble; rewrite prose mentions to "set the parent_uuid (resolve from type_id via db.resolve_ref()) to ..."; `grep -n parent_type_id plugins/pd/commands/create-feature.md` returns 0 |
| F.2 | `plugins/pd/commands/secretary.md` lines 517,796-798,820,830 | Same replacement pattern; per-file grep returns 0 |
| F.3 | `plugins/pd/commands/create-project.md` lines 95,121 | Same; grep returns 0 |
| F.4 | `plugins/pd/skills/brainstorming/SKILL.md` lines 281,291 | Same; grep returns 0 |
| F.5 | `plugins/pd/skills/decomposing/SKILL.md` line 248 | Same; grep returns 0 |
| F.6 | AC-4 verification | `grep -rn 'parent_type_id' plugins/pd/commands/ plugins/pd/skills/ --include='*.md'` returns 0 |

Single commit (or split per file at implementer discretion).

---

## Phase G — FR-7 Phase H validation (Complexity: Medium)

**Explicit internal ordering (iter-1 blocker #4):**

```
G.1 (helper) → G.2 (timing test) → G.3 (stress benchmark)
                                       ↓
G.4 (per-pkg pytest logs) ‖ G.5 (hook+validate logs) ‖ G.6 (bash-version)
                                       ↓
G.7 (.qa-gate.json) ← consumes evidence from G.2/G.4/G.5/G.6
                                       ↓
G.8 (NFR-2 diff) → G.9 (backlog annotation) → G.10 (MED reconciliation notes)
```

| Task | DoD |
|------|-----|
| G.1 | `_seed_v10_entities(db, count)` helper added to `test_database.py`; deterministic UUIDs (`f"test-uuid-{i:06d}"`); every 5th row gets parent_type_id=first-row |
| G.2 | `test_migration_11_runtime` in `test_database.py`: seed 500 v10 rows; time `MIGRATIONS[11]`; if elapsed > 2.0: `warnings.warn(f"Migration 11 took {elapsed:.2f}s > 2s threshold", UserWarning)`; assert `elapsed < 30.0` (AC-11) |
| G.3 | `test_migration_11_stress_benchmark` (10k rows) with `@pytest.mark.benchmark`; not invoked by `./validate.sh` |
| G.4 | Run all 6 packages: `<prefix> plugins/pd/hooks/lib/entity_registry/ > agent_sandbox/2026-05-12/112-validation/entity-registry-pytest.log 2>&1`; same for `doctor/`, `mcp/`, `workflow_engine/`, `reconciliation_orchestrator/`, `ui/` (file: `ui-pytest.log`); 6 log files non-empty (AC-10) |
| G.5 | `bash plugins/pd/hooks/tests/test-hooks.sh > agent_sandbox/.../hooks-tests.log 2>&1`; `./validate.sh > agent_sandbox/.../validate.log 2>&1`; both files non-empty |
| G.6 | `bash --version > agent_sandbox/.../bash-version.log`; append `/bin/bash --version`; append `/bin/bash plugins/pd/hooks/tests/test-hooks.sh` exit+tail (per AC-12) |
| G.7 | Author `.qa-gate.json` (one-shot manual JSON, 41 entries per AC-9 schema). Validator: `python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert len(d)==41; assert all((e.get("evidence") or e.get("backlog_ref") or e.get("condition")) for e in d)' docs/features/112-workspace-identity-cleanup/.qa-gate.json` returns 0 |
| G.8 | Diff G.4 logs against `baseline.log` (T0.1); `diff <(grep -E '^FAILED\|^ERROR' baseline.log)  <(grep -E '^FAILED\|^ERROR' all_phase_g_logs)` shows 0 net-new failures (AC-14) |
| G.9 | Annotate `docs/backlog.md` entries #00360-#00366: append `(fixed in feature:112-workspace-identity-cleanup)` to Description column |
| G.10 | Per #00367-#00388 (22 MED), record (a) commit ref / (b) verification cmd showing resolved / (c) rationale ≥2 sentences + target feature in `docs/features/112-workspace-identity-cleanup/med-reconciliation-notes.md` (consumed by retro.md in /pd:finish-feature) |

---

## Implementation Orchestration

- **Phase 0:** single dispatch.
- **Phase A ‖ Phase B:** can run in parallel via worktree-parallel implementer pattern (independent files).
- **Phase C → D → E:** sequential single-agent (heavy dependencies).
  - Within Phase C: C.3-C.14 are parallel-safe (12 independent engine files), but C.1/C.2 must precede them, and C.15 depends on all of them.
- **Phase F:** parallel-safe with Phase G (markdown-only, no runtime impact). Schedule after E for prose accuracy.
- **Phase G:** sequential per the internal-ordering graph above.

---

## Risk-Driven Tasks (per spec R-1...R-6)

- **R-1** (resolve_ref explosion): E.3, E.4, E.5, E.6 use batch-resolve at function entry.
- **R-2** (read/write asymmetry): C.2 + handler-audit per-call classification + C.15 list_features_by_* default change.
- **R-3** (markdown sweep agents): T0.5 adds `plugins/pd/agents/` audit.
- **R-4** (pre-existing failures): T0.1 baseline + G.8 diff check.
- **R-5** (migration timing): T0.2 design-time measurement; T0.3 conditional halt.
- **R-6** (frontmatter dict-keys): E.5, E.6 audit dict-key forms; E.9 schema bump.

---

## Total: ~32 commits across 8 phases.
