# Retrospective: 017-command-cleanup-and-pseudocode

## AORTA Analysis

### Observe (Quantitative Metrics)

| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 70 min | 6 | spec-reviewer x2 (blockers: preservation gap, scope ambiguity, contradiction; then: get_phase JSON shape, chicken-and-egg ordering) + phase-reviewer x2 (ambiguous text, vacuous AC, traceability gap) |
| design | 60 min | 6 | design-reviewer x4 (entity_db source, CLAUDE.md prereqs, narrow grep scope; then 3 stale files outside target list; then stale file count '7'); handoff-reviewer x2 (secretary.md sequencing notes) |
| create-plan | 40 min | 6 | plan-reviewer x2 (blank line preservation, id/slug extraction, replacement text precision; then conditional vs definitive) + chain-reviewer x2 (underspecified replacement, missing smoke test) |
| create-tasks | 70 min | 6 | task-reviewer x4 (baseline split, inline verbatim, expanded AC checks, smoke test; count errors, oversized tasks, verbatim FR-9; stale count; --feature flag nonexistent) + chain-reviewer x2 (smoke test downgrade, AC-7 missing check) |
| implement | 80 min | 3 | Iter 1: quality warning on misleading {lastCompletedPhase} label + spec reference leak. Iter 2: approved. Iter 3: final validation, all approved. |

Total active work: ~320 minutes across 5 phases. 27 total review iterations. Every pre-implement phase hit exactly 6 iterations. Implement was the cleanest phase (3 iterations, 1 substantive fix). Net outcome: 21 tasks, 35 steps, 188 lines removed (~1,880-2,820 tokens saved), 20 commits, 11 files changed.

### Review (Qualitative Observations)

1. **Verbatim text omission was the dominant blocker pattern across plan and tasks phases.** Every phase involving replacement text required revision to embed exact text inline rather than reference by spec section number. Evidence: Plan iter 1: "Step 2.3 replacement text formatting not specified precisely enough." Task iter 1: "[blocker] Task 2.2: Replacement text referenced by spec line numbers not reproduced inline." Task iter 2: "[blocker] Task 3.1: Missing verbatim FR-9 replacement text."

2. **Scope boundary discovery was consistently deferred — the target file list grew from 7 to 10 files across three design iterations.** The first design-reviewer pass accepted the initial 7-file list without a broad grep, and stale references outside that list were found only after a blocker in iteration 2. Evidence: Design iter 2: "[blocker] 3 files outside 7 targets contain stale references: hookify.docs-sync.local.md, command-template.md, patterns.md." Design iter 3: "File count '7' stale after adding files."

3. **Smoke test specification was contested across 4 revision cycles.** The live /iflow:specify invocation specified in the spec was impractical (--feature flag nonexistent), but this was not discovered until task iteration 3.

### Tune (Process Recommendations)

1. **Require verbatim inline text in any plan/task step that writes to a file** (high confidence) — 5 of 6 task-review blockers involved text referenced by spec section. Inlined tasks had zero implementation blockers.

2. **Run broad-scope stale-reference grep before drafting the design component map** (high confidence) — Component map grew 7 to 10 files across 3 iterations. Earlier grep would have produced correct scope on first pass.

3. **Document full MCP tool response shapes (including null variants) inline in the spec** (medium confidence) — 2 spec iterations needed for get_phase JSON response shape including null current_phase handling.

4. **Verify smoke test command syntax against actual CLI interface during spec authoring** (medium confidence) — Smoke test went through 4 revision cycles because --feature flag was assumed to exist.

5. **Reinforce invest-in-task-detail pattern** (high confidence) — Implement phase was the cleanest (3 iterations) despite 21 tasks. Heavy upfront task authoring paid off.

### Act (Knowledge Bank Updates)

**Patterns:** Inline verbatim replacement text in tasks; parallelize implementation across disjoint file sets.

**Anti-patterns:** Building component maps from planned scope (not grep results); referencing MCP response shapes by field name only; specifying smoke tests with unverified CLI flags.

**Heuristics:** Grep-first scope discovery for removal/renaming features; full JSON response shapes inline in specs; derive counts from lists rather than hardcoding in prose.

## Raw Data

- Feature: 017-command-cleanup-and-pseudocode
- Mode: Standard
- Branch lifetime: ~1 day (2026-03-07 to 2026-03-08)
- Total review iterations: 27
- Commits: 20
- Files changed: 11 (51 insertions, 236 deletions, net -185 lines)
- Artifact lines: 1,021 total (spec 341, design 130, plan 223, tasks 279, impl-log 48)
- Net production line reduction: 188 lines (~1,880-2,820 tokens saved)
- workflow-state/SKILL.md: 363 to 174 lines (-52%)
