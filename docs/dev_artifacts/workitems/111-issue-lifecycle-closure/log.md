<!-- Append-only history of 111-issue-lifecycle-closure. Entry shapes: plugins/pd/references/log-entries.md. The entries below were converted from legacy files by pd-adopt. -->

## 2026-05-15 18:35+00:00 phase start -> brainstorm
Status: closed (legacy)

## 2026-05-15 18:35+00:00 review brainstorm — legacy
Status: closed (legacy)
Iterations: 1
"Brainstorm artifact = parent project PRD at docs/projects/P003-entity-system-redesign/prd.md. Scope crystallized via project decomposition: F9 (issue_spawn MCP \u2014 spontaneous mid-flight issue capture: issue_spawn(parent_uuid, kind, summary)), F10 (complete_phase(closes=[uuid...]) atomic closure linkage with entity_relations(from, to, kind='fixes') rows), Cleanup (drop free-text suffix parsing, remove FIVE_D_ENTITY_TYPES frozenset, dead-type literals). Per P003 roadmap M4 \u2014 Phase 4 Lifecycle Closure. This is the final feature in project P003; completes the entity system redesign initiative. Same brainstorm-skip pattern as features 108-110."

## 2026-05-15 19:04+00:00 review specify — legacy
Status: closed (legacy)
Iterations: 6
"spec-reviewer 3 iters (cap hit, approved with warnings, fixed inline in rev 3.1); phase-reviewer 3 iters (approved with minor edits, fixed in rev 3.3 final). 4 spec blockers + 3 phase blockers resolved. Carry-forward to design: R2 lifecycle_class enumeration audit, R5 workflow_phases trigger audit, R6 caller-uuid stability edge case (doc only). Empirical SUT pins A-K verified."

## 2026-05-15 19:32+00:00 review design — legacy
Status: closed (legacy)
Iterations: 4
"design-reviewer 2 iters (target cap; iter-1 had 4 blockers all resolved including ENTITY_MACHINES vs workflow_phases CHECK gap \u2192 status-only model adopted; iter-2 approved). phase-reviewer 2 iters (target cap; both approved-with-warnings, all addressed inline). Final design rev 2.3 = 925 lines. Spec was patched inline during design phase (rev 3.4) per Cross-Phase Spec Patch memory pattern. Carry-forward to create-plan: R6 caller-uuid stability (doc only), R7 entity_relations FK defense, R8 fixture taxonomy, COMMIT-ordering verification in IF-2 step 5, orphan detection accepted out-of-scope, same-PR Group-A+B constraint."

## 2026-05-16 04:04+08:00 review legacy — Step 1: Spec-Reviewer Review
Status: closed (legacy)
### Iteration 1 — 2026-05-15 (rev 1)
- **Reviewer:** spec-reviewer (Opus 4.7, model: opus)
- **Decision:** Needs Revision (approved=false; 4 blockers + 7 warnings + 3 suggestions)
- **Blockers:**
  - B1: 'issue' inconsistently typed as entity_type vs polymorphic kind
  - B2: complete_phase hardcoded status='closed' invalid for non-issue entities
  - B3: feature_uuid resolution within complete_phase unspecified
  - B4: FR-CL.1/AC-CL.2 contradicts §6 on backfill behavior
- **Changes:** Rewrote §1.1 to reflect post-109 (type, kind, lifecycle_class) triple; FR-9.2 maps kind→triple via register_entity internal mapping; FR-10.2 explicit caller uuid resolution; FR-10.3 step 3 derives terminal state per-lifecycle_class; AC-CL.2 reworded to document behavioral change.

### Iteration 2 — 2026-05-15 (rev 2)
- **Reviewer:** spec-reviewer
- **Decision:** Needs Revision (approved=false; 2 NEW blockers + 7 warnings + 3 suggestions)
- **Blockers:**
  - B5: task lifecycle gap — FR-BM.3 said task uses work_flow but work_flow has no 'closed' terminal
  - B6: cross-workspace closure leakage — FR-10.3 step 2 omitted workspace_uuid filter
- **Changes:** New ENTITY_MACHINES['task'] entry; lifecycle_class='task_flow' (new value); FR-10.2 resolves caller_workspace_uuid; FR-10.3 step 2 enforces same-workspace constraint; AC-10.9 (cross-workspace) added. Plus replay phase_event suppression, cross-closer error message specificity, AC-BM expansion, metadata merge semantics, Pin H (phase=NULL), Pin G exact count, doctor lint PROJECT_ROOT resolution.

### Iteration 3 — 2026-05-16 (rev 3 / 3.1)
- **Reviewer:** spec-reviewer (FINAL — cap-3 per CLAUDE.md)
- **Decision:** Approved with warnings (approved=true; 3 warnings + 5 suggestions)
- **Status:** Strict-threshold gate is FAIL (warnings present), but at iteration cap. Proceeding to phase-reviewer per skill: "If FAIL AND iteration == max: Note concerns / Proceed to Step 2 with warning."
- **Warnings (all fixed inline in rev 3.1):** concrete-N replay count (AC-10.4 = 3 replays); AC-10.x numbering jump (renumber); 'already terminal but no closer record' substring AC (AC-10.7); Pin I (live-DB task count = 0); Pin J (pre-109 live DB schema state); AC-MR.7 schema_migrations down state; AC-CL.4 two-CWD doctor test.

## 2026-05-16 04:04+08:00 review-2 legacy — Step 2: Phase-Reviewer Validation
Status: closed (legacy)
### Iteration 1 — 2026-05-16 (rev 3.1 → 3.2)
- **Reviewer:** phase-reviewer (Sonnet 4.6, model: sonnet)
- **Decision:** Needs Revision (approved=false; 3 blockers + 1 warning + 1 suggestion)
- **Blockers:**
  - PB1: FR-10.4 contradicts FR-10.3 step 4 on same-closer replay (FR-10.4 (b) "already terminal" unconditional triggers rollback)
  - PB2: Migration 14 missing lifecycle_class CHECK widening (no Pin confirming the column has no CHECK)
  - PB3: Duplicate AC-10.6/AC-10.7 numbering (cross-workspace and entity_status_changed both labeled AC-10.6; caller-not-registered and terminal-no-closer both labeled AC-10.7)
- **Changes:** FR-10.4 (b) narrowed to "already terminal AND different closer"; Pin K confirms lifecycle_class has no CHECK constraint at database.py:2983 + :3294 (verified empirically); AC-10.x renumbered to sequential 1-10; §6 cross-reference updated from AC-10.9 → AC-10.6; FR-MR.7 docstring clarifies Python-constant down-migration mechanism.

### Iteration 2 — 2026-05-16 (rev 3.2 → 3.3)
- **Reviewer:** phase-reviewer
- **Decision:** Approved with warnings (approved=true; 2 warnings + 1 suggestion)
- **Warnings (all fixed inline in rev 3.3):** _CLOSES_TERMINAL dict ownership pinned with literal Python dict in FR-10.3 step 3; FR-MR.2 ordering rule pinned ('bug' inserted between 'backlog' and 'initiative'); R2 blast radius enumerated (entity_engine.py, doctor/checks.py).

### Iteration 3 — 2026-05-16 (rev 3.3 final)
- **Reviewer:** phase-reviewer (FINAL — target cap per CLAUDE.md)
- **Decision:** Approved with minor edits (approved=true; 1 warning + 1 suggestion)
- **Warning:** Caller uuid stability across workspace re-registration — added R6 to §7.
- **Suggestion:** AC-MR.8 dangling "FR-10.7" reference — corrected to "FR-10.3 step 7".
- **Final status:** Spec is design-ready. All blockers cleared; minor edits applied in rev 3.3 final commit.

## 2026-05-16 04:04+08:00 review-3 legacy — Summary
Status: closed (legacy)
- **Spec-reviewer iterations:** 3 (hit cap; approved with warnings at iter 3 — all warnings fixed inline)
- **Phase-reviewer iterations:** 3 (target cap; approved with warnings at iter 2, all addressed; iter 3 final pass approved with minor edits applied)
- **Cumulative reviewer dispatches:** 6 (3 spec + 3 phase)
- **Final spec revision:** 3.3 (280-ish lines, FR groups F9 / F10 / Migration 14 / cleanup, AC groups AC-9.x / AC-10.x / AC-MR.x / AC-BM.x / AC-CL.x, §1.2 Pins A-K)
- **Empirical SUT pins:** 11 (A through K, all verified at spec time)
- **Open carry-forward considerations for design phase:** (1) entity_engine.py / doctor lifecycle_class enumeration sites (R2); (2) workflow_phases trigger audit for parent-row touches (R5); (3) caller uuid stability edge case (R6, doc-only).

### Design Phase Review History

## 2026-05-16 04:04+08:00 review-4 legacy — Step 3: Design-Reviewer
Status: closed (legacy)
### Iteration 1 — 2026-05-16 (rev 1 → rev 2)
- **Reviewer:** design-reviewer (Opus 4.7)
- **Decision:** Needs Revision (approved=false; 4 blockers + 5 warnings + 3 suggestions)
- **Blockers:**
  - DB1: ENTITY_MACHINES['bug']/['task'] use phase values workflow_phases.workflow_phase CHECK doesn't admit.
  - DB2: EntityNotFoundError + InvalidCloseTargetError classes referenced but undefined.
  - DB3: append_phase_event closure-transaction call omits required workspace_uuid.
  - DB4: TERMINAL_STATUSES_NON_TARGET unspecified; overlaps with 'already terminal but no closer record' path.
- **Spec patches:** ENTITY_MACHINES approach REMOVED for bug/task — status-only model adopted (FR-BM → FR-BL; AC-BM → AC-BL); FR-EX added defining exception classes; FR-MR.9 + AC-MR.10/11 added down-migration pre-flight; AC-10.11 added pinning state-machine bypass; Pins L + M added.
- **Design changes:** C4 rewritten (no ENTITY_MACHINES extension); C10 added (exception classes); C11 added (4 new EntityDatabase helper methods); IF-1 step 10 + IF-2 pass workspace_uuid; IF-9 defines exception classes; IF-3 down-migration adds pre-flight; §5 reorganized (Group A = DDL only; Group B = all Python constants); _CLOSES_TERMINAL placement clarified.

### Iteration 2 — 2026-05-16 (rev 2 → rev 2.1)
- **Reviewer:** design-reviewer (FINAL — target cap)
- **Decision:** Approved with nits (approved=true; 3 warnings + 3 suggestions)
- **All nits addressed in rev 2.1:** IF-1 ValueError-vs-EntityNotFoundError docstring; IF-1 workspace_uuid-on-spawned_child defensive note; IF-7 module placement → database.py; same-PR Group A+B constraint; IF-2 workspace_uuid scope check note.

## 2026-05-16 04:04+08:00 review-5 legacy — Step 4: Phase-Reviewer Validation
Status: closed (legacy)
### Iteration 1 — 2026-05-16 (rev 2.1 → rev 2.2)
- **Reviewer:** phase-reviewer (Sonnet)
- **Decision:** Approved with warnings (approved=true; 3 warnings + 2 suggestions)
- **All nits addressed in rev 2.2:** test_migration_14_safety.py → Group B; closes_applied replay-inclusion explicit comment; §5 parallelization restructured (B strictly before C); test_workflow_state_server.py audit sub-task added; doctor CHECK_ORDER registry location pinned at __init__.py:32.

### Iteration 2 — 2026-05-16 (rev 2.2 → rev 2.3 final)
- **Reviewer:** phase-reviewer (FINAL — target cap)
- **Decision:** Approved with minor nits (approved=true; 2 warnings + 1 suggestion)
- **All nits addressed in rev 2.3:** Explicit COMMIT-ordering note in IF-2 step 5 (transaction-close vs post-commit dual-write); orphan-detection accepted-out-of-scope statement in IF-1 atomicity (no compensating doctor check); closes_applied append inline comment.

## 2026-05-16 04:04+08:00 review-6 legacy — Summary
Status: closed (legacy)
- **Design-reviewer iterations:** 2 (target cap; iter-1 had 4 real blockers all resolved; iter-2 approved with nits addressed inline in rev 2.1)
- **Phase-reviewer iterations:** 2 (target cap; both rounds approved-with-warnings, all addressed inline)
- **Spec patches applied during design:** FR-BL replaces FR-BM (status-only model), FR-EX added (exception classes), FR-MR.9 added (down-migration pre-flight), AC-10.11 added (state-machine bypass), Pins L + M added.
- **Final design revision:** 2.3 (925 lines)
- **Sub-features:** 5 implementation groups (Migration 14 DDL / discriminator + Python constants / F9 / F10 / cleanup); strict ordering: A → B → {C ∥ D ∥ E}.
- **New code components:** issue_spawn MCP (IF-1), complete_phase closes= extension (IF-2), Migration 14 (IF-3), exception classes (IF-9), 4 EntityDatabase helpers (C11), _CLOSES_TERMINAL dict (IF-7), doctor check_no_free_text_status_parsers (IF-8).
- **Carry-forward to create-plan:** R6 caller-uuid stability (doc-only), R7 entity_relations FK violation defense, R8 test fixture taxonomy alignment, COMMIT-ordering implementer verification (IF-2 step 5), orphan-detection accepted out-of-scope.

### Create-Plan Phase Review History

## 2026-05-16 04:04+08:00 review-7 legacy — Reviewer 1: Plan-Reviewer
Status: closed (legacy)
### Iteration 1 — 2026-05-16 (rev 1 → rev 2)
- **Decision:** Needs Revision (approved=false; 4 blockers + 6 warnings + 2 suggestions)
- **Blockers:** PB1 Group A no test in same commit (TDD red-first), PB2 transaction-ordering vs feature 088 FR-5.1, PB3 missing Why-this-item/Why-this-order rationales, PB4 Group E parallel-with-D AC-CL.3 dependency.
- **Resolution:** Plan §1.1 documents atomic-DDL precedence + Task A.8 red-equivalent smoke; design rev 2.4 pins closure writes INSIDE existing transaction (caller's completed STAYS OUTSIDE preserving FR-5.1); per-Group Why-this-item/order rationales added; AC-CL.3 fixtures pinned as hand-crafted (E parallel-safe).

### Iteration 2 — 2026-05-16 (rev 2 → rev 3 + spec 3.4→3.5 + design 2.4→2.5)
- **Decision:** Needs Revision (approved=false; 2 NEW blockers + 4 warnings + 2 suggestions)
- **Blockers:** PB5 Pin G trigger — 5th parser site at reconciliation_orchestrator/entity_status.py:14-16 violates "re-spec on 5th site" contract; PB6 db.get_entity_by_uuid ALREADY EXISTS at database.py:4788 (don't duplicate).
- **Resolution (cross-phase spec patch per memory pattern):** Spec rev 3.5 adds FR-CL.1b for 5th-site cleanup + Pin G enumerates 3 paths + AC-CL.1 grep target = 3 paths; design rev 2.5 C8.b + IF-8 target_files = 3 paths + C11 corrected to "reuse existing"; plan rev 3 Group E Files lists entity_status.py; tasks E.4b added + B.11 simplified to reuse.

### Iteration 3 — 2026-05-16 (rev 3 → rev 3.1) — FINAL per CLAUDE.md cap
- **Decision:** Approved with warnings (approved=true; 1 warning + 3 suggestions)
- **All addressed in rev 3.1:** B.2 vs B.15 substring alignment; E.4b name-cleanup OOS; B.9 _REQUIRED_PARAMS downgrade; C.3 invocation note.

## 2026-05-16 04:04+08:00 review-8 legacy — Reviewer 2: Task-Reviewer
Status: closed (legacy)
### Iteration 1 — 2026-05-16 (tasks rev 3.1 → rev 3.2)
- **Decision:** Needs Revision (approved=false; 4 blockers + 5 warnings + 2 suggestions)
- **Blockers:** TB1 E.1 grep only 2 files (need 3); TB2 E.7 says "grep both files" (need 3); TB3 B.3 envelope test creates Group-D cross-dependency in Group-B test file; TB4 A.8 smoke script migration chain replay flawed.
- **Resolution:** E.1 + E.7 expanded to 3 production paths; B.3 simplified to AC-EX.1 only (AC-EX.2 moved to D.2); A.8 simplified to `EntityDatabase(':memory:')` constructor.

### Iteration 2 — 2026-05-16 (tasks rev 3.2 → design rev 2.6)
- **Decision:** Approved with nits (approved=true; 2 warnings + 1 suggestion)
- **All addressed in design rev 2.6:** C9 prose lists all 3 target files; design outline Group E shown as parallel-with-D.

## 2026-05-16 04:04+08:00 review-9 legacy — Reviewer 3: Phase-Reviewer (Chain Review)
Status: closed (legacy)
### Iteration 1 — 2026-05-16 (design rev 2.6 → rev 2.7) — FINAL
- **Decision:** Approved with stale-doc warnings (approved=true; 4 warnings + 1 suggestion)
- **All addressed in design rev 2.7:** spec rev cross-ref bumped 3.4→3.5; §1 architecture diagram corrected (ENTITY_MACHINES UNCHANGED); F10 dependency cell clarified ("NOT F9"); TD-8 snippet target_files extended to 3 paths.

## 2026-05-16 04:04+08:00 review-10 legacy — Summary
Status: closed (legacy)
- **Plan-reviewer iterations:** 3 (hit cap; 2 rounds of real blockers — including Pin G cross-phase spec patch in iter 2)
- **Task-reviewer iterations:** 2 (target cap; both rounds approved with iter-1 having 4 blockers all resolved)
- **Phase-reviewer iterations:** 1 (target — approved with stale-doc nits all addressed)
- **Cumulative reviewer dispatches:** 6 (3 plan + 2 task + 1 phase)
- **Spec patches during create-plan:** 1 — rev 3.4 → 3.5 (FR-CL.1b for 5th parser site, FR-CL.4 target_files = 3 paths, AC-CL.1 grep = 3 paths, Pin G revised to enumerate 3 production sites).
- **Design revisions during create-plan:** 2.4 → 2.5 → 2.6 → 2.7 (closure-transaction boundary, 3-path parser scope, parallelization outline, stale-doc residual fixes).
- **Final plan revision:** 3 (204 lines).
- **Final tasks revision:** 3.2 (~453 lines, 50 tasks across A/B/C/D/E + 3 cross-group verifications).
- **Carry-forward to implement:** R6 caller-uuid stability (doc-only), R7 entity_relations FK defense (FR-10.2 pre-validates), R8 fixture taxonomy alignment, same-PR Group-A-and-B verification gate, orphan-detection accepted OOS, E.4b name-cleanup OOS.

## 2026-05-15 20:05+00:00 review create-plan — legacy
Status: closed (legacy)
Iterations: 6
"plan-reviewer 3 iters (hit cap; iter 2 triggered Pin G cross-phase spec patch \u2014 5th parser site at reconciliation_orchestrator/entity_status.py + get_entity_by_uuid reuse; iter 3 approved with nits). task-reviewer 2 iters (target cap; iter 1 had 4 blockers all resolved). phase-reviewer 1 iter (approved with stale-doc nits all fixed in design rev 2.7). Spec patched 3.4\u21923.5 mid-phase. Design revised 2.3\u21922.7. Final plan rev 3 + tasks rev 3.2 (50 tasks across A/B/C/D/E + cross-group verification). Carry-forward to implement: same-PR A+B gate, COMMIT-ordering at workflow_state_server.py:1195-1199, orphan-detection OOS, name-cleanup OOS."

## 2026-05-15 21:30+00:00 review implement — legacy
Status: closed (legacy)
Iterations: 2
"All 4 reviewers approved at final-validation round. Iter 1: implementation-reviewer + relevance-verifier + code-quality-reviewer approved with non-blocking suggestions; security-reviewer raised 1 BLOCKER (FR-9.6 cross-workspace parent gap in issue_spawn). Iter 2: fixed via _catch_issue_spawn_errors decorator + canonical workspace resolution; all 4 reviewers approved 0 issues. Final regression: 4019 passed / 0 failures from project root. 6 implementation commits + 1 security/envelope fix: 40b6e1cf, d5e763c0, ac080777, 27aaf2a6, 357bfb6b, F12-fix, 1dd70a55."

## 2026-05-16 05:46+08:00 qa legacy .qa-gate.json
Status: closed (legacy)
Verdict: approved
```json
{
  "head_sha": "f4d34d7c8a7c9801b91ff7243977b25ad3f2e49e",
  "feature_id": "111-issue-lifecycle-closure",
  "run_at": "2026-05-15T22:00:00+00:00",
  "reviewers_dispatched": 4,
  "reviewers_completed": 4,
  "high_count": 0,
  "med_count": 23,
  "low_count": 11,
  "verdict": "approved",
  "test_only_refactor": false,
  "remap_applied": {
    "test_deepener_high_to_med": 2,
    "reason": "AC-5b: mutation_caught=false AND no cross-confirmation"
  },
  "low_findings_sidecar": ".qa-gate-low-findings.md",
  "merge_block": false
}
```

## 2026-05-15 21:47+00:00 review finish — legacy
Status: closed (legacy)
