# Retrospective: 022-context-and-review-hardening

## AORTA Analysis

### Observe (Quantitative Metrics)
| Phase | Duration | Iterations | Notes |
|-------|----------|------------|-------|
| specify | 1.5h | 6 (4 spec + 2 phase) | Blockers at iter 1-2, approved iter 3 |
| design | 1.7h | 7 (5 design + 2 handoff) | Circuit breaker hit at 5; blocker: regex matched zero files |
| create-plan | 2.4h | 9 (5 plan + 4 chain) | Longest phase; approved iter 3, iters 4-5 informational |
| create-tasks | 1.75h | 6 (3 task + 3 chain) | Most efficient; approved iter 2 both stages |
| implement | 3.3h | 2 | 14/14 tasks, 0 deviations, 1 cosmetic warning |

**Total:** 10.65 hours, 30 review iterations (34 including informational passes)

Design hit the circuit breaker due to a fundamental task parser format mismatch (checkbox vs heading). Plan phase had the most iterations (9) and longest duration (2.4h), with 2 post-approval informational iterations adding no changes. Implementation was the cleanest phase: 14 tasks completed with zero deviations against 30 prior review iterations.

### Review (Qualitative Observations)
1. **Line number references persisted as a cross-phase issue despite existing anti-pattern** -- Plan Review Iteration 1: "Line number references in Step 2 contradict project's own anti-pattern on line numbers." Also flagged in Task Chain Review iterations 0 and 1 with concrete line-number mismatches (50 vs 52, 59 vs 61). The anti-pattern from Feature 018 is being violated during authoring and caught only by reviewers.

2. **Design iteration 3 exposed a foundational assumption failure: parser regex designed for wrong file format** -- Design Review Iteration 3: "C1 Task Block Parser regex matches zero actual tasks.md files -- real format is heading-based, not checkbox-based." This was the feature's single highest-impact issue, requiring Interface 1 rewrite, type change (number to string), and completion strategy overhaul.

3. **Testability was consistently enforced across phases, catching untestable criteria early** -- Spec iterations flagged AC-9 and SC-13 as untestable/subjective. Plan iteration 2 blocked on missing verification steps for regex parsing. Task iteration 0 caught missing expected values for inline verification. Each was resolved before implementation.

### Tune (Process Recommendations)
1. **Mandate codebase verification for parsers/formats in design** (Confidence: high)
   - Signal: Design circuit breaker hit because task parser regex was designed against assumed format without reading actual files
   - Action: Design skill should require "verified against: <file path>" annotation for any regex, parser, or format specification

2. **Promote line-number anti-pattern to reviewer hook rule** (Confidence: high)
   - Signal: Line number references flagged in 4 separate review phases despite existing anti-pattern entry since Feature 018
   - Action: Add reviewer instruction to flag primary line-number anchors as warnings, shifting enforcement from author memory to reviewer checklist

3. **Add early-exit rule for post-approval informational iterations** (Confidence: medium)
   - Signal: Plan review iterations 4-5 produced zero changes (all "no change needed"), adding ~30 min wall-clock time
   - Action: Once plan-reviewer approves with zero blockers/actionable warnings, skip further informational iterations

4. **Reinforce: heavy upfront review pays off in clean implementation** (Confidence: high)
   - Signal: 30 pre-implementation iterations led to 14/14 clean tasks with 0 deviations
   - Action: Update "Reviewer Iteration Count as Complexity Signal" heuristic: high early-phase iterations predict thorough preparation, not implementation risk

5. **Upgrade "Read Target Files" from heuristic to mandatory task-creation step** (Confidence: high)
   - Signal: Create-tasks was most efficient phase (approved iter 2) -- correlates with following the heuristic from Feature 021
   - Action: Make target-file reading a required step in create-tasks skill, not just a recommendation

### Act (Knowledge Bank Updates)
**Patterns added:**
- Heavy upfront review investment (30+ iterations) correlates with clean implementation (0 deviations, 14/14 tasks). (from: Feature #022, implementation phase)
- Matching indentation of surrounding prompt template context prevents formatting issues. (from: Feature #022, Task 1.5)

**Anti-patterns added:**
- Designing parsers against assumed format without verifying against actual files. (from: Feature #022, design iteration 3 -- regex matched zero files)
- Continuing review iterations after approval when all remaining issues are informational. (from: Feature #022, plan iterations 4-5 -- zero changes produced)

**Heuristics added:**
- Circuit breaker hits indicate foundational assumption mismatches, not incremental quality issues. (from: Feature #022, design phase)
- Cross-cutting changes (14+ files) need per-file insertion anchor verification in plan phase. (from: Feature #022, plan/tasks phases -- prevented 4 incorrect line references)

## Raw Data
- Feature: 022-context-and-review-hardening
- Mode: Standard
- Branch lifetime: <1 day (single-day feature)
- Total review iterations: 30 substantive (34 including informational passes)
- Commits: 9
- Files changed: 23
- Implementation tasks: 14/14 completed, 0 skipped, 0 deviations
- Artifacts: spec.md (254 lines), design.md (697 lines), plan.md (663 lines), tasks.md (365 lines)
- Circuit breaker: Hit in design phase (5 iterations)
- Key blocker: Task parser regex designed for checkbox format, actual files use heading format
