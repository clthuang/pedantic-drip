# PRD: Phase Transition Summary

## Status
- Created: 2026-03-27
- Status: Draft
- Problem Type: UX Improvement
- Backlog: #00049

## Problem Statement
When a phase completes and the user is asked "Continue to next phase?", there is no context about what just happened. The user sees bare prompts like "Specification complete. Continue to next phase?" with no summary of:
- How many review iterations it took
- What the reviewer approved or flagged
- Whether any warnings remain from the review cycle
- What artifacts were produced

This forces users to either blindly continue or manually inspect review history — neither is ideal.

### Evidence
- `specify.md` line 410: `"question": "Specification complete. Continue to next phase?"` — no context
- Same pattern in `design.md`, `create-plan.md`, `create-tasks.md`, `implement.md`
- The review results (approved/issues) are available in the main conversation context at the point of the AskUserQuestion — they just aren't included in the output text

## Goals
1. Before every phase transition AskUserQuestion, output a brief summary block
2. Summary includes: phase name, iteration count, reviewer verdict, remaining warnings/suggestions
3. Zero new agent dispatches — the data is already in conversation context from the review cycle

## Requirements

### Functional
- FR-1: Before each completion AskUserQuestion in the 5 command files, output a summary block:
  ```
  ## Phase Summary: {phase_name}
  - Iterations: {n} ({domain_reviewer}: {n1}, {phase_reviewer}: {n2})
  - Result: {Approved | Approved with warnings}
  - Remaining feedback: {count} suggestions
    {list of suggestion-severity issues if any, max 5}
  ```
- FR-2: If all reviewers approved with zero remaining issues, show:
  ```
  ## Phase Summary: {phase_name}
  - Iterations: {n}
  - Result: Clean approval (zero issues)
  ```
- FR-3: The summary is plain text output BEFORE the AskUserQuestion — not part of the question itself. This ensures it's visible even in YOLO mode (where AskUserQuestion is skipped).
- FR-4: Data source: use the review results already captured in the conversation context (the reviewer JSON responses). No new file reads or agent dispatches needed. Assumption: the LLM has reliable recall of iteration counts from the immediately preceding review loop. If count is unavailable, output `Iterations: completed`.
- FR-5: If no review data is available in context (review loop did not run or was skipped), omit the Phase Summary block entirely and proceed directly to AskUserQuestion.

**Reviewer name mapping per command:**
- specify: spec-reviewer + phase-reviewer
- design: design-reviewer + phase-reviewer
- create-plan: plan-reviewer + phase-reviewer
- create-tasks: task-reviewer + phase-reviewer
- implement: implementation-reviewer + code-quality-reviewer + security-reviewer (3-reviewer variant)

### Non-Functional
- NFR-1: Summary must not exceed 10 lines — brief enough to scan, detailed enough to inform
- NFR-2: YOLO mode still sees the summary (it's output text, not part of the skipped AskUserQuestion)

## Files to Change
| File | Change |
|------|--------|
| `plugins/pd/commands/specify.md` | Add summary block before completion AskUserQuestion |
| `plugins/pd/commands/design.md` | Same |
| `plugins/pd/commands/create-plan.md` | Same |
| `plugins/pd/commands/create-tasks.md` | Same |
| `plugins/pd/commands/implement.md` | Same (3 reviewers instead of 2) |

## Decision
Pure prompt addition. Add a "Phase Summary" output block before each completion AskUserQuestion. The data is already available in context — this is formatting, not computation.
