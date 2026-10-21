# Specification: Workflow Orchestration & Iterative Review

## Problem Statement

The my-ai-setup plugin workflow lacks enforced stage transitions, iterative quality review before presenting to users, proper worktree management, and feature lifecycle tracking—resulting in inconsistent outputs and workflow confusion.

## Success Criteria

- [ ] Stage transitions follow defined sequence with advisory/blocking validation
- [ ] Each phase artifact goes through reviewer-executor loop before user sees it
- [ ] Worktree location is validated and warnings shown when mismatched
- [ ] Feature status (active/completed/abandoned) is tracked and queryable
- [ ] All 19 acceptance test scenarios pass

## Scope

### In Scope

1. **Workflow State Skill** - Central state management
   - Read/write `.meta.json` state
   - Validate phase transitions (hard + soft prerequisites)
   - Track phase completion and verification status

2. **Reviewer-Executor Loop** - Quality iteration
   - Spawn reviewer subagent after each phase produces artifact
   - Reviewer critiques (read-only, no scope creep)
   - Executor revises based on feedback
   - Iterate until approved or max iterations reached
   - Mode-based iteration limits (Hotfix=1, Quick=2, Standard=3, Full=5)

3. **Reviewer Agent** - Hardened persona
   - Chain validation: ensure output is self-sufficient for next phase
   - Final validation: ensure implementation matches spec
   - Scope-creep prevention built into persona

4. **Worktree Awareness** - Location validation
   - SessionStart hook warns if outside feature worktree
   - Phase commands check cwd vs worktree
   - Warn once per session, don't nag

5. **Feature Lifecycle** - Status tracking
   - States: active, completed, abandoned
   - Transitions via /finish command (one-way to terminal states)
   - No reopen - completed/abandoned are terminal (new work = new feature)

6. **Review History** - Tiered storage
   - Summary in `.meta.json` (iteration count, final notes)
   - Full history in `.review-history.md` during development
   - Cleanup on /finish

### Out of Scope

- Artifact versioning (rely on git)
- Paused feature status
- Reopen/resume completed or abandoned features
- Blocking verification (all verification is advisory)
- Automatic worktree switching
- Multi-feature parallel tracking UI

## Data Schema

### .meta.json

```json
{
  "id": "string - feature ID (e.g., '003')",
  "name": "string - feature slug (e.g., 'workflow-orchestration')",
  "mode": "hotfix | quick | standard | full",
  "status": "active | completed | abandoned",
  "created": "ISO timestamp",
  "completed": "ISO timestamp | null - when status changed to terminal",
  "worktree": "string | null - relative path to worktree",
  "currentPhase": "string - current workflow phase",
  "phases": {
    "{phaseName}": {
      "started": "ISO timestamp",
      "completed": "ISO timestamp | null",
      "verified": "boolean",
      "iterations": "number - reviewer iterations count",
      "reviewerNotes": ["string - final unresolved concerns"]
    }
  }
}
```

## Requirements

### R1: Workflow State Skill

- R1.1: Skill defines phase sequence: brainstorm → specify → design → create-plan → create-tasks → implement → verify → finish
- R1.2: Skill provides validation function for phase transitions
- R1.3: Hard prerequisites block execution: spec.md required for /implement, plan.md required for /create-tasks
- R1.4: Soft prerequisites warn but allow: all other out-of-order transitions
- R1.5: State updates use read-modify-write pattern for atomic changes

### R2: Reviewer-Executor Loop

- R2.1: After phase produces artifact, spawn reviewer subagent
- R2.2: Reviewer receives: previous phase output + current output + next phase expectations
- R2.3: Reviewer returns structured feedback (approved/not + issues list)
- R2.4: If not approved and iterations < max, executor revises
- R2.5: At max iterations, present to user with remaining concerns
- R2.6: Iteration limits per mode: Hotfix=1, Quick=2, Standard=3, Full=5

### R3: Reviewer Agent Persona

- R3.1: Reviewer is read-only (cannot edit files)
- R3.2: Reviewer validates chain sufficiency: "Can next phase work from only this output?"
- R3.3: Reviewer MUST NOT suggest new features or expand scope
- R3.4: Reviewer MUST NOT add nice-to-haves or question product decisions
- R3.5: Final reviewer validates implementation matches original spec

### R4: Worktree Awareness

- R4.1: SessionStart hook checks if active feature has worktree
- R4.2: If cwd ≠ worktree, warn once per session
- R4.3: Phase commands re-check worktree before execution
- R4.4: Skip worktree checks when worktree is null (Hotfix mode)

### R5: Feature Lifecycle

- R5.1: `.meta.json` includes status field (active/completed/abandoned)
- R5.2: /finish with merge/PR sets status to completed (terminal)
- R5.3: /finish with discard sets status to abandoned (terminal)
- R5.4: SessionStart hook only shows active features

### R6: Review History

- R6.1: `.meta.json` stores summary: iteration count, final reviewer notes
- R6.2: `.review-history.md` stores full iteration details during development
- R6.3: /finish deletes `.review-history.md`
- R6.4: User queries history conversationally; LLM reads `.review-history.md` and responds with summary + file path for full details

### R7: Partial Phase Handling

- R7.1: Detect partial phase (started but not completed)
- R7.2: Ask user: continue from draft, start fresh, or review existing
- R7.3: Track started timestamp separate from completed timestamp

## Acceptance Criteria

### AC1: Happy Path - Full Workflow
- Given a new feature in Standard mode
- When user runs commands in order (brainstorm → specify → design → create-plan → create-tasks → implement → verify → finish)
- Then each phase completes with reviewer loop, state updates correctly, feature marked completed

### AC2: Happy Path - Hotfix Mode
- Given a new feature in Hotfix mode
- When user runs /implement directly
- Then single iteration, no worktree checks, minimal verification

### AC3: Happy Path - Full Mode
- Given a new feature in Full mode
- When user runs any phase command
- Then up to 5 reviewer iterations occur before presenting to user

### AC4: Transition - Normal Order
- Given specify phase is complete
- When user runs /design
- Then command proceeds normally (correct order, no warnings)

### AC5: Transition - Soft Warning (Skip)
- Given brainstorm phase is complete (no spec)
- When user runs /design
- Then warning shown about skipping specify, user can acknowledge and proceed

### AC6: Transition - Hard Block
- Given no spec.md exists
- When user runs /implement
- Then command is blocked with message "spec.md required before implementation"

### AC7: Transition - Hard Block
- Given no plan.md exists
- When user runs /create-tasks
- Then command is blocked with message "plan.md required before task creation"

### AC8: Iteration - Early Approval
- Given reviewer approves on first iteration
- When phase completes
- Then only 1 iteration recorded, result presented immediately

### AC9: Iteration - Max Reached
- Given reviewer has concerns after max iterations
- When max iterations reached
- Then result presented with "Reviewer still has concerns: [list]"

### AC10: Reviewer - No Scope Creep
- Given reviewer subagent is processing artifact
- When tempted to suggest new features
- Then reviewer focuses only on clarity/completeness of existing scope

### AC11: Worktree - Session Warning
- Given active feature has worktree at /path/to/worktree
- When session starts in different directory
- Then warning shown once: "Feature worktree is /path/to/worktree"

### AC12: Worktree - Command Warning
- Given user acknowledged session warning
- When user runs phase command still outside worktree
- Then command warns and asks to proceed (not blocked)

### AC13: Worktree - Hotfix Skip
- Given active feature has no worktree (Hotfix mode)
- When session starts or commands run
- Then no worktree warnings shown

### AC14: State - Partial Resume
- Given user started /design but interrupted
- When user runs /design again
- Then detected as partial, user asked: continue/fresh/review

### AC15: State - Complete via Merge
- Given implementation is done
- When user runs /finish and selects merge
- Then status changes to "completed", worktree cleaned up

### AC16: State - Abandon via Discard
- Given user wants to abandon feature
- When user runs /finish and selects discard
- Then status changes to "abandoned", worktree cleaned up

### AC17: Chain - Spec Insufficient
- Given spec.md is missing details needed for design
- When reviewer validates spec
- Then feedback includes "Missing: [specific details needed for design phase]"

### AC18: Chain - Design Insufficient
- Given design.md doesn't fully address spec requirements
- When reviewer validates design
- Then feedback includes "Missing: [specific requirements not addressed]"

### AC19: Chain - Final Validation
- Given implementation is complete
- When final reviewer compares to original spec
- Then any unimplemented requirements are flagged

## Dependencies

- Existing plugin infrastructure (commands, skills, hooks, agents)
- Python3 for JSON parsing in hooks
- Git for worktree management

## Open Questions

None - all decisions resolved during brainstorming.
