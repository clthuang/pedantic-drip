# Retrospective: Rotted Doctor-Check Fix (feature/131-rotted-doctor-check-fix)

- **Mode:** standard
- **Started:** 2026-07-10T11:21:57Z (specify) · **Implement complete:** 2026-07-10T15:29:19Z
- **Branch lifetime:** ~4h 11m; 19 commits (11:18–15:29 UTC), 0 uncommitted rework
- **Total reviewer iterations:** 16 phase-tracked (specify 6 / design 5 / create-plan 4 / implement 1) + 1 pre-implementation relevance gate + 4 parallel implement-QA dispatches
- **Blocker-severity issues:** 7 total (2 specify, 3 design, 2 create-plan, 0 implement), all resolved pre-merge

## AORTA Analysis

### Aim
Fix 7 doctor-check SQL sites broken by features 108/109 dropping `entities.entity_type`/`project_id` — 3 checks silently returned nothing (false negatives via swallowed `sqlite3.Error`), 1 check mass-flagged ~320 false positives; delete `check_project_attribution` as a duplicate of the live `check_unknown_workspace_orphans`; add a durable surface/tolerate discriminator (`_run_live_schema_query`) plus a committed EXPLAIN scan so the next schema drop fails loud instead of rotting silently.

### Observations

| Phase | Duration | Iterations | Blockers | Notes |
|---|---|---|---|---|
| specify | 52m36s | 6 (4 spec-reviewer + 2 phase-reviewer) | 2 | iter-2 blocker reversed the fix→delete scope decision; iter-4 was blocker-free and corrected a false claim iter-3 had introduced |
| design | 45m03s | 5 (3 design-reviewer + 2 handoff) | 3 | iter-1/iter-2 blockers were both new-vs-existing reconciliation gaps; handoff-iter-1 caught a half-applied interface contract |
| create-plan | 44m48s | 4 (plan-1 + task-2 + readiness-1) | 2 | both blockers landed in task-review iter-1 (a dropped plan-mandated test, a self-contradicting summary) |
| implement | 1h38m36s | 1 primary pass (5 commits) | 0 | 2 implementer dispatches + simplifier + test-deepener; 4 independent QA gates (implementation/relevance/quality/security) all approved iteration 1; 1 warning fixed inline, no re-dispatch |

- Tests: `test_checks.py` 114→122 (dispatch 1, +8); full doctor package 236→244→248 passed (1 persistent skip) across the 3 implementation commits — net growth despite fully deleting `check_project_attribution`'s suite.
- Live doctor, before → after: orphan-class false positives 0/12 (was a ~320-warning class); `project_attribution` issues 0; `feature_status`/`brainstorm_status` candidate sets 283/5 (previously silent no-ops, now alive); total issue count 601→740 (the increase is newly-surfaced TRUE drift — features 126/127's target — not a regression).
- The single highest-leverage catch in the whole trail was spec iteration 2's blocker: it reversed the feature's core scope decision (fix → DELETE) by cross-referencing Migration 11's sentinel mapping against the live sibling check — evidence that was already in the repo, just not yet checked.
- Spec iteration 3's own revision introduced a **false factual claim** ("`backfill_project_ids` writes the dropped `project_id`") that a fresh iteration-4 dispatch refuted by citing `database.py:7818-7824` — the claim had already been written into SC#6 and Evidence for one full round before being caught.
- "Vacuous green" (a test passing by silently falling through to the tolerate/fallback branch instead of exercising the new path) was independently flagged in 4 separate rounds — design iter-1, iter-2, iter-3, and plan-review — before `[D].1`'s non-vacuity guard fully stuck.

### Root Causes
1. **Fresh-dispatch-per-iteration is what caught the false reviewer claim** — a persistent reviewer revising its own prior text has no structural reason to re-derive what `backfill_project_ids` actually writes; a genuinely independent iteration-4 dispatch did.
2. **The spec/design blockers were substantive, not cosmetic** — every blocker cited above changed a decision (scope, test strategy, or interface contract), which is why 6+5 rounds were earned rather than nitpick churn.
3. **Vacuous-green risk is structural, not a one-off oversight** — any feature adding a new code path beside an existing fallback path creates a blind spot where "zero errors" tests pass without ever touching the new path; this repo re-discovered that fact 4 times in one feature before encoding it as `[D].1`.
4. **Interface changes inside one markdown doc don't self-propagate** — `design.md`'s docstring was updated to the `(rows, tolerated)` contract, but its own function signature and two code snippets a few paragraphs away still showed a bare `list` return; nothing greps the document for the changed symbol.
5. **Implement's clean first pass reflects upstream cost, not luck** — by the time code was written, spec (6 rounds) + design (5 rounds) + create-plan (4 rounds) had already resolved every ambiguity down to byte-exact line citations pinned in `design.md`'s literal code blocks.

### Takeaways

**Patterns (worked well):**
- Fresh-dispatch-per-round self-corrected a reviewer's own error one round later — trust the next independent pass over the current one's confidence.
- Delegating "final verification" to the next gate instead of re-dispatching at the iteration cap (specify iter-4, design iter-3, implement's Final Validation citing `anti-patterns.md:645`) kept 16 tracked iterations from becoming runaway loops.
- Design code blocks pinned literally, with a stated "re-locate by content if drifted" fallback, meant implementers needed zero clarification rounds — all 4 implement-phase reviewers approved on iteration 1.

**Anti-patterns (avoid):**
- A reviewer-introduced factual claim was accepted into the spec for a full round before independent verification — reviewer output isn't self-verifying and needs the same citation discipline as author output.
- New logic was designed in isolation from the nearest pre-existing adjacent mechanism twice in the same phase (legacy test fixtures, then the `local_entity_ids` heuristic) — each cost a dedicated blocker round.

**Heuristics:**
- When a new/rewritten path sits beside an existing tolerate/fallback path, every new-path test must assert something true *only* on that path — "no exception raised" is satisfied by the fallback too.
- When a reviewer's fix note contains a specific, checkable claim about existing code behavior, cite the file:line that verifies it before the claim propagates to the next phase.

### Actions
1. Extract the 3×-duplicated workspace-resolution block (`plugins/pd/hooks/lib/doctor/checks.py`, mirrors `:582-592`) into a shared `_resolve_project_root_workspace_uuids` helper — feature 129 (workspace-scoped-queries), per the Level-3 code-quality-reviewer follow-up.
2. Rename the misnamed `Test*Has14Checks` class(es) in `plugins/pd/hooks/lib/doctor/test_doctor.py` (asserts 20, not 14) when feature 133 (the 12-check retirement) next touches that file.
3. Log the security-reviewer's 2 defense-in-depth suggestions (entity_id path-join guard for read-only existence probes; `checks.py:1583` startswith-prefix edge) to the backlog.
4. Add a Risk/Open-Question entry to `docs/brainstorms/20260710-153500-workflow-rebuild.prd.md`: FR-4 collapses skeptic+gatekeeper into one reviewer pass per gate, but feature 131's iteration-3→4 catch shows a false reviewer claim was only caught by a *second independent dispatch* — evaluate before that PRD reaches design.
5. Add a non-vacuity checklist line to `plugins/pd/agents/design-reviewer.md` and `plugins/pd/agents/plan-reviewer.md`: for every new-path/tolerate-path pair, does at least one test assert a fact true only on the new path?
6. Feed the 283 (`feature_status`) + 5 (`brainstorm_status`) newly-visible drift warnings into the next P004 checkpoint (features 126/127) as their starting backlog.

## Raw Data
- Feature: 131-rotted-doctor-check-fix | Mode: standard | Branch: `feature/131-rotted-doctor-check-fix`
- lastCompletedPhase: implement; finish phase started 2026-07-10T15:30:31Z (this retro)
- Commits: 19 (branch created 11:18:06 UTC → last fix commit 15:29:06 UTC)
- Per-phase iterations: specify 6 / design 5 / create-plan 4 / implement 1 (+ 1 relevance gate, +4 parallel implement-QA dispatches)
- Total blocker-severity issues: 7 (2 specify, 3 design, 2 create-plan, 0 implement)
- Tests: 248 passed / 1 skipped (final); doctor issues 601→740 (0 false positives, 0 project_attribution)
