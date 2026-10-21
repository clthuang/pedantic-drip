# Tasks: Branch-Based Development & Retro Before Cleanup

## Task Overview

17 files across 6 phases. Tasks are ordered by dependency.

---

## Phase 1: Foundation

### Task 1.1: Update session-start hook for branch detection
- [ ] **File:** `hooks/session-start.sh`
- [ ] Replace `check_worktree_mismatch()` with `check_branch_mismatch()`
- [ ] Update `parse_feature_meta()` to read `branch` field (with worktree fallback)
- [ ] Update `build_context()` warning message to show branch mismatch
- [ ] Test: Start new session, verify hook reads branch correctly
- [ ] Test: Verify backward compatibility with existing worktree field

**Blocked by:** None
**Blocks:** All subsequent tasks

---

### Task 1.2: Update workflow-state skill schema
- [ ] **File:** `skills/workflow-state/SKILL.md`
- [ ] Change schema example: `"worktree"` → `"branch"`
- [ ] Add note about backward compatibility

**Blocked by:** None
**Blocks:** Tasks 2.1, 2.2

---

## Phase 2: Feature Creation

### Task 2.1: Update /create-feature command
- [ ] **File:** `commands/create-feature.md`
- [ ] Remove "Worktree Creation Steps" section (lines ~68-88)
- [ ] Remove mode-based worktree logic (Hotfix/Quick/Standard/Full handling)
- [ ] Add simple branch creation: `git checkout -b feature/{id}-{slug}`
- [ ] Update .meta.json example to use `"branch"` field
- [ ] Update output message to mention branch, not worktree

**Blocked by:** Task 1.2
**Blocks:** Tasks 3.x, 4.x, 5.x

---

### Task 2.2: Update brainstorming skill promotion flow
- [ ] **File:** `skills/brainstorming/SKILL.md`
- [ ] Remove "Worktree Creation Steps" section (lines ~89-114)
- [ ] Remove mode-based worktree decisions in promotion flow
- [ ] Add branch creation: `git checkout -b feature/{id}-{slug}`
- [ ] Update .meta.json example in promotion to use `"branch"` field
- [ ] Simplify mode explanation (affects iterations, not isolation)

**Blocked by:** Task 1.2
**Blocks:** Tasks 3.x, 4.x, 5.x

---

## Phase 3: Phase Commands

*These 6 tasks can be done in parallel after Phase 2 is complete.*

### Task 3.1: Update /specify command branch check
- [ ] **File:** `commands/specify.md`
- [ ] Replace "1b. Check Worktree Location" section with "1b. Check Branch"
- [ ] Update warning message format to mention branch

**Blocked by:** Tasks 2.1, 2.2
**Blocks:** Task 6.x

---

### Task 3.2: Update /design command branch check
- [ ] **File:** `commands/design.md`
- [ ] Replace "1b. Check Worktree Location" section with "1b. Check Branch"
- [ ] Update warning message format to mention branch

**Blocked by:** Tasks 2.1, 2.2
**Blocks:** Task 6.x

---

### Task 3.3: Update /create-plan command branch check
- [ ] **File:** `commands/create-plan.md`
- [ ] Check if "1b. Check Worktree Location" section exists
- [ ] If exists: Replace with "1b. Check Branch"
- [ ] If not: Skip (no changes needed)

**Blocked by:** Tasks 2.1, 2.2
**Blocks:** Task 6.x

---

### Task 3.4: Update /create-tasks command branch check
- [ ] **File:** `commands/create-tasks.md`
- [ ] Check if "1b. Check Worktree Location" section exists
- [ ] If exists: Replace with "1b. Check Branch"
- [ ] If not: Skip (no changes needed)

**Blocked by:** Tasks 2.1, 2.2
**Blocks:** Task 6.x

---

### Task 3.5: Update /implement command branch check
- [ ] **File:** `commands/implement.md`
- [ ] Replace "1b. Check Worktree Location" section with "1b. Check Branch"
- [ ] Update warning message format to mention branch

**Blocked by:** Tasks 2.1, 2.2
**Blocks:** Task 6.x

---

### Task 3.6: Update /verify command branch check
- [ ] **File:** `commands/verify.md`
- [ ] Replace "1b. Check Worktree Location" section with "1b. Check Branch"
- [ ] Update warning message format to mention branch

**Blocked by:** Tasks 2.1, 2.2
**Blocks:** Task 6.x

---

## Phase 4: Listing Commands

*These 2 tasks can be done in parallel with Phase 3.*

### Task 4.1: Update /show-status command
- [ ] **File:** `commands/show-status.md`
- [ ] Change "If in worktree" to "If on feature branch"
- [ ] Add branch name parsing: `feature/{id}-{slug}` pattern
- [ ] Update example output if present

**Blocked by:** Tasks 2.1, 2.2
**Blocks:** Task 6.x

---

### Task 4.2: Update /list-features command
- [ ] **File:** `commands/list-features.md`
- [ ] Change column header: "Worktree" → "Branch"
- [ ] Update example output table
- [ ] Change hint from `cd {worktree}` to `git checkout {branch}`

**Blocked by:** Tasks 2.1, 2.2
**Blocks:** Task 6.x

---

## Phase 5: Completion Flow

### Task 5.1: Update /finish command with retro reordering
- [ ] **File:** `commands/finish.md`
- [ ] Move "Suggest Retrospective" section up, before "Worktree Cleanup"
- [ ] Rename to "Run Retrospective" (required, not suggested)
- [ ] Add "Commit retro artifacts" step after retrospective
- [ ] Replace "Worktree Cleanup" with "Branch Cleanup"
- [ ] Update "Keep branch" option to exit early (no retro, no cleanup)
- [ ] Remove worktree-specific commands

**Blocked by:** Tasks 2.1, 2.2
**Blocks:** Task 6.x

---

### Task 5.2: Update finishing-branch skill
- [ ] **File:** `skills/finishing-branch/SKILL.md`
- [ ] Remove "Step 4: Cleanup Worktree" section
- [ ] Keep branch deletion commands (`git branch -d/-D`)
- [ ] Update Quick Reference table (remove "Keep Worktree" column)

**Blocked by:** Tasks 2.1, 2.2
**Blocks:** Task 6.x

---

## Phase 6: Cleanup

### Task 6.1: Delete worktree skill
- [ ] **File:** `skills/using-git-worktrees/SKILL.md`
- [ ] Delete entire file
- [ ] Verify no broken references

**Blocked by:** All Phase 3, 4, 5 tasks
**Blocks:** None

---

### Task 6.2: Update README
- [ ] **File:** `README.md`
- [ ] Line ~64: "Create git worktree" → "Create feature branch"
- [ ] Line ~105: "cleanup worktree" → "cleanup branch"
- [ ] Line ~162: Update command table description
- [ ] Line ~206: Remove `using-git-worktrees` skill reference

**Blocked by:** Task 6.1
**Blocks:** None

---

### Task 6.3: (Optional) Update pre-commit guard comment
- [ ] **File:** `hooks/pre-commit-guard.sh`
- [ ] Line ~110: Change comment "worktree-aware" to "directory-context-aware"
- [ ] Optional - skip if not worth the commit

**Blocked by:** None
**Blocks:** None

---

## Verification Tasks

### Task V1: Verify Phase 1 complete
- [ ] Start new Claude session
- [ ] Confirm hook reads `branch` from .meta.json
- [ ] Confirm hook falls back to worktree extraction
- [ ] Confirm warning shows branch (not worktree) mismatch

### Task V2: Verify Phase 2 complete
- [ ] Run `/create-feature "test"`
- [ ] Confirm branch created (not worktree)
- [ ] Confirm .meta.json has `branch` field
- [ ] Delete test feature

### Task V3: Verify Phases 3-4 complete
- [ ] Run a phase command (e.g., `/specify`)
- [ ] Confirm branch check warning format
- [ ] Run `/list-features`
- [ ] Confirm Branch column (not Worktree)

### Task V4: Verify Phase 5 complete
- [ ] Check `/finish` command structure
- [ ] Confirm retro section before cleanup
- [ ] Confirm "Keep branch" exits early

### Task V5: Verify Phase 6 complete
- [ ] `grep -r "worktree" commands/ skills/ hooks/` returns no matches
- [ ] README reflects branch-based workflow

---

## Summary

| Phase | Tasks | Can Parallelize |
|-------|-------|-----------------|
| 1 | 1.1, 1.2 | No |
| 2 | 2.1, 2.2 | No |
| 3 | 3.1-3.6 | Yes (6 tasks) |
| 4 | 4.1, 4.2 | Yes (with Phase 3) |
| 5 | 5.1, 5.2 | No |
| 6 | 6.1-6.3 | No |
| V | V1-V5 | After each phase |

**Total:** 17 implementation tasks + 5 verification tasks
