# Retrospective: 011-reconciliation-mcp-tool

## AORTA Analysis

### A — Actual Outcomes vs Expected

**Expected:** Standard mode MCP feature adding 4 reconciliation tools to `workflow_state_server.py` backed by a new `reconciliation.py` module. Moderate complexity given dual reconciliation dimensions (workflow state drift + frontmatter drift) and dependency on two prior features (009, 003).

**Actual:**
- 10 files changed, 6,695 net insertions, 3 deletions
- 4 new MCP tools: `reconcile_check`, `reconcile_apply`, `reconcile_frontmatter`, `reconcile_status`
- `reconciliation.py`: 630 lines (new module)
- `test_reconciliation.py`: 2,174 lines (103 unit tests)
- `workflow_state_server.py`: +284 lines
- `test_workflow_state_server.py`: +1,370 lines (146 MCP integration tests)
- 249 total tests passing, 0 security issues
- Branch lifetime: single day (2026-03-07, ~15.6 hours wall clock)
- 32 total review iterations (28 pre-implementation, 4 implementation)

**Outcome assessment:** Feature completed with high test coverage and zero logic deviations. The 3 reviewer caps hit during pre-implementation phases were investment, not failure — they eliminated structural gaps before they reached code. Force-approve at implement iter 4 was correct and appropriate.

---

### O — Observations (What Happened)

#### Phase Metrics

| Phase | Duration | Iterations | Cap Hit | Notes |
|-------|----------|------------|---------|-------|
| specify | 2h 45min | 7 (5 spec + 2 phase) | spec-reviewer (5/5) | Field-source mapping table missing; AC testability gaps; path traversal defense |
| design | 1h 50min | 8 (3 design + 5 handoff) | handoff/phase-reviewer (5/5) | ReconcileAction 'created' not in spec enum; healthy flag asymmetry; serializer direction |
| create-plan | 1h 25min | 7 (5 plan + 2 chain) | plan-reviewer (5/5) | TOCTOU race in meta_json_only path; vestigial 'meta' param; bulk db_only detection unspecified |
| create-tasks | 45min | 6 (3 task + 3 chain) | none | AC-18 error type ambiguity; ValueError prefix convention established at chain iter 2 |
| implement | 8h 15min | 4 | force-approved at iter 4 | Inverted branch (iter 1 genuine fix) then cascading type annotation formatting (iters 2-4) |

**Pre-implementation total:** 28 iterations across 4 phases
**Implementation total:** 4 iterations
**Phases hitting cap:** 3 of 5 (specify spec-reviewer, design handoff, create-plan plan-reviewer)

---

### R — Reflections (Why It Happened)

**1. Specify cap: missing field-source mapping table**

The spec described comparison semantics in prose across multiple requirement sections (R1, R2, R8) without a unified field-source table. Each iteration addressed one manifestation of the same underlying gap because the structural fix was incremental rather than complete.

**Root cause:** No spec template requirement for a field-source mapping table when the feature compares fields from heterogeneous sources.

**2. Design handoff cap: untraced design enhancement**

`ReconcileAction` introduced a `'created'` action value not in spec R2's enum. The enhancement was annotated in design iter 2, but downstream implications (AC-8 assertion, ReconciliationResult.summary, healthy flag) were discovered one-per-iteration across 5 handoff iterations.

**Root cause:** No design-time protocol for tracing deviations from spec to downstream impact. The three-step trace was executed iteratively rather than atomically.

**3. Implement type annotation cascade**

The code-quality reviewer caught a genuine inverted branch condition in iter 1. Then raised a type annotation missing from the if-branch in iter 2. The fix added annotations to both branches — iter 3 flagged the double annotation. Removing the else-branch annotation resolved it in iter 4. Three iterations with zero logic changes.

**Root cause:** Branch-level type annotation is non-canonical Python. The canonical fix (annotate at variable declaration before the if/else) was not applied.

---

### T — Takeaways (Lessons Learned)

1. **Field-source mapping tables are required for comparison specs.** Prose descriptions of field comparison will drive 3+ reviewer iterations.
2. **Design deviations require three-step atomic trace.** Definition annotation + AC mapping + test strategy note must be completed in one edit.
3. **TOCTOU races need catch-scope TDs.** "Catch ALL ValueError uniformly" is the stable resolution; enumerating race scenarios is always incomplete.
4. **Type annotation cascade is a known anti-pattern.** Annotate at the variable declaration site before the conditional, not at each branch.
5. **Force-approve is correct when all domain reviewers individually approved** and remaining warnings are formatting/documentation only.
6. **ValueError prefix convention as error-type routing contract.** Establish prefix convention in design TD section.
7. **28 pre-implementation iterations produced 0 implementation logic blockers.** Front-loading investment, not waste.

---

### A — Actions (Concrete Improvements)

1. Add field-source mapping table requirement to spec-reviewer checklist for comparison features
2. Add design enhancement three-step trace to design-reviewer checklist
3. Add TOCTOU TD requirement to plan-reviewer checklist for create-after-check operations
4. Add type annotation placement fix-pattern to code-quality-reviewer instructions
5. Document force-approve criteria in implement phase guidance

---

## Raw Data

- Feature: 011-reconciliation-mcp-tool
- Mode: standard
- Branch lifetime: ~15.6 hours (single day, 2026-03-07)
- Total review iterations: 32 (28 pre-implementation + 4 implementation)
- Phases hitting cap: specify/spec-reviewer, design/handoff-reviewer, create-plan/plan-reviewer
- Test coverage: 249 tests (103 unit + 146 integration)
- Security issues: 0
- Implementation logic deviations: 0
- Git: 20 commits, 10 files changed, 6,695 insertions, 3 deletions
