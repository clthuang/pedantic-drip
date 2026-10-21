# Retrospective: 020-entity-list-and-detail-views

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 45 min | 2 | Clean pass — standard for a UI feature with a defined dependency |
| design | 45 min | 5 (3 design + 2 handoff) | Elevated but contained — FastAPI+Jinja2+HTMX interaction surface |
| create-plan | 45 min | 1 | Cleanest phase — design artifacts were fully self-sufficient for planning |
| create-tasks | 65 min | 8 (4 task + 4 chain) | Highest pre-implementation load; both review stages ran near-cap |
| implement | 160 min | 4 (incl. final validation) | Structural issues resolved in iter 1; iter 3 approved; iter 4 was regression gate |

**Total pre-implementation review iterations:** 16 (2 + 5 + 1 + 8)
**Total implement iterations:** 4
**Mode:** Standard
**Approximate wall-clock:** ~6.3 hours

create-tasks was the primary bottleneck. create-plan was the most efficient phase (1 iteration), confirming that design produced a self-sufficient handoff artifact. Implementation resolved all substantive issues in 3 actionable iterations — iter 4 served only as a regression validation gate.

---

### Review (Qualitative Observations)

1. **Three-reviewer parallel dispatch caught three distinct issue classes in a single iteration** — implementation, quality, and security reviewers each surfaced non-overlapping concerns in iter 1 (DRY violation, readability issues, raw exception exposure). No reviewer overlap. All fixed in one response cycle.

2. **DRY violation between sibling route modules reached implement review rather than design** — board.py duplicated the missing-DB error block that entities.py had already extracted into `_missing_db_response()`. The fix required creating helpers.py, updating imports in 2 files, and correcting 6 test assertions.

3. **Raw exception content (str(exc)) in HTML error templates is a web UI security class not caught at design time** — the security reviewer surfaced raw exception rendering in error.html at two call sites. Fix required a DB_ERROR_USER_MESSAGE constant and 6 updated test assertions.

4. **Review convergence was healthy once structural issues were addressed** — iter 2 contained only 2 residual warnings, iter 3 achieved full approval with only suggestions, iter 4 confirmed no regressions.

---

### Tune (Process Recommendations)

1. **Add 'Shared Error Utilities' design section for multi-route UI features** (Confidence: high)
   - When a design covers 2+ sibling route modules, include a "Shared Utilities" subsection naming any common error-response helpers with their module path.

2. **Add web UI error-template security check to design-reviewer for FastAPI/Jinja2 features** (Confidence: high)
   - Design-reviewer prompt should include: "Verify all error template variables use user-safe constants (not str(exc), exception.args, or raw traceback content)."

3. **Investigate create-tasks iteration driver for UI route features** (Confidence: medium)
   - create-tasks ran 4+4=8 iterations while create-plan passed in 1. The ambiguity was introduced during plan-to-tasks conversion.

4. **Use this feature's design artifact structure as a reference template for future UI view features** (Confidence: medium)
   - create-plan's single-iteration approval suggests design.md was well-structured for planning.

5. **Scope final validation iteration to regression checks only when iter 3 is fully clean** (Confidence: medium)
   - Full 3-reviewer dispatch consumed resources without producing changes when prior iteration was clean.

---

### Act (Knowledge Bank Updates)

**Patterns:**
- Three-reviewer parallel dispatch with selective re-dispatch efficiently surfaces distinct issue classes in a single iteration cycle (observation count: 3)

**Anti-patterns:**
- Designing sibling route modules without naming shared error utility at design time
- Passing raw exception content (str(exc)) as template variables to HTML error pages

**Heuristics:**
- For FastAPI+Jinja2 features with 2+ sibling route modules, include a 'Shared Error Utilities' design section
- Require user-safe message constants for all error template variables in web UI designs

---

## Raw Data

- Feature: 020-entity-list-and-detail-views
- Mode: Standard
- Branch: feature/020-entity-list-and-detail-views
- Total review iterations: 20 (16 pre-implementation + 4 implement)
- Files changed: 18
- Insertions/deletions: 2812 / 21
- Key files: entities.py (191 lines), helpers.py (24 lines), test_entities.py (1353 lines), 4 templates, board.py (modified)
- Artifact sizes: spec.md 12383B, design.md 14170B, plan.md 12999B, tasks.md 17599B
