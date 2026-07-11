# Retrospective: Workspace-Scoped Queries (feature/129-workspace-scoped-queries)

- **Mode:** standard · **Status:** implement complete, finish/merge pending
- **Active work window:** specify start 20:27:48 UTC (Jul 10) → implement complete 01:50:38 UTC (Jul 11) = ~5h23m. Branch `created` 11:07:53 shows ~9h20m pre-specify idle — same batch-creation pattern noted in 118/131's retros.
- **Commits:** 10 (`develop..HEAD`) — 7 attributed to implement (5 task commits + test-deepening + battery polish), ~3 for spec/design/plan docs.
- **Review dispatches:** 18 reviewer/gate dispatches, plus 1 test-deepener and 5 implementer task dispatches.
- **Blocker-severity issues:** 9 total — specify 1, design 4 (3 skeptic + 1 phase-gate), create-plan 4, implement 0.

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Blockers | Notes |
|---|---|---|---|---|
| specify | ~47m | skeptic 2 + gate 1 | 1 | iter-1: 2 behavior-equivalent inline gates missed by the symbol-scoped sweep; iter-2 approved (4 warnings, all fixed) |
| design | ~49m | skeptic 3 + gate 2 | 4 | iter-1: 2 (phantom-workspace-minting resolver; wholesale test-module deletion); iter-2: 1 (orphan-retention contradiction); gate round-1: 1 (unclosed UI-sweep assumption) |
| create-plan | ~1h4m | plan 3 + task 1 + relevance 1 + gate 1 | 4 | iter-1: 2 (orphaned test class; unsatisfiable grep); iter-2: 2 (unsatisfiable sibling greps; callerless validator block) |
| implement | ~2h43m | implementer×5 + battery×3 + 360-verifier (all approved iter-1) | 0 | implementation/code-quality/security ALL approved, zero warnings (2 suggestions total); 360-verifier separately: 2 warnings, both artifact-staleness only |

Both design-reviewer and plan-reviewer used their full 3-iteration allowance (CLAUDE.md's hard cap) before converging — neither breached it, but neither had headroom left either.

### Review (Qualitative Observations)

1. **Every blocker that would NOT have self-signaled at implement was a silent scope/coverage bug; blockers that WOULD have self-signaled still consumed full blocker-severity rounds.** design iter-1 I2 (wholesale test-module deletion — "silent coverage loss + vacuous grep pin") and plan iter-2 I2 (callerless validator block, "coverage regression on retained-but-dead code") ship undetected if missed — no test fails. plan iter-1 I1 (orphaned `TestFilterStatesByWorkspaceExceptionHandling`) and plan iter-3 I1 (stub TypeError from a missing `=None` default) would instead have failed loudly at the SAME task's own "Verify: suite green" step — cheap to catch late, but scored identically to the silent class today.
2. **131's follow-up action ("extract the duplicated workspace-resolution block into a shared helper," explicitly assigned to 129) closed by adopting existing dead code rather than writing a new helper.** Spec iter-2 I5 rejected a new helper for the two 2-arm doctor sites, adopting the zero-caller `_lookup_workspace_uuid_by_project_root` instead. The 4-arm `check_workspace_uuid_consistency` site was explicitly scoped OUT (its 0-vs->1 branching doesn't fit the helper's shape) — 2 of 3 duplicate sites closed, 1 still open for a future feature.
3. **A same-class dead-code leftover survived 3 rounds of plan review and was only caught during implementation.** The "callerless trigger-dance helper" was deleted with the fixer that owned its only call sites — same class as plan-iter-2's validator-block blocker. Plan review demonstrably knew this failure mode by name (it blocked on the validator block) but didn't apply the check exhaustively to every private symbol in the file it was already editing.

### Tune (Process Recommendations)

1. **Split blocker severity by failure signature.** 4 of 9 spec/design/plan blockers were self-signaling (collection-time ImportError, missing-default TypeError) vs. 5 silent (dead code, dropped coverage, contradicted contract) — both scored as BLOCKER today. Self-signaling issues can downgrade to WARNING; reserve BLOCKER for failure classes that ship undetected. Confidence: medium (single-feature sample; mechanism generalizes). → registered to backlog (workflow-rebuild track owns reviewer severity semantics).
2. **Keep the 118/131 import-sweep and non-vacuity checklist lines unchanged — still finding real, distinct bugs.** design iter-3 I1 (combined-import partial-surgery) is a direct hit of 118's import-sweep line; design iter-1 I2 and plan iter-2 I2 are direct hits of the non-vacuity line — three fires, three different code sites. Confidence: high.
3. **Add a schema-constraint check to design/plan-reviewer checklists.** design Testing Strategy #6b — unchanged through 3 design + 3 plan iterations + task-review + relevance-verifier — pinned a fixture asserting divergent `kanban_column` values per workspace for a colliding `type_id`: physically unconstructible, since `workflow_phases.type_id` is the table's PK (one shared row). The implementer caught it only by building the actual fixture. Any new test fixture that differentiates rows by a column must be checked against that table's PK/UNIQUE constraints before the strategy is pinned in prose. Confidence: high — new failure mode, not covered by any existing guardrail. → design-reviewer checklist line.
4. **Make the callerless-symbol check a whole-file sweep, not a single-symbol trace.** When a plan deletes a function/class, grep the CONTAINING FILE for every other `_`-prefixed symbol and confirm each still has a caller OUTSIDE the deletion span — not just the deletion target's own immediate call graph. Confidence: high — mechanical, generalizable. → plan-reviewer checklist line.
5. **Compress confirmatory phase-gate reruns, not skeptic rounds.** 18 reviewer/gate dispatches; 17 surfaced at least one fix-worthy finding — only design's second phase-gate round was a pure zero-finding reconfirmation. Skip a phase-gate's automatic second round when round-1's fix is a small, independently-quoted diff; do NOT extend this to the artifact skeptic reviewers — 8 of their 9 blockers were real. Confidence: medium.

### Act (Reflections)

**Patterns:**
- Landing every deletion WITH its reversal-test disposition in the same plan step produced zero implement-phase blockers on a feature deleting five separate enforcement-surface members — clearest evidence yet the 118 "front-load skeptic rounds" pattern scales to wider deletions. (confidence: high)
- A reviewer checklist line encoded from a prior feature's retro (import-sweep, non-vacuity) keeps finding genuinely new bugs on later features rather than going stale after one use. (confidence: high)
- Adopting an existing zero-caller helper instead of writing a new one — discovered mid-review, not pre-planned — closed a prior feature's retro action AND shipped less code than that action originally proposed. (confidence: high)

**Anti-patterns:**
- Pinning a test's row-differentiating column in design prose without checking it against the target table's PK/UNIQUE constraints — the assertion can be physically unconstructible, and no amount of reviewer re-reading catches it short of attempting the actual insert. (confidence: high)
- Treating "sole caller is the thing I'm deleting" as a one-off check applied to the specific symbol a reviewer happens to trace, rather than a transitive closure over every private symbol in the file being edited. (confidence: medium)
- Dispatch-report findings that are not persisted to feature artifacts are invisible to retro: the test-deepener observed a transient `TestMigration11ConcurrentRunners` flake (pre-existing test, passed in isolation and on re-run) in its dispatch report, but it was never recorded in `.review-history.md` — the retro's artifact grep could not see it. Load-bearing observations from dispatch reports must land in the review history. (confidence: high)

**Heuristics:**
- A plan bug that will fail LOUDLY at the next task's own "Verify" step (collection error, TypeError) is lower review-priority than one that fails SILENTLY (deleted-but-uncovered code, a contradicted contract). (confidence: medium)
- Before pinning a multi-row test fixture's discriminating column in a design doc, grep-verify that column is not (part of) the table's PK — two rows cannot differ only in column X if X's containing key IS the row's identity. (confidence: high)

## Raw Data
- Feature: `129-workspace-scoped-queries` · Mode: standard · Branch: `feature/129-workspace-scoped-queries` · lastCompletedPhase: implement
- Per-phase dispatches: specify 3 / design 5 / create-plan 6 / implement 4 reviewers + 1 test-deepener = 18 total review/gate dispatches
- Blocker-severity: 9 total (specify 1, design 4, create-plan 4, implement 0), all resolved pre-gate
- Doctor: 20→19 checks, 709→689 issues, zero drift elsewhere; tests 3411 passed (3423 post-deepening); validate.sh 0 errors; hooks 67/67
- Campaign blocker trajectory (131 → 118 → 129): 7 → 5 → 9. 129 spans a wider surface in one feature (DB + engine + MCP + UI + doctor, 5-member deletion set) than either predecessor — not directly comparable without a scope normalizer. Implement-phase blockers: 131 several, 118 zero-with-warnings, 129 zero-with-zero-warnings (first fully-clean battery).
- 118-retro actions exercised: Action 6 (import-sweep + non-vacuity checklist lines) — VALIDATED, fired 3× independently. Action 1 (shared-config blast-radius sweep) — NOT exercised (no config bump in 129's scope).
- 131-retro action exercised: Action 1 (workspace-resolution dedup, assigned to 129) — 2 of 3 sites closed via existing-helper adoption; `check_workspace_uuid_consistency` (4-arm) remains open.
- Pre-existing rot absorbed: UI test suite (42 failed + 25 errors → 0; root causes features 108/109), fixed in-path during task 5 while already touching `ui/tests/` — correctly scoped per leave-ground-tidier (fixed because encountered, not sought out).
