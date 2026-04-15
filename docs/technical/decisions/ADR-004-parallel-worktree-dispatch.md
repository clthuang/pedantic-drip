---
last-updated: 2026-04-15T00:00:00Z
source-feature: 078-cc-native-integration
status: Accepted
---
# ADR-004: Parallel Worktree Dispatch for Implementing Skill

## Status
Accepted

## Context
The implementing skill dispatched tasks serially — one implementer agent at a time. This left significant wall-clock time on the table for features with many independent tasks. CC provides an `isolation: worktree` parameter on Agent/Task calls, but it is silently ignored for plugin-defined `subagent_type` values (CC Issue #33045). pd's `pd:implementer` is plugin-defined, making the built-in isolation unusable. Feature 078 adds parallel execution as a core capability improvement while working around the CC bug.

## Decision
Replace the serial Step 2 dispatch loop in `implementing/SKILL.md` with a three-phase manual worktree dispatch model:

1. **Worktree setup** — create git worktrees under `.pd-worktrees/` on branches named `worktree-{feature_id}-task-{N}` before dispatching agents.
2. **Parallel agent dispatch** — dispatch up to `max_concurrent_agents` implementer agents simultaneously, each receiving absolute-path directives restricting file operations to its worktree.
3. **SHA validation + sequential merge + cleanup** — verify no out-of-worktree commits occurred, merge each worktree branch into the feature branch in task order, then remove the worktree.

## Alternatives Considered
- **Use `isolation: worktree` inline** — silently ignored for plugin-defined subagent types (CC #33045); not viable until upstream fix.
- **Remain serial** — no parallelism benefit; acceptable only as full fallback when worktrees fail.
- **Per-worktree DB copies** — would eliminate SQLite contention entirely but adds significant setup complexity and diverges entity state until merge; not worth it given WAL + `busy_timeout=15s` handles typical contention.

## Consequences
- Significant reduction in wall-clock time for multi-task features when tasks are independent.
- Adds ~150–200 lines to `implementing/SKILL.md` for worktree orchestration, merge, validation, and fallback logic. When CC fixes #33045, ~120 of those lines become removable.
- Merge conflicts halt the workflow; the user resolves manually and re-runs `/pd:implement` to resume.
- `.pd-worktrees/` must be added to `.gitignore`; the skill handles this during Phase 1.

## References
- CC Issue #33045 — `isolation: worktree` silently ignored for plugin agents
- `plugins/pd/skills/implementing/SKILL.md` Step 2
- Feature 078 design.md TD-1
