# Retrospective: 002-markdown-entity-file-header-sc

## AORTA Analysis

### Observe (Quantitative Metrics)
| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 2h 45m | 9 (4 spec + 5 phase, cap hit) | 3 blockers iter 1; phase-reviewer drove 5 sequential ACs and merge semantics iterations; 2 unresolved warnings at cap |
| design | 2h 30m | 5 (3 design + 2 handoff) | 3 blockers iter 1 all resolved; cleanest phase relative to scope; handoff approved iter 2 |
| create-plan | 1h 10m | 9 (4 plan + 5 chain, cap hit) | Plan iter 1: 9 issues (3 blockers); iter 3-4 post-approval; chain cap with 2 API/teardown warnings unresolved |
| create-tasks | 50m | 7 (5 task cap hit + 2 chain) | PYTHONPATH recurred across 4 iterations; task cap hit before full resolution; chain iter 1 closed final gap |
| implement | 4h 00m | 6 (incl. final validation) | Quality reviewer sole driver iter 2-4; bare open() caught 3 times in 3 separate locations; all 96 tests pass |

**Total:** 11h 15m · 36 review iterations · 3 circuit breaker hits (specify, create-plan, create-tasks) · 3,368 lines produced

### Review (Qualitative Observations)

1. **Factual error in spec iter 1 (PyYAML stdlib assumption) cascaded into mandatory architecture redesign** — spec-reviewer: "C1 YAML library constraint is wrong — `yaml` is NOT in Python stdlib; PyYAML is third-party. Creates ambiguous dual-path implementation." This single correction defined the entire implementation approach (mandatory custom parser) propagating into design (`_parse_block`), plan (parser algorithm), and tasks.

2. **PYTHONPATH prefix recurred across 4 of 5 task-review iterations in a specificity cascade** — each fix revealed the same gap on an adjacent task. Chain review iter 1 caught the final instance. Root cause: no shared prefix declaration; authors applied it task-by-task from memory.

3. **Bare `open()` calls caught in 3 separate locations across 3 consecutive implement iterations** — `frontmatter.py` (iter 2, 2 sites), `test_frontmatter.py` (iter 3, 1 site). Each iteration fixed one site, missing adjacent ones. The plan described context managers conceptually but did not enumerate `open()` call sites.

4. **Post-approval informational iterations consumed ~20 min in create-plan** — plan iter 3 approved with 3 warnings all marked "no change needed"; iter 4 dispatched, producing documentation expansions to already-correct content. Matches documented Anti-Pattern: Post-Approval Informational Iterations.

5. **Design phase is a reference example of the skeptic reviewer pattern** — 3 blockers in iter 1 (return type mismatch, data lineage gap, SKILL.md integration model) all resolved within iteration; handoff approved at iter 2. No design issues propagated to implement.

### Tune (Process Recommendations)

1. **Add Invocation Prefix field to task template for Python tasks** (Confidence: high)
   - Signal: PYTHONPATH recurred across 4 task-review iterations and 1 chain-review iteration. Each fix was per-task. Cap hit before convergence.
   - Recommendation: Add an "Invocation prefix" field to task template populated once per task, applied to all done-when commands. Task-reviewer flags any Python done-when without a declared prefix as a blocker.

2. **Add file I/O self-check step to implementation plans** (Confidence: high)
   - Signal: Bare `open()` caught in 3 locations across 3 implement iterations. Plan did not enumerate call sites.
   - Recommendation: Add plan verification step: `grep -rn "open(" in implementation files and confirm each uses context manager.` Converts 3 review iterations to 1 self-check.

3. **Enforce early-exit at approved plan — do not dispatch post-approval informational iterations** (Confidence: high)
   - Signal: Plan iter 3 approved, iter 4 dispatched, produced changes to already-approved content. ~20 min wasted.
   - Recommendation: Update create-plan command logic: any approved outcome (with or without informational warnings) is terminal. Capture informational warnings as implementation notes.

4. **Add library availability verification step before spec authoring** (Confidence: high)
   - Signal: PyYAML stdlib assumption in spec iter 1 caused mandatory architecture pivot cascading into all downstream phases.
   - Recommendation: Add pre-specify checklist item: "Verify all named libraries are stdlib vs third-party." Spec-reviewer prompt should list "stdlib assumption" as an explicit factual-error check category.

5. **Add dependency API read step in plan before first caller implementation step** (Confidence: medium)
   - Signal: UUID key mismatch (`entity_uuid` vs actual `uuid`) caught at plan iter 1. `get_entity()` type_id acceptance left unresolved at chain cap.
   - Recommendation: For each external API called, plan must include a read step documenting: function signature, parameter types, return key names — verified against source before implementation.

### Act (Knowledge Bank Updates)

**Patterns added:**
- Typed exception subclasses instead of string-matched ValueError for programmatic dispatch (from: Feature 002, implement iter 1 — `FrontmatterUUIDMismatch(ValueError)` introduced)
- Design phase with skeptic reviewer resolving 3+ blockers in iter 1 as reference for early feasibility catch (from: Feature 002, design phase — no design issues propagated to implement)

**Anti-patterns added:**
- Stdlib assumption for third-party libraries (PyYAML) in spec without verification — causes mandatory architecture pivot (from: Feature 002, specify iter 1)
- Per-task PYTHONPATH in done-when commands without shared prefix declaration — causes specificity cascade to task-reviewer cap (from: Feature 002, create-tasks)
- Bare `open()` calls in production and test files without context managers — quality reviewer catches one site per iteration, N bare sites = N-1 extra implement iterations (from: Feature 002, implement iters 2-4)

**Heuristics added:**
- Use a Shared Verification section in tasks.md with canonical PYTHONPATH export; all done-when commands reference it by name (from: Feature 002, create-tasks — 4 iterations of drift before convergence)
- Treat plan-reviewer approved-with-informational-warnings as terminal; capture warnings as implementation notes, not re-review triggers (from: Feature 002, create-plan iters 3-4)
- Add explicit dependency API read step in plan before first implementation step calling into existing APIs (from: Feature 002, create-plan — UUID key mismatch and type_id acceptance remained uncertain)

## Raw Data
- Feature: 002-markdown-entity-file-header-sc
- Mode: standard
- Branch: feature/002-markdown-entity-file-header-sc
- Project: P001 / Module: Entity Identity
- Depends on: 001-entity-uuid-primary-key-migrat
- Branch lifetime: 2026-03-01 to 2026-03-03 (~2 days)
- Total review iterations: 36
- Circuit breaker hits: 3 (specify phase-reviewer, create-plan chain-reviewer, create-tasks task-reviewer)
- Artifact totals: 3,368 lines (spec: 137, design: 466, plan: 350, tasks: 369, frontmatter.py: 321, frontmatter_inject.py: 203, test_frontmatter.py: 1,522)
- Tests: 96 passing
