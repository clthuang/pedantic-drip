---
last-updated: 2026-04-15T00:00:00Z
source-feature: 078-cc-native-integration
status: Accepted
---
# ADR-005: Two-Tier Fallback Strategy for Worktree Dispatch

## Status
Accepted

## Context
Parallel worktree dispatch (ADR-004) introduces several new failure modes: individual worktree creation failures, agents writing outside their assigned worktree, SQLite lock contention under concurrent writes, and merge conflicts. A consistent failure-handling strategy is needed to ensure the workflow degrades gracefully rather than halting entirely on minor failures.

## Decision
Apply a two-tier fallback strategy:

| Failure | Scope | Behavior |
|---------|-------|----------|
| `git worktree add` exits non-zero | Per-task | That task dispatches without worktree isolation; other tasks continue normally |
| Agent commits outside worktree (SHA mismatch in Phase 3) | Per-task | Halt and flag for manual review; do not merge the affected worktree branch |
| SQLite BUSY after `busy_timeout` (15s) exhausted | Full batch | All remaining tasks in current and future batches switch to serial dispatch |
| Merge conflict | Halt | Surface conflict details and recovery path; user resolves, then re-runs `/pd:implement` |

Per-task failures are contained to the failing task. Only SQLite exhaustion or merge conflicts escalate to broader fallback or halt.

## Alternatives Considered
- **Halt on any worktree failure** — too conservative; a single git failure would block all parallelism benefit.
- **Retry indefinitely on SQLite BUSY** — risks starvation loops; a bounded retry then serial fallback is safer.
- **Auto-resolve merge conflicts** — too risky; conflicts indicate divergent task changes that require human judgment.

## Consequences
- Workflow is resilient to intermittent worktree creation failures without sacrificing all parallel benefit.
- SQLite contention under high concurrency gracefully degrades to serial execution rather than failing.
- Merge conflict recovery requires a manual step (resolve + re-run), which is appropriate given the risk of data loss from auto-resolution.
- The per-task fallback creates a mixed environment (some tasks in worktrees, some not) within a single batch; this is acceptable since the merge sequence handles both cases identically.

## References
- ADR-004 — Parallel Worktree Dispatch for Implementing Skill
- Feature 078 design.md TD-2
- `database.py` — `busy_timeout=15000` default configuration
