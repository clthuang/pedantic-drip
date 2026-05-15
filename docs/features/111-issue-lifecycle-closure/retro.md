# Retrospective: Feature 111 — Issue Lifecycle Closure

## AORTA Analysis

### A — Actions / O — Observe (Quantitative Metrics)

| Phase | Iterations | Notes |
|---|---|---|
| brainstorm | 1 | Reused parent project PRD (P003) — instant transition (same pattern as features 108-110) |
| specify | 6 (3 spec-reviewer cap-3 + 3 phase-reviewer) | 4 iter-1 blockers + 2 iter-2 blockers + 3 iter-3 warnings (all fixed inline); 3 phase-reviewer blockers iter 1 (FR-10.4 same-closer carve-out, Pin K lifecycle_class no-CHECK, AC-10.x renumber); approved with stale-doc nits |
| design | 5 (2 design-reviewer target cap + 3 phase-reviewer iter cap) | 4 iter-1 blockers (status-only model invented to resolve workflow_phases CHECK incompatibility; EntityNotFoundError/InvalidCloseTargetError pinned; workspace_uuid wiring; TERMINAL_STATUSES_NON_TARGET dropped); 2 iter-2 phase-reviewer blockers (COMMIT ordering vs FR-5.1; test_migration commit boundary) — all resolved |
| create-plan | 7 reviewer dispatches | plan-reviewer 3 iters (cap; iter-2 triggered Pin G cross-phase spec patch — 5th parser site at reconciliation_orchestrator/entity_status.py + get_entity_by_uuid reuse); task-reviewer 2 iters (4 iter-1 blockers — E.1/E.7 3-file grep, B.3 envelope test cross-group dep, A.8 smoke script); phase-reviewer 1 iter (approved with stale-doc nits all fixed) |
| implement | 5 Group-level dispatches + 1 follow-up fix + 1 security/envelope fix | Group A (Migration 14 DDL only) → Group B (Python constants + helpers + tests, same PR per NFR-1) → Groups C/D/E parallel; F12 audit-comment placement fix; iter-2 security blocker fix (FR-9.6 cross-workspace parent gate + FR-EX.3 envelope) |

**Cumulative reviewer iterations across pre-implement phases: 18+** (6 specify + 5 design + 7 create-plan).

**Implementation review cycle: 2 iterations** — iter-1 had 1 security blocker (FR-9.6 cross-workspace parent gate missing in issue_spawn); fixed iter-2; final-validation all 4 reviewers approved.

**Final feature-111-scoped test count:** 88 passing (test_migration_14_safety.py 14 + test_status_only_lifecycle.py 8 + test_entity_lifecycle.py extension 2 + test_cleanup_suffix_parsers.py 7 + test_check_no_free_text_status_parsers.py 5 + test_issue_spawn.py 13 + test_complete_phase_closes.py 13 + cross-cutting 26).

**Broader suite at merge:** 4019 passing, 3 skipped, 0 failures (from project root).

**Total commits on feature/111-issue-lifecycle-closure:** 7 (40b6e1cf migration + d5e763c0 constants/helpers + ac080777 issue_spawn + 27aaf2a6 closes= + 357bfb6b cleanup + F12-fix + 1dd70a55 security/envelope) + docs.

### R — Review (Qualitative Observations)

1. **Pin G's "5th parser site → re-spec" contract fired exactly as designed.** Spec rev 3.4 enumerated 4 parser sites (2 production + 2 test paths); during plan-reviewer iter 2, the reviewer empirically discovered a 5th production site at `reconciliation_orchestrator/entity_status.py:14-18`. Pin G's pre-written escalation clause ("If a 5th parser site appears during design phase, re-spec instead of silently expanding scope") triggered an inline spec patch (rev 3.4 → 3.5) via the "Cross-Phase Spec Patch in Lieu of Backward-Travel" memory pattern. Spec grew FR-CL.1b + widened FR-CL.4 target_files to 3 paths + extended AC-CL.1 grep target. No full backward-travel to specify phase. Net cost: ~1 extra reviewer iteration. Net benefit: avoided silent cleanup-scope expansion and gave Group E a fully-bounded task list.

2. **Empirical-verification heuristic caught 2 design-phase factual errors.** Design-reviewer iter 1 verified `db.get_entity_by_uuid` already exists at database.py:4788 (vs. design C11 claiming it as a NEW helper). And iter 2 surfaced the existing `_process_complete_phase` post-commit dual-write at workflow_state_server.py:1202-1229 (feature 088 FR-5.1 contract — caller's `completed` event STAYS OUTSIDE the transaction). Both findings rerouted the implementation: REUSE the existing helper (saved ~5 LoC + a method namespace collision), and place closure writes INSIDE the existing with-block with mixed-semantics boundary (caller's completed stays outside per FR-5.1). The pattern "before writing 'NEW' anywhere in the design, grep the codebase for the symbol" is now reinforced as a hard discipline.

3. **The "status-only model" emerged from a design-reviewer blocker, not the spec.** Spec rev 3.3 declared `ENTITY_MACHINES['bug']` + `ENTITY_MACHINES['task']` entries with phase-state graphs. Design-reviewer iter 1 (B1) caught that workflow_phases.workflow_phase CHECK doesn't admit `'resolved'/'closed'/'wont_fix'` — adding bug/task to ENTITY_MACHINES would require ANOTHER copy-rename of workflow_phases. The cleaner resolution: **drop ENTITY_MACHINES entries entirely** and use status-only tracking (no workflow_phases rows for issue entities; status lives in entities.status; lifecycle_class is a declarative tag consumed by `_CLOSES_TERMINAL`). This was a structural simplification, not a feature regression. Spec FR-BM was rewritten as FR-BL; AC-BM as AC-BL. Net code saved: ~80 LoC (no ENTITY_MACHINES extension + no copy-rename of workflow_phases CHECK).

4. **Implementer-skill RED-first discipline was honored cleanly except for Group A.** Group A is DDL-only per NFR-1 atomic-commit discipline — tests live in Group B (same PR). Per the implement-skill's "Final-validation should not count against iteration cap" anti-pattern, the local smoke validation (Task A.8) was preserved as the red-equivalent gate AND its output was captured in Group A's commit message for self-witnessing. This is now a documented pattern.

5. **Security blocker in implementation review caught a real cross-workspace leak.** Spec FR-9.6 mandates parent_uuid must be in the same workspace as the caller. Group C's initial implementation validated existence + kind but NOT workspace. A caller supplying `workspace_uuid='<ws-A>'` with `parent_uuid` pointing to ws-B would have silently created a child in ws-A with cross-workspace parent_uuid reference (OWASP A01 broken access control). The fix: resolve caller's canonical workspace via `_db._resolve_workspace_uuid_kwargs(...)` BEFORE comparing to `parent_row['workspace_uuid']` — same canonical path register_entity uses internally, so the legacy `project_id='__unknown__'` alias resolves correctly. Reinforces: security reviewer is load-bearing for multi-workspace surfaces, not theater.

6. **FR-EX.3 envelope translation symmetry was found by code-quality, not security.** Code-quality-reviewer iter 1 warned that issue_spawn raised ValueError directly while complete_phase had `_catch_close_errors` decorator translating to `{"error": True, "error_type": ..., "message": ...}` JSON envelope. The symmetry violation was a quality issue (consistency) — but also a usability issue (MCP clients couldn't parse issue_spawn errors uniformly). Resolved via `_catch_issue_spawn_errors` decorator mirroring the F10 pattern.

### T — Tune (Process Recommendations)

1. **Promote the "empirical method-existence check" as a heuristic.** Before any design doc claims a NEW helper method or class, the design-reviewer (or design-author) MUST grep the codebase for the symbol. Pattern: `grep -nE "def {name}\b|class {name}\b" {target_file}`. If the symbol exists with compatible return shape, the design says REUSE; if absent, the design says NEW with explicit "(no existing definition — grep confirms)" annotation.

2. **Pin G escalation pattern is a reusable template.** When a spec enumerates a small N (production parser sites, migration paths, doctor check targets), include an inline escalation clause: "If an (N+1)th site appears during {downstream phase}, re-spec instead of silently expanding scope." This converts hidden assumption-drift into explicit re-spec triggers. Save this pattern.

3. **Mixed-semantics transaction boundaries deserve explicit documentation.** The F10 closure block lands INSIDE the existing `with db.transaction():` block (atomicity for closures per FR-10.4), while the caller's `completed` event STAYS OUTSIDE (preserves feature 088 FR-5.1 non-rollback guarantee). This is a deliberate trade-off. Document this kind of decision in design TDs AND in inline code comments, not just commit messages — future maintainers will lose the rationale otherwise.

4. **Pre-implementation reviewer iteration budget needs explicit upgrading for cross-phase-patch features.** Plan §1.1 + spec rev 3.5 + design rev 2.5 cross-phase patches consumed 2 additional reviewer iterations (across 3 reviewer types). The current "target 1-2, max 3 per phase" budget assumes self-contained phases; cross-phase patches need additional headroom. Recommend a heuristic: "If a downstream-phase reviewer triggers an upstream-phase patch (Pin G class), budget +1 reviewer iteration in the current phase to verify the patch."

### A — Act (Knowledge Bank Updates)

Knowledge bank updates added to `docs/knowledge-bank/{patterns,anti-patterns,heuristics}.md`:

- **Pattern:** Cross-Phase Spec Patch In Lieu of Backward-Travel (re-used from feature 110; reinforced here for Pin G trigger).
- **Pattern:** Status-Only Lifecycle Model for Lightweight Entities (no workflow_phases row; entities.status is sole state field; lifecycle_class is declarative tag).
- **Pattern:** Mixed-Semantics Transaction Boundary (atomic-side closures + best-effort caller dual-write — explicitly documented in IF-2 + TD-1).
- **Pattern:** Pin G "Re-Spec on (N+1)th Site" Escalation Clause (template for enumeration-bound specs).
- **Anti-Pattern:** Design Claims "NEW Helper" Without Codebase Grep (caught at design-reviewer iter 1 — `get_entity_by_uuid` already existed at :4788).
- **Heuristic:** Implementation-Reviewer Final-Validation Round Must Not Count Against Iteration Cap (already in memory — reinforced by F12 audit follow-up fix + security iter-2 fix that didn't exceed the 3-cap).
- **Heuristic:** Cross-Workspace Boundary Is Load-Bearing Across All Workspace-Scoped MCP Surfaces (FR-9.6 parent-side check mirrors FR-10.3 closes= same-workspace check — symmetric enforcement).

## Summary

Feature 111 delivered the full F9 (issue_spawn) + F10 (complete_phase closes=) + Migration 14 + cleanup scope across 5 implementation Groups + 1 security follow-up + 1 placement fix. 18+ pre-implement reviewer iterations across 4 phases converged with all blockers resolved (4 blocker-triggering cross-phase patches: spec rev 3.5 for Pin G, design rev 2.4 for FR-5.1 boundary, design rev 2.5 for get_entity_by_uuid reuse, spec rev 3.4→3.5 for parser scope expansion). Implementation was atomic-DDL-first (Group A standalone), Python-constants-second (Group B same-PR), then parallel-where-possible (Groups C/D/E independent worktrees). 88 feature-111 tests + 4019 broader regression all green at merge. Security reviewer caught a cross-workspace parent leak (FR-9.6) that the design phase had implicitly assumed but never asserted in tests — caught + fixed within the implement-phase review cycle (no backward-travel needed).

**Final state:** 7 implementation commits + docs + retro on `feature/111-issue-lifecycle-closure`, ready for merge to `develop`. This is the final feature in project P003 — closes M4 (Phase 4 Lifecycle Closure). Project P003 (entity-system-redesign) now complete across all 12 fixes / 4 features / 4 milestones.

**Tooling friction:** Codex CLI broken (ENOENT) — all reviewer dispatches used pd:Task per codex-routing fallback protocol. 3 pre-existing CWD-sensitive subprocess tests (semantic_memory/test_maintenance.py) fail when pytest runs from `plugins/pd/` but pass from project root — these are unrelated to feature 111 and persisted from prior features.
