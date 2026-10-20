# Specification: Branch-Based Development & Retro Before Cleanup

## Problem Statement

Two related workflow issues require addressing:

1. **Worktree friction with Claude Code**: Git worktrees were chosen for feature isolation, but they cause significant friction:
   - Claude Code's cwd doesn't persist after `cd` commands
   - Feature docs must be synced between main repo and worktree
   - Directory switching loses Claude session context
   - Cognitive overhead tracking which directory contains what

2. **Retrospective timing**: The `/finish` command suggests running retrospective AFTER branch deletion, when context is lost and diffs against main are harder to review.

## Goals

1. Remove worktree support entirely - use branches for feature isolation
2. Move retrospective to happen before branch cleanup (while context exists)
3. Make retrospective required for completed features
4. Simplify the overall workflow

## Non-Goals

- Supporting parallel worktrees as an optional mode
- Automatic migration of existing worktrees
- Changing the branch naming convention

## Requirements

### Part 1: Branch-Based Development

#### R1: Remove Worktree Creation

The `/create-feature` command MUST NOT create worktrees. Instead:

```
/create-feature "description"
├── Determine feature ID (highest in docs/features/ + 1)
├── Create slug from description
├── Create folder: docs/features/{id}-{slug}/
├── Create branch: git checkout -b feature/{id}-{slug}
├── Create .meta.json with branch reference
└── Continue to /specify
```

#### R2: Updated .meta.json Schema

The `worktree` field MUST be replaced with `branch`:

**Before:**
```json
{
  "id": "006",
  "name": "retro-before-cleanup",
  "mode": "full",
  "worktree": "../my-ai-setup-006-retro-before-cleanup"
}
```

**After:**
```json
{
  "id": "006",
  "name": "retro-before-cleanup",
  "mode": "full",
  "branch": "feature/006-retro-before-cleanup"
}
```

#### R3: Branch Check Instead of Worktree Check

All commands that currently check worktree location MUST instead check branch:

**Current pattern (remove):**
```
If feature has a worktree defined in .meta.json:
- Compare current working directory against worktree path
- If mismatch: warn user
```

**New pattern:**
```
If feature has a branch defined in .meta.json:
- Get current branch: git branch --show-current
- If current branch != expected branch:
  "You're on '{current}', feature uses '{expected}'.
   Run: git checkout {expected}"
```

Commands requiring this update:
- `/verify`
- `/implement`
- `/specify`
- `/design`
- `/create-plan`
- `/create-tasks`

#### R4: Session Start Hook Branch Check

The session-start hook MUST check branch instead of worktree:

```bash
# Get expected branch from .meta.json
expected_branch=$(jq -r '.branch // empty' "$meta_file")

# Get current branch
current_branch=$(git branch --show-current)

# Compare
if [[ -n "$expected_branch" && "$current_branch" != "$expected_branch" ]]; then
  # Warn user
  echo "You're on '$current_branch', feature uses '$expected_branch'."
  echo "Run: git checkout $expected_branch"
fi
```

#### R5: Show Status Branch Detection

`/show-status` MUST detect feature from branch name:

**Current:** "If in worktree: Extract feature ID from branch name"
**New:** "If on feature branch: Extract feature ID from branch name pattern `feature/{id}-{slug}`"

#### R6: List Features Without Worktree Column

`/list-features` MUST show branch info instead of worktree paths:

```
Active Features:

ID   Name              Phase        Branch                           Last Activity
───  ────              ─────        ──────                           ─────────────
006  retro-cleanup     design       feature/006-retro-cleanup        30 min ago
005  make-specs-exec   implement    feature/005-make-specs-exec      2 hours ago

Commands:
  /show-status {id}        View feature details
  /create-feature          Start new feature
  git checkout {branch}    Switch to feature
```

#### R7: Delete Worktree Skill

The file `skills/using-git-worktrees/SKILL.md` MUST be deleted.

#### R8: Update Brainstorming Skill Promotion Flow

The promotion flow in `skills/brainstorming/SKILL.md` MUST create branches instead of worktrees:

**Remove:** All worktree creation logic and mode-based worktree decisions
**Add:** Simple branch creation for all modes:

```bash
git checkout -b feature/{id}-{slug}
```

Store in `.meta.json`: `"branch": "feature/{id}-{slug}"`

Mode no longer affects isolation strategy (all modes use branches).

#### R9: Update Finishing Branch Skill

`skills/finishing-branch/SKILL.md` MUST remove worktree cleanup:

**Remove:**
```bash
git worktree remove <worktree-path>
```

**Keep:**
```bash
git branch -d <feature-branch>  # after merge
git branch -D <feature-branch>  # for discard
```

### Part 2: Retrospective Before Cleanup

#### R10: Reorder /finish Command

The `/finish` command MUST run retrospective BEFORE branch deletion:

```
/finish
├── Pre-completion checks
│   ├── Check for uncommitted changes
│   ├── Check tasks completion
│   ├── Suggest quality review (Standard/Full)
│   └── Offer documentation review
│
├── Completion choice: PR / Merge / Keep / Discard
│
├── If "Keep": exit early (no changes, no retro)
│
├── Execute choice
│   ├── Option 1 (PR): git push, gh pr create
│   ├── Option 2 (Merge): git checkout main, git merge, git push
│   └── Option 4 (Discard): confirm, mark abandoned
│
├── RETROSPECTIVE (required for options 1, 2, 4)
│   ├── Invoke retrospecting skill
│   ├── User selects which learnings to keep
│   └── Save to docs/features/{id}-{slug}/retro.md
│
├── Commit retro artifacts (if on feature branch still)
│
├── Update .meta.json status
│   ├── completed: timestamp (for options 1, 2)
│   └── abandoned: timestamp (for option 4)
│
├── Delete .review-history.md
│
└── Branch cleanup
    ├── git branch -d feature/{id}-{slug}  # after merge
    └── git branch -D feature/{id}-{slug}  # for discard
```

#### R11: Retrospective is Required

- Retrospective MUST run automatically for terminal actions (PR, Merge, Discard)
- No "want to run retro?" prompt - it just happens
- User controls which learnings to keep during the retrospective
- Retro artifacts saved before branch deletion

#### R12: Keep Branch Skips Everything

The "Keep branch" option MUST exit early:
- No retrospective
- No status update
- No branch deletion
- User runs `/finish` again when ready

### Part 3: Documentation Updates

#### R13: Update README.md

All worktree references MUST be updated:
- Line ~64: "Create git worktree" → "Create feature branch"
- Line ~105: "cleanup worktree" → "cleanup branch"
- Line ~162: "Folder, worktree, mode selection" → "Folder, branch, mode selection"
- Line ~206: Remove or update `using-git-worktrees` skill reference

#### R14: Update Workflow State Skill

`skills/workflow-state/SKILL.md` schema example MUST use `branch` instead of `worktree`.

## Acceptance Criteria

### Branch Migration
- [ ] `/create-feature` creates branch, not worktree
- [ ] `.meta.json` uses `"branch"` field, not `"worktree"`
- [ ] Session-start hook checks branch, suggests `git checkout`
- [ ] All phase commands check branch instead of worktree
- [ ] `/list-features` shows branch column, not worktree
- [ ] `/show-status` detects feature from branch name
- [ ] `skills/using-git-worktrees/SKILL.md` deleted
- [ ] `skills/brainstorming/SKILL.md` creates branch in promotion
- [ ] `skills/finishing-branch/SKILL.md` has no worktree cleanup

### Retro Ordering
- [ ] `/finish` runs retrospective before branch deletion
- [ ] Retrospective is automatic (no "want to run?" prompt)
- [ ] "Keep branch" exits without retro or cleanup
- [ ] Retro artifacts committed before branch deletion
- [ ] `.meta.json` status updated after retro

### Documentation
- [ ] README.md updated with branch-based workflow
- [ ] No remaining worktree references in commands/skills

## Files to Modify

| Action | File | Description |
|--------|------|-------------|
| DELETE | `skills/using-git-worktrees/SKILL.md` | No longer needed |
| REWRITE | `commands/create-feature.md` | Branch creation, remove worktree |
| REWRITE | `commands/finish.md` | Retro before cleanup, branch deletion |
| REWRITE | `skills/brainstorming/SKILL.md` | Branch in promotion flow |
| REWRITE | `hooks/session-start.sh` | Branch check instead of worktree |
| UPDATE | `commands/show-status.md` | Branch detection |
| UPDATE | `commands/list-features.md` | Branch column |
| UPDATE | `commands/verify.md` | Branch check |
| UPDATE | `commands/implement.md` | Branch check |
| UPDATE | `commands/specify.md` | Branch check |
| UPDATE | `commands/design.md` | Branch check |
| UPDATE | `commands/create-plan.md` | Branch check |
| UPDATE | `commands/create-tasks.md` | Branch check |
| UPDATE | `skills/finishing-branch/SKILL.md` | Remove worktree cleanup |
| UPDATE | `skills/workflow-state/SKILL.md` | Schema change |
| UPDATE | `README.md` | Documentation |
| CHECK | `hooks/pre-commit-guard.sh` | Verify no worktree-specific logic |

## Migration Notes

For users with existing worktrees:

```bash
# 1. List existing worktrees
git worktree list

# 2. For each feature worktree, ensure changes are committed
cd ../my-ai-setup-{id}-{slug}
git status
git add -A && git commit -m "WIP: migration to branch-based workflow"

# 3. Return to main repo
cd ../my-ai-setup

# 4. Remove worktrees (keeps branches)
git worktree remove ../my-ai-setup-{id}-{slug}

# 5. Update .meta.json files
# Change "worktree": "..." to "branch": "feature/{id}-{slug}"
```

## Open Questions

None - all decisions made during brainstorming.
