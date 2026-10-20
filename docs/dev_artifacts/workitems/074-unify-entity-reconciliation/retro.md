# Retrospective: 074-unify-entity-reconciliation

## AORTA Analysis

### Observe

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | ~7 min | 3 | Status vocabulary disambiguation, AC-9 ambiguity |
| design | ~7 min | 3 | Interface signatures, project_root vs full_artifacts_path |
| create-plan | ~9 hr wall-clock (4 iter) | 4 | 21 tasks, 7 stages, atomic commit boundaries |
| implement | ~35 min | 2 | Iter 2 fixed assert→ValueError, db._conn→list_entities |
| **Total** | | **12** | Front-loaded: 10/12 iterations before implement |

### Review

1. Known API gotchas (assert→ValueError, db._conn) caught by review — documented in CLAUDE.md but not checked beforehand.
2. Spec resolved vocabulary/edge-cases upfront — design and implement did not revisit.
3. Task checkboxes marked post-hoc, not in real time (process gap).
4. Pseudocode-depth design correlated with fast implement (35 min, 2 iter).

### Tune

1. **Pre-implement gotcha checklist for entity registry** (high) — would prevent mechanical review fixes
2. **Real-time task checkbox ticking** (high) — reinforce in implement skill
3. **Atomic commit boundary validation in plan review** (medium) — for consolidation features
4. **Vocabulary alignment tables in multi-entity specs** (medium) — front-load status mapping
5. **Pseudocode-depth design for infrastructure** (high) — maintain this investment

### Act

- Pattern: Spec vocabulary resolution prevents downstream rework
- Pattern: Pseudocode-depth design → fast implement for infrastructure
- Pattern: Atomic commit boundaries in plan prevent broken test windows
- Anti-pattern: assert for validation instead of ValueError
- Anti-pattern: db._conn direct access bypassing public API
- Anti-pattern: Deferred task checkbox updates
- Heuristic: Consolidation features need 3-4 plan iterations
- Heuristic: Pre-implement entity registry gotcha review

## Raw Data
- Feature: 074-unify-entity-reconciliation
- Total iterations: 12 (specify 3, design 3, create-plan 4, implement 2)
- Implement first-pass: no (1 fix iteration for API gotchas)
