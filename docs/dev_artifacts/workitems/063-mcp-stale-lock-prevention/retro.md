# Retrospective: MCP Stale Lock Prevention (063)

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 8 min | 3 | Edge cases in acceptance criteria: macOS orphan reparenting, PPID=1 UI server exception, GIL atomicity caveat |
| design | 23 min | 3 | Longest phase. Blocker in iter 2: db.insert_workflow_phase() does not exist. Iter 3: raw SQL spec violation |
| create-plan | 10 min | 2 | Blocker: TOCTOU race in run_backfill(); missing test file CREATE declaration |
| create-tasks | 12 min | 2 | 5 blockers in iter 1: missing insertion points, omitted feature derivation logic, underdefined bash sections |
| implement | ~13 min | 1 | Direct pass. 20 files, +3041/-293 lines, 30 new tests. Zero rework. |

**Total:** ~78 minutes. 11 pre-implementation review iterations; 1 clean implement pass.

### Review (Qualitative Observations)

1. **Wrong public API method names were the primary driver of design iterations.** Referenced db.insert_workflow_phase() (non-existent), db.update_entity() (wrong context), db.register_entity() (wrong context). Appeared in design iterations 1 and 2.

2. **TOCTOU race slipped through design, caught at plan phase.** The design specified backfill update logic in detail but did not surface the concurrent-deletion race.

3. **Tasks with 5 blockers in one iteration shared one root cause: missing implementation specificity.** Insertion points, line references, logic preservation steps all absent.

### Tune (Process Recommendations)

1. **Add API verification step to design authoring** — grep source before citing methods (high confidence)
2. **Add concurrency checklist for DB-mutating design code** — "Could a concurrent deletion cause this to raise?" (high confidence)
3. **Require insertion-point anchors for tasks modifying existing files** — "after line N" or "replace lines Y-Z" (high confidence)
4. **Preserve front-loading pattern for infrastructure features** — 11 pre-impl iterations → zero-rework implement (medium confidence)

### Act (Knowledge Bank Updates)

- Anti-pattern: API method name fabrication in design documents (already stored)
- Heuristic: Grep-verify method names before design submission (already stored)
- Pattern: Front-loading review iterations produces zero-rework implementation

## Raw Data

- Feature: 063-mcp-stale-lock-prevention
- Mode: Standard
- Branch lifetime: 1 day (2026-03-25)
- Total review iterations: 11 (specify: 3, design: 3, plan: 2, tasks: 2, implement: 1)
- Commits: 22, Files changed: 20 (+3041/-293), New tests: 30
- Artifacts: spec 112 lines, design 492 lines, plan 271 lines, tasks 417 lines
- RCA addressed: docs/rca/20260325-entity-mcp-connection-failure.md
