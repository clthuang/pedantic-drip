# Tasks: Make Workflow Specs Executable

## Task List

### Phase 1: Foundation

#### Task 1.1: Read existing command files
- **Files:** `commands/specify.md`, `commands/design.md`, `commands/create-plan.md`, `commands/create-tasks.md`, `commands/implement.md`
- **Do:** Read all 5 phase commands to understand current structure and identify where to add reviewer loop
- **Test:** Can identify the section in each command where artifact production happens
- **Done when:** Notes captured on where to insert execution instructions in each file

---

### Phase 2: Executor-Reviewer Loop

#### Task 2.1: Update specify.md with reviewer loop
- **Depends on:** Task 1.1
- **Files:** `commands/specify.md`
- **Do:**
  1. Add `--no-review` to argument-hint in frontmatter
  2. Add "Execute with Reviewer Loop" section after artifact production
  3. Include Task tool call format for chain-reviewer
  4. Include iteration loop logic with mode-based max
  5. Include review history append format
  6. Reference: Previous=brainstorm.md, Current=spec.md, Next="Design needs: All requirements listed, acceptance criteria defined, scope boundaries clear"
- **Test:** Command file has complete reviewer loop instructions that match design.md Interface 1-4
- **Done when:** specify.md contains executable reviewer loop instructions

#### Task 2.2: Update design.md with reviewer loop
- **Depends on:** Task 2.1 (use as template)
- **Files:** `commands/design.md`
- **Do:** Same pattern as Task 2.1, adapted for:
  - Previous=spec.md, Current=design.md
  - Next="Plan needs: Components defined, interfaces specified, dependencies identified, risks noted"
- **Test:** Command file has complete reviewer loop instructions
- **Done when:** design.md contains executable reviewer loop instructions

#### Task 2.3: Update create-plan.md with reviewer loop
- **Depends on:** Task 2.1 (use as template)
- **Files:** `commands/create-plan.md`
- **Do:** Same pattern as Task 2.1, adapted for:
  - Previous=design.md, Current=plan.md
  - Next="Tasks needs: Ordered steps with dependencies, all design items covered, clear sequencing"
- **Test:** Command file has complete reviewer loop instructions
- **Done when:** create-plan.md contains executable reviewer loop instructions

#### Task 2.4: Update create-tasks.md with reviewer loop
- **Depends on:** Task 2.1 (use as template)
- **Files:** `commands/create-tasks.md`
- **Do:** Same pattern as Task 2.1, adapted for:
  - Previous=plan.md, Current=tasks.md
  - Next="Implement needs: Small actionable tasks (<15 min each), clear acceptance criteria per task"
- **Test:** Command file has complete reviewer loop instructions
- **Done when:** create-tasks.md contains executable reviewer loop instructions

#### Task 2.5: Update implement.md with reviewer loop
- **Depends on:** Task 2.1 (use as template)
- **Files:** `commands/implement.md`
- **Do:** Same pattern as Task 2.1, adapted for:
  - Previous=tasks.md, Current=code changes
  - Next="Verify needs: All tasks addressed, tests exist/pass, no obvious issues"
- **Test:** Command file has complete reviewer loop instructions
- **Done when:** implement.md contains executable reviewer loop instructions

---

### Phase 3: Worktree Auto-Creation

#### Task 3.1: Update create-feature.md with worktree creation
- **Depends on:** None (independent of Phase 2)
- **Files:** `commands/create-feature.md`
- **Do:**
  1. Add worktree creation section after feature folder creation
  2. Add mode-based decision logic:
     - Hotfix: Skip, set `"worktree": null`
     - Quick: Ask user, create if confirmed
     - Standard/Full: Auto-create
  3. Add explicit bash commands from design.md
  4. Add success/failure handling with .meta.json update
- **Test:** Command includes complete worktree creation instructions with mode branching
- **Done when:** create-feature.md contains executable worktree creation instructions

#### Task 3.2: Update brainstorming SKILL.md with worktree in promotion
- **Depends on:** Task 3.1 (use as template)
- **Files:** `skills/brainstorming/SKILL.md`
- **Do:**
  1. Find promotion flow section (where brainstorm becomes feature)
  2. Add same worktree creation logic as Task 3.1
  3. Ensure mode-based decision matches create-feature.md
- **Test:** Skill includes worktree creation in promotion flow
- **Done when:** brainstorming/SKILL.md contains executable worktree creation in promotion

---

### Phase 4: Verification

#### Task 4.1: Manual test reviewer loop
- **Depends on:** Tasks 2.1-2.5
- **Files:** None (testing)
- **Do:**
  1. Create a test feature in Quick mode
  2. Run `/specify` and verify reviewer spawns
  3. Run `/specify --no-review` on another feature and verify reviewer skipped
- **Test:** Reviewer spawns when expected, skips when flagged
- **Done when:** Both scenarios work correctly

#### Task 4.2: Manual test worktree creation
- **Depends on:** Tasks 3.1-3.2
- **Files:** None (testing)
- **Do:**
  1. Run `/create-feature` in Standard mode, verify worktree created
  2. Run `/create-feature` in Hotfix mode, verify worktree skipped
  3. Run `/create-feature` in Quick mode, verify user is prompted
- **Test:** Worktree behavior matches mode expectations
- **Done when:** All three mode scenarios work correctly

---

## Summary

- Total tasks: 9
- Phase 1: 1 task (foundation)
- Phase 2: 5 tasks (reviewer loop)
- Phase 3: 2 tasks (worktree)
- Phase 4: 2 tasks (verification)

## Implementation Notes

- Tasks 2.2-2.5 can reference Task 2.1 as a template
- Tasks 3.1 and 3.2 can be done in parallel with Phase 2
- Phase 4 requires a clean test environment
