# Specification: Make Workflow Specs Executable

## Problem Statement

Multiple workflow specifications document behavior in pseudocode but lack actual execution mechanics:
1. Executor-reviewer iteration cycle never triggers (reviews don't happen)
2. Worktree auto-creation never triggers (Standard/Full features lack worktrees)

## Success Criteria

### Executor-Reviewer Loop
- [ ] Each phase command includes working reviewer loop logic
- [ ] Chain-reviewer agent is spawned via Task tool after artifact creation
- [ ] Loop iterates until approved OR max iterations reached (mode-dependent)
- [ ] `--no-review` flag allows skipping review
- [ ] `.review-history.md` records each iteration
- [ ] `.meta.json` tracks iteration count per phase

### Worktree Auto-Creation
- [ ] `/create-feature` creates worktree automatically for Standard/Full modes
- [ ] `/brainstorm` promotion flow creates worktree for Standard/Full modes
- [ ] Quick mode prompts user before creating worktree
- [ ] Hotfix mode skips worktree entirely
- [ ] `.meta.json` stores worktree path correctly

## Scope

### In Scope

**Executor-Reviewer Loop:**
- Add execution instructions to 5 phase commands:
  - `/specify`
  - `/design`
  - `/create-plan`
  - `/create-tasks`
  - `/implement`
- Define input/output format for chain-reviewer agent
- Implement iteration tracking in commands
- Add `--no-review` flag to all phase commands
- Update `.review-history.md` format if needed

**Worktree Auto-Creation:**
- Add execution instructions to `/create-feature` command
- Add execution instructions to `/brainstorm` promotion flow
- Explicit invocation of `using-git-worktrees` skill
- Mode-based decision logic (skip for Hotfix, ask for Quick, auto for Standard/Full)

### Out of Scope

- Creating new orchestration skill (commands handle logic inline)
- Modifying chain-reviewer agent persona (already defined)
- Hook-based automation
- Final reviewer integration (focus on chain-reviewer first)
- Modifying the using-git-worktrees skill itself (already complete)

## Acceptance Criteria

### Reviewer Invocation

- Given `/specify` completes artifact creation
- When no `--no-review` flag is present
- Then chain-reviewer agent is spawned via Task tool
- And previous artifact (brainstorm.md) and current artifact (spec.md) are passed

### Iteration Loop

- Given chain-reviewer returns "needs revision"
- When iteration count < mode limit
- Then command prompts for revision
- And increments iteration count
- And re-invokes reviewer after revision

### Iteration Limits

- Given mode is Standard (limit: 3)
- When 3 iterations complete without approval
- Then phase is marked complete with unresolved concerns
- And warning is displayed

### Skip Flag

- Given user runs `/specify --no-review`
- When artifact is created
- Then reviewer is NOT spawned
- And phase completes immediately

### State Tracking

- Given each review iteration completes
- When updating state
- Then `.review-history.md` has new entry with:
  - Iteration number
  - Reviewer decision (approved/needs-revision)
  - Feedback summary
- And `.meta.json` iterations count is updated

### Worktree Auto-Creation

- Given user runs `/create-feature` with Standard mode
- When feature folder is created
- Then `using-git-worktrees` skill is invoked
- And worktree is created at `../{project}-{id}-{slug}`
- And `.meta.json` stores the worktree path

### Mode-Based Worktree Decision

- Given mode is Hotfix
- When feature is created
- Then worktree is NOT created
- And `.meta.json` has `"worktree": null`

- Given mode is Quick
- When feature is created
- Then user is asked "Create worktree? (y/n)"
- And worktree is created only if user confirms

## Dependencies

- Existing chain-reviewer agent (`agents/chain-reviewer.md`)
- Existing using-git-worktrees skill (`skills/using-git-worktrees/SKILL.md`)
- Existing phase commands
- Feature 003 design documents for reference

## Technical Notes

### Task Tool Format for Reviewer

```
Task tool call:
  subagent_type: chain-reviewer
  prompt: |
    Review the following artifacts for chain sufficiency.

    Previous artifact (brainstorm.md):
    {content}

    Current artifact (spec.md):
    {content}

    Next phase expectations:
    {expectations from design.md}

    Return: APPROVED or NEEDS_REVISION with specific feedback
```

### Mode Iteration Limits

| Mode | Max Iterations |
|------|----------------|
| Hotfix | 1 |
| Quick | 2 |
| Standard | 3 |
| Full | 5 |
