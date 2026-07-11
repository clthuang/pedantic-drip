# Retrospective: Append-Only Event Log (feature/119-append-only-event-log)

- **Mode:** standard · **Status:** implement complete, finish/merge pending
- **Scope:** 2 new files + 2 modified (`events.py`, `test_events.py` new; `schema_v2.py`, `test_schema_v2.py` modified) — all dark, zero live wiring, zero deletions. Smallest surface in the 131/118/129/119 lineage.
- **Active window:** specify-started 03:01:33 UTC → implement-completed 05:25:20 UTC (Jul 11) = **~2h24m** — fastest of the campaign (131 ~4h11m, 118 ~3h18m, 129 ~5h23m).
- **Blocker-severity issues:** 2 total (specify 0, design 0, create-plan 2, implement 0) — campaign low (131: 7, 118: 5, 129: 9).
- **Review/gate dispatches:** 13 (specify 2, design 2, create-plan 5, implement 4) + 1 test-deepener — fewer than 129 (18) and 118 (16).

## AORTA Analysis

### Observe (Quantitative Metrics)

Per-phase `started`→`completed` deltas in `.meta.json` are 11-15s for ALL four phases — verified at source (`workflow_state_server.py:944`, `:1213-1214`: both fields are genuine call-time timestamps). **Known mechanism (orchestrator correction):** under this session's YOLO orchestration, `transition_phase` is deliberately called at phase END immediately before `complete_phase` as a workaround for the current-phase projection lag (backlog:055 territory) — so started_at ≈ completed_at by construction. Durations below use completion-to-completion gaps (118's workaround).

| Phase | Duration (gap proxy) | Iterations | Blockers | Notes |
|---|---|---|---|---|
| specify | not isolable | 2 (spec-reviewer + gate) | 0 (2 warnings) | both iter-1 |
| design | 19m46s | 2 (design-reviewer + gate) | 0 (1 warning) | gate CLEAN 0/0 |
| create-plan | 49m4s | 5 (plan 1 + task 2 + relevance 1 + gate 1) | 2 | both at task-review iter-1; plan-review itself clean |
| implement | 1h14m46s | 4 battery (all iter-1) + test-deepener | 0 | 3rd straight blocker-free iter-1 battery; 2nd zero-warning |

### Review (Qualitative Observations)

1. **Both create-plan blockers landed at task-review, not plan-review** — a CHECK-count miscount (tasks said 4, design D7 has 3) and a payload-casing fork. A clean plan-reviewer iter-1 approval did not predict a clean task-review round.
2. **The casing fork originated in design D2, not the task breakdown** — `spec.md:22` already specified camelCase (`reviewerNotes`, `skippedPhases`); design D2's first draft flipped to snake_case; plan.md and tasks.md both copied the fork forward untouched. Caught only when task-review checked it against the live consumer (`workflow_state_server.py:474/:481/:1218` — camelCase is the live contract).
3. **Two runtime facts survived all 6 specify/design/create-plan review dispatches and were caught only by running real code** — (a) `autocommit=True` makes `conn.commit()`/`conn.rollback()` documented no-ops against a raw `BEGIN IMMEDIATE`; design D5 originally read `conn.rollback()`, corrected after the implementer scratch-tested it; (b) the committed 30-trial harness measured 27/30 pre-lock failures, worse than 118's uncommitted ~15/30 exploratory number — neither figure existed before someone ran the contention scenario.

### Tune (Process Recommendations)

1. **Keep plan-review AND task-review both mandatory regardless of how clean the other ran.** Create-plan blockers split task-review-only for 131/118/119 vs plan-review-only for 129: the split tracks scope-type (deletion-heavy work front-loads risk to the plan; pure-addition/dark work front-loads risk to the breakdown's transcription), not reviewer redundancy. Confidence: medium (n=4). → no process change; recorded as validation.
2. **Broaden the reviewer-claim verification guardrail to author-restated literals.** The casing fork is author-introduced literal drift, caught only by diffing against the LIVE consumer, not the immediately-prior artifact. Require restated literals (key names, casing, constants) to be diffed against BOTH the prior artifact AND the live consumer. Confidence: high. → CLAUDE.md guardrail edit.
3. **Generalize the schema-constructibility checklist line to stdlib/API behavior claims.** The D5 autocommit/rollback correction is the same failure class (prose claim about runtime behavior, unverified until run) as 129's PK-constructibility line — just for API semantics. Any design claim asserting specific stdlib/third-party behavior needs a cited runnable snippet or doc reference. Confidence: medium (single occurrence, validated class). → design-reviewer checklist edit.
4. **Per-phase timing is unrecoverable under the current projection-lag workaround.** The end-of-phase transition+complete pairing (backlog:055's consequence) collapses started_at into completed_at. Root fix is the phase-events write bug, not skill edits — recorded onto backlog:055 as a measured consequence. Confidence: high.
5. **129's Tune-5 (skip zero-finding confirmatory gate reruns) remains untested** — every 119 gate converged in 1 round; nothing to skip. Weak n=2 signal that the DESIGN phase-gate specifically is the lowest-yield dispatch. Confidence: low-medium; stays in backlog:058.

### Act (Reflections)

**Patterns:**
- An approved-clean plan-review round does not predict a clean task-review round, or vice versa — both independently earn their dispatch. (confidence: medium)
- Implementer-side empirical checks (scratch-testing an API claim, running the actual contention harness) catch stdlib/runtime facts a full artifact-review chain does not. (confidence: high)

**Anti-patterns:**
- A literal spelling correct in the spec can be silently flipped by the very next artifact and copied forward through two more before anyone diffs it against the live consumer instead of the immediately-prior doc. (confidence: high)
- `.review-history.md` records fix-worthy findings only, never clean checklist-line passes — a later retro cannot distinguish "checklist line exercised-and-passed" from "inapplicable". Same structural gap 129's retro flagged for dispatch-report findings. (confidence: medium)

**Heuristics:**
- When a review-fix touches a chain of artifacts, explicitly check whether the same literal appears in artifacts EARLIER than the one under review — fixes propagate forward by default and need a dedicated backward check (119's relevance-verifier spec-SC2 backport catch). (confidence: high)

## Raw Data

- Feature: 119-append-only-event-log · Mode: standard · lastCompletedPhase: implement
- Blocker-severity: 2 (0/0/2/0) vs campaign 131=7, 118=5, 129=9
- Review/gate dispatches: 13 (2/2/5/4) + 1 test-deepener; 9 commits over develop at retro time
- Tests: 3444 passed; SC6 grep 0; validate.sh 0 errors; hooks 67/67; doctor 19 (no live surface)
- **Scope confound (Q1):** 119 is the only campaign feature with BOTH zero live wiring AND zero deletions. The 9→2 drop (129→119) is more plausibly scope-driven than guardrail-driven — 129 ran AFTER 118's guardrails and still hit 9. Guardrails contributed at the margin (task-review's 2 mechanical catches; relevance-verifier's backport catch), not as the primary driver.
- Retro-facilitator correction absorbed: review-history cannot confirm clean checklist passes (only findings) — the "129 lines fired and were validated" claim in the dispatch brief was not verifiable from artifacts and is not asserted here.
