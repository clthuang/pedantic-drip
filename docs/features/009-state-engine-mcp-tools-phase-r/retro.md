# Retrospective: 009 — State Engine MCP Tools Phase R/W

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 30 min | 2 | Approved cleanly. No blockers in review history. |
| design | 50 min | 4 (2 design-reviewer + 2 phase-reviewer) | Iter 1 had 2 blockers: missing sys.path safety net, missing import block. Converged on iter 2 of each reviewer. |
| create-plan | 35 min | 6 (3 plan-reviewer + 3 chain-reviewer) | Plan-reviewer spent 2 of 3 iterations on TDD structure reform. Chain-reviewer added perf verification step and yolo_active test case. |
| create-tasks | 25 min | 5 (3 task-reviewer + 2 chain-reviewer) | 3 blockers in task iter 1 (guard IDs, conflicting done-when, missing monkeypatch). 2 more blockers in iter 2. Chain review: fixture naming + done-when completeness. |
| implement | 60 min | 3 (impl + quality + security) | Quality found 2 warnings — both fixed with comment-only edits. Iter 3 was final regression validation. All 3 reviewers triggered LAZY-LOAD-WARNING in iter 1. |

**Quantitative summary:** 5 phases, 20 total review iterations across 5 days of branch lifetime. Pre-implementation phases (design, create-plan, create-tasks) consumed 15 of 20 iterations (75%). Create-plan was the highest-iteration phase at 6. Implementation itself was structurally clean — zero logic changes required post-review. Test-to-production ratio: 846 test lines / 253 production lines = ~3.3:1 across 50 tests.

---

### Review (Qualitative Observations)

1. **TDD discipline was not authored into the plan — reviewers had to enforce it iteratively.** Plan-reviewer spent 2 of 3 iterations reforming step structure (renaming "Implement X + tests" to "Tests + X", adding RED/GREEN labels) that should have been present from the first draft. Evidence: Plan Review Iteration 1: *"TDD order ambiguous — steps 2.3-2.8 bundle test+impl without test-first guidance"*; Iteration 2: *"Step titles still say 'Implement X + tests' — should emphasize test-first"*.

2. **Test scaffolding was systematically underspecified across both planning phases.** Guard IDs, fixture states, monkeypatch targets, fixture parameter signatures, and fixture names all required reviewer intervention. Evidence: Task Review Iteration 1: 3 blockers — *"test_transition_phase_yolo_active lacks specific guard ID and fixture state"*, *"Conflicting completion states... ambiguous done when"*, *"test_validate_prerequisites_value_error doesn't specify monkeypatch mechanism"*. Chain Review Iteration 1: *"Fixture named large_db but returns WorkflowStateEngine — misleading name"*.

3. **Design omitted structural patterns directly observable in the existing peer server (entity_server.py).** Missing sys.path safety net and import block are copy-consistency issues, not design decisions. Evidence: Design Review Iteration 1: *"[blocker] Missing sys.path safety net — both existing servers include in-module import path setup"*, *"[blocker] Missing explicit import block — implementer must guess correct from...import paths"*.

4. **All 3 implement-phase reviewers triggered LAZY-LOAD-WARNING in iteration 1 — 100% non-compliance rate.** This is a systematic dispatch prompt failure, not reviewer behavior.

---

### Tune (Process Recommendations)

1. **Add TDD structure checklist to create-plan skill prompt** (Confidence: high)
   - Signal: Plan-reviewer consumed 2 of 3 iterations on TDD structure reform.
   - Recommendation: Require plan authors to self-verify before submission: (a) all implementation steps titled "Tests + X", (b) each step explicitly labeled (RED)/(GREEN), (c) no step bundles test and implementation without sequencing.

2. **Require explicit test scaffolding fields in design phase test structure section** (Confidence: high)
   - Signal: 3 blockers in task-review iter 1 and 2 more in iter 2 traced to underspecified test scaffolding.
   - Recommendation: Design phase test structure section must include: guard IDs, fixture state preconditions, monkeypatch targets, and return-type-aligned fixture names.

3. **Add peer server parity check step to MCP server design phase** (Confidence: high)
   - Signal: 2 design blockers were copy-consistency issues from entity_server.py.
   - Recommendation: When designing a new MCP server in an existing family, require an explicit peer server parity check.

4. **Escalate LAZY-LOAD-WARNING to auto-reject in implement review dispatch** (Confidence: high)
   - Signal: All 3 implement reviewers fired LAZY-LOAD-WARNINGs in iter 1.
   - Recommendation: Make file-read confirmation a hard gate that auto-rejects reviews without it.

5. **Add task author self-check for fixture naming and done-when completeness** (Confidence: medium)
   - Signal: Chain review found polish issues (fixture naming, done-when incompleteness).
   - Recommendation: Task authors verify fixture names reflect return types and done-when conditions are measurable.

---

### Act (Knowledge Bank Updates)

**Patterns:**
- MCP server peer parity during design yields clean implementation
- Processing-function / async-handler split pattern makes MCP servers highly testable
- FastMCP lifespan pattern is the correct lifecycle hook for DB/engine initialization

**Anti-patterns:**
- "Implement X + tests" step titles hide test-first requirement
- Test tasks without guard IDs, fixture states, and monkeypatch targets force design onto implementer
- LAZY-LOAD-WARNING on all reviewers simultaneously signals dispatch prompt gap

**Heuristics:**
- 6 review iterations on a plan almost always means structural gaps, not content gaps
- Test-to-production ratio of ~3:1 is healthy for processing-function MCP servers
- Engine wrapper features must verify engine's public API surface during design

---

## Raw Data

- Feature: 009-state-engine-mcp-tools-phase-r
- Mode: Standard
- Branch lifetime: 5 days (2026-03-01 to 2026-03-06)
- Total review iterations: 20
- Phases: specify (2) + design (4) + create-plan (6) + create-tasks (5) + implement (3)
- Commits: 20
- Files changed: 11 (+2891 insertions)
- Artifact lines: spec.md 187 + design.md 485 + plan.md 237 + tasks.md 340 = 1,249
- Code lines: workflow_state_server.py 253 + test_workflow_state_server.py 846 + run-workflow-server.sh 40 + test_run_workflow_server.sh 156 = 1,295
- Tests: 50 (30 TDD RED-GREEN + 20 deepened)
- LAZY-LOAD-WARNINGs: 3 (all implement reviewers, iter 1)
