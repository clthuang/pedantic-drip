# Implementation Plan: Branch-Based Development & Retro Before Cleanup

## Overview

This plan sequences the implementation of the worktree-to-branch migration and retro reordering changes. The order is designed to:
1. Minimize breaking changes during transition
2. Enable parallel work where possible
3. Maintain backward compatibility throughout

---

## Phase 1: Foundation (Sequential)

These must be done first as other changes depend on them.

### Step 1.1: Update Session-Start Hook

**File:** `hooks/session-start.sh`

**Changes:**
1. Replace `check_worktree_mismatch()` with `check_branch_mismatch()`
2. Update `parse_feature_meta()` to extract `branch` (with worktree fallback)
3. Update `build_context()` warning message

**Why first:** Hook runs on every session start. It must handle both old (worktree) and new (branch) schemas during migration.

**Estimated scope:** ~40 lines changed

---

### Step 1.2: Update Workflow State Skill Schema

**File:** `skills/workflow-state/SKILL.md`

**Changes:**
1. Update schema example to use `branch` instead of `worktree`
2. Document backward compatibility approach

**Why second:** This documents the new schema that other files will follow.

**Estimated scope:** ~10 lines changed

---

## Phase 2: Feature Creation (Sequential)

These change how new features are created.

### Step 2.1: Update /create-feature Command

**File:** `commands/create-feature.md`

**Changes:**
1. Remove all worktree creation logic (lines ~68-88)
2. Replace with simple branch creation: `git checkout -b feature/{id}-{slug}`
3. Update .meta.json creation to use `branch` field
4. Remove mode-based worktree decisions (all modes now use branches)

**Estimated scope:** ~50 lines removed, ~15 lines added

---

### Step 2.2: Update Brainstorming Skill Promotion Flow

**File:** `skills/brainstorming/SKILL.md`

**Changes:**
1. Remove worktree creation steps (lines ~89-114)
2. Replace with branch creation
3. Simplify mode explanation (mode no longer affects isolation)

**Estimated scope:** ~40 lines removed, ~15 lines added

---

## Phase 3: Phase Commands (Parallel)

These can be done in parallel as they're independent.

### Step 3.1: Update /specify Command

**File:** `commands/specify.md`

**Changes:**
1. Replace section "1b. Check Worktree Location" with "1b. Check Branch"
2. Update warning message format

**Estimated scope:** ~15 lines changed

---

### Step 3.2: Update /design Command

**File:** `commands/design.md`

**Changes:** Same as 3.1

**Estimated scope:** ~15 lines changed

---

### Step 3.3: Update /create-plan Command

**File:** `commands/create-plan.md`

**Changes:** Same as 3.1 (if worktree check exists)

**Estimated scope:** ~15 lines changed

---

### Step 3.4: Update /create-tasks Command

**File:** `commands/create-tasks.md`

**Changes:** Same as 3.1 (if worktree check exists)

**Estimated scope:** ~15 lines changed

---

### Step 3.5: Update /implement Command

**File:** `commands/implement.md`

**Changes:** Same as 3.1

**Estimated scope:** ~15 lines changed

---

### Step 3.6: Update /verify Command

**File:** `commands/verify.md`

**Changes:** Same as 3.1

**Estimated scope:** ~15 lines changed

---

## Phase 4: Listing Commands (Parallel with Phase 3)

### Step 4.1: Update /show-status Command

**File:** `commands/show-status.md`

**Changes:**
1. Update feature detection logic: branch name instead of worktree
2. Change "If in worktree" to "If on feature branch"
3. Add branch name parsing regex

**Estimated scope:** ~10 lines changed

---

### Step 4.2: Update /list-features Command

**File:** `commands/list-features.md`

**Changes:**
1. Change column header: "Worktree" → "Branch"
2. Update data source to read `branch` from .meta.json
3. Update example output

**Estimated scope:** ~10 lines changed

---

## Phase 5: Completion Flow (Sequential)

### Step 5.1: Update /finish Command

**File:** `commands/finish.md`

**Changes:**
1. Reorder sections: move retrospective before cleanup
2. Make retrospective required (remove "suggest" language)
3. Replace worktree cleanup with branch cleanup
4. Add "commit retro artifacts" step
5. Update "Keep branch" to exit early (no retro)

**Estimated scope:** ~40 lines reordered/changed

---

### Step 5.2: Update Finishing Branch Skill

**File:** `skills/finishing-branch/SKILL.md`

**Changes:**
1. Remove worktree cleanup step
2. Keep branch deletion commands
3. Update quick reference table

**Estimated scope:** ~10 lines changed

---

## Phase 6: Cleanup (Sequential, Last)

### Step 6.1: Delete Worktree Skill

**File:** `skills/using-git-worktrees/SKILL.md`

**Action:** Delete entire file

**Estimated scope:** -102 lines (file deletion)

---

### Step 6.2: Update README

**File:** `README.md`

**Changes:**
1. Line ~64: "Create git worktree" → "Create feature branch"
2. Line ~105: "cleanup worktree" → "cleanup branch"
3. Line ~162: Update command table
4. Line ~206: Remove worktree skill reference

**Estimated scope:** ~5 lines changed

---

### Step 6.3: Optional - Update Pre-commit Guard Comment

**File:** `hooks/pre-commit-guard.sh`

**Changes:** Update comment "worktree-aware" to "directory-context-aware" (optional clarity)

**Estimated scope:** 1 line changed (optional)

---

## Implementation Order Summary

```
Phase 1: Foundation (must be first)
├── 1.1 hooks/session-start.sh
└── 1.2 skills/workflow-state/SKILL.md

Phase 2: Feature Creation
├── 2.1 commands/create-feature.md
└── 2.2 skills/brainstorming/SKILL.md

Phase 3: Phase Commands (parallel)          Phase 4: Listing (parallel)
├── 3.1 commands/specify.md                 ├── 4.1 commands/show-status.md
├── 3.2 commands/design.md                  └── 4.2 commands/list-features.md
├── 3.3 commands/create-plan.md
├── 3.4 commands/create-tasks.md
├── 3.5 commands/implement.md
└── 3.6 commands/verify.md

Phase 5: Completion Flow
├── 5.1 commands/finish.md
└── 5.2 skills/finishing-branch/SKILL.md

Phase 6: Cleanup (must be last)
├── 6.1 DELETE skills/using-git-worktrees/SKILL.md
├── 6.2 README.md
└── 6.3 hooks/pre-commit-guard.sh (optional)
```

---

## Dependency Graph

```
                    ┌─────────┐
                    │  1.1    │ session-start.sh
                    │  1.2    │ workflow-state schema
                    └────┬────┘
                         │
              ┌──────────┴──────────┐
              │                     │
         ┌────▼────┐           ┌────▼────┐
         │  2.1    │           │  2.2    │
         │ create- │           │ brain-  │
         │ feature │           │ storm   │
         └────┬────┘           └────┬────┘
              │                     │
              └──────────┬──────────┘
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
┌───▼───┐           ┌────▼────┐          ┌────▼────┐
│ 3.1-6 │           │  4.1-2  │          │  5.1-2  │
│ phase │           │ listing │          │ finish  │
│ cmds  │           │ cmds    │          │ flow    │
└───┬───┘           └────┬────┘          └────┬────┘
    │                    │                    │
    └────────────────────┼────────────────────┘
                         │
                    ┌────▼────┐
                    │  6.1-3  │
                    │ cleanup │
                    └─────────┘
```

---

## Verification Checkpoints

### After Phase 1
- [ ] New session starts without errors
- [ ] Hook correctly reads `branch` from .meta.json
- [ ] Hook falls back to extracting branch from `worktree` field
- [ ] Warning message shows branch mismatch (not worktree)

### After Phase 2
- [ ] `/create-feature` creates branch, not worktree
- [ ] Brainstorm promotion creates branch
- [ ] New .meta.json files have `branch` field, not `worktree`

### After Phases 3-4
- [ ] All phase commands check branch, not worktree
- [ ] `/show-status` detects feature from branch name
- [ ] `/list-features` shows branch column

### After Phase 5
- [ ] `/finish` runs retrospective before cleanup
- [ ] "Keep branch" exits early without retro
- [ ] Branch is deleted after merge/discard

### After Phase 6
- [ ] No worktree references remain in codebase
- [ ] README reflects branch-based workflow

---

## Rollback Plan

If issues arise during migration:

1. **Partial rollback:** Revert specific file changes via git
2. **Full rollback:** `git revert` the entire feature branch
3. **Existing worktrees:** Still functional - hook has backward compatibility

The backward compatibility in the hook (reading `worktree` and extracting branch) means existing features continue to work during and after migration.

---

## Estimated Total Scope

| Category | Lines Changed |
|----------|---------------|
| Lines removed | ~200 |
| Lines added | ~100 |
| Lines modified | ~80 |
| Files modified | 16 |
| Files deleted | 1 |

Net reduction: ~100 lines (simplification achieved)
