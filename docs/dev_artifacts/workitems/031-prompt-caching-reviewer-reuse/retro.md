# Retrospective: 031-prompt-caching-reviewer-reuse

## AORTA Analysis

### Observe (Quantitative Metrics)
| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | ~25 min | 1 | No review history entries — likely first-pass approval |
| design | ~2h 20m | 5 (design: 3, handoff: 2) | 3 blockers on iter 1 (annotation count, template uniformity, in-memory diff infeasibility) |
| create-plan | ~1h 35m | 8 (plan: 4, chain: 4) | Plan iter 1 found test regression risk; iter 3 had 2 blockers + 9 warnings |
| create-tasks | ~3h 50m | 10 (task: 5, chain: 5) | **Both stages hit circuit breaker.** 5 concerns carried as unresolved warnings |
| implement | ~3h 10m | 3 | All issues fixed on first attempt; iter 3 was final validation confirmation |

**Total wall-clock:** ~11 hours | **Total iterations:** ~27 | **Commits:** 20 | **Lines changed:** 4,624 (+), 118 (-)

create-tasks consumed 35% of total time and was the only phase to hit circuit breakers. Implementation was the cleanest phase despite being the largest code change.

### Review (Qualitative Observations)
1. **Non-executable placeholder syntax drove repeated review iterations** — `{actual_headers}` in code-fenced grep commands (create-tasks chain review iters 0-4), `{phase}` placeholder ambiguity (task review iter 5). These are not valid shell and produce vacuous matches, but authors struggled to replace them with concrete instructions without losing generality.

2. **Git operation edge cases were a persistent cross-phase concern** — In-memory diff infeasibility for LLM orchestrator (design iter 1 blocker), HEAD~1 vs last_commit_sha contradiction (design iter 2 blocker), empty commit handling (design iter 2), git add -A staging scope (plan iter 2, implement iter 1). Four phases, five distinct git issues.

3. **Self-referential verification remained unresolved through circuit breaker** — Task 12's acceptance criteria iterated from self-attestation to grep verification to label-dependent grep, with the chain reviewer noting the replacement was equally weak. The verification weakness was never fully resolved before the cap was reached.

### Tune (Process Recommendations)
1. **Add pre-review lint for placeholder syntax in code fences** (Confidence: high)
   - Signal: `{actual_headers}` and `{phase}` placeholders inside code-fenced shell commands caused 4+ create-tasks iterations across both review stages
   - Action: Add a hook or pre-review check that flags `{...}` patterns inside triple-backtick code blocks in tasks.md. Either replace with concrete examples or mark explicitly as "substitute before executing"

2. **Create a Git Operations Reference for design phase** (Confidence: high)
   - Signal: Git edge cases appeared in 4/5 phases with 5+ distinct issues, consuming 2 of 3 design iterations
   - Action: Add a structured checklist to the design template covering diff baseline, empty commits, staging scope, commit message format, and SHA lifecycle. Designer addresses each before review

3. **Preserve the three-reviewer implement pattern** (Confidence: high)
   - Signal: Implementation resolved all issues in 1 fix cycle despite 4,624 lines changed. Quality caught off-by-one, security caught staging scope, implementation caught spec compliance
   - Action: No change needed. Document as a reinforced pattern

4. **Batch related plan reviewer concerns** (Confidence: medium)
   - Signal: Plan review iterations 1-3 each produced 2-3 blockers + 5-9 warnings. Iteration 3 alone had 14 issues across 4 concern domains
   - Action: Either tune the plan reviewer to batch related concerns (e.g., "git operation concerns" as one compound issue) or add a pre-review self-check that catches mechanical issues before submission

5. **Investigate LAZY-LOAD-WARNING persistence in phase-reviewer** (Confidence: medium)
   - Signal: 3 LAZY-LOAD-WARNING entries for phase-reviewer in create-tasks chain review (iterations 0, 1, 2)
   - Action: Check whether the phase-reviewer prompt in create-tasks.md includes the artifact read confirmation instruction prominently. Track rate per post-deployment monitoring table

### Act (Knowledge Bank Updates)
**Patterns added:**
- Three-reviewer parallel dispatch with selective re-dispatch resolves implementation issues efficiently (from: Feature 031, implement phase — 3 distinct issue categories found and fixed in one cycle)
- Enumerate git operation edge cases in a dedicated Technical Decision section during design (from: Feature 031, design phase — 2 of 3 iterations driven by git edge cases)

**Anti-patterns added:**
- Curly-brace template placeholders inside code-fenced shell commands in task descriptions (from: Feature 031, create-tasks phase — {actual_headers} and {phase} drove 4+ iterations)
- Self-attestation verification methods in task acceptance criteria (from: Feature 031, create-tasks phase — Task 12 iterated 3 times without resolution)

**Heuristics added:**
- If both stages of a two-stage review hit circuit breaker, the artifact has a structural authoring problem (from: Feature 031, create-tasks — both stages 5/5, unresolved warnings point to authoring patterns)
- Plan review iterations scale with distinct concern domains; cross-cutting features should expect 4+ iterations (from: Feature 031, create-plan — 8 iterations across git, testing, dependency, verification domains)

## Raw Data
- Feature: 031-prompt-caching-reviewer-reuse
- Mode: Standard
- Branch lifetime: <1 day (created and completed 2026-02-28)
- Total review iterations: ~27
- Files changed: 13
- Lines: +4,624 / -118
- Circuit breaker hits: 2 (create-tasks taskReview and chainReview)
- LAZY-LOAD-WARNINGs: 3 (phase-reviewer in create-tasks)
