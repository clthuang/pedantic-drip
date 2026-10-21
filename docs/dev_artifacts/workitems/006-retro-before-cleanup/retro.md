# Retrospective: 006-retro-before-cleanup

**Date:** 2026-01-30
**Status:** Completed
**Mode:** Full

## Summary

Migrated from worktree-based to branch-based feature development and reordered the `/finish` command to run retrospective before cleanup.

## What Changed

- Removed all worktree support (17 files changed)
- All modes now create feature branches
- Retrospective runs before branch deletion
- Deleted `skills/using-git-worktrees/SKILL.md`
- Updated CLAUDE.md with key principles

## Learnings Captured

### 1. Design Around Claude Code cwd Limitation

**Context:** Git worktrees were originally chosen for feature isolation, but `cd` commands don't persist in Claude Code - the cwd resets after each shell command.

**Insight:** Instead of fighting this limitation or adding workarounds, design the workflow around it. Branches work in a single directory and don't require cwd changes.

**Principle:** When a tool has constraints, adapt the design rather than adding complexity to work around it.

### 2. No Backward Compatibility for Private Tooling

**Context:** Initial implementation included backward compatibility code to support legacy `worktree` fields in `.meta.json`.

**Insight:** This is private tooling with no external users. Maintaining backward compatibility adds complexity for zero benefit.

**Principle:** For private/personal tooling, delete old code rather than maintaining compatibility shims. Added to CLAUDE.md as a key principle.

## Commits

- `feat: migrate from worktree-based to branch-based development`
- `chore: remove backward compatibility, update CLAUDE.md`
- `chore: update feature .meta.json to use branch field`
