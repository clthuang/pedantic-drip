# Feature 116 Retrospective — F115 QA-Gate Deferred Hardening

**Status:** Implement complete; QA gate `MERGE_OK_HIGH_ZERO` (HIGH=0 / MED=17 / LOW=11)
**Branch:** `feature/116-f115-qa-deferred`
**Session date:** 2026-05-17
**Mode:** Standard (YOLO autonomous execution)
**Inherits from:** F115 `qa-override.md` (8 HIGH carry-forwards → FR-1 through FR-9)

## AORTA Analysis

### Aim
Close the 8 HIGH-severity findings deferred from F115's pre-release QA gate without disrupting F115's already-merged surface. Use F115 design rev 2 as canonical evidence base; add four code-surface deltas (C16-116 DiagnosticReport extension, C19-116 check_severity_vocab AST audit, C20-116 check_cross_workspace_parent_uuid file extraction, C21-116 _normalize_and_validate_fix_hint defensive parser).

### Outcomes (Observe — Quantitative)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| brainstorm | inherited | 4 (2 prd + 2 brainstorm) | 6 prd blockers iter1; approved iter2 with 3 cosmetic suggestions. 8 F115 HIGH carry-forwards mapped 1:1 to FR-1…FR-9. |
| specify | 50 min | 7 (4 spec + 3 phase) | 11 blockers iter1 + 4 iter3 + 2 iter3-retest. Substantial spec hardening. |
| design | 35 min | 5 (3 design + 2 phase) | 3 blockers iter1 + 2 sync blockers iter2. 4 code-surface deltas designed. |
| create-plan | 40 min | 6 (2 plan + 2 task + 1 phase + 1 relevance) | 1 TDD-order blocker (P-C.7 split → 7a red / 7b green) + 4 task blockers. relevance-verifier 4/4 clean. |
| implement | 70 min | 1 | 5 parallel implementers, 23 tasks, ~32 new tests across 7 files. 889 passed / 2 skipped / 0 failed. 14 CHECK_ORDER==19 sites swept to ==20. |
| finish | 15 min | 1 | 4-reviewer QA gate. HIGH=0 post AC-5b remap. MED=17 / LOW=11 deferred to F117 / retro fold. |

**Total:** ~24 reviewer iterations, ~3h 55min wall time, HIGH=0 outcome.

### Reflections (Review — Qualitative)

1. **Spec-phase iteration depth caught factual errors that would have caused implement-time failures.** Wrong migration function names, missing NOT NULL columns, FR-6 API signature mismatches, M15 transaction collision — all surfaced at spec review, not implement test runs. Compress-iterations strategy paid off downstream.

2. **TC.4 implementer discovered a real production gap.** `_fix_triage_cross_workspace_link` re-attribute branches will fail against `enforce_immutable_workspace_uuid` trigger. Caught because tests were written against production semantics, not mocks. Filed for F117.

3. **MCP entity-server unavailable throughout (lingering M12 from F108).** Third consecutive feature (F114→F115→F116) with the same outage. Manual `.meta.json` + direct DB INSERT pattern from F115 reused. Reconciliation pass needed on next MCP-available session.

4. **14 hard-coded `len(CHECK_ORDER)==19` assertions had to be swept to `==20` during TA.6.** Per F115 retro KB candidate #6, the test-fixture-sweep cost is materializing linearly with check additions, as predicted.

5. **F115 → F116 in-feature partial-and-resume pattern validated again.** F116 carried 8 HIGH gaps as a clean follow-up rather than F115 blocking. Three features now validate the pattern (F114→F115 in-feature resume; F115→F116 carry-forward).

### Tradeoffs / Tune (Process Recommendations)

1. **Codify partial-and-resume as a first-class workflow state** (high confidence) — add `qa-deferred` status enum + `next-feature-seed.json` emission.
2. **Front-load factual cross-checks before spec-reviewer iter1** (high) — pre-review symbol-validation sweep.
3. **Reconcile MCP entity-server state, don't keep falling back** (high) — `check_mcp_entity_server_reachable` doctor check + `pd:doctor --reconcile-mcp-state`.
4. **Promote dynamic-count test fixtures before next migration/check** (high) — schedule F117 task to convert all hard-coded `len(CHECK_ORDER)` / `schema_version` assertions.
5. **Treat the 17 MED test-deepener findings as a single F117 cluster** (medium) — coverage matrix as AC, not 17 separate FRs.
6. **Pre-implementation production-semantics smoke for trigger-protected columns** (medium) — plan-reviewer grep for `CREATE TRIGGER ... BEFORE UPDATE OF` against planned mutations.

### Takeaways (Act — Knowledge Bank Candidates)

**Patterns:**
- **Carry-forward HIGH findings as a follow-up feature, not an in-feature blocker** (high). When QA gate produces HIGH-but-non-blocking findings, file them in `qa-override.md` with explicit F-next references, merge to develop, and seed the next feature's brainstorm from the override list.
- **Compress reviewer iteration phases when artifacts inherit from a reviewed evidence base** (high). If F[N] inherits design/spec from F[N-1]'s already-approved canonical surface, fold implement Step 7 into finish-feature Step 5b.
- **Write implementer tests against real production semantics (triggers, constraints, gates), not mocked simulations** (high). Tests against real DB triggers surface collision bugs at test-write time.

**Anti-patterns:**
- **Deferring dynamic-fixture refactors when migration / check counts grow** (high). Hard-coded `len(CHECK_ORDER)==N` assertions accumulate linearly.
- **Repeatedly running with MCP entity-server unavailable rather than reconciling** (high). Fallback that works becomes load-bearing; reconciliation debt compounds.

**Heuristics:**
- **Plan-reviewer must flag trigger-collision when planned mutations touch trigger-protected columns** (medium). Grep `CREATE TRIGGER ... BEFORE UPDATE OF` against planned mutation columns.
- **Spec-reviewer iter1 blocker count is a leading indicator of factual-anchor drift** (medium). >6 iter1 blockers on symbols/signatures → pre-review symbol-validation sweep needed.

## 17 MED Findings (folded for F117 follow-up)

**4 remapped-HIGH gaps** (test-deepener, no cross-confirmation): skipped-check synthetic path, AST visitor non-Issue call, FR-9 byte-vs-char length, FR-9 integration point unguarded.

**11 MED gaps** (test-deepener original): within-check severity mix, unknown severity drop, AST recursion, M6/M7 boundary + no-op, M15 runner contiguity, SAVEPOINT isolation, plus 5 others detailed in `.qa-gate.json`.

**2 code-quality warnings:** regex comment clarity, byte-vs-char error message.

Recommended F117 framing: single FR "test-deepener coverage closure for F116 doctor checks" with a coverage matrix as the AC, not 17 individual FRs.

## 11 LOW Findings

Captured in sidecar `.qa-gate-low-findings.md`. 2 security (defense-in-depth) + 3 code-quality (cosmetic) + 2 implementation (stale docstring + commit SHA) + 4 test-deepener (round-trip + AST self-module + M7 no-op + FR-9 segment order).

## Production Gap (filed for F117)

`_fix_triage_cross_workspace_link` re-attribute branches at `fix_actions/__init__.py:472-482` issue `UPDATE entities SET workspace_uuid = ?` directly without dropping the `enforce_immutable_workspace_uuid` trigger first. In production this will fail with `'workspace_uuid is immutable — use re-attribution API'`. Other production re-attribution paths (`claim_unknown_entities` at `database.py:7956-7975`) drop + recreate the trigger; the cross-workspace triage fix function does not. Out of scope for F116 (coverage-only) — must be fixed in F117 before the triage feature can be used in real environments.

## Raw Data

- Feature: 116-f115-qa-deferred
- Mode: Standard (YOLO)
- Branch lifetime: same-day (created 05:55, complete 09:45)
- Total review iterations: ~24
- Tests: 889 passed / 2 skipped / 0 failed in F116 scope
- Files changed: 14 (8 new, 6 modified)
- HIGH=0 outcome; MED=17 + LOW=11 deferred

## Reference Files

- F116 artifacts: `docs/features/116-f115-qa-deferred/{prd,spec,design,plan,tasks,retro}.md`
- F116 QA gate: `.qa-gate.json` + `.qa-gate-low-findings.md`
- F115 inheritance: `docs/features/115-pd-data-model-followups/{retro.md,qa-override.md}`
- F115 retro KB predictions (validated by F116): #6 (test sweep cost linear), #5 (in-feature partial-and-resume)
