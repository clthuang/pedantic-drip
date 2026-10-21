# Plan: Change Workflow Ordering

## Implementation Order

### Phase 1: Foundation (No Dependencies)

1. **Create docs/brainstorms/.gitkeep** — Ensure scratch directory exists in git
   - Complexity: Simple
   - Files: `docs/dev_artifacts/brainstorms/.gitkeep`

2. **Rename commands/plan.md to commands/create-plan.md** — Fix command collision
   - Complexity: Simple
   - Files: `commands/plan.md` → `commands/create-plan.md`

### Phase 2: Reference Updates (Depends on Phase 1.2)

3. **Update /plan references in skills** — Point to /create-plan
   - Complexity: Simple
   - Depends on: Item 2
   - Files:
     - `skills/designing/SKILL.md` (line 121)
     - `skills/breaking-down-tasks/SKILL.md` (line 13)

4. **Update /plan references in README** — Point to /create-plan
   - Complexity: Simple
   - Depends on: Item 2
   - Files: `README.md` (lines 72, 166)

5. **Update SessionStart hook** — Fix workflow display and add /create-plan
   - Complexity: Simple
   - Depends on: Item 2
   - Files: `hooks/session-start.sh` (line 118, 120-121)
   - Changes:
     - Make `/brainstorm` primary entry point
     - Add `/create-plan` to flow between /design and /create-tasks
     - Show `/create-feature` as alternative
     - Update "No active feature" message to suggest /brainstorm

### Phase 3: Core Skill Updates (No Dependencies)

6. **Update skills/specifying/SKILL.md** — Add no-feature guard
   - Complexity: Simple
   - Depends on: None
   - Files: `skills/specifying/SKILL.md`
   - Changes:
     - Update Prerequisites section
     - Guide to /brainstorm if no feature

7. **Update skills/brainstorming/SKILL.md — Part A: Standalone mode**
   - Complexity: Medium
   - Depends on: None
   - Files: `skills/brainstorming/SKILL.md`
   - Changes:
     - Add "Standalone Mode" section
     - Scratch file creation (timestamp + slug)
     - Context-aware behavior (active feature check)

8. **Update skills/brainstorming/SKILL.md — Part B: Promotion flow**
   - Complexity: Medium
   - Depends on: Item 7
   - Files: `skills/brainstorming/SKILL.md`
   - Changes:
     - Promotion prompt logic
     - Mode selection flow
     - Feature folder creation
     - Worktree handling (per mode)
     - .meta.json creation
     - File move (scratch → feature folder)
     - Auto-chain to /specify

### Phase 4: Command Updates (Depends on Phase 3)

9. **Update commands/brainstorm.md** — Remove feature requirement
   - Complexity: Simple
   - Depends on: Items 7, 8
   - Files: `commands/brainstorm.md`
   - Changes:
     - Update description: "Start brainstorming - works with or without active feature"
     - Update argument-hint
     - Add context detection instructions

10. **Update commands/create-feature.md** — Make alternative entry point
    - Complexity: Simple
    - Depends on: Items 7, 8
    - Files: `commands/create-feature.md`
    - Changes:
      - Update messaging (note: skipping brainstorm)
      - Chain to /specify instead of /brainstorm
      - Mark as "alternative entry point" in description

11. **Update commands/specify.md** — Add no-feature guard
    - Complexity: Simple
    - Depends on: Item 6
    - Files: `commands/specify.md`
    - Changes:
      - Check for active feature
      - Suggest /brainstorm if none

### Phase 5: New Command (Depends on Phase 1.1)

12. **Create commands/cleanup-brainstorms.md** — New cleanup command
    - Complexity: Simple
    - Depends on: Item 1
    - Files: `commands/cleanup-brainstorms.md` (new)
    - Content:
      - List files in docs/brainstorms/
      - Display with relative dates
      - User selects numbers to delete
      - Confirm before deletion

## Dependency Graph

```
Phase 1 (Foundation) - can run in parallel
├── 1. .gitkeep ─────────────────────────────────► 12. cleanup command
└── 2. rename plan.md ───┬──► 3. skill refs
                         ├──► 4. README refs
                         └──► 5. session-start hook

Phase 3 (Skills) - can run in parallel with Phase 2
├── 6. specifying skill ─────────────────────────► 11. specify cmd
└── 7. brainstorming (A) ──► 8. brainstorming (B) ─┬► 9. brainstorm cmd
                                                   └► 10. create-feature cmd
```

## Parallel Execution Groups

| Group | Items | Can Run Together |
|-------|-------|------------------|
| A | 1, 2 | Yes (no deps) |
| B | 3, 4, 5 | Yes (all depend only on 2) |
| C | 6, 7 | Yes (no deps between them) |
| D | 9, 10, 11, 12 | Yes (after their deps resolve) |

## Risk Areas

| Item | Risk | Mitigation |
|------|------|------------|
| Item 8 (promotion flow) | Complex logic, largest change | Break into sub-steps, test manually |
| File move during promotion | Data loss if interrupted | Copy first, delete after verify |
| Worktree creation | Can fail (permissions, path issues) | Graceful fallback: warn and continue without |

## Testing Strategy

**Manual testing (in order):**

1. **Standalone brainstorm flow**
   - `/brainstorm "test idea"` without feature → creates scratch file
   - Verify file at `docs/dev_artifacts/brainstorms/YYYYMMDD-HHMMSS-test-idea.md`

2. **Promotion flow**
   - At end of brainstorm, answer "yes" to promotion
   - Select mode (test Standard)
   - Verify: feature folder created, worktree created, file moved, chains to /specify

3. **Decline promotion**
   - `/brainstorm "another idea"`, answer "no"
   - Verify file stays in scratch folder

4. **Context-aware brainstorm**
   - With active feature, run `/brainstorm`
   - Verify: asks "Add to existing or new?"

5. **Specify guard**
   - Without feature, run `/specify`
   - Verify: suggests /brainstorm

6. **Create-feature alternative**
   - `/create-feature "skip brainstorm"`
   - Verify: chains to /specify (not /brainstorm)

7. **Cleanup command**
   - Add some files to docs/brainstorms/
   - `/cleanup-brainstorms` → lists files, allows deletion

8. **Command rename**
   - `/create-plan` → invokes planning skill (not built-in plan mode)
   - Verify no references to old `/plan` remain

**Edge cases:**
- Empty topic → generate generic slug like "untitled"
- Very long topic (>50 chars) → truncate to 30
- Special characters → sanitize to hyphens
- Worktree creation failure → continue without, warn user

## Definition of Done

- [ ] All 12 items implemented
- [ ] Manual test cases pass (8 scenarios + edge cases)
- [ ] No references to old `/plan` command remain
- [ ] docs/brainstorms/ directory exists with .gitkeep
- [ ] README reflects new workflow
- [ ] SessionStart hook shows correct command flow
- [ ] Promotion flow handles all modes correctly
