# Retrospective — Feature 106 QA Findings Batch Cleanup

**Branch:** `feature/106-qa-findings-batch-cleanup`
**Closes:** #00310-#00319 (10 deferred QA findings from features 104+105).

## Outcome

Shipped a 6-file/1-delete batch closing 10 backlog items in one ritual. All 8 FRs / 18 ACs verified PASS. test-hooks.sh now runs 120 tests (114 internal + 6 from external scripts). Direct-orchestrator implement; single-pass review-phase approval (all 4 reviewers approved iter 1 with only 2 non-blocking warnings on test infrastructure).

## A — Achievements

- **Direct-orchestrator implement holds across 6 consecutive features (101, 102, 104, 105, 106).** Heavy upstream review (specify 2 + design 1 + create-plan 3 = 6 iterations) traded for single-pass implement convergence. The pattern continues to deliver.
- **3 conflicting/coupled fixes resolved cleanly via Decision sections in spec.** Spec scope-decisions D1 (#00310 vs #00315), D2 (#00312 vs #00314), D3 (#00319 documentation-only), D4 (#00317 wontfix) were made explicit at spec time, eliminating mid-implementation debate. Saved at least one round of review iteration.
- **Test consolidation preserved both functions' coverage.** Spec-reviewer iter 1 caught a real factual error in my draft FR-3 (I wrongly described the underscored file as covering `cleanup_stale_correction_buffers`; it actually covers `cleanup_stale_mcp_servers`). After verification + spec rewrite, the consolidated `test-session-start.sh` now runs 6 tests (1 corr + 5 mcp) where previously the project had 2 disjoint files with copy-paste extraction. AC-3.3 ≥6 test-count guard catches lost coverage.
- **Closure disposition table prevents over-implementation.** Of the 10 backlog items, 7 were implemented as code, 1 was subsumed (sed-extract during consolidation), 1 was wontfix-rationaled (#00317), 1 was documented-only (#00319). The disposition table in spec made the "do everything" anti-pattern explicit and avoided it.

## O — Obstacles

- **Spec-reviewer iter 1 caught factual error in FR-3.** I drafted FR-3 assuming both files covered `cleanup_stale_correction_buffers` (the AC-6.1 function from feature 104). They actually covered different functions in the same source file. Spec AC-3.1 ≥1 grep would have passed trivially without preserving MCP-server coverage. Lesson: when consolidating files, READ both files first and explicitly document what each covers.
- **Plan-reviewer iter 1 caught the FR-5 / test-script env-var coupling.** T1 added the `CLAUDE_CODE_DEV_MODE` guard but forgot to also export the var in `test-capture-on-stop.sh`. The guard would have made existing tests fail silently because the seam went no-op. Plan-reviewer flagged this as a blocker. Lesson: when adding a defensive guard to a production code path, audit the test scripts that exercise that path.
- **Task-reviewer iter 1 caught regex inconsistency between spec AC-4.1 and design I-4 function names.** My tasks.md regex matched `test_category_(anti_patterns|preference)\(\)` but design I-4 named the functions `test_category_mapping_(anti_patterns|preference)\(\)`. The DoD check would have failed even after correct implementation. Both reviewers (task + phase) caught it independently. Lesson: when AC verification involves regex-checking against design-named identifiers, derive the regex from design verbatim, not paraphrased.
- **T1+T4 shared-file dependency was not in the plan's parallelism graph.** Group A and Group B were marked parallelizable, but T1 (Group A) and T4 (Group B) both write to `test-capture-on-stop.sh`. Both reviewers (task + phase) caught it. Lesson: dependency graphs must check for shared-file edits, not just task-by-task semantic dependencies.
- **AC-3.2 grep pattern initially over-escaped.** My T3 verification snippet used `'sed -n '/^cleanup_stale_correction_buffers'` (single-quoted) which broke shell-quote propagation. Re-running with double-quotes worked. Lesson: shell-script inside markdown verification snippets needs a quick "would this actually run" review.

## R — Risks Surfaced

- **#00317 wontfix could become real later.** The validate.sh `|| true` pipeline-error-handling pattern is documented as future-audit. If a real bug surfaces from masked errors in the diff pipeline, it's already documented as known. Acceptable.
- **Test infrastructure depends on env-var ordering.** FR-5 guard means `test-capture-on-stop.sh` MUST `export CLAUDE_CODE_DEV_MODE=1` before any sourced helper or subprocess that exercises the seam. If a future test refactor moves the export, tests silently no-op. Code-quality-reviewer flagged the shared-TEST_HOME defense-in-depth gap; addressed via trap-based HOME restore. Sed-extract silent-failure also addressed via grep sanity check.
- **Multiple feature-derived dispatch sites for `cleanup_stale_mcp_servers` testing now consolidated.** If session-start.sh ever introduces a third cleanup function, the merge target's organization (1 helper + N tests) handles it cleanly.

## T — Themes / Trends

- **Spec scope-decisions are load-bearing for batch features.** Feature 102 batch (Memory pipeline closure), 104 batch B (Test hardening), and now 106 (QA findings batch) all benefit from explicit decision sections that resolve conflicting/coupled fixes BEFORE design. Without that, design-reviewer would have re-litigated the same questions.
- **Reviewer agreement is high on regex/dependency issues.** Both task-reviewer and phase-reviewer independently caught the same 2 issues (regex mismatch + shared-file). Two reviewers agreeing on the same issue is strong signal. The redundancy is not waste; it's confidence.
- **Test infrastructure hardening is suggestion-territory after primary scope is met.** Code-quality-reviewer flagged 2 test-infra defense-in-depth gaps as warnings (not blockers). Both fixes are <10 lines and isolate failure modes. Pattern: fix as part of the same feature when fixes are micro; defer otherwise.

## A — Actions

1. **Knowledge bank entries to capture:**
   - Pattern: "Spec scope-decisions section resolves conflicting/coupled fix items before design; saves a review round." (process category)
   - Anti-pattern: "Drafting FR descriptions about consolidation without reading both target files first." (process / spec category)
   - Pattern: "When adding a defensive guard to production code, audit test scripts that exercise the gated path; both production AND test edits are part of the same task." (test-engineering)
   - Pattern: "Regex DoD checks must derive identifier names from design verbatim, not paraphrased." (process / spec)
2. **Document agent_sandbox/ gitignore convention** — done in this feature (FR-1b → component-authoring.md). Future features inherit the documented convention.
3. **Watch for #00317 (validate.sh `|| true` pipeline) reappearing as a real defect.** Currently wontfix; promote to backlog if observed.

## Workarounds Captured

None this feature. The factual error in FR-3 was corrected at spec time. The T1/T4 shared-file dependency was made explicit; not a persistent workaround.

## Iteration Counts

| Phase | Reviewer iterations |
|-------|---------------------|
| specify | 2 (spec-reviewer iter 1+2 → APPROVED; phase-reviewer iter 1 → APPROVED) |
| design | 1 (design-reviewer iter 1 → APPROVED; phase-reviewer iter 1 → APPROVED) |
| create-plan | 3 (plan-reviewer iter 1+2+3 → APPROVED; task-reviewer iter 1+2 → APPROVED; phase-reviewer iter 1+2 → APPROVED with 2 warnings then APPROVED) |
| implement | 1 (all 4 reviewers approved iter 1 with 2 suggestion warnings on test infra; both addressed inline) |
| **Total** | **7 reviewer-cycle iterations across 4 phases** |

The 7-iteration upstream investment paid off in 1-iteration implement convergence — same heavy-upstream/cheap-downstream pattern as features 101, 102, 104, 105.
