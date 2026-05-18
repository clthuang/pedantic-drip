# Feature 117 Retrospective — pd Post-F116 Production Hygiene

**Status:** Implement complete; AC-C.5 reduction target unmet (cross-workspace pollution); 14 ✅ + 1 ⏸ (TC.4 deferred)
**Branch:** `feature/117-post-f116-hygiene`
**Session date:** 2026-05-18
**Mode:** Standard (YOLO autonomous)
**Inherits from:** F116 retro production-gap appendix (`_fix_triage_cross_workspace_link` trigger collision); F115 retro KB candidate #6 (dynamic-fixture refactor); post-F116 doctor audit (3 themes).

## AORTA Analysis

### Aim
Bundle 3 post-F116 audit themes into a single atomic landing without expanding code surface beyond strictly necessary:
- **A**: Production trigger drop/recreate via `sqlite_master` capture/replay (FR-A.1) with two-layer atomicity (TD-A.1: `finally` for DDL + `with conn:` for DML rollback).
- **B**: Dynamic doctor version pinning + 14-site test sweep (lands F115 retro KB candidate #6).
- **C**: Operational reconciliation (`reconcile_apply` + 4 brainstorm transitions + 21 cross-workspace links triage).

Scope discipline: no new MCP tools, no new migrations, no new exception classes.

### Assumptions Challenged

| Going-in assumption | What turned out true |
|---|---|
| `reconcile_apply` will clear 132 + 129 = 261 doctor warnings (PRD/spec evidence) | 132/129 warnings are **cross-workspace pollution** from other projects sharing `~/.claude/pd/entities/entities.db`. `reconcile_apply` correctly skipped 197 db_only cross-workspace rows. AC-C.5 reduction target was structurally unreachable. |
| F114/F115/F116 entities exist in entity DB and just need status reconciliation | Entities **never existed** in DB (created during MCP-down sessions; F108 outage carried through F116). Required manual `register_entity` MCP for F114/F115/F116 prep before `reconcile_apply` could create the DB rows. |
| FR-A.1's `claim_unknown_entities:7956-7975` is a "pattern-match" reference for trigger drop/recreate | Reference uses **hardcoded inline CREATE TRIGGER**; F117 is a *strengthening* (sqlite_master capture/replay) — corrected in PRD rev 2.1. |
| `_FailingUpdateConn` proxy can delegate `with conn:` via `__getattr__` | **Wrong** — Python's special-method-lookup uses `type(obj).__enter__`, bypassing `__getattr__` entirely. Required explicit `__enter__`/`__exit__` methods (design rev 2.1 blocker). |
| Direct-orchestrator implement pattern needs per-task implementer dispatch | KB-injected at create-plan transition; F117's 15 binary-DoD tasks executed without per-task implementer dispatch and passed 4-reviewer Step 7 in 1 iteration. Pattern confirmed. |

### Outcomes (Observe — Quantitative)

| Phase | Iterations | Reviewer breakdown |
|-------|------------|--------------------|
| brainstorm | 4 | prd-reviewer 3 iter (3 blockers iter1; 2 framing warnings iter2; APPROVED iter3) + brainstorm-reviewer Stage 6 gate APPROVED with 2 cosmetic suggestions (rev 2.2). Stage 1+2 skipped per YOLO. |
| specify | 3 | spec-reviewer 2 iter (2 blockers iter1: FR-A.2 tx-wrapper + FR-A.4 injection-unverified; APPROVED iter2 with 2 suggestions rev 2.1) + phase-reviewer 1 iter (APPROVED with 1 warning + 2 suggestions rev 2.2). |
| design | 4 | design-reviewer 3 iter (2 blockers iter1: TD-A.1 DDL/DML semantics + C-A.2 fabricated test names; 1 NEW blocker iter2: proxy missing `__enter__`/`__exit__`; APPROVED iter3 clean) + phase-reviewer 1 iter (APPROVED with 1 cosmetic). |
| create-plan | 5 | plan-reviewer 2 iter (1 blocker AC-P.2 time-estimates + 3 warnings) + task-reviewer 2 iter (3 warnings rev 2) + phase-reviewer 1 iter (2 suggestions rev 2.1) + relevance-verifier PASS 4/4 clean. |
| implement | 1 | Direct-orchestrator (KB-injected for rigorous-upstream profile). 14 ✅ + 1 ⏸. 4-reviewer Step 7: implementation-reviewer APPROVED 4/4; relevance-verifier PASS 4/4; code-quality-reviewer APPROVED with 1 PEP8 warning + 2 suggestions applied as rev 2; security-reviewer APPROVED 0 vulnerabilities. |

**Total:** 17 reviewer iterations (16 upstream + 1 implement). Per-phase reviewer iteration counts: 4 / 3 / 4 / 5 / 1. Average upstream phase iterations: 4.0; above F116 target of 1-2 per phase, driven by 2 blocker waves in design + create-plan's chain-review.

**Key wins (verified):**
- Doctor stale-version errors: 2 → 0 (FR-B.1 dynamic version pinning).
- Production trigger drop/recreate bug fix landed; TDD red → green confirmed (`sqlite3.IntegrityError: workspace_uuid is immutable` reproduced in test, fixed by `_execute_re_attribute_with_trigger_dance`).
- Full pytest: 2166 passed, 3 skipped, 0 failures.
- `validate.sh`: 0 errors, 5 warnings (baseline match per F116).
- 4 stuck-active brainstorms → `status='promoted'`; 0 F117-attributable active brainstorms remain (2 cross-project active remain, out of scope).
- 14-site test sweep complete (6 entity_registry + 8 semantic_memory + 3 leave-the-ground-tidier fixes in `test_checks.py`).
- 6 new tests added (4 F117-FR + 2 helpers).

**Outcomes against acceptance criteria:**
- AC-A.1 through AC-A.5: ✅ all five (trigger-active fixture, byte-identical SQL post-call, mid-UPDATE rollback, RuntimeError guard, TC.4 compatibility).
- AC-B.1 through AC-B.7: ✅ all seven.
- AC-C.1, AC-C.2 (partially), AC-C.3, AC-C.5: ✅/⚠/✅/⚠.
- AC-C.4: ⏸ deferred per FR-C.4 deferral path (21 cross-workspace links require operator-interactive triage).
- AC-C.5 reduction target ≥ 280 (or ≥ 259 deferred): **unmet** — 132/129 warnings are cross-workspace pollution, not F117-addressable. Doctor total: 538 (vs baseline 537; +1 from F117 entity itself contributing 1 orphan during reconcile transition). 0 errors goal ✅.

### Reflections (Review — Qualitative)

1. **Cross-workspace pollution insight — shared DB ≠ single-project state.** The pre-F117 audit assumed 132 `feature_status` + 129 `workflow_phase` doctor warnings reflected pedantic-drip drift. They reflected **other projects'** entities in the shared `~/.claude/pd/entities/entities.db` (the global feature per CLAUDE.md). `reconcile_apply` is workspace-scoped and correctly skipped 197 db_only cross-workspace entries. The PRD/spec/design didn't surface this until TC.2 hit `error_type=not_found` for F114/F115/F116 and operator queried the DB directly. **Evidence:** TC.2 first invocation: 3 "Entity not found" errors; second invocation after `register_entity` prep: 3 created, 200 skipped (cross-workspace), 0 errors. Reduction count: 0 doctor warnings cleared by reconcile (vs target ≥ 261).

2. **MCP unavailability legacy compounded for the 4th feature in a row.** F108-F116 ran with MCP entity-server unavailable. F114/F115/F116 entity DB rows never existed (created during outage). F117's reconcile_apply required preliminary `register_entity` for those 3 features before it could create the rows it needed. This is the second consecutive retro flagging this (F116 retro #3); the F116 retro KB Tune #3 ("Reconcile MCP entity-server state, don't keep falling back") was the right call but didn't fully prevent this — the operational sequence (register-missing-entities, THEN reconcile) wasn't formalized.

3. **TC.4 deferral landed cleanly; deferral semantics from design held up in practice.** Design § C-C.4 deferral semantics specified: trigger condition, decision authority (operator explicit), retro artifact format, reduction accounting per AC-C.5 conditional. All four held in implement. The 21-link deferral was recorded in `implementation-log.md` "Deferred Triage Links" section with resume command. **Evidence:** F117 deferred with no implementation friction; AC-C.5 IF-deferred branch acceptance criteria matched the design.

4. **PEP 8 import-block placement gap surfaced; `validate.sh` doesn't catch it.** code-quality-reviewer (Step 7, Level 3) flagged: `_latest_entity_version()` and `_latest_memory_version()` helpers were interleaved with import statements in both `test_database.py` files. **Evidence:** "PEP 8 import-block violation in 2 test_database.py files (helpers interleaved with imports)" — caught at iter 1, fixed in rev 2. `validate.sh` 0 errors, 5 baseline warnings (no PEP 8 awareness). This is a real validator gap: future test-helper additions risk the same violation.

5. **Direct-orchestrator implement pattern validated for rigorous-upstream features.** F117 had 16 reviewer iterations upstream (deeply specified) and 15 binary-DoD tasks. The implement skill used direct-orchestrator (KB-injected at create-plan transition) — no per-task implementer dispatch. Step 7 4-reviewer review passed in 1 iteration: implementation-reviewer ✅ 4/4 levels, relevance-verifier PASS 4/4 checks, code-quality-reviewer APPROVED with 1 PEP8 warning + 2 suggestions, security-reviewer APPROVED 0 vulnerabilities. **Evidence:** F117 implement phase iter=1; .meta.json reviewerNotes "All 15 TDD tasks executed via direct-orchestrator pattern (KB-injected for rigorous-upstream profile)". The pattern works when upstream artifacts converge to implementation-ready (rigorous-upstream profile).

### Tradeoffs / Tune (Process Recommendations)

1. **Define cross-workspace-aware reduction baselines in pre-flight audits** (high confidence). When auditing doctor warnings before a hygiene feature, partition counts by `(workspace_uuid == current_workspace)` vs cross-workspace. **Signal:** F117 PRD/spec evidence "537 issues" was a single number; the 261 reconcile-addressable subset assumed single-project ownership; in fact only ~64 issues were F117-addressable. **Recommendation:** add a pre-flight doctor query partitioned by workspace_uuid to the brainstorm Stage 2 (RESEARCH) checklist; PRD success criteria reference workspace-scoped counts, not aggregate.

2. **Formalize "register-missing-entities before reconcile" sequence** (high confidence). **Signal:** F117 TC.2 first invocation returned 3 "Entity not found" errors for F114/F115/F116; required manual `register_entity` MCP prep. **Recommendation:** add a `reconcile_check_with_missing_entities` MCP variant (or a doctor sub-check) that lists entities present in `.meta.json` but absent from DB. Pre-reconcile checklist: "verify .meta.json features have DB rows; pre-register the missing ones".

3. **Codify TC.4-style deferral as first-class workflow state** (medium-high confidence). **Signal:** F117 design § C-C.4 deferral semantics worked cleanly in practice; F114→F115 in-feature partial-and-resume + F116 QA-deferred carry-forward each invented its own deferral shape. **Recommendation:** add a `deferred_to_future_session` lifecycle tag (or backlog entry type) that captures: deferral reason, resume command, follow-up trigger condition. Doctor would surface deferred entries; next session's brainstorm Stage 2 would scan them.

4. **Add lint coverage for helper-vs-import block placement** (medium confidence). **Signal:** F117 code-quality-reviewer Step 7 caught helpers interleaved with imports in 2 test_database.py files; `validate.sh` did not catch this. **Recommendation:** add a `validate.sh` lint rule (ast-based or regex-based) that flags `def`-statements appearing between `import` statements at module top. Single-rule addition; protects future test-helper additions.

5. **Recommend direct-orchestrator implement as the default for "rigorous-upstream" profile features** (high confidence). **Signal:** F117 upstream reviewer iterations totaled 16; implement phase iter=1 with 4-reviewer clean review. **Recommendation:** make direct-orchestrator the default when create-plan emits `complexity_profile: rigorous-upstream` AND tasks have binary DoD. Currently it's KB-injected at transition; promote to a workflow-state field set by create-plan's relevance-verifier output.

### Takeaways (Act — Knowledge Bank Candidates)

#### Patterns

- **Two-layer atomicity for trigger drop/recreate around DML** (high confidence). When you must temporarily drop a `BEFORE UPDATE OF` trigger to issue a column update the trigger forbids, use **`finally` for DDL restoration + `with conn:` for DML rollback**. The `finally` is the SOLE trigger-restoration mechanism (CPython sqlite3 legacy autocommit mode commits DDL immediately and does not include it in the implicit DML transaction). The `with conn:` covers UPDATE rollback only. Both layers load-bearing.
  - *Provenance:* F117 design TD-A.1; FR-A.1 implementation at `fix_actions/__init__.py` `_execute_re_attribute_with_trigger_dance`.
  - *Reasoning:* CPython's legacy autocommit mode opens implicit transactions only for DML via textual prefix match; DDL bypasses the implicit-tx layer entirely. A single-layer atomicity claim (e.g., "with conn: wraps everything") would be incorrect and would leave the trigger missing on UPDATE-failure paths.
  - *Keywords:* sqlite, trigger, ddl-dml, atomicity, autocommit, transaction-rollback, cpython.

- **Capture-and-replay trigger SQL from sqlite_master for byte-identity guarantee** (high confidence). When dropping and recreating a trigger as part of a fix, prefer `SELECT sql FROM sqlite_master WHERE name=?` capture-then-replay over hardcoded inline `CREATE TRIGGER`. Captured SQL stays byte-identical to whatever the live DB has, regardless of source-code drift. Add a `RuntimeError` guard for the trigger-absent case.
  - *Provenance:* F117 FR-A.1 strengthening of `claim_unknown_entities:7956-7975` (the reference used hardcoded inline SQL).
  - *Reasoning:* Hardcoded trigger literals silently diverge if the canonical source ever changes (e.g., error-message edit). sqlite_master capture binds the recreated trigger to live state, preventing source-vs-runtime drift.
  - *Keywords:* sqlite, trigger, capture-replay, sqlite-master, byte-identity, drift-prevention.

- **Direct-orchestrator implement for rigorous-upstream + binary-DoD task profile** (high confidence). When upstream artifacts (PRD + spec + design + plan + tasks) have converged through ≥10 reviewer iterations and each task has binary pass/fail DoD, dispatch implementation as a direct orchestrator pass without per-task implementer Task dispatch. Step 7's 4-reviewer review serves as the gate.
  - *Provenance:* F117 implement phase (15 tasks, 1 iteration, Step 7 all 4 reviewers approved); KB-injected pattern at create-plan transition.
  - *Reasoning:* Per-task implementer dispatch is overhead when upstream has already pinned every site, signature, and verification command. Binary DoD makes implementer judgment unnecessary; the orchestrator can sequence directly.
  - *Keywords:* direct-orchestrator, implement, rigorous-upstream, binary-dod, parallel-dispatch, task-execution.

- **Special-method lookup bypasses `__getattr__` for context managers** (medium confidence). When building proxy classes that wrap a `sqlite3.Connection` (or any object used in a `with` block), explicitly define `__enter__` and `__exit__` on the proxy class. Python's CPython data model § 3.3.10 looks up special methods on `type(obj)`, not via instance attribute access — `__getattr__` delegation will silently raise `AttributeError` before the context manager block fires.
  - *Provenance:* F117 design rev 2.1 blocker — `_FailingUpdateConn` proxy required explicit `__enter__`/`__exit__` even though `__getattr__` already delegated everything else.
  - *Reasoning:* Python's data model bypasses instance `__getattr__` for dunder methods used by language syntax (e.g., `with`, `for`, `in`). Proxies that work "for normal method calls" silently break when those instances enter syntactic contexts.
  - *Keywords:* python, proxy-pattern, special-method-lookup, dunder, context-manager, with-statement.

#### Anti-patterns

- **Assuming a shared global DB = single-project state** (high confidence). When a doctor / audit / linter operates against a globally-shared DB (e.g., `~/.claude/pd/entities/entities.db`), don't treat aggregate counts as project-attributable. Always partition by workspace_uuid (or whatever the multi-tenant discriminator is) before drawing scope conclusions. Cross-workspace entries are noise for single-project hygiene work.
  - *Provenance:* F117 AC-C.5 reduction target unreachable because 132+129 doctor warnings were cross-workspace pollution; reconcile_apply correctly skipped 197 cross-workspace entries.
  - *Reasoning:* Multi-tenant DBs have an implicit assumption that operations are workspace-scoped; aggregating across workspaces and then setting reduction targets confuses noise-from-other-projects with drift-in-current-project.
  - *Keywords:* shared-database, multi-tenant, workspace-scope, doctor-counts, baseline-attribution, cross-workspace.

- **Reconciling without first ensuring source-of-truth entities exist in DB** (high confidence). When `reconcile_apply` (or equivalent) needs to update DB rows that match `.meta.json` source-of-truth, but the rows never existed (e.g., created during a tooling outage), reconcile will return `error_type=not_found` per missing entity. Pre-register the missing entities first.
  - *Provenance:* F117 TC.2 first invocation: 3 "Entity not found" errors for F114/F115/F116. Required manual `register_entity` MCP prep before second `reconcile_apply` invocation succeeded.
  - *Reasoning:* Reconciliation conceptually means "make B match A", but most implementations operate as "UPDATE B SET ... WHERE row exists" rather than "INSERT OR UPDATE". When B is missing rows entirely (not stale), reconcile fails silently or with not-found errors.
  - *Keywords:* reconcile, mcp-outage, entity-registration, missing-rows, upsert-semantics, pre-flight.

#### Heuristics

- **PEP 8 import-block placement: helpers go AFTER all `import` statements** (medium confidence). When adding a module-level helper function to a test file, place it after all `from X import Y` and `import X` statements. Interleaving helper defs with imports passes pytest but trips style linters and `code-quality-reviewer`.
  - *Provenance:* F117 code-quality-reviewer Step 7 iter 1 flagged helpers interleaved with imports in `entity_registry/test_database.py` and `semantic_memory/test_database.py`; fixed in rev 2.
  - *Reasoning:* PEP 8 § "Imports" recommends grouping imports at the top of the module before any other code; module-level definitions appearing between imports break the visual grouping convention that lint tools and human readers rely on for top-of-file scanning.
  - *Keywords:* pep-8, imports, test-helper, module-layout, code-quality, lint-style.

- **Convergence indicator: implement-phase reviewer iterations ≤ 1 only when upstream iterations ≥ 10** (medium confidence). If upstream phases (spec + design + create-plan) collectively complete ≤ 6 reviewer iterations, expect implement Step 7 to surface ≥ 2 iterations of fixes. If upstream ≥ 10 iterations and tasks have binary DoD, implement Step 7 commonly passes in 1 iteration.
  - *Provenance:* F117 (16 upstream + 1 implement); F116 (~23 upstream + 1 implement). Pattern: rigorous upstream → clean implement.
  - *Reasoning:* Reviewer iteration cost is paid either upstream (catching design/spec defects before code lands) or downstream (catching code defects in implement Step 7). Net cost is roughly conserved; choosing upstream is preferable because design-time fixes are cheaper than retroactive code changes.
  - *Keywords:* reviewer-iterations, convergence, implement-phase, upstream-investment, conservation.

## Deferred Triage Links (FR-C.4 — for future operator session)

21 cross-workspace `parent_uuid` links require operator-interactive triage. Per implementation-log.md, each link's `child_uuid` is the entity with a `parent_uuid` pointing across workspaces. Operator chooses per link: re-attribute parent / re-attribute child / delete relation / grandfather.

Resume command (per implementation-log.md):
```bash
PYTHONPATH=plugins/pd/hooks/lib plugins/pd/.venv/bin/python -m doctor --fix \
  --entities-db ~/.claude/pd/entities/entities.db \
  --memory-db ~/.claude/pd/memory/memory.db \
  --project-root /Users/terry/projects/pedantic-drip \
  --artifacts-root docs
```

(F117 made `_fix_triage_cross_workspace_link` work against the trigger-active DB, so resume is now safe.)

## Raw Data

- Feature: 117-post-f116-hygiene
- Mode: Standard (YOLO autonomous)
- Branch lifetime: same-day (created 2026-05-18 02:30, implement complete 03:51)
- Total reviewer iterations: 17 (16 upstream + 1 implement)
- Per-phase: brainstorm 4 / specify 3 / design 4 / create-plan 5 / implement 1
- Tests: 2166 passed, 3 skipped, 0 failed (full hooks/lib subsuite)
- Files changed: 6 (production: `fix_actions/__init__.py`, `checks.py`; tests: `test_fix_actions.py`, `test_checks.py`, 2× `test_database.py`)
- New tests: 6 (4 F117-FR + 2 helpers); 4 fixture re-arms in existing F116 TC.4 tests
- New helpers: 4 (`_execute_re_attribute_with_trigger_dance`, `_get_expected_entity_version`, `_get_expected_memory_version`, `_recreate_workspace_uuid_trigger`)
- Doctor: 0 errors (down from 2); 537 warnings (cross-workspace pollution — non-F117-addressable); severity_summary preserved
- `validate.sh`: 0 errors, 5 warnings (baseline match)

## Reference Files

- F117 artifacts: `docs/features/117-post-f116-hygiene/{prd,spec,design,plan,tasks,implementation-log,retro}.md`
- F117 dry-run: `docs/features/117-post-f116-hygiene/reconcile-dry-run.json`
- F116 inheritance: `docs/features/116-f115-qa-deferred/{retro.md,qa-override.md}` (production gap appendix)
- F115 retro: `docs/features/115-pd-data-model-followups/retro.md` (KB candidate #6 validated)
- Production fix location: `plugins/pd/hooks/lib/doctor/fix_actions/__init__.py` `_execute_re_attribute_with_trigger_dance`
- Dynamic version helpers: `plugins/pd/hooks/lib/doctor/checks.py` `_get_expected_entity_version` / `_get_expected_memory_version`
