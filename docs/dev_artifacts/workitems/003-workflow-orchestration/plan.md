# Plan: Workflow Orchestration & Iterative Review

## Implementation Order

### Phase 1: Foundation (No Dependencies)

Core components that other items depend on.

1. **Workflow State Skill** — Central state management and validation logic
   - Complexity: Medium
   - Files: `skills/workflow-state/SKILL.md` (create)
   - Defines: Phase sequence, validation rules, state update patterns

2. **Chain Reviewer Agent** — Artifact quality reviewer with hardened persona
   - Complexity: Medium
   - Files: `agents/chain-reviewer.md` (create)
   - Defines: Review interface, no-scope-creep constraints, feedback format

3. **Final Reviewer Agent** — Implementation vs spec validator
   - Complexity: Simple
   - Files: `agents/final-reviewer.md` (create)
   - Defines: Spec comparison logic, requirement tracking

### Phase 2: Hook Enhancement (Depends on Phase 1)

Session context and worktree awareness.

4. **Enhanced SessionStart Hook** — Add worktree warning and active feature filter
   - Depends on: Workflow State Skill (for status filtering)
   - Complexity: Medium
   - Files: `hooks/session-start.sh` (modify)
   - Changes: Add cwd vs worktree check, filter by status=active, show next command

### Phase 3: Command Integration (Depends on Phase 1, 2)

Apply reviewer loop pattern to all phase commands.

5. **Specify Command** — Add validation and reviewer loop
   - Depends on: Workflow State Skill, Chain Reviewer Agent
   - Complexity: Medium
   - Files: `commands/specify.md` (modify)
   - Changes: Add validation call, reviewer loop, state updates

6. **Design Command** — Add validation and reviewer loop
   - Depends on: Workflow State Skill, Chain Reviewer Agent
   - Complexity: Medium
   - Files: `commands/design.md` (modify)
   - Changes: Add validation call, reviewer loop, state updates

7. **Create-Plan Command** — Add validation and reviewer loop
   - Depends on: Workflow State Skill, Chain Reviewer Agent
   - Complexity: Medium
   - Files: `commands/create-plan.md` (modify)
   - Changes: Add validation call, reviewer loop, state updates

8. **Create-Tasks Command** — Add validation and reviewer loop
   - Depends on: Workflow State Skill, Chain Reviewer Agent
   - Complexity: Medium
   - Files: `commands/create-tasks.md` (modify)
   - Changes: Add validation call, reviewer loop, hard prerequisite (plan.md)

9. **Implement Command** — Add validation and reviewer loop
   - Depends on: Workflow State Skill, Chain Reviewer Agent
   - Complexity: Medium
   - Files: `commands/implement.md` (modify)
   - Changes: Add validation call, reviewer loop, hard prerequisite (spec.md)

### Phase 4: Lifecycle Management (Depends on Phase 1)

Feature completion and cleanup.

10. **Finish Command** — Add status updates and history cleanup
    - Depends on: Workflow State Skill
    - Complexity: Medium
    - Files: `commands/finish.md` (modify)
    - Changes: Set status to completed/abandoned, delete .review-history.md, cleanup worktree

## Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PHASE 1: Foundation                         │
│                                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     │
│  │ 1. Workflow     │  │ 2. Chain        │  │ 3. Final        │     │
│  │    State Skill  │  │    Reviewer     │  │    Reviewer     │     │
│  └────────┬────────┘  └────────┬────────┘  └─────────────────┘     │
│           │                    │                                    │
└───────────┼────────────────────┼────────────────────────────────────┘
            │                    │
            ▼                    │
┌───────────────────────┐        │
│ PHASE 2: Hook         │        │
│                       │        │
│ 4. SessionStart Hook  │        │
└───────────┬───────────┘        │
            │                    │
            ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE 3: Command Integration                     │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────┐│
│  │5. specify│  │6. design │  │7. plan   │  │8. tasks  │  │9. impl││
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └───────┘│
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌───────────────────────┐
│ PHASE 4: Lifecycle    │
│                       │
│ 10. Finish Command    │◄── Depends on: Workflow State Skill
└───────────────────────┘
```

## Risk Areas

| Item | Risk | Mitigation |
|------|------|------------|
| Chain Reviewer Agent | May scope creep despite instructions | Test with examples, iterate on persona constraints |
| Command modifications | Breaking existing functionality | Incremental changes, test each command after modification |
| SessionStart Hook | Python/bash compatibility on different systems | Already fixed macOS compatibility; test on target systems |
| State updates | Concurrent modifications could corrupt | Read-modify-write pattern with full file rewrite |

## Testing Strategy

**Unit Tests (per component):**
- Workflow State Skill: Test validation rules (hard block, soft warn, proceed)
- Chain Reviewer Agent: Test feedback format, scope creep rejection
- Final Reviewer Agent: Test spec comparison logic

**Integration Tests (per command):**
- Each command: Run through happy path, verify state updates
- Reviewer loop: Verify iteration counting, max limit handling
- Partial phase: Test resume detection and user options

**End-to-End Tests (full workflow):**
- AC1: Full workflow in Standard mode
- AC2: Hotfix mode (single iteration, no worktree)
- AC6-7: Hard block scenarios

## Definition of Done

- [ ] All 10 items implemented
- [ ] Workflow state skill defines complete phase sequence
- [ ] Chain reviewer has hardened no-scope-creep persona
- [ ] All phase commands include reviewer loop
- [ ] SessionStart hook shows worktree warning
- [ ] Finish command updates status and cleans up
- [ ] All 19 acceptance criteria pass
- [ ] Plugin cache updated and tested
