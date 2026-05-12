# Retrospective: 113-feature-112-qa-followups

## AORTA Analysis

### Observe (Quantitative Metrics)
| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | ~16 min | 5 spec-reviewer + 3 phase-reviewer | Factual error in FR-4.1 (claimed Migration 11 column missing when it existed); verification skipped iter 1 |
| design | ~15 min | 2 design-reviewer + 2 phase-reviewer | Iter 1: 3 blockers + 2 warnings + 3 suggestions; iter 2: clean PASS |
| create-plan | ~20 min | 3 plan-reviewer + 2 task-reviewer + 2 phase-reviewer | task-reviewer iter 1 found 3 mechanical blockers plan-reviewer missed |
| implement | ~2 hr | 1 (all 4 reviewers PASS first attempt) | Simplification pass applied post-approval; AC-12 baseline diff empty (3852 passed, +33 new tests, 0 net-new failures); 1 destructive-edit incident on PI-1 caught and restored |

Standard-mode feature, ~3h end-to-end. Specify dominated iteration cost (5 iters, hard-cap territory). Implement was the cleanest phase (4/4 reviewers approved iter 1), validating that thorough upstream review pays off downstream. Total review iterations: 12. 35 commits, 34 files, +4343/-55 LOC, 33 new tests, zero regressions.

### Review (Qualitative Observations)
1. **Specify hit 5 iterations because factual claims about existing code were unverified.** — Spec asserted Migration 11 lacked workspace_uuid on workflow_phases when the column existed; reviewers absorbed the cost of a verifiable factual error.
2. **task-reviewer caught 3 mechanical blockers plan-reviewer missed.** — Dangling T7a.4 reference, missing finish-feature.md wiring task, unassigned FINAL_FAIL_COUNT shell var. Validates the two-tier review chain.
3. **Implement achieved first-pass approval from all 4 reviewers.** — TDD Tests+X/Impl+X structure plus surgical scope (no schema migration, ~150-250 LOC) produced highly reviewable per-PI commits.
4. **Implementer agent on PI-1 produced an out-of-scope destructive overwrite (maintenance.py 845→3 lines).** — Caught manually; reviewers focused on PI scope and would not have surfaced it.

### Tune (Process Recommendations)
1. **Add Verification Checklist preamble to specifying-feature skill** (Confidence: high)
   - Signal: Specify ran 5 iters largely correcting unverified factual claims (FR-4.1 column existence).
   - Action: Require grep/SQL verification of every concrete claim about existing code before spec submission.
2. **Keep task-reviewer/plan-reviewer separation; add cross-reference check to plan-reviewer** (Confidence: high)
   - Signal: task-reviewer caught 3 blockers (dangling task IDs, missing wiring, unassigned shell var) plan-reviewer missed.
   - Action: Add explicit 'all referenced task IDs must exist in tasks.md' rule to plan-reviewer prompt; preserve two-tier structure.
3. **Reinforce TDD Tests+X/Impl+X plan pairing as documented default** (Confidence: high)
   - Signal: 4/4 first-pass approval across 8 PIs correlates with TDD pairing structure.
   - Action: Document in create-plan skill as the expected per-PI shape.
4. **Add scope-creep diff sentinel for implementer agent returns** (Confidence: high)
   - Signal: PI-1 implementer overwrote out-of-scope maintenance.py (845→3 lines), caught manually.
   - Action: PostToolUse hook or implementing-skill check: flag any file modification not in PI scope OR net change < -50% of original size.
5. **Promote mutation-pin (.MUT) gates as a pattern for observability PIs** (Confidence: medium)
   - Signal: PI-3.MUT and PI-6a.MUT produced explicit traceability for emitter/helper changes.
   - Action: Add checklist item to create-plan: 'PIs touching emit/log/event paths include explicit .MUT mutation-pin gate task.'

### Act (Knowledge Bank Updates)
**Patterns added:**
- TDD Tests+X/Impl+X plan pairing per PI produces first-pass reviewer approval (from: Feature 113, implement phase — 4/4 reviewers PASS iter 1 across 8 PIs)
- Two-tier plan review (plan-reviewer + task-reviewer) catches distinct defect classes (from: Feature 113, create-plan — task-reviewer iter 1 caught 3 mechanical blockers post plan-reviewer PASS)
- Mutation-pin observability gates (PI-N.MUT) provide explicit verification for emitter/hook changes (from: Feature 113, PI-3.MUT and PI-6a.MUT)

**Anti-patterns added:**
- Asserting facts about existing code in spec without grep/SQL verification (from: Feature 113, specify phase — FR-4.1 factual error drove 5 iters)
- Trusting implementer agents to stay within PI scope without automated diff sentinel (from: Feature 113, PI-1 — maintenance.py 845→3 line destructive overwrite caught manually)

**Heuristics added:**
- After 3 reviewer iterations in any phase, pause and meta-review: artifact wrong or recurring issue class? (from: Feature 113, specify — 5 iters in a recurring class signaled need to address upstream)
- Surgical-scope QA-followup features should target Standard mode with TDD per-PI pairing and expect first-pass implement approval (from: Feature 113 — 11 MED findings, ~150-250 LOC, no schema, 4/4 first-pass approval)

## Raw Data
- Feature: 113-feature-112-qa-followups
- Mode: standard
- Branch lifetime: ~3 hours active (specify start 06:34Z → implement complete 09:24Z, 2026-05-12)
- Total review iterations: 12 across phases (5+3 specify, 2+2 design, 3+2+2 create-plan, 1 implement)
- Commits: 35 (11 FR + 4 simplification/quality + CHANGELOG + meta updates)
- Files: 34 changed, +4343/-55 LOC
- Tests: +33 new, 3852 passing, 0 net-new failures
