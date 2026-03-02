# Retrospective: 005-workflowphases-table-with-dual

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 30 min | 1 | 3 blockers + 6 warnings all addressed; clean single-revision pass |
| design (designReview) | 20 min (review only) | 3 | Hit 3-iteration max; 2 blockers per round rooted in DB-state and private-API assumptions |
| design (handoffReview) | 10 min | 2 | Data flow diagram ambiguity → revision → approved |
| create-plan | 30 min | 2 | 3 blockers in iter 1 (stale constant ref, wrong return value, no test file placement); 4 warnings in iter 2 |
| create-plan (chainReview) | included | 1 | 1 ADR path warning → approved |
| create-tasks | 25 min | 3 | Precision warnings across all 3 rounds: wrong section refs, ambiguous file paths, missing IntegrityError branch detail |
| create-tasks (chainReview) | included | 1 | Approved first attempt |
| implement | 90 min | 4 | Quality reviewer drove all rounds; iter 1 blocker (missing malformed-JSON warning log); iters 2-3 readability warnings; iter 4 approved with suggestions only; force-approved at circuit breaker with all 3 reviewers individually passing |

**Quantitative summary:** Feature spanned ~4.5 hours wall-clock (08:00-12:30 on 2026-03-03). 17 total review iterations across 5 phases. Design (5 iterations) and implement (4 iterations) were the heaviest phases. Security and implementation compliance passed on implement iteration 1 — all subsequent rework was quality/readability. 545 tests pass at completion. 20 files changed, 8,205 insertions.

---

### Review (Qualitative Observations)

1. **Assumption gaps in specs and designs consistently produced downstream blockers across every phase** — Spec iter 1 issued 3 blockers all tagged `[assumptions]`: missing abandoned-feature workflow derivation, unspecified `.meta.json` path resolution, unspecified transaction management pattern. These propagated: Design iter 1 produced 2 blockers tagged `[assumptions]` and `[consistency]` (NULL status in DB not handled, `_now_iso()` private API boundary). Plan iter 1 produced 2 of its 3 blockers tagged `[assumption]` (stale `SCHEMA_VERSION` constant reference, wrong `_derive_next_phase` return value). The assumption-gap pattern repeated in every pre-implement phase.

2. **Code quality reviewer drove 100% of implement rework — security and implementation reviewers passed on iteration 1** — Implement iter 1: "Implementation Review: Approved", "Security Review: Approved", "Quality Review: Issues found". Iterations 2-4 skipped implementation and security reviews entirely. All rework was readability and flow: stale TDD phase comments, duplicate inline `TD-10` comments, exploratory prose left in test bodies, missing malformed-JSON warning log. Security correctness was solid; the iteration cost was cosmetic debt.

3. **Private API boundary crossing (`db._conn`, `_now_iso`) created a two-phase chase — flagged in design, then re-flagged in implementation** — Design iter 2 blocker: "TD-8 claims `_now_iso()` is module-level but it is `@staticmethod` on `EntityDatabase` — import path will fail." Design correctly captured the `db._conn` crossing as TD-10. Implementation iter 2 warning: "db._conn private attribute access in backfill lacks explicit TD-10 reference comments at both access sites." The design made the right call but failed to embed the required comment format into the corresponding task, so implementation required a correction round to add documentation that was already known to be necessary.

---

### Tune (Process Recommendations)

1. **Enforce explicit artifact read confirmation before every review** (Confidence: high)
   - Signal: LAZY-LOAD-WARNINGs appeared in three separate reviewer runs (design-reviewer, plan-reviewer, task-reviewer). Design review hit the 3-iteration maximum. Blockers in design iter 1 and plan iter 1 were rooted in reviewers not reading current artifact state.
   - Recommendation: Add a mandatory "Confirm artifact reads" step to every reviewer prompt — reviewer must list the files it read and their line counts before issuing any findings. Reject review output that lacks this confirmation.

2. **Add an implementer pre-submit self-review checklist targeting the exact patterns quality review catches** (Confidence: high)
   - Signal: Quality reviewer drove all 4 implement iterations. Iter 1 blocker: missing warn log for malformed JSON (AC-18 / D-9 gap). Iters 2-3 warnings: stale TDD RED/GREEN scaffold comment, duplicate `TD-10` inline comment, exploratory mid-test prose. All were detectable without running any tools.
   - Recommendation: Embed a pre-submit checklist in the implement skill: (1) remove all TDD RED/GREEN scaffolding comments, (2) strip mid-test exploratory prose — keep only GWT structure, (3) verify every design-decision comment references its TD number at every access site exactly once, (4) grep for `AC-` and `D-` from spec/design that involve logging and verify each log call exists.

3. **Plan and task authoring must read current artifact content — not rely on memory** (Confidence: high)
   - Signal: Plan iter 1 blocker: "references non-existent SCHEMA_VERSION constant." Task iter 1 warning: "references non-existent 'Appendix E'." Both are stale cross-references from an older artifact version.
   - Recommendation: Require plan-authoring and task-authoring agents to explicitly confirm they read the current spec.md and design.md line counts before generating content.

4. **Embed required inline comment format in tasks for deliberate API boundary violations** (Confidence: medium)
   - Signal: Design TD-10 documented `db._conn` direct access. Implementation iter 2 still needed a warning round to add `TD-10` reference comments. The design decision was correct; the task failed to carry the comment format forward.
   - Recommendation: When a design decision (TDx) justifies a policy violation, the task step must include the exact comment template: `# TDx: <one-line rationale>`.

5. **Tasks with IntegrityError handling must enumerate each distinct error branch explicitly** (Confidence: medium)
   - Signal: Task iter 1 warning: "IntegrityError handling missing message-inspection branches." Both are precision gaps that required extra iterations.
   - Recommendation: For any task involving exception handling with multiple branches, list each branch as a sub-bullet with the expected error message pattern.

---

### Act (Knowledge Bank Updates)

**Patterns:**

- **Security and implementation compliance pass on iteration 1 when spec and design phases are thorough** — all implement rework was quality/readability, not correctness. The correctness signal is upstream quality.

- **3-tier status resolution (entity status -> .meta.json status -> default) with explicit ordered fallback is robust for cross-source data backfills** — making the fallback chain ordered and explicit prevents silent data corruption and makes test coverage tractable.

- **_UNSET sentinel (`object()`) for distinguishing "not provided" from `None` in update functions** — `None` is a valid value for nullable columns; a module-level `_UNSET` sentinel makes intent unambiguous.

**Anti-patterns:**

- **Writing plan or task steps from memory rather than from current artifact content** — produces stale cross-references that cost a full review iteration to catch.

- **Leaving TDD phase scaffolding comments and exploratory mid-test prose in submitted implementation** — they become stale immediately and cost quality-review iterations.

- **Documenting a deliberate private API boundary crossing in design without embedding the required inline comment format in the corresponding task** — leaves implementation to discover the convention independently.

**Heuristics:**

- **When a reviewer hits 3 iterations, check for a LAZY-LOAD-WARNING first** — the reviewer likely did not read all source artifacts.

- **Spec blockers tagged `[assumptions]` that survive into design produce approximately one design-iteration blocker each** — catching assumption gaps in spec is cheaper.

- **For backfill operations, measure entity count before bypassing the public API for `db._conn` direct access** — at small counts the public API is simpler.

---

## Raw Data

- Feature: 005-workflowphases-table-with-dual
- Mode: Standard
- Branch: feature/005-workflowphases-table-with-dual
- Branch lifetime: 1 day (2026-03-01 created, 2026-03-03 completed)
- Phase window: 2026-03-03T08:00 -> 12:30 (+08:00)
- Total review iterations: 17 (spec: 1, design: 5, plan: 3, tasks: 4, implement: 4)
- Commits: 22
- Files changed: 20 (+8,205 / -10)
- Tests passing: 545
- Artifact sizes: spec 267 lines, design 475 lines, plan 271 lines, tasks 313 lines (113 tasks)
- Circuit breaker: implement phase — force-approved after all 3 reviewers individually passed at iteration 4
