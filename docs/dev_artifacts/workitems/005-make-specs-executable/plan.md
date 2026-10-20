# Plan: Make Workflow Specs Executable

## Implementation Order

### Phase 1: Foundation

No new files to create. This feature modifies existing command files.

1. **Understand current command structure** — Read all 5 phase commands to understand existing patterns
   - Complexity: Simple
   - Files: `commands/specify.md`, `commands/design.md`, `commands/create-plan.md`, `commands/create-tasks.md`, `commands/implement.md`

### Phase 2: Core Implementation (Executor-Reviewer Loop)

Add execution instructions to each phase command.

1. **Update specify.md** — Add reviewer invocation, iteration loop, flag handling
   - Depends on: Phase 1
   - Complexity: Medium
   - Files: `commands/specify.md`
   - Changes:
     - Add `--no-review` to argument-hint
     - Add "Reviewer Invocation" section with Task tool format
     - Add "Iteration Loop" instructions
     - Add review history append format

2. **Update design.md** — Add reviewer invocation, iteration loop, flag handling
   - Depends on: Phase 1
   - Complexity: Medium
   - Files: `commands/design.md`
   - Changes: Same pattern as specify.md, different artifacts (spec.md → design.md)

3. **Update create-plan.md** — Add reviewer invocation, iteration loop, flag handling
   - Depends on: Phase 1
   - Complexity: Medium
   - Files: `commands/create-plan.md`
   - Changes: Same pattern, different artifacts (design.md → plan.md)

4. **Update create-tasks.md** — Add reviewer invocation, iteration loop, flag handling
   - Depends on: Phase 1
   - Complexity: Medium
   - Files: `commands/create-tasks.md`
   - Changes: Same pattern, different artifacts (plan.md → tasks.md)

5. **Update implement.md** — Add reviewer invocation, iteration loop, flag handling
   - Depends on: Phase 1
   - Complexity: Medium
   - Files: `commands/implement.md`
   - Changes: Same pattern, different artifacts (tasks.md → code changes)

### Phase 3: Worktree Auto-Creation

Add worktree creation instructions to feature creation flows.

1. **Update create-feature.md** — Add worktree creation based on mode
   - Depends on: None (independent of Phase 2)
   - Complexity: Medium
   - Files: `commands/create-feature.md`
   - Changes:
     - Add mode-based worktree decision logic
     - Add explicit bash commands for worktree creation
     - Add `.meta.json` worktree path storage

2. **Update brainstorming SKILL.md** — Add worktree creation in promotion flow
   - Depends on: None (independent of Phase 2)
   - Complexity: Medium
   - Files: `skills/brainstorming/SKILL.md`
   - Changes:
     - Add worktree creation step when promoting to feature
     - Same mode-based logic as create-feature

### Phase 4: Verification

1. **Manual testing** — Test updated commands
   - Depends on: Phase 2, Phase 3
   - Complexity: Simple
   - Verification steps:
     - Run `/specify` on a test feature, verify reviewer spawns
     - Run `/specify --no-review`, verify reviewer skipped
     - Run `/create-feature` in Standard mode, verify worktree created

## Dependency Graph

```
Phase 1 (Read commands)
    │
    ├──→ specify.md ──┐
    ├──→ design.md ───┤
    ├──→ create-plan.md ─┼──→ Phase 4 (Verification)
    ├──→ create-tasks.md ─┤
    └──→ implement.md ──┘

create-feature.md ─────────────→ Phase 4 (Verification)
brainstorming/SKILL.md ────────→ Phase 4 (Verification)
```

## Risk Areas

- **Claude following the loop**: Risk that Claude doesn't execute numbered steps in order
  - Mitigation: Explicit step-by-step instructions with clear branching

- **JSON parsing**: Reviewer might return malformed JSON
  - Mitigation: Include retry instruction if parsing fails

- **Iteration state**: Counter must persist across loop iterations
  - Mitigation: Explicit note that counter is maintained in memory

## Testing Strategy

- Manual testing only (no automated tests for markdown command files)
- Test each command with and without `--no-review` flag
- Test worktree creation in each mode (Hotfix, Quick, Standard, Full)

## Definition of Done

- [ ] All 5 phase commands updated with reviewer loop instructions
- [ ] `--no-review` flag documented in all phase commands
- [ ] `create-feature.md` includes worktree auto-creation
- [ ] `brainstorming/SKILL.md` includes worktree in promotion flow
- [ ] Manual testing confirms reviewer invocation works
- [ ] Manual testing confirms worktree creation works per mode
