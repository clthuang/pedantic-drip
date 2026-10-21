# Brainstorm: Workflow Improvements - Branch-Based Development & Retro Ordering

**Date:** 2026-01-30
**Topic:** Migrate from worktree-based to branch-based development + fix retro ordering

---

## Part 1: Migrate from Worktrees to Branches

### Problem

Git worktrees were chosen for feature isolation, but they cause friction with Claude Code:
- **cwd doesn't persist** - `cd` to worktree resets after each command
- **Docs sync issues** - feature docs need to exist in both main and worktree
- **Context loss** - switching directories loses Claude session context
- **Cognitive overhead** - tracking which directory has what

Research findings (2025-2026 best practices):
- Worktrees are for **parallel work** (multiple things simultaneously)
- Branches are for **sequential work** (one thing at a time)
- The plugin workflow is sequential: brainstorm → specify → ... → finish
- Parallel AI agent work requires separate terminals anyway

### Solution

Remove worktree support entirely. Use git branches for feature isolation.

**Benefits:**
- Single directory - Claude Code just works
- No cwd switching issues
- Simpler mental model
- All tools work in same cwd
- Less disk space

**Trade-offs accepted:**
- Can't run parallel tests/builds in different features (rare need)
- Must commit/stash to switch features (acceptable)

### Decisions

1. **Complete removal vs optional?** → Complete removal. Simplicity wins.
2. **Migration path for existing worktrees?** → Document manual cleanup steps.
3. **Branch naming convention?** → Keep `feature/{id}-{slug}` pattern.

---

## Part 2: Retrospective Before Cleanup

### Problem

Current `/finish` command suggests retrospective AFTER:
- Merging/PR creation
- Branch deletion

By then, you've lost:
- Easy access to diff against main
- Context for reflection

### Solution

Move retrospective to happen BEFORE cleanup, and make it required.

### Decisions

1. **Required vs Offered?** → Required, automatic. User chooses what learnings to keep.
2. **Before or After Merge?** → After merge decision, before branch deletion.
3. **"Keep Branch" Option?** → Keep it, no retro (feature not done yet).

---

## Combined Flow

### Feature Creation
```
/create-feature "description"
├── Create docs/features/{id}-{slug}/
├── git checkout -b feature/{id}-{slug}
├── Store in .meta.json: "branch": "feature/{id}-{slug}"
└── Continue to /specify
```

### Session Start Hook
```
SessionStart
├── Detect active feature from docs/features/
├── Get expected branch from .meta.json
├── Check: git branch --show-current
├── If mismatch:
│   "You're on '{current}', feature uses '{expected}'.
│    Run: git checkout {expected}"
└── Show phase and next command
```

### Feature Completion
```
/finish
├── Pre-completion checks
├── Completion choice: PR / Merge / Keep / Discard
│
├── If "Keep": exit early (no retro, no cleanup)
│
├── Execute choice (merge/PR/abandon)
├── RETROSPECTIVE (required, automatic)
│   └── User selects which learnings to keep
├── Commit retro artifacts
├── Update .meta.json status
└── git branch -d feature/{id}-{slug}
```

---

## Files to Change

### DELETE
- `skills/using-git-worktrees/SKILL.md`

### MAJOR REWRITE
- `commands/create-feature.md` - branch creation instead of worktree
- `commands/finish.md` - retro before cleanup, branch deletion
- `skills/brainstorming/SKILL.md` - branch creation in promotion
- `hooks/session-start.sh` - branch check instead of worktree check

### MODERATE UPDATES
- `commands/show-status.md` - branch detection
- `commands/list-features.md` - branch info instead of worktree
- `commands/verify.md` - branch check
- `commands/implement.md` - branch check
- `commands/specify.md` - branch check
- `commands/design.md` - branch check
- `commands/create-plan.md` - branch check
- `commands/create-tasks.md` - branch check
- `skills/finishing-branch/SKILL.md` - remove worktree cleanup
- `skills/workflow-state/SKILL.md` - schema change

### MINOR UPDATES
- `README.md` - update documentation
- `hooks/pre-commit-guard.sh` - verify/update if needed

---

## Scope

Large - 1 deletion, 4 major rewrites, 10 moderate updates, 2+ minor updates.
This is a foundational change that simplifies the entire workflow.
