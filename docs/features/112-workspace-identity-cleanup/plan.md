# Feature 112 — Workspace Identity Cleanup — Plan

**Spec:** [`spec.md`](spec.md) (575 lines)
**Design:** [`design.md`](design.md) (790 lines) + [`handler-audit.md`](handler-audit.md)
**Approach:** Per-method incremental rollout (NFR-3). 7 FR clusters
sequenced per the dependency graph in design.md Architecture.

---

## Phase Sequence (FR clusters)

```
Phase 0: Baseline + Pre-checks
   ↓
Phase A: FR-1 detect_project_id removal (9 files)
Phase B: FR-3 ENTITY_PROJECT_ID removal (parallel-safe with A)
   ↓
Phase C: FR-2 _workspace_uuid wiring (workflow_state_server + 12 engine fns)
   ↓
Phase D: FR-6 project_id rendering cleanup (session-start + _project_id global)
   ↓
Phase E: FR-4 parent_type_id kwarg drop (production callers + shim removal + JOIN alias drop + .meta.json schema bump)
   ↓
Phase F: FR-5 markdown sweep (17 hits / 5 files)
   ↓
Phase G: FR-7 Phase H validation + .qa-gate.json + AC-32 timing test
```

**Why this order:**
- Phase 0 captures the baseline before any edits land (NFR-2 pinning per design).
- A and B are independent — both delete unused surfaces, both can land in parallel.
- C must precede E because Phase E removes the deprecation-shim path; if Phase C hasn't wired `_workspace_uuid`, workflow_state_server writes break.
- D must follow A (D removes `_project_id` lazy global which is currently populated by `detect_project_id`).
- E is the heaviest cluster (production callers + shim + JOIN alias + schema rewrite).
- F is markdown-only and parallel-safe with everything else; scheduled after E so prose examples match post-E kwarg forms.
- G is by definition last — it audits what's landed.

---

## Phase 0 — Baseline + Pre-checks

**Goal:** Pin NFR-2 baseline; verify design assumptions before edits.

| Task | Deliverable | DoD |
|------|-------------|-----|
| T0.1 Capture pytest baseline | `agent_sandbox/{today}/112-validation/baseline.log` | `plugins/pd/.venv/bin/python -m pytest plugins/pd/` output captured; pass/fail counts + failing test_ids extracted |
| T0.2 Run design-time migration timing | `agent_sandbox/{today}/112-validation/migration-timing-baseline.log` | Per TD-6: 500-row seed + Migration 11 forward; wall-clock recorded |
| T0.3 Decision on perf sub-task | Inline note in `plan.md` (this file, post-task) | If T0.2 result > 5s → file new task; if ≤5s → proceed to Phase A |
| T0.4 Re-grep handler-audit | Updated `handler-audit.md` if drift | Re-run audit grep (design TD-3); update audit table if call count drifts |

**Estimated time:** 30–45 min. Single commit
(`chore(112): Phase 0 baseline capture`).

---

## Phase A — FR-1 detect_project_id removal

**Goal:** Delete `detect_project_id` from `project_identity.py:499` and
migrate 9 files (design Component C1).

**Order:** Migrate callers FIRST (one commit per file or per cluster),
then delete the function definition in the LAST commit. This way
every intermediate commit leaves the codebase runnable.

| Task | File | DoD |
|------|------|-----|
| TA.1 | `task_promotion.py:18,335` | Import replaced with `resolve_workspace_uuid`; call site updated; `pytest plugins/pd/hooks/lib/workflow_engine/test_task_promotion.py` green |
| TA.2 | `doctor/fix_actions.py:332,334` | Lazy import replaced; call site updated; `pytest plugins/pd/hooks/lib/doctor/` green |
| TA.3 | `reconciliation_orchestrator/__main__.py:23,112` | Import replaced; call site updated; `python -m reconciliation_orchestrator --help` works |
| TA.4 | `mcp/entity_server.py:28,218` | Import dropped; `_project_id` retention deferred to Phase D; `pytest plugins/pd/mcp/` green |
| TA.5 | `mcp/workflow_state_server.py:36,213` | Import dropped; caller migration coordinated with Phase C (this task is a no-op import drop) |
| TA.6 | `test_project_identity.py` | TestDetectProjectId class rewritten as TestResolveWorkspaceUuid; AC-2b new test added |
| TA.7 | `test_entity_server.py:294,297,316` | Monkeypatch retargeted to `resolve_workspace_uuid` |
| TA.8 | `test_task_promotion.py:30,31,33` | Monkeypatch retargeted to `resolve_workspace_uuid` |
| TA.9 | DELETE `detect_project_id` from `project_identity.py:499` | Function removed; AC-1 grep passes (`grep -rn 'detect_project_id' plugins/pd/ --include='*.py'` returns 0) |

**Estimated time:** 2–3 hours. Each task is one commit
(`feat(112): drop detect_project_id from {file}`).

**Verification at Phase A close:** AC-1 grep + `./validate.sh` + scoped pytest.

---

## Phase B — FR-3 ENTITY_PROJECT_ID removal

**Goal:** Delete `os.environ.get("ENTITY_PROJECT_ID")` read from
`project_identity.py:512` and convert the legacy test (design FR-3
section, AC-2 + AC-2b).

| Task | DoD |
|------|-----|
| TB.1 Delete env-var read | `project_identity.py:512` block deleted; `grep -r 'ENTITY_PROJECT_ID' plugins/pd/ --include='*.py'` returns 0 (AC-2) |
| TB.2 Rewrite test | `test_project_identity.py:140` `test_detect_project_id_env_override` → `test_resolve_workspace_uuid_env_override`; asserts `ENTITY_WORKSPACE_UUID` override path; passes (AC-2b) |
| TB.3 CHANGELOG entry | `CHANGELOG.md` `[Unreleased]` section under `### Removed` — entry per NFR-5 #1 |

**Estimated time:** 30 min. Single commit
(`feat(112): drop ENTITY_PROJECT_ID env-var (FR-3)`).

**Parallel-safe with Phase A** — can interleave commits without
dependency.

---

## Phase C — FR-2 `_workspace_uuid` wiring + 12 engine fns

**Goal:** Wire `_workspace_uuid` through `workflow_state_server.py`
tool handlers + the 12 engine functions per design C2 / C2b. Add
AC-8 integration test FIRST (TDD red), then make it green.

| Task | DoD |
|------|-----|
| TC.1 Reconcile C2b vs handler-audit | Single authoritative function-list checklist appended to `handler-audit.md` |
| TC.2 Add AC-8 pre-test (TDD red) | New test in `plugins/pd/mcp/test_workflow_state_server.py::test_init_feature_state_scopes_to_active_workspace` per design handler-audit snippet; FAILS pre-fix |
| TC.3 Engine fn signatures (12) | Add `workspace_uuid: str \| None = None` kwarg to each per C2b table; forward to every `db.*` write call; non-MCP callers pass `workspace_uuid=None` (deprecation shim handles) unless implementer's commit body justifies explicit migration (AC-15) |
| TC.4 workflow_state_server handler wiring | Per `handler-audit.md` table, 21 handlers classified; 6 write + 6 read+write handlers add `workspace_uuid=_workspace_uuid or None` to every db write call. AC-7 grep passes. AC-8 test now PASSES (TDD green) |
| TC.5 list_features_by_* default change | Both handlers default single-workspace; pass `project_id="*"` for cross-workspace; CHANGELOG entry per NFR-5 #4 |
| TC.6 Remove workflow_state_server.py:99-111 TODO | Delete the `TODO(backlog:00361)` block on `_workspace_uuid` global |

**Estimated time:** 3–4 hours (largest cluster). Sequence as multiple
commits — one per engine function group + one for handler wiring.

---

## Phase D — FR-6 project_id rendering + `_project_id` global removal

**Goal:** Switch session-start render to `workspace_uuid_short`; drop
`_project_id` lazy global from `entity_server.py`.

| Task | DoD |
|------|-----|
| TD.1 session-start.sh:129 read | `meta.get('project_id', '')` → `meta.get('workspace_uuid', '')`; hook tests green |
| TD.2 session-start.sh:463-485 render | `workspace_uuid_short=${WORKSPACE_UUID:0:8}` declared; context line uses it; AC-5b grep passes |
| TD.3 Drop `_project_id` from entity_server.py | Line 55 declaration deleted; line 218 assignment deleted; line 531 usages route via `_workspace_uuid` only; AC-6 narrowed grep passes |
| TD.4 Verified Behavior matrix check | Run TD-5 inputs against `/bin/bash` (3.2) and host bash; record in `bash-version.log` if drift |
| TD.5 CHANGELOG entry | NFR-5 #3 (session-start render format change) |

**Estimated time:** 1–2 hours. 1–2 commits.

---

## Phase E — FR-4 parent_type_id kwarg drop (HEAVIEST)

**Goal:** Remove `parent_type_id` from production code: kwarg
signatures, callers, synthesized SELECT JOIN aliases, downstream
readers, .meta.json schema. Per design C3, C3b, C4b.

### E.1 — Pre-check (R-6 mitigation)
| Task | DoD |
|------|-----|
| TE.0a Verify MCP path for .meta.json rewrite | Confirm `update_entity` accepts metadata replace; document chosen path in commit per design C4b |

### E.2 — Production callers (one commit per file/cluster)
| Task | File | DoD |
|------|------|-----|
| TE.1 | `mcp/entity_server.py:435,449,561,1119,1126` | Pre-resolve via `db.resolve_ref()`; pass `parent_uuid=`; scoped pytest green |
| TE.2 | `workflow_engine/task_promotion.py:346` | Same |
| TE.3 | `workflow_engine/reconciliation.py:50,314,331` | Resolve at function entry (batched); per-row in-memory lookup |
| TE.4 | `entity_registry/server_helpers.py:262,439,457` | Same |
| TE.5 | `entity_registry/frontmatter_inject.py:227,236` | Same; dict-key form also handled |
| TE.6 | `entity_registry/frontmatter_sync.py:501,545,548,553,556,658,668,746,756,800` | Heaviest file; batch-resolve at sync entry; dict-key rewrites |

### E.3 — Synthesized SELECT JOIN aliases (design C3b)
| Task | DoD |
|------|-----|
| TE.7a | `database.py:2995,3595,3647,4567` drop `p.type_id AS parent_type_id` SELECT alias |
| TE.7b | Update downstream readers per C3b table: `frontmatter_sync.py` (already touched in TE.6); `reconciliation.py:314` (TE.3); `database.py:4611` export envelope |

### E.4 — Shim removal (LAST commit of phase)
| Task | DoD |
|------|-----|
| TE.8 | Delete `parent_type_id` kwarg + alias block from `register_entity` (db.py:3354,3420-3445) and `register_entities_batch` |
| TE.9 | AC-3, AC-3b, AC-3c grep verification |

### E.5 — `.meta.json` schema bump (design C4b)
| Task | DoD |
|------|-----|
| TE.10a | Audit existing `.meta.json` hits: `grep -rn 'parent_type_id' docs/features/ docs/projects/ --include='*.json'` |
| TE.10b | MCP-path rewrite via `update_entity` per affected file (PRIMARY path) |
| TE.10c | Contingency: `agent_sandbox/{today}/112-validation/meta-json-rewrite.py` if MCP path insufficient |
| TE.10d | Post-rewrite grep returns 0 hits |

### E.6 — CHANGELOG
| TE.11 | NFR-5 #2 entry (parent_type_id kwarg removal) |

**Estimated time:** 4–6 hours. 8–12 commits.

---

## Phase F — FR-5 markdown sweep

**Goal:** Replace 17 prose `parent_type_id` hits in 5 markdown files
per design C4.

| Task | File | DoD |
|------|------|-----|
| TF.1 | `plugins/pd/commands/create-feature.md` (6 hits at 194,211-214,224) | Prose rewritten to use `parent_uuid` + db.resolve_ref preamble |
| TF.2 | `plugins/pd/commands/secretary.md` (6 hits at 517,796-798,820,830) | Same |
| TF.3 | `plugins/pd/commands/create-project.md` (2 hits at 95,121) | Same |
| TF.4 | `plugins/pd/skills/brainstorming/SKILL.md` (2 hits at 281,291) | Same |
| TF.5 | `plugins/pd/skills/decomposing/SKILL.md` (1 hit at 248) | Same |
| TF.6 | AC-4 verification | `grep -rn 'parent_type_id' plugins/pd/commands/ plugins/pd/skills/ --include='*.md'` returns 0 |

**Estimated time:** 1 hour. 1 commit
(`docs(112): parent_type_id markdown sweep (FR-5)`).

---

## Phase G — FR-7 Phase H validation + `.qa-gate.json` + AC-32 timing test

**Goal:** Produce validation artifacts per design C6.

| Task | DoD |
|------|-----|
| TG.1 Add `_seed_v10_entities` helper | In `test_database.py`; deterministic UUIDs; pseudo-random parent edges |
| TG.2 Add `test_migration_11_runtime` | Per AC-11; 500-row dataset; asserts <30s; warns >2s |
| TG.3 Add `test_migration_11_stress_benchmark` | 10k rows; `@pytest.mark.benchmark`; not invoked by validate.sh |
| TG.4 Capture per-package pytest logs | `agent_sandbox/{today}/112-validation/{entity-registry,doctor,mcp,workflow-engine,recon-orch,ui}-pytest.log` (AC-10) |
| TG.5 Capture hook tests + validate logs | `hooks-tests.log`, `validate.log` (AC-10) |
| TG.6 Capture bash-version.log | 3 lines per AC-12: host `bash --version`, `/bin/bash --version`, test-hooks.sh exit/tail with `/bin/bash` |
| TG.7 Author `.qa-gate.json` | 41 entries per AC-9 schema; status assignment per design C6 walker logic |
| TG.8 NFR-2 diff check | Diff post-impl pytest result vs `baseline.log` (T0.1); 0 net-new failures (AC-14) |
| TG.9 AC-16 backlog annotation | Annotate #00360–#00366 with `(fixed in feature:112-workspace-identity-cleanup)` |
| TG.10 AC-17 MED reconciliation | Each #00367–#00388 marked (a)/(b)/(c) per AC-17 rubric; output in `retro.md` (deferred to retrospective) |

**Estimated time:** 2–3 hours. 3–4 commits.

---

## Parallel Group Summary

| Group | Tasks | Notes |
|-------|-------|-------|
| Independent setup | T0.1–T0.4 | Phase 0; must complete before any FR cluster |
| Independent FR | Phase A + Phase B | Both delete unused surfaces; safe to interleave |
| Sequential | Phase C → Phase D → Phase E | Stack of dependencies per architecture |
| Parallel-safe | Phase F (markdown) | Can land any time after E; scheduled last for prose accuracy |
| Sequential close | Phase G | Audits what's landed; last by definition |

---

## Risk-Driven Tasks

Picked from spec R-1…R-6:

- **R-1 mitigation:** TE.3, TE.4, TE.5, TE.6 batch-resolve parent
  references at function entry.
- **R-2 mitigation:** TC.4 + `handler-audit.md` per-call-site
  classification.
- **R-3 mitigation:** Phase F sequenced after E for prose accuracy.
- **R-4 mitigation:** T0.1 baseline + AC-14 diff check at TG.8.
- **R-5 mitigation:** T0.2 design-time timing measurement;
  conditional perf sub-task at T0.3.
- **R-6 mitigation:** TE.5, TE.6 audit dict-key forms; TE.10a-d
  .meta.json schema rewrite.

---

## Estimated Total

15–20 hours across ~30 commits. Per NFR-3, no single commit
cross-cuts more than one FR cluster (Phase 0 baseline excluded).
