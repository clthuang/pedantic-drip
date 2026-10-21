<!-- Append-only history of 117-post-f116-hygiene. Entry shapes: plugins/pd/references/log-entries.md. The entries below were converted from legacy files by pd-adopt. -->

## 2026-05-18 02:30+00:00 note entity_created
Status: closed (legacy)
- kind: feature
- name: Post F116 Hygiene
- status: active

## 2026-05-18 02:47+00:00 phase start -> brainstorm
Status: closed (legacy)

## 2026-05-18 02:47+00:00 review brainstorm — legacy
Status: closed (legacy)
Iterations: 4
"prd-reviewer 3 iter (iter1: 3 blockers + 5 warnings + 4 suggestions; iter2: 2 framing warnings; iter3: APPROVED with 2 non-blocking suggestions). brainstorm-reviewer Stage 6 gate: APPROVED with 2 cosmetic suggestions applied as rev 2.2. Stage 1 CLARIFY + Stage 2 RESEARCH skipped per YOLO (evidence empirically pinned via doctor JSON + entity DB queries at session start)."

## 2026-05-18 02:48+00:00 phase brainstorm -> specify
Status: closed (legacy)

## 2026-05-18 02:48+00:00 review specify — legacy
Status: closed (legacy)
Iterations: 3
"spec-reviewer 2 iter (iter1 2 blockers FR-A.2-tx-wrapper FR-A.4-injection-unverified + 4 warnings + 3 suggestions; iter2 APPROVED 2 suggestions applied rev 2.1 DDL-comment + line-367-enumeration). phase-reviewer 1 iter (APPROVED 1 warning + 2 suggestions applied rev 2.2 variable-bindings + FR-A.4-framing + AC-D.3-workflow-note). Rev 2.2 implementation-ready: 14 sweep sites enumerated, 4 migration-safety pins preserved (test_migration_13_safety.py:194/205/224/367), FR-A.1 capture/replay with `with ctx.entities_conn:` connection-level rollback."

## 2026-05-18 03:04+00:00 phase specify -> design
Status: closed (legacy)

## 2026-05-18 03:04+00:00 review design — legacy
Status: closed (legacy)
Iterations: 4
"design-reviewer 3 iter (iter1: 2 blockers TD-A.1-DDL/DML-semantics + C-A.2-fabricated-test-names + 5 warnings + 2 suggestions; iter2: 1 NEW blocker _FailingUpdateConn proxy missing __enter__/__exit__ \u2014 Python special-method-lookup bypasses __getattr__; iter3: APPROVED clean). phase-reviewer 1 iter (APPROVED with 1 cosmetic suggestion re TDD step numbering divergence). Total 4 reviewer iterations. Compress-iterations strategy applied. Design rev 2.1 implementation-ready: C-A.1 _execute_re_attribute_with_trigger_dance with two-layer atomicity (finally for DDL + with conn: for DML rollback), C-A.2 with verified test_t2a_7_* names + _FailingUpdateConn proxy with explicit __enter__/__exit__, C-B.1 lazy-import dynamic constants, C-B.2 14-site sweep, R-1 mitigation via regex source-drift detector."

## 2026-05-18 03:18+00:00 phase design -> create-plan
Status: closed (legacy)

## 2026-05-18 03:18+00:00 review create-plan — legacy
Status: closed (legacy)
Iterations: 5
"plan-reviewer 2 iter + task-reviewer 2 iter + phase-reviewer 1 iter + relevance-verifier pre-impl gate PASSED clean (4/4: coverage, completeness, testability, coherence). Total 6 reviewer iterations. Rev 2.1 implementation-ready: 15 tasks TA.1-5 + TB.1-5 + TC.1-5 mirroring design 15-step TDD ordering; critical path 9 steps with TA.4||TA.5 + TB.2||TB.3||TB.4 parallel groups; all 16 FRs map to discrete tasks with binary DoD."

## 2026-05-18 11:51+08:00 review legacy — Step 1: Spec-Reviewer Review
Status: closed (legacy)
### Iteration 1 (2026-05-18)

**Reviewer:** pd:spec-reviewer (skeptic)
**Decision:** Needs Revision

**Issues:**
- [blocker] [assumptions] FR-A.2 claimed atomicity via "outer `with self.transaction():` rolls back" — production function uses raw `ctx.entities_conn` with explicit `commit()` at line 560; no such wrapper exists. (at: spec.md FR-A.2)
  Suggestion: Add explicit `with ctx.entities_conn:` context manager wrapping DROP/UPDATE/recreate; or scope atomicity to single-statement UPDATE + trigger restore.
- [blocker] [testability] FR-A.4 prescribed 3 alternative failure-injection mechanisms without verifying any would actually fire mid-UPDATE. (at: spec.md FR-A.4)
  Suggestion: Pick ONE concrete mechanism (FK injection recommended, NULL workspace_uuid violating NOT NULL).
- [warning] FR-A.5 TC.4 fixture re-creation ordering ambiguous.
- [warning] AC-C.5 reduction target ≥ 280 unachievable if FR-C.4 deferred.
- [warning] FR-A.3 didn't quote literal trigger error message.
- [warning] FR-B.2c regex spec not falsifiable by example.
- [suggestion] FR-B.2b sibling files deferred.
- [suggestion] FR-A.1 pseudocode used unbound `now_iso`.
- [suggestion] Overview did not propagate "stricter variant" framing.

**Changes Made (rev 2):**
All 9 findings resolved per the Review History table in spec.md. Key changes: connection-level rollback via `with ctx.entities_conn:`, FK-injection mechanism for FR-A.4, 4-step ordered TC.4 fixture flow, conditional AC-C.5 reduction targets, empirical sibling-file enumeration (0 sites), removed `updated_at` mutation pseudocode (not present in production).

---

### Iteration 2 (2026-05-18)

**Reviewer:** pd:spec-reviewer (skeptic)
**Decision:** APPROVED

**Issues:**
- [suggestion] [clarity] FR-A.1 inline DDL/transaction comment internally contradictory (pre-3.6 vs post-3.6 sqlite3 semantics). (at: spec.md FR-A.1 code block)
  Suggestion: Cite bpo-27334 explicitly; frame `finally` as defense-in-depth.
- [suggestion] [traceability] FR-B.2b missed test_migration_13_safety.py:367 (`v[0] == "12"` post-down-migration pin). (at: spec.md FR-B.2b)
  Suggestion: Add as 4th pinned site for enumeration completeness.

**Changes Made (rev 2.1):**
Both suggestions applied: DDL comment rewritten with bpo-27334 citation; line 367 added as 4th pinned site in FR-B.2b.

---

## 2026-05-18 11:51+08:00 review-2 legacy — Step 2: Phase-Reviewer Validation
Status: closed (legacy)
### Iteration 1 (2026-05-18)

**Reviewer:** pd:phase-reviewer (gatekeeper)
**Decision:** APPROVED (with cosmetic fixes applied as rev 2.2)

**Issues:**
- [warning] FR-A.1 pseudocode used unbound `target_workspace_uuid` / `target_entity_uuid` without cross-referencing lines 532-541. (at: FR-A.1 pseudocode)
  Suggestion: Annotate which lines bind which values.
- [suggestion] FR-A.4 pre-flight verification framed as runtime test step. (at: FR-A.4)
  Suggestion: Reframe as design-time one-shot check.
- [suggestion] AC-D.3 (lastCompletedPhase) is workflow-tool invariant. (at: AC-D.3)
  Suggestion: Move to workflow note.

**Changes Made (rev 2.2):**
Variable bindings annotated inline; FR-A.4 reframed as design-time verification; AC-D.3 moved to workflow note.

**Spec phase complete. Ready for design.**

---

### Design Phase

## 2026-05-18 11:51+08:00 review-3 legacy — Step 3: Design-Reviewer Review
Status: closed (legacy)
### Iteration 1 (2026-05-18)

**Reviewer:** pd:design-reviewer
**Decision:** Needs Revision (2 blockers + 5 warnings + 2 suggestions)

**Issues (resolved in rev 2):**
- [blocker] [feasibility] TD-A.1 `with conn:` rollback claim wrong for DDL+DML mix (CPython legacy autocommits DDL).
- [blocker] [consistency] C-A.2 listed 4 fabricated test names; actual tests use `test_t2a_7_*` naming.
- [warning] [feasibility] FR-A.4 monkey-patch "raise on 2nd call" would fire on preamble SELECT.
- [warning] [feasibility] R-1 mitigation cited nonexistent `inspect.getsource(EntityDatabase._create_triggers)`.
- [warning] [consistency] Trigger-scope rationale ("re-arming harmless") unstated.
- [warning] [assumptions] TD-B.1 circular-import framing speculative-as-observed.
- [warning] [completeness] C-C.4 deferral semantics thin.
- [suggestion] Dual-commit pattern unexplained.
- [suggestion] LOC counts not load-bearing.

**Changes Made (rev 2):** All 9 resolved per design.md Review History table.

---

### Iteration 2 (2026-05-18)

**Reviewer:** pd:design-reviewer
**Decision:** Needs Revision (1 NEW blocker)

**Issues:**
- [blocker] [feasibility] `_FailingUpdateConn` proxy missing `__enter__`/`__exit__`. Python `with conn:` uses type-level dunder lookup (datamodel.html §3.3.10) which bypasses `__getattr__`. Without explicit `__enter__`/`__exit__`, the proxy raises `AttributeError` before reaching UPDATE.

**Changes Made (rev 2.1):** Added explicit `__enter__`/`__exit__` methods delegating to `self._real.__enter__/__exit__` + inline docstring NOTE explaining the special-method-lookup gotcha.

---

### Iteration 3 (2026-05-18)

**Reviewer:** pd:design-reviewer
**Decision:** APPROVED clean. 0 issues.

Empirical verification: `sqlite3.Connection.__enter__` exists in CPython stdlib (Modules/_sqlite/connection.c) and returns the connection; `__exit__` commits/rolls back per stdlib docs. Delegation pattern correct.

---

## 2026-05-18 11:51+08:00 review-4 legacy — Step 4: Phase-Reviewer Handoff
Status: closed (legacy)
### Iteration 1 (2026-05-18)

**Reviewer:** pd:phase-reviewer
**Decision:** APPROVED (1 cosmetic suggestion)

**Issues:**
- [suggestion] TDD step numbering divergence between spec (13 steps, TC.4 fixture re-arm grouped into TA.4) and design (15 steps, separate TA.5). Cosmetic; plan-phase should treat design ordering as authoritative.

**Changes Made:** None — cosmetic only; the plan phase will treat design's 15-step ordering as canonical (noted by reviewer for plan-phase reference).

**Design phase complete. Ready for create-plan.**

---

### Create-Plan Phase

## 2026-05-18 11:51+08:00 review-5 legacy — Combined Reviewer Loop
Status: closed (legacy)
### Iteration 1 (2026-05-18)

**Reviewer 1: pd:plan-reviewer**
**Decision:** Needs Revision (1 blocker + 3 warnings + 2 suggestions)

**Issues (resolved in rev 2):**
- [blocker] [feasibility] AC-P.2 had time estimate ('5-20 minutes for code tasks') — violates plan agent guidance.
- [warning] [dependency] Critical path arithmetic 9 vs 10 — internally inconsistent.
- [warning] [tdd-order] TA.2 (test helper) placed before TA.1 (red test that uses helper).
- [warning] [assumption] Phase A acceptance gate grep '1 def + 2 call sites' unfalsifiable.
- [suggestion] Per-row 'Why this order' rationale missing.
- [suggestion] R-2 mitigation artifact traceability — needs anchor in production code (TA.3 docstring).

**Reviewer 2: pd:task-reviewer**
**Decision:** APPROVED with warnings (3 warnings + 2 suggestions all resolved in rev 2)

**Issues (resolved in rev 2):**
- [warning] TB.1 DoD import path used absolute dotted form `from plugins.pd.hooks.lib.doctor.checks` — would fail.
- [warning] TB.4 DoD parenthetical "in non-migration sites" misleading.
- [warning] TC.5 DoD missing severity_summary jq verification.
- [suggestion] TA.1 parametrize hint for single re-arm site (re-numbered as TA.2 in rev 2 after TA.1/TA.2 swap).
- [suggestion] TB.5 baseline capture procedure.

**Changes Made (rev 2):**
All 11 issues resolved: AC-P.2 → complexity levels; critical path arithmetic reconciled to 9 with TA.4||TA.5; TA.1/TA.2 swapped (helper precedes red test); Phase A acceptance gate split into 2 grep -cE commands; per-row rationale added; R-2 docstring note in TA.3; TB.1 import path → PYTHONPATH form; TB.4 parenthetical removed; TC.5 jq verification added; TA.2 parametrize hint; TB.5 git stash baseline.

---

### Iteration 2 (2026-05-18)

**Reviewer 1: pd:plan-reviewer**
**Decision:** APPROVED clean. 0 issues.

All 6 iter-1 findings cleanly resolved. No new issues introduced.

**Reviewer 2: pd:task-reviewer**
**Decision:** APPROVED clean. 0 issues.

All 5 iter-1 findings cleanly resolved.

**Reviewer 3: pd:phase-reviewer (chain review — iter 2/5)**
**Decision:** APPROVED with 2 non-blocking suggestions (applied as rev 2.1)

**Issues:**
- [suggestion] FR-B.3 verification command only in plan.md, not in any task DoD — added explicit grep bullet to TB.5 DoD.
- [suggestion] TB.5 baseline capture phrased conditionally ('Implementer SHOULD have') — could cause silent skip — rephrased to imperative with explicit condition.

**Changes Made (rev 2.1):**
2 cosmetic suggestions applied. Plan + tasks implementation-ready.

**Create-plan phase complete. Ready for implement.**

---

### Implement Phase

## 2026-05-18 11:51+08:00 review-6 legacy — Step 7: 3-Level Review (Iteration 1)
Status: closed (legacy)
### Reviewer 1: pd:implementation-reviewer (Level 1+2 — tasks + spec + design + PRD)

**Decision:** APPROVED — all 4 levels passed. 0 blockers, 2 non-blocking suggestions.

**Issues:**
- [suggestion] [spec/incomplete] AC-C.5 reduction target not met — 132/129 warnings are cross-workspace pollution (non-F117-addressable). Documented as retro finding.
- [suggestion] [prd/incomplete] FR-C.4 deferred per explicit deferral path. Schedule operator session for triage.

### Reviewer 2: pd:relevance-verifier (Level 2 — full coherence)

**Decision:** PASS — all 4 checks (coverage, completeness, testability, coherence) clean. 0 gaps.

### Reviewer 3: pd:code-quality-reviewer (Level 3 — quality)

**Decision:** APPROVED with cosmetic fixes (applied as rev 2).

**Issues:**
- [warning] [formatting] PEP 8 import-block violation in 2 test_database.py files (helpers interleaved with imports).
- [suggestion] [readability] Stale comment at checks.py:1076 still said `schema_version == 4`.
- [suggestion] [formatting] Missing type annotation on `_execute_re_attribute_with_trigger_dance(conn)` parameter.

**Changes Made (rev 2):**
- Moved `_latest_entity_version()` + `_latest_memory_version()` helpers to AFTER all import statements in both test_database.py files.
- Updated `# 1. schema_version == 4` → `# 1. schema_version == expected (dynamic, see _get_expected_memory_version)`.
- Added `conn: sqlite3.Connection` type annotation to `_execute_re_attribute_with_trigger_dance`.
- Regression check: 804 tests passed (doctor + entity_registry + semantic_memory subsuites), 0 new failures.

### Reviewer 4: pd:security-reviewer (Level 3 — security)

**Decision:** APPROVED. 0 blockers, 2 low-severity suggestions (defense-in-depth on recreate-failure visibility; informational sqlite_master trust model note). 0 vulnerabilities found.

**Implement phase complete. Ready for finish-feature.**

Per F114/F115/F116 compress-iterations pattern, finish-feature's Step 5b pre-release QA gate re-dispatches the same 4 reviewers — iter 1 fixes-applied suffices for this phase.

## 2026-05-18 03:51+00:00 review implement — legacy
Status: closed (legacy)
Iterations: 1
"All 15 TDD tasks executed via direct-orchestrator pattern (KB-injected for rigorous-upstream profile). 14 \u2705 + 1 \u23f8 (TC.4 deferred per FR-C.4 deferral path \u2014 21 cross-workspace links recorded to implementation-log.md). 4-reviewer Step 7 review (implementation-reviewer APPROVED 4/4 levels; relevance-verifier PASS 4/4 checks; code-quality-reviewer APPROVED with 1 PEP8 warning + 2 suggestions applied as rev 2; security-reviewer APPROVED 0 vulnerabilities). Compress-iterations strategy: code-quality fixes applied without re-dispatch since finish-feature Step 5b re-runs same 4 reviewers. Key F117 outcomes: 2 stale-version errors \u2192 0 errors (FR-B.1), production trigger drop/recreate bug fix landed (FR-A.1 with two-layer atomicity TD-A.1), 14-site test sweep complete (FR-B.2a), reconcile registered 3 missing entities, 4 brainstorm transitions, 6 new tests + 4 fixture re-arms. 2166 pytest passed 0 failures; validate.sh 0 errors 5 baseline warnings. Retro finding: AC-C.5 reduction target unmet because 132+129 warnings are cross-workspace pollution from other projects in shared DB, not reconcile-addressable."

## 2026-05-18 12:11+08:00 note legacy implementation-log.md
Status: closed (legacy)
### Phase A — Theme A (Production trigger drop/recreate)

### TA.1 — `_CANONICAL_TRIGGER_SQL` + `_recreate_workspace_uuid_trigger`
- **File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - Constant + helper added near top of file (lines 35-58).
  - Em-dash U+2014 confirmed via `grep -n "—"` at line 43 (canonical SQL body).

### TA.2 — `test_re_attribute_against_trigger_active_db` (TDD red)
- **File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
- **Status:** ✅ COMPLETE (red → green confirmed)
- **DoD verified:**
  - Parametrized test added (re-attribute parent + re-attribute child variants).
  - Red phase: `sqlite3.IntegrityError: workspace_uuid is immutable` raised at `fix_actions/__init__.py:532` — production bug reproduced.
  - Green phase: post-TA.3, both variants pass.

### TA.3 — `_execute_re_attribute_with_trigger_dance` helper + UPDATE replacements
- **File:** `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - Helper added with R-2 docstring note (CPython sqlite3 legacy autocommit assumption per design TD-A.1).
  - 2 bare UPDATE blocks replaced with helper calls (parent + child branches).
  - `grep -cE '^def _execute_re_attribute_with_trigger_dance' → 1`; `grep -cE '_execute_re_attribute_with_trigger_dance\(' → 3` (1 def + 2 call sites).
  - TA.2 test now PASSES (TDD green confirmed).

### TA.4 — FR-A.4 + FR-A.6 + R-1 tests
- **File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - 3 new tests added: `test_re_attribute_aborts_when_trigger_absent` (FR-A.6), `test_re_attribute_restores_trigger_on_update_failure` (FR-A.4 via `_FailingUpdateConn` proxy with explicit `__enter__`/`__exit__`), `test_canonical_trigger_sql_matches_production_source` (R-1 drift detector).
  - All 3 pass.

### TA.5 — Re-arm trigger in 4 existing TC.4 sites
- **File:** `plugins/pd/hooks/lib/doctor/test_fix_actions.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - `_recreate_workspace_uuid_trigger()` call added after `_seed_cross_workspace_pair()` in 4 sites (`test_t2a_7_triage_branch`, `test_t2a_7_triage_grandfather_without_reason_uses_fallback`, `test_t2a_7_triage_unknown_choice_raises_value_error`, `test_fr9_legitimate_grandfather_with_reason_preserves_behavior`).
  - Full `test_fix_actions.py` test suite: 21 passed (15 F116 + 6 new F117).

### Phase B — Theme B (Dynamic version pinning + test sweep)

### TB.1 — `_get_expected_*_version` helpers in `checks.py`
- **File:** `plugins/pd/hooks/lib/doctor/checks.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - Hardcoded constants `ENTITY_SCHEMA_VERSION = 11` / `MEMORY_SCHEMA_VERSION = 4` removed.
  - Lazy-import helpers added (returns `max(MIGRATIONS.keys())`).
  - Smoke test via `cd plugins/pd && PYTHONPATH=hooks/lib .venv/bin/python -c "..."` prints `17 7`.

### TB.2 — Update `db_readiness` + `memory_health` to use helpers
- **File:** `plugins/pd/hooks/lib/doctor/checks.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - `check_db_readiness` calls `_get_expected_entity_version()`.
  - `check_memory_health` calls `_get_expected_memory_version()`.
  - Doctor stale-version errors: 2 → 0 (production bug fix confirmed).

### TB.3 — Sweep 6 entity_registry test_database.py sites
- **File:** `plugins/pd/hooks/lib/entity_registry/test_database.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - Helper `_latest_entity_version()` added.
  - 6 sites converted (lines 370, 678, 2688, 2890, 3081, 4673).
  - EXPORT_SCHEMA_VERSION sites at lines 4077-4081, 4524 preserved (out of sweep regex scope).
  - `grep -nE 'get_metadata\("schema_version"\)\s*==\s*"\d+"|get_schema_version\(\)\s*==\s*\d+' → 0 matches`.

### TB.4 — Sweep 8 semantic_memory test_database.py sites
- **File:** `plugins/pd/hooks/lib/semantic_memory/test_database.py`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - Helper `_latest_memory_version()` added.
  - 8 sites converted (lines 91, 116, 123, 127, 191, 1266, 1306, 1310).
  - Migration-safety pin at line 2863 (`_read_schema_version(db_path) == "5"`) preserved.

### TB.5 — Full pytest + validate.sh regression
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - `pytest plugins/pd/hooks/lib/{doctor,entity_registry,semantic_memory}/` (from project root): **2166 passed, 3 skipped, 0 failures**.
  - `./validate.sh`: **0 errors, 5 warnings** (matches F116 baseline).
  - FR-B.3 forward-compat: `grep -rn 'len(CHECK_ORDER)\s*==\s*[0-9]\+' plugins/pd → 0 matches`.
  - **Pre-existing test_checks.py brittleness resolved (leave-the-ground-tidier):** 2 fixtures hardcoded `schema_version='11'` and the `_make_memory_db` helper hardcoded `'4'`. Updated to use dynamic `_get_expected_*_version()` helpers (F117-attributable since F117 changed the expected versions).

### Phase C — Theme C (State reconciliation)

### TC.1 — `reconcile_check` dry-run
- **File:** `docs/dev_artifacts/workitems/117-post-f116-hygiene/reconcile-dry-run.json`
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - JSON captured (3950 lines).
  - `jq` valid; summary: 3 in_sync, 3 meta_json_only (F114/F115/F116/F117 pending), 197 db_only (cross-workspace from other projects — correctly NOT reconciled), 1 phase_events_drift.

### TC.2 — `reconcile_apply`
- **Status:** ✅ COMPLETE (after entity registration repair)
- **DoD verified:**
  - First `reconcile_apply` returned 3 errors (Entity not found) — F114/F115/F116 records didn't exist in DB.
  - Manually registered F114, F115, F116 entities via `register_entity` MCP (`status='completed'`).
  - Second `reconcile_apply` succeeded: 3 created, 200 skipped (cross-workspace), 0 errors.
- **Key finding (retro-worthy):** The 132 `feature_status` + 129 `workflow_phase` doctor warnings are cross-workspace pollution from other projects' entities in the shared `~/.claude/pd/entities/entities.db`. They are NOT pedantic-drip drift and CANNOT be reconciled via `reconcile_apply` (which correctly leaves cross-workspace entities alone). The PRD/spec's "≥261 reduction from reconcile" assumption was based on an incomplete understanding of what reconcile addresses.

### TC.3 — 4 brainstorm transitions
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - 4 `update_entity` calls succeeded (F114, F115, F116, older phase-transition-summary brainstorms → `status='promoted'`).
  - Post-call SQL query: 2 active brainstorms remaining (`three-claws-v2-protocol`, `openclaw-gap-analysis`) — both cross-project, out of F117 scope.

### TC.4 — 21-link cross-workspace triage
- **Status:** ⏸️ DEFERRED per FR-C.4 deferral path
- **Rationale:**
  - 21 cross-workspace `parent_uuid` links require operator-interactive judgment per link (re-attribute parent / re-attribute child / delete relation / grandfather).
  - In autonomous YOLO session, deferring is appropriate.
  - AC-C.5 IF-deferred branch applies: reduction target ≥ 259 instead of ≥ 280.
- **Deferred artifact:** see `## Deferred Triage Links` section below + retro.md (to be created in /pd:finish-feature).

### TC.5 — Final doctor sanity check
- **Status:** ✅ COMPLETE
- **DoD verified:**
  - 0 errors ✓ (F117-attributable: 2 stale-version errors eliminated).
  - `severity_summary` field present: `{error: 0, warning: 537, info: 1}` (F116 invariant preserved).
  - Total issues: 538 vs baseline 537 = +1 (F117 entity itself contributes 1 orphan warning during reconcile transition state).
  - **AC-C.5 verdict:** Reduction target NOT met because 132/129 warnings are cross-workspace pollution (not F117-addressable). Critical F117 outcomes (0 errors, production bug fix landed, dynamic versioning landed) all confirmed.

### Deferred Triage Links (FR-C.4 — for future operator session)

The following 21 cross-workspace `parent_uuid` links require operator-interactive triage. Each link's `child_uuid` is the entity with a `parent_uuid` pointing across workspaces. Operator must choose per link: re-attribute parent / re-attribute child / delete relation / grandfather.

| # | Child UUID (`entity` field from doctor issue) |
|---|-----------------------------------------------|
| 1 | 154eb998-51d0-458c-897b-86a90cf9f654 |
| 2 | 45fcda8a-c6ef-4dcd-879f-e03dbf62941a |
| 3 | d291bdbc-9e4d-4fb9-94d1-fc634b5d03b0 |
| 4 | 157247ab-0a89-41bf-a900-426f68f1eb87 |
| 5 | 2b3aba82-52da-4018-86d8-7e3c154e792c |
| 6 | cecf3490-f7db-4181-99de-49022766c993 |
| 7 | f7029b56-83ee-4734-b416-113c1b132411 |
| 8 | 6e9d81f4-d419-45e6-97d1-900bd22dd258 |
| 9 | 2d76911e-fa98-49f2-986d-631f221e18d9 |
| 10 | 16c2a8a1-0e54-4a30-8d6e-d398e475dceb |
| 11 | 8dcae2d8-f70d-4047-b3f5-9164051c889e |
| 12 | 19e5e946-8f35-411d-abe5-6afa6c2124b6 |
| 13 | d03e8286-a18e-4ed1-b03c-139a013f1ec9 |
| 14 | fc26509f-02ed-48e0-be06-65106caf0876 |
| 15 | 0a07b8e6-749b-47a6-afb2-c750e8fccb86 |
| 16 | 7fa83a07-0b71-48c0-b86a-7d6432c1aa39 |
| 17 | b51e42fa-e9b3-4376-a5d9-ccb6e5b5a8ec |
| 18 | d137f12e-0368-4530-a0b9-7df953b85588 |
| 19 | 5f7f9f78-8abb-4a02-8ae4-29c1bf131556 |
| 20 | b681a4d1-ebe8-46a4-b348-a30956b4eb49 |
| 21 | ed0ac402-a0ca-4a6e-abef-913e5543b20c |

To resume triage in a future session:
```bash
### Option 1: invoke doctor --fix with interactive harness (current pd:doctor pattern)
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor --fix \
  --entities-db ~/.claude/pd/entities/entities.db \
  --memory-db ~/.claude/pd/memory/memory.db \
  --project-root /Users/terry/projects/pedantic-drip \
  --artifacts-root docs

### Option 2: per-link manual via _fix_triage_cross_workspace_link
### (F117 made this work against the trigger-active DB)
```

### Aggregate Summary

- **Files changed:**
  - `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` (FR-A.1 helper + 2 call-site updates)
  - `plugins/pd/hooks/lib/doctor/checks.py` (FR-B.1 dynamic helpers, hardcoded constants removed)
  - `plugins/pd/hooks/lib/doctor/test_fix_actions.py` (4 new F117 tests + 4 fixture re-arms)
  - `plugins/pd/hooks/lib/doctor/test_checks.py` (3 fixtures updated to dynamic versions — leave-the-ground-tidier)
  - `plugins/pd/hooks/lib/entity_registry/test_database.py` (TB.3 sweep — 6 sites)
  - `plugins/pd/hooks/lib/semantic_memory/test_database.py` (TB.4 sweep — 8 sites)
- **Tests:** 6 new (4 F117 + 2 helpers); 21 existing in `test_fix_actions.py` adapted via fixture re-arm.
- **Regression gate:** 2166 passed, 3 skipped, 0 failures.
- **validate.sh:** 0 errors, 5 warnings (baseline match).
- **Doctor:** 0 errors (down from 2); 537 warnings (cross-workspace pollution — non-F117-addressable).
- **TC.4 deferred:** 21 cross-workspace links recorded for future session.

## 2026-05-18 04:12+00:00 note entity_status_changed
Status: closed (legacy)
- old_status: active
- new_status: completed

## 2026-05-18 04:12+00:00 review finish — legacy
Status: closed (legacy)
Iterations: 1
"Step 5a validate.sh: 0 errors, 5 baseline warnings. Step 5b 4-reviewer QA gate dispatched in parallel: security APPROVED (0 HIGH/0 MED/1 LOW defense-in-depth), code-quality 1 BLOCKER iter 1 (PEP 8 import placement in semantic_memory/test_database.py) fixed in rev 3 + 1 LOW docstring task-label, implementation-reviewer APPROVED 4/4 levels with 1 MED warning re: $(awk ...) literal in implementation-log.md:131 fixed in rev 3 + 1 LOW retro Tune #1, test-deepener Step A surfaced 3 HIGH coverage-debt gaps (mutation_caught=true, not cross-confirmed \u2014 per AC-5b stay HIGH; qa-override.md authorizes deferral to F118 candidate) + 9 MED folded into retro Tunes + 4 LOW sidecar. Decision MERGE_OK_HIGH_ZERO after qa-override. LOW sidecar at .qa-gate-low-findings.md (gitignored). Merged to develop via --no-ff (commit b573e4b5) and pushed. NOT released \u2014 user directive: release is separate from finish per F116 pattern. Branch retained for any F118 follow-up reference."
