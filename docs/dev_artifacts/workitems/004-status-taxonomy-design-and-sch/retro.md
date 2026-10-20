# Retrospective: Feature 004 — Status Taxonomy Design and Schema

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 60 min | 6 | 4 spec-reviewer + 2 phase-reviewer. Missing .meta.json fields caught twice. |
| design | 55 min | 4 | 2 design-reviewer + 2 handoff-reviewer. FK clause, mode CHECK, deliverable boundary. |
| create-plan | 25 min | 3 | 2 plan-reviewer + 1 phase-reviewer. Field discovery step added; backward transition gap. |
| create-tasks | 25 min | 3 | 2 task-reviewer + 1 chain-reviewer. Full paths, T13 placement, executable test form. |
| implement | 80 min | 4 | 3-reviewer cycle. Appendix G readability, FK comment correction, design.md alignment. |

**Total wall-clock:** ~4h5m across 5 phases
**Total review iterations:** 20
**Commits:** 19 on feature branch
**Artifacts:** spec.md (212L), design.md (250L), plan.md (182L), tasks.md (458L), adr-004-status-taxonomy.md (304L)

Specify was the heaviest planning phase (6 iterations, 60 min). Implement was heaviest overall (4 iterations, 80 min) despite zero code deliverables — two of four implement iterations were consumed by a single unverified SQLite platform fact.

---

### Achievements

- **Plan self-corrected upstream friction.** The grep-based field discovery pre-step added to the plan directly compensated for the spec's missing .meta.json field coverage, preventing the same gap from cascading into implementation.
- **Design reviewer caught structural schema gaps early.** FK ON DELETE clause, mode CHECK constraint, and workflow_phase primacy were all identified at design-review — before DDL was committed — keeping schema corrections cheap.
- **Efficient planning phase durations.** create-plan and create-tasks each completed in 25 minutes despite 3 iterations each, indicating reviewer cycles were converging quickly rather than spinning.
- **Comprehensive ADR with 7 appendices.** The 304-line output covers schema DDL, event maps, conflict scenarios, and backward compatibility — a complete reference artifact produced in a single feature.
- **Implement phase reviewers operated as intended.** Security reviewer caught the FK semantics gap; implementation reviewer caught design.md alignment; quality reviewer caught Appendix G readability — three distinct concern domains resolved across 4 iterations.

---

### Obstacles

1. **Missing .meta.json fields caught twice in spec review.** Two separate spec-reviewer iterations flagged the same class of gap. The template does not prompt for field enumeration during initial authoring.
2. **SQLite FK default unknown at design time.** FK default is NO ACTION, not RESTRICT. This single platform fact was unknown when the schema was designed and surfaced as a security reviewer blocker at implement iter 2, driving 2 of 4 implement iterations.
3. **Backward transition coverage missing from spec.** Forward transitions were specified; backward transitions were not addressed. Plan reviewer raised the gap — two phases after the appropriate fix point.
4. **Appendix G readability caught at implement, not handoff.** A structural readability issue (section too large, needed splitting) was not caught during any design-adjacent review phase. It appeared only at implement review iter 1.
5. **Grep-only verification for documentation feature.** No executable test assertions exist for the ADR. All acceptance criteria rely on grep checks, providing weak post-implementation confidence.

---

### Root Causes

| Obstacle | Root Cause |
|----------|------------|
| .meta.json fields caught twice | Spec template has no field inventory prompt — fields are discovered reactively by reviewers |
| SQLite FK default unknown | No platform-default verification checklist in design-reviewer for database schema features |
| Backward transitions missing from spec | Spec-reviewer checklist does not require explicit coverage of transition direction completeness |
| Appendix G caught at implement | No readability gate exists at handoff for large appendix sections (80+ lines without subheadings) |
| Grep-only verification | Plan template does not distinguish automatable vs manual verification for documentation features |

---

### Takeaways

1. **Compensating downstream steps signal upstream template gaps.** The grep pre-step in the plan that fixed the .meta.json problem is a symptom, not a cure. Fix the spec template, not the plan.
2. **Platform defaults are one-lookup facts — verify at design, not implement.** SQLite's FK, CHECK, and WAL semantics take seconds to look up and have outsized review impact when unknown.
3. **Silence on transition direction is not the same as out-of-scope.** A single sentence in spec — "backward transitions are out of scope because X" — closes a gap that otherwise surfaces as a plan-review blocker.
4. **Documentation features need explicit weak-verification labeling.** Grep checks look like tests in review. Label them honestly so reviewers apply appropriate skepticism.
5. **Readability gates belong at handoff, not implement.** Large sections without subheadings are structural problems. Catching them at implement review is one phase too late.

---

### Actions

| Action | Target | Confidence |
|--------|--------|------------|
| Add `.meta.json field inventory` required section to spec template — list all fields the feature reads, writes, or depends on before first spec-reviewer dispatch | spec-reviewer prompt or spec template | high |
| Add `Platform Default Verification` checklist to design-reviewer prompt for database schema features — FK ON DELETE/ON UPDATE defaults, CHECK constraint support, WAL mode | design-reviewer prompt | high |
| Add `transition direction completeness` check to spec-reviewer — if any state-machine transitions are specified, backward transitions must be explicitly addressed or scoped out | spec-reviewer prompt | medium |
| Add `readability pre-flight` to handoff-reviewer — any artifact section exceeding 80 lines must have clear subheadings; flag absence as a blocker before handoff approval | handoff-reviewer prompt | medium |
| Add `verification strategy` required section to plan template for documentation-only features — distinguish automatable grep checks from manual review gates explicitly | plan template | medium |

---

### Act (Knowledge Bank Updates)

**Patterns added:**
- Reactive plan steps compensating for upstream template gaps signal the fix belongs in the template, not the downstream phase. (Feature 004, specify phase)
- For ADR-style documentation features, assign explicit readability owners: appendix sections exceeding 80 lines require subheading structure verified at design-handoff. (Feature 004, implement phase)

**Anti-patterns added:**
- Deferring SQLite platform-default verification (FK semantics, CHECK constraints) to implement review causes comment-level corrections to consume multi-iteration review capacity. (Feature 004, implement iters 2-3)
- Specifying forward state-machine transitions without explicitly addressing backward transitions produces a plan-review blocker that could have been closed at spec time with one sentence. (Feature 004, create-plan phase)

**Heuristics added:**
- For database schema features using SQLite: verify FK ON DELETE default (NO ACTION), CHECK constraint syntax, and WAL implications during design. These are one-lookup facts with outsized review impact if unknown. (Feature 004)
- Documentation-only features should label verification strategy explicitly in the plan: distinguish automatable grep checks from manual readability/completeness gates. Unlabeled weak verification passes review but provides false confidence. (Feature 004)

---

## Raw Data

- Feature: 004-status-taxonomy-design-and-sch
- Mode: Standard (null)
- Branch: feature/004-status-taxonomy-design-and-sch
- Branch lifetime: single session (~4h5m)
- Total review iterations: 20
- Commits: 19
- Files changed: 7 / 1771 insertions
- Deliverable type: Documentation only (ADR)
- Tests: None (grep-based verification only)
