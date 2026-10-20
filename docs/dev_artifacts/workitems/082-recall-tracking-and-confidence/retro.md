# Retrospective: 082-recall-tracking-and-confidence

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Iterations | Notes |
|-------|-----------:|-------|
| specify | 7 | 4 spec-reviewer + 3 phase-reviewer. Blockers: FR-3 field count contradiction, AC-10 idempotency incoherence, HP-5 arithmetic, _resolve_int_config prefix, session-start invocation idioms, NFR-2/AC-24 contradiction |
| design | 6 | 3 design-reviewer + 3 phase-reviewer. Blockers: read_config signature wrong (file path vs project root), __init__ lifecycle elided, SIGKILL recovery wording, timeout value conflict with spec |
| create-plan | 9 | 3 plan-reviewer + 5 task-reviewer + 1 phase-reviewer. Blockers: AC-32 seam duplication, test-hooks.sh monolithic runner pattern, AC-30 missing from plan, 15-task chain cap |
| implement | 1 | All 4 reviewers approved first try |

**Totals:** 23 review iterations (22 pre-implementation + 1 implement). ~82 min pre-implementation review time.

**Deliverables:** ~4860 insertions across 15 files. NEW: maintenance.py (~480 LOC), test_maintenance.py (~1600 LOC). EDITED: database.py (+110), test_database.py (+320), session-start.sh (+45), test-hooks.sh (+134), 3 config/doc files (+25).

**Tests:** 516 semantic_memory (was 453, +63) + 103 hook tests (was 101, +2). validate.sh: 0 errors, 4 warnings (= baseline).

**Performance:** AC-24 elapsed_ms=36ms for 10k entries (target: <500ms local, <5000ms CI). EXPLAIN QUERY PLAN: full table SCAN (acceptable at current scale per R-6).

### Review (Qualitative Observations)

1. **Spec phase drove most rework (7 iterations) due to internal AC inconsistencies** — FR-3 field count contradiction (said "four" but listed five), AC-10 skipped_floor under-count (spec said 1, correct answer was 2 for the 3-entry seed), NFR-2/AC-24 performance target contradiction. These are cross-reference failures, not missing requirements.

2. **Task-reviewer was the highest-iteration single reviewer (5 in create-plan)** — Caught AC-32 seam duplication (test needed at both database.py and decay level), test-hooks.sh monolithic runner pattern violation (proposed separate file, corrected to inline functions), AC-30 entirely missing from plan, and 15-task chain cap requiring Phase 3 split into 3a/3b/3c sub-stages.

3. **Design pseudocode had a correctness bug in the SQL NULL branch** — I-2 prescribed `last_recalled_at IS NULL AND created_at < grace_cutoff` but the Python partition needed in-grace rows in the result set to count them for `skipped_grace`. Implementation deviated by widening the NULL branch to fetch all never-recalled entries. Caught during implementation, not during design review — a gap in the review process.

4. **Implementation passed all 4 reviewers on first try** — Zero rework after 22 pre-implementation review iterations. Validates the heavy-upfront-review strategy for features touching established infrastructure (session-start.sh, database.py). The 82-minute review investment avoided what would likely have been multi-hour debugging cycles.

5. **Phase 6 (existing-test remediation) was a verified no-op** — 0 ordering-assertive tests impacted because `memory_decay_enabled` defaults to `false`. The entire phase was reduced to a single audit-grep confirming no hits.

### Tune (Process Recommendations)

1. **AC consistency cross-check for shared-state variables** (Confidence: high)
   - Signal: 7 spec iterations primarily from numeric inconsistencies between ACs referencing the same state (skipped_floor count, performance targets).
   - Recommendation: add spec-reviewer instruction to build a "shared-state consistency matrix" listing variables mentioned in multiple ACs and verifying numeric expectations match the explicit test seed data described in those ACs.

2. **Plan AC coverage diff** (Confidence: high)
   - Signal: AC-30 was entirely missing from plan; discovered only after 3 plan-reviewer iterations.
   - Recommendation: add plan-reviewer pre-check that diffs the full AC list from spec against ACs referenced in plan tasks. Flag uncovered ACs immediately rather than discovering omissions iteratively.

3. **Validate upfront review depth for infrastructure-additive features** (Confidence: high)
   - Signal: 22 pre-implementation iterations yielded 1-iteration implementation with zero rework.
   - Recommendation: maintain current review depth for features touching session-start.sh + database.py. The investment ratio (82 min review : 0 min rework) is excellent.

4. **Conditional R-6 remediation phase for opt-in features** (Confidence: medium)
   - Signal: Phase 6 was a verified no-op (0 impacted tests) because decay defaults to disabled.
   - Recommendation: when a new feature defaults to disabled, reduce R-6 to a single audit-grep + conditional gate. Skip planning 3 remediation tasks — plan 1 audit + conditional.

5. **SQL pseudocode trace tables in design** (Confidence: medium)
   - Signal: design I-2 NULL branch was incorrect; caught during implementation, not review.
   - Recommendation: require design reviewer to validate SQL pseudocode with a 3-4 row trace table showing representative inputs and expected bucket assignments for each branch.

### Act (Knowledge Bank Updates)

**Patterns:**
- **Heavy upfront review investment yields zero-iteration implementation** — 22 pre-implementation review iterations across spec/design/plan yielded an implementation that passed all 4 reviewers on first try. The 82-minute review investment prevented multi-hour debugging cycles on a 15-file, ~4860-line change.
- **Opt-in features (default disabled) reduce R-6 remediation to audit-only** — existing tests cannot break when the new code path is never entered under default config. Phase 6 becomes a verified no-op confirmed by a single audit-grep.
- **Raw INSERT for test seeding when timestamp control is needed** — helper methods like `upsert_entry` auto-set timestamps. Tests exercising staleness, grace periods, or decay need deterministic timestamps via raw INSERT.

**Anti-patterns:**
- **SQL pseudocode with NULL WHERE clauses without row-tracing** — NULL comparisons do not follow standard boolean logic. A trace table forces the designer to enumerate edge cases and verify each row survives the correct pipeline stage. Design I-2's incorrect NULL-branch filter would have been caught by a 4-row trace table.
- **Numeric AC expectations not derived from explicit test seed data** — AC-10 said `skipped_floor==1` without counting all floor-eligible entries in the 3-entry seed (correct answer was 2). Casual numeric estimates in ACs create spec-implementation friction.

**Heuristics:**
- **5+ task-reviewer iterations signals structural plan issues** — at that point, re-read the plan skeleton (missing ACs, cap violations, seam duplication) before iterating on individual task descriptions. Content issues resolve in 1-2 iterations; structure issues persist until acknowledged.
- **Session-start integration module sizing** — ~480 LOC production + ~1600 LOC tests for a single-responsibility module with comprehensive AC coverage (1:3.3 ratio).
- **SQL NULL branch designs need trace tables** — require the design to include 3-4 representative rows showing which branch/bucket each row lands in.

## Raw Data
- Feature: 082-recall-tracking-and-confidence
- Mode: standard
- Branch: feature/082-recall-tracking-and-confidence
- Total review iterations: 23 (7 specify + 6 design + 9 create-plan + 1 implement)
- Tests landed: 516 semantic_memory (+63), 103 hook (+2)
- Final validate.sh: 0 errors, 4 warnings (= baseline)
- Performance: AC-24 36ms / 10k rows (SCAN plan, no explicit index needed at current scale)
