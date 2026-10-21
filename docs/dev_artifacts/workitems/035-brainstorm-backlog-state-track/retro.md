# Retrospective: Feature 035 — Brainstorm & Backlog State Tracking

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| brainstorm | ~1 min | 0 | PRD sourced from existing brainstorm doc |
| specify | ~5 min (est) | 0 | No reviewer iterations recorded |
| design | ~10 min (est) | 2 | 2 design-reviewer iterations |
| create-plan | ~15 min (est) | 4 | 3 plan-reviewer + 1 phase-reviewer; blockers in rounds 1-2 |
| create-tasks | ~2 min (est) | 0 | Single commit |
| implement | ~45 min (est) | 1 | All 3 reviewers approved first try |

**Summary:** 79 minutes total, 13 commits, 24 files changed, +4,379/-55 lines. Plan phase was the bottleneck at 4 reviewer iterations. Implementation passed all 3 reviewers on first attempt — the detailed plan eliminated ambiguity. YOLO mode active throughout. 62 new tests (45 TDD + 17 deepened), 1,658 total, 0 failures.

### Review (Qualitative Observations)

1. **Plan phase was disproportionately review-heavy (4 iterations vs 1 for implement)** — Commits `7b896c4` through `9323054` show 3 plan-reviewer rounds with blockers in rounds 1-2, followed by a phase-reviewer pass. The plan eventually included inline code snippets with exact insertion points, which is what the reviewer needed.

2. **Design had a retroactive fix after plan creation exposed a gap** — Commit `9db4135` ("fix: add backfill case 3 (null-phase UPDATE) to C6 design") was made after plan creation began. The design-reviewer missed the incomplete state enumeration for the backfill component. The plan process served as an accidental second design review.

3. **Implementation was clean across all review dimensions** — Code quality: "3 warnings, none blocking" (check ordering, terminal transitions in forward set, error code naming). Security: "No critical/high vulns, all SQL parameterized." Implementation: "All ACs verified." The isolation principle (zero shared code paths with feature workflow) made regression risk negligible.

### Tune (Process Recommendations)

1. **Require explicit row-state enumeration in design docs** (Confidence: medium)
   - Signal: Design C6 initially missed the null-phase UPDATE case. Caught during plan creation, requiring retroactive fix.
   - Recommendation: For any component touching DB tables, design-reviewer should require enumeration of all possible row states (no row, null fields, populated fields) with handling logic for each.

2. **Front-load plan detail to reduce iteration count** (Confidence: high)
   - Signal: Plan required 4 iterations but once detailed enough (inline code, insertion points, edge cases), implement passed first try.
   - Recommendation: Add a plan completeness checklist to the planning skill: (1) insertion point for each code change, (2) all design doc edge cases addressed, (3) test-first RED/GREEN markers per task.

3. **Extract entity lifecycle orchestration from SKILL.md** (Confidence: medium)
   - Signal: Brainstorming SKILL.md grew to 596 lines (guideline <500), up from 559, due to 6 MCP call insertion points for entity lifecycle management.
   - Recommendation: Extract lifecycle calls into a reusable agent or shared instruction block. Would reduce SKILL.md by ~40-50 lines and prevent growth as more entity types are added.

4. **Reinforce current TDD task structure** (Confidence: high)
   - Signal: 45 TDD tests across 7 implementation phases, all passing, first-try reviewer approval.
   - Recommendation: Keep the test-first RED/GREEN/suite-verify task format as the standard for plan.md. This pattern produced zero regressions.

5. **Defer db._conn abstraction** (Confidence: high)
   - Signal: TD-10 (direct _conn access for workflow_phases) is pre-existing and reviewer-acknowledged.
   - Recommendation: No action now. Migrate all _conn users together if/when a public workflow_phases API is added.

### Act (Knowledge Bank Updates)

**Patterns:**
- When plan phase includes inline code snippets with exact insertion points and edge-case handling, implementation passes review on the first iteration
- Use the isolation principle when adding new functionality to an existing MCP server: own error decorator, own constants, zero shared code paths

**Anti-patterns:**
- Do not pass a design through review without explicitly enumerating all possible database row states for each DB-touching component

**Heuristics:**
- If plan-reviewer requires 3+ iterations, check whether the design doc covers all row states and edge cases before re-submitting the plan
- For entity-type-aware UI, derive entity_type from type_id in the template rather than passing it from the route

## Raw Data
- Feature: 035-brainstorm-backlog-state-track
- Mode: standard
- Branch: feature/035-brainstorm-backlog-state-track
- Branch lifetime: ~79 minutes (single session)
- Total review iterations: 7 (2 design + 4 plan + 1 implement)
- YOLO mode: active throughout
- Commits: 13
- Files changed: 24
- Lines: +4,379 / -55
- Tests added: 62 (45 TDD + 17 deepened)
- Total test suite: 1,658 passing, 0 failures
