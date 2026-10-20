# Retrospective: 008-workflowstateengine-core

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Domain Reviewer Iterations | Chain/Handoff Iterations | Total | Notes |
|-------|----------|---------------------------|--------------------------|-------|-------|
| specify | 70 min | 3 (spec-reviewer) | 2 (phase-reviewer) | 5 | Iter 1: 4 blockers, all API assumption errors. Approved iter 3 with warnings. |
| design | 85 min | 3 (design-reviewer) | 2 (handoff-reviewer) | 5 | Iter 1: hydration divergence + frozen dataclass mutation. Iter 2: complete_phase finish inconsistency. Approved iter 3. |
| create-plan | 75 min | 4 (plan-reviewer) | 2 (chain-reviewer) | 6 | TDD ordering blocker at iter 1 AND iter 2 (partial fix). Iter 3 strict warning threshold fail. Approved iter 4. |
| create-tasks | 45 min | 5 (task-reviewer) -- **CAP HIT** | 2 (chain-reviewer) | 7 | Patch namespace blocker at iter 3. YOLO test blocker at iter 4. Task-reviewer cap hit before approval; chain review added task-size split. |
| implement | 105 min | 5 (quality-reviewer) -- **CAP HIT** | -- | 5 | Impl-reviewer: approved iter 1. Security-reviewer: approved iter 1. Quality-reviewer: cap hit iter 5. Falsy guard recurred at iters 2 and 3. ValueError flip-flop between iters 2 and 4. Final validation skipped (cap). |
| **Total** | **380 min (~6.3 hrs)** | | | **28** | Two circuit breaker hits. 31 commits. 4,126 insertions. 12 files changed. |

**Quantitative summary:** Feature 008 is a mid-complexity Python module (366 lines engine, 1,739 lines tests / 85 tests -- 4.7:1 ratio). Pre-implementation phases consumed 23 iterations across 305 minutes; implement consumed 5 iterations across 105 minutes. Circuit breakers fired at create-tasks (task-reviewer 5/5) and implement (quality-reviewer 5/5). The two implementation-adjacent reviewers (impl-reviewer, security-reviewer) passed on iteration 1, indicating the architecture and security posture were sound from the outset.

---

### Review (Qualitative Observations)

1. **API assumption errors dominated specify iter 1** -- All 4 iter-1 blockers were resolvable by reading the feature 007 and feature 005 source before spec authoring. The spec referenced a non-existent DB method, a wrong function signature, a wrong return type, and a missing entity-existence precondition.

2. **Falsy guard recurred across 3 implement iterations due to a partial-fix sweep** -- The `if not last_completed:` vs `if last_completed is None:` defect class appeared at iter 2 (derivation path) and iter 3 (hydration path) as a blocker. The iter 2 fix addressed `_derive_completed_phases` but did not sweep `_hydrate_from_meta_json`.

3. **TDD ordering was a blocker in two consecutive plan iterations due to an incomplete Phase 1 fix** -- Plan iter 1 fix stated "Reordered all phase sub-steps" but did not reorder Phase 1, which still scaffolded production files before tests.

4. **Cross-artifact consistency required explicit correction at every phase boundary** -- Every handoff introduced a new contradiction. The terminal-phase `workflow_phase` value (`None` vs `"finish"`) propagated as an inconsistency through spec, design, and handoff review.

5. **ValueError catch scope flip-flopped between implement iters 2 and 4** -- Iter 2 broadened the catch (remove string-match). Iter 4 narrowed it (bare catch masks errors). No design TD addressed catch scope. Resolution required only a comment documenting pre-validation invariants.

---

### Tune (Process Recommendations)

1. **Add dependency API pre-read gate to specify phase** (Confidence: high) -- For features with `depends_on_features`, require reading each dependency's public interface before authoring FRs.

2. **Apply sibling-sweep rule after every partial-fix on cross-cutting patterns** (Confidence: high) -- After fixing a pattern that must be consistent across N sections, verify ALL sibling sections before closing the issue.

3. **Add a None-check sweep step to quality-reviewer prompt** (Confidence: high) -- After any quality fix involving a None-check, grep the entire file for `if not <var>:` patterns.

4. **Require exception catch scope in design Technical Decisions for race condition handlers** (Confidence: medium) -- Cover what exception types are caught and what pre-validation invariants make the catch safe.

5. **Pre-specify mock patch namespaces in plan for features with from-import external gates** (Confidence: medium) -- Enumerate mock patch targets using the engine module namespace, not the source module namespace.

---

### Act (Knowledge Bank Updates)

#### Patterns

- **Dependency API Pre-Read Before Spec Authoring** -- For features with `depends_on_features`, read each dependency's public interface before authoring any FR. Annotate each consumed API reference with `verified against: <file>:<line>`. (high confidence)

- **Sibling-Sweep After Cross-Cutting Fix** -- After fixing a pattern that must be consistent across N sections, verify the fix is present in ALL sibling sections before submitting. (high confidence)

#### Anti-patterns

- **Applying TDD Reorder Fix Without Per-Phase Verification** -- When a TDD ordering fix claims "reordered all phases," verify each phase individually. Unverified global claims guarantee follow-up blockers. (high confidence)

- **Unspecified Exception Catch Scope in Race Condition Handlers** -- When design describes a race condition handler without specifying catch scope, implement reviewers will flip-flop between "too narrow" and "too broad." (medium confidence)

#### Heuristics

- **Pre-spec API Research Budget** -- For features with `depends_on_features`, budget 30 minutes to read each dependency's public interface before spec authoring. (high confidence)

- **4-5:1 Test-to-Code Line Ratio for Transition-Orchestrator Modules** -- State-machine orchestrators require combinatorial path coverage. A 4-5:1 ratio is a floor, not a ceiling. (medium confidence)

---

## Raw Data

- Feature: 008-workflowstateengine-core
- Mode: standard
- Project: P001
- Branch: feature/008-workflowstateengine-core
- Total elapsed: ~6.5 hours
- Total review iterations: 28
- Circuit breaker hits: 2 (create-tasks task-reviewer, implement quality-reviewer)
- Commits: 31
- Files changed: 12
- Insertions: 4,126
- Key artifacts: engine.py (366 lines), test_engine.py (1,739 lines / 85 tests)
