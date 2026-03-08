# Retrospective: 036-kanban-column-lifecycle-fix

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 7 min 21 sec | 2 | spec-reviewer approved iter 2, phase-reviewer approved iter 1 |
| design | 13 min 10 sec | 3 | Longest pre-impl phase; dual mapping regime decision |
| create-plan | 10 min 30 sec | 3 | 3 iterations to structure plan |
| create-tasks | 14 min 36 sec | 3 | task-reviewer needed 3 iterations; phase-reviewer approved iter 2 |
| implement | ~47 min | 3 | Iter 1: inline imports + constant duplication. Iter 2-3: clean |

**Summary:** Total wall-clock ~93 minutes from specify-start to implementation-review-complete. 14 total review iterations across 5 phases (avg 2.8/phase). 10 files changed, 1045 insertions, 588+ tests passing, 0 failures. 14 TDD tasks with RED-GREEN cycle, 15 deepened tests added.

### Review (Qualitative Observations)

1. **Code organization (imports + constant placement) dominated implementation findings** -- Review iter 1 flagged inline imports of FEATURE_PHASE_TO_KANBAN and duplicated STATUS_TO_KANBAN local variables. Both are KISS violations that could be caught pre-review.

2. **Design explicitly deferred consolidation that reviewers later flagged** -- Design phase chose to keep STATUS_TO_KANBAN in 3 copies as a deliberate scope decision, but this wasn't communicated to implementation reviewers, costing one review iteration.

3. **RCA quality directly determined implementation success** -- The RCA identified 6 interlocking root causes mapping to exactly 3 files. Implementation confirmed 100% prediction accuracy with no scope creep. The closed-system analysis prevented partial fixes.

### Tune (Process Recommendations)

1. **Compress design phase for RCA-backed features** (Confidence: medium)
   - Signal: Design hit 3 iterations (13 min) for a bug fix where the RCA already identified all affected files and root causes.
   - Recommendation: For bug-fix features rooted in an RCA, start the design phase from the RCA's "Files Requiring Changes" table as a structural skeleton.

2. **Serialize TDD tasks that share test modules** (Confidence: high)
   - Signal: Parallel task agents 6+7 independently discovered the same test failures, wasting compute.
   - Recommendation: Document shared-module dependencies in tasks.md. Serialize tasks targeting the same test file, or add a pre-task check that skips if the target test was modified by a sibling.

3. **Add pre-review lint for common KISS violations** (Confidence: medium)
   - Signal: Implementation iter 1 flagged inline imports and duplicate constants -- both are mechanically detectable.
   - Recommendation: Add a pre-review check that flags inline imports in function bodies and duplicate constant definitions across files.

4. **Inject RCA "Files Requiring Changes" into design/plan phases** (Confidence: high)
   - Signal: RCA predicted all 3 files and exact line numbers; implementation confirmed 100%.
   - Recommendation: When an RCA precedes a feature, inject its file-change predictions as hard constraints in design and plan phases.

### Act (Knowledge Bank Updates)

**Patterns added:**
- RCA-driven feature development compresses discovery and keeps scope tight (from: Feature 036, design phase -- RCA identified 6 root causes mapping to 3 files with 100% accuracy)
- Dual-mapping regime for lifecycle state: separate init-time (status-based) and runtime (phase-based) mappings (from: Feature 036, design phase -- STATUS_TO_KANBAN vs FEATURE_PHASE_TO_KANBAN)

**Anti-patterns added:**
- Adding a new entity type to a state machine without updating ALL write paths (creation, transition, completion, drift detection, reconciliation) (from: Feature 036 RCA -- 6 independent gaps formed a closed system of silent drift)
- Running parallel task agents against the same test module without dependency awareness (from: Feature 036, implement phase -- agents 6+7 duplicated work)

**Heuristics added:**
- RCA-backed standard-mode bug fixes: budget ~90 min wall-clock for 10-15 TDD tasks (from: Feature 036 -- 93 min actual, 14 TDD tasks)
- When design defers consolidation, annotate it so implementation reviewers skip the warning (from: Feature 036 -- STATUS_TO_KANBAN duplication flagged despite being a deliberate deferral)

## Raw Data
- Feature: 036-kanban-column-lifecycle-fix
- Mode: standard
- Branch lifetime: 1 day (2026-03-08 to 2026-03-09)
- Total review iterations: 14 (across 5 phases)
- Files changed: 10
- Insertions: 1045
- Tests: 588+ passing, 0 failures
- TDD tasks: 14
- Deepened tests: 15
- RCA: docs/rca/20260309-kanban-column-drift.md (6 root causes identified)
