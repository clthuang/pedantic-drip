# Tasks: Workflow Orchestration & Iterative Review

## Task List

### Phase 1: Foundation (No Dependencies)

#### Task 1.1: Create workflow-state skill with phase sequence
- **Files:** `skills/workflow-state/SKILL.md`
- **Do:** Create skill directory and SKILL.md with:
  - Frontmatter (name, description)
  - Phase sequence: brainstorm → specify → design → create-plan → create-tasks → implement → verify → finish
- **Test:** File exists with valid YAML frontmatter and complete phase order
- **Done when:** Skill file created with phase sequence defined

#### Task 1.2: Add validation rules and state patterns to workflow-state skill
- **Files:** `skills/workflow-state/SKILL.md`
- **Do:** Add to the skill:
  - Hard prerequisites (spec.md for /implement, plan.md for /create-tasks)
  - Soft prerequisites (all other transitions warn but allow)
  - Read-modify-write pattern for .meta.json updates
  - validateTransition and updatePhaseState interfaces
- **Test:** Both validation rules and state update patterns documented with examples
- **Done when:** Skill is complete and self-contained

#### Task 1.3: Create chain-reviewer agent with review interface
- **Files:** `agents/chain-reviewer.md`
- **Do:** Create agent file with:
  - Frontmatter (name, description, tools: Read, Glob, Grep - read-only)
  - Input format: previous artifact, current artifact, next phase expectations
  - Output format: {approved, issues, summary}
- **Test:** File exists with valid frontmatter and interface matches design.md
- **Done when:** Agent structure and interface documented

#### Task 1.4: Add hardened persona and expectations table to chain-reviewer
- **Files:** `agents/chain-reviewer.md`
- **Do:** Add to the agent:
  - Explicit "MUST NOT" rules: no scope expansion, no new features, no nice-to-haves, no questioning product decisions
  - Next-phase expectations table from design.md (what each phase needs)
- **Test:** All constraints from brainstorm.md included, table covers brainstorm through implement
- **Done when:** Hardened persona complete with expectations reference

#### Task 1.5: Create final-reviewer agent with comparison logic
- **Files:** `agents/final-reviewer.md`
- **Do:** Create agent file with:
  - Frontmatter (name, description, tools: Read, Glob, Grep - read-only)
  - Comparison logic: implementation vs original spec.md
  - Flag patterns: unimplemented requirements, extra work, misunderstandings
- **Test:** File exists with read-only tools, logic covers all comparison cases
- **Done when:** Agent can validate implementation against spec

### Phase 2: Hook Enhancement (Depends on Phase 1)

#### Task 2.1: Add worktree check to session-start.sh
- **Depends on:** Task 1.2 (state patterns)
- **Files:** `hooks/session-start.sh`
- **Do:** Compare current working directory against worktree from .meta.json, add warning message if different
- **Test:** When cwd != worktree, warning appears in context
- **Done when:** Worktree warning logic implemented

#### Task 2.2: Verify status filter in session-start.sh
- **Depends on:** Task 1.2 (state patterns)
- **Files:** `hooks/session-start.sh`
- **Do:** Verify existing status=active filter works correctly, enhance if needed
- **Test:** Completed/abandoned features not shown in session context
- **Done when:** Status filter verified working

#### Task 2.3: Add next command suggestion to session-start.sh
- **Depends on:** Task 1.1 (phase sequence)
- **Files:** `hooks/session-start.sh`
- **Do:** Based on currentPhase, suggest the next command (e.g., "Next: /design")
- **Test:** Correct next command shown for each phase
- **Done when:** Next command appears in context message

### Phase 3: Command Integration (Depends on Phase 1, 2)

#### Task 3.1: Add state update to brainstorm command
- **Depends on:** Task 1.2 (state patterns)
- **Files:** `commands/brainstorm.md`
- **Do:** Add instructions to mark phase started/completed in .meta.json when brainstorm produces brainstorm.md
- **Test:** State updates for started, completed documented
- **Done when:** State management integrated
- **Note:** Brainstorm is entry point - no validation needed, no reviewer loop (user explores freely)

#### Task 3.2: Add validation, reviewer loop, and state to specify command
- **Depends on:** Tasks 1.2, 1.3, 1.4 (skill + chain-reviewer)
- **Files:** `commands/specify.md`
- **Do:** Add:
  - Transition validation call (workflow-state skill)
  - Reviewer loop: spawn chain-reviewer, iterate until approved or max, handle feedback
  - State updates: mark started/completed, track iterations
- **Test:** Command has validation, loop pattern matches design.md, state updates present
- **Done when:** Full workflow integration complete

#### Task 3.3: Add validation, reviewer loop, and state to design command
- **Depends on:** Tasks 1.2, 1.3, 1.4 (skill + chain-reviewer)
- **Files:** `commands/design.md`
- **Do:** Add:
  - Transition validation call
  - Reviewer loop with design-specific expectations (next: plan)
  - State updates
- **Test:** Full pattern present with correct next-phase expectations
- **Done when:** Full workflow integration complete

#### Task 3.4: Add validation, reviewer loop, and state to create-plan command
- **Depends on:** Tasks 1.2, 1.3, 1.4 (skill + chain-reviewer)
- **Files:** `commands/create-plan.md`
- **Do:** Add:
  - Transition validation call
  - Reviewer loop with plan-specific expectations (next: tasks)
  - State updates
- **Test:** Full pattern present with correct next-phase expectations
- **Done when:** Full workflow integration complete

#### Task 3.5: Add validation, reviewer loop, and state to create-tasks command
- **Depends on:** Tasks 1.2, 1.3, 1.4 (skill + chain-reviewer)
- **Files:** `commands/create-tasks.md`
- **Do:** Add:
  - Transition validation with **hard prerequisite** (plan.md required - block if missing)
  - Reviewer loop with tasks-specific expectations (next: implement)
  - State updates
- **Test:** Hard block for missing plan.md, full pattern present
- **Done when:** Full workflow integration complete with hard prerequisite

#### Task 3.6: Add validation, reviewer loop, and state to implement command
- **Depends on:** Tasks 1.2-1.5 (skill + both reviewers)
- **Files:** `commands/implement.md`
- **Do:** Add:
  - Transition validation with **hard prerequisite** (spec.md required - block if missing)
  - Reviewer loop with chain-reviewer during implementation
  - Final-reviewer call at end for spec compliance
  - State updates
- **Test:** Hard block for missing spec.md, both reviewer patterns present
- **Done when:** Full workflow integration complete with final validation

#### Task 3.7: Add validation and state to verify command
- **Depends on:** Tasks 1.2 (state patterns)
- **Files:** `commands/verify.md`
- **Do:** Add:
  - Transition validation (warn if verifying phase that isn't complete)
  - Update .meta.json verified field to true on pass
- **Test:** Verified flag set to true when verification passes
- **Done when:** Verify updates state correctly
- **Note:** Verify doesn't produce artifact, so no reviewer loop - it IS the review

### Phase 4: Lifecycle Management (Depends on Phase 1)

#### Task 4.1: Add status update to finish command
- **Depends on:** Task 1.2 (state patterns)
- **Files:** `commands/finish.md`
- **Do:** Add logic to set status to "completed" (merge/PR) or "abandoned" (discard)
- **Test:** Both terminal states documented
- **Done when:** Status transitions implemented

#### Task 4.2: Add review history cleanup to finish command
- **Depends on:** Task 1.2 (state patterns)
- **Files:** `commands/finish.md`
- **Do:** Add instruction to delete .review-history.md on finish
- **Test:** Cleanup step documented
- **Done when:** History cleanup integrated

#### Task 4.3: Add worktree cleanup to finish command
- **Depends on:** Task 1.2 (state patterns)
- **Files:** `commands/finish.md`
- **Do:** Add instruction to clean up git worktree when feature completes
- **Test:** Worktree removal documented
- **Done when:** Worktree cleanup integrated

## Command Coverage Matrix

| Command | Validation | Reviewer Loop | State Update | Notes |
|---------|------------|---------------|--------------|-------|
| brainstorm | N/A (entry) | N/A (exploration) | Task 3.1 | Entry point, free exploration |
| specify | Task 3.2 | Task 3.2 | Task 3.2 | Standard pattern |
| design | Task 3.3 | Task 3.3 | Task 3.3 | Standard pattern |
| create-plan | Task 3.4 | Task 3.4 | Task 3.4 | Standard pattern |
| create-tasks | Task 3.5 | Task 3.5 | Task 3.5 | Hard prereq: plan.md |
| implement | Task 3.6 | Task 3.6 | Task 3.6 | Hard prereq: spec.md, final-reviewer |
| verify | Task 3.7 | N/A (is review) | Task 3.7 | Updates verified flag |
| finish | N/A | N/A | Tasks 4.1-4.3 | Terminal state, cleanup |

## Summary

- Total tasks: 18
- Phase 1: 5 tasks (Foundation - can be parallelized)
- Phase 2: 3 tasks (Hook Enhancement)
- Phase 3: 7 tasks (Command Integration - all 8 workflow commands)
- Phase 4: 3 tasks (Lifecycle Management)

Execution pattern:
- Phase 1 tasks are independent and can be worked in parallel
- Phase 2-4 depend on Phase 1 completion
- Within Phase 3, commands can be worked in any order after their dependencies
