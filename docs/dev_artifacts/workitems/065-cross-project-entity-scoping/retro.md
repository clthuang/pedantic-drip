# Retrospective: 065 — Cross-Project Entity Scoping

## AORTA Analysis

### Observe

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| brainstorm | 9 min | 1 | PRD reviewer: 4 blockers + 8 warnings, all resolved |
| specify | 16 min | 4 | Highest pre-impl count; schema decisions drove churn |
| design | 23 min | 3 | 5 blockers iter 1; 8 technical decisions |
| create-plan | 12 min | 3 | Missing reconciliation, incomplete enum, rationale gaps |
| create-tasks | 8 min | 3 | Missing test specs, verify commands, file lists |
| implement | 142 min | 2 | 31 commits, 59 files, +6314/-980; 3 quality blockers |

**Total:** ~4.5 hours, 16 review iterations. Specify highest-friction (4 iters). Implementation efficient (2 iters) given scope.

### Review

1. **Schema migration FK cascade** — UNIQUE(type_id) → UNIQUE(project_id, type_id) silently broke workflow_phases FK. Design did not audit FK dependents. Discovered at implementation Phase 2.
2. **Required-parameter scope blindness** — Spec declared project_id required without call-site count. 607 callers discovered at implementation, requiring two-step migration not in spec.
3. **Pre-existing test failures** — 17 failures surfaced during implementation. Not regressions but required unplanned fixes (doctor v7→v8, task_promotion fixture).

### Tune

1. **FK dependency checklist for UNIQUE migrations** (high) — Add to spec-reviewer checklist: "List all FK references to affected columns."
2. **Call-site impact estimate for breaking params** (high) — If call-site count >50, design must specify phased migration.
3. **Task-reviewer checklist** (high) — Require test specs, verify commands, file lists per task.
4. **Budget simplification pass** (medium) — Add "Phase N+1: Simplification" template for cross-cutting features.
5. **Baseline test suite** (medium) — Record pre-existing failures before implement phase.

### Act

**Patterns:** TDD with explicit test counts per phase; phased call-site migration with sentinel defaults.
**Anti-patterns:** UNIQUE constraint migration without FK audit; required parameter without call-site audit.
**Heuristics:** PRAGMA foreign_key_list before design review; test baseline before cross-cutting implement.
