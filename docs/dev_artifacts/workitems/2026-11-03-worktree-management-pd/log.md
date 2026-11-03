<!-- Append-only history of 2026-11-03-worktree-management-pd. Entry shapes: plugins/pd/references/log-entries.md. Example:
## 2026-10-14 09:12+08:00 decision
Q: criteria signed off?
A (user, verbatim): "Yes."
-->

## 2026-11-03 11:02+08:00 note
Request (verbatim):
> Investigate and design worktree management in pd
Round request (user, 2026-11-03, verbatim):
> proceed to investigate, design and plan for three open backlog items in this round

## 2026-11-03 11:02+08:00 phase triage -> specify
Reason: standard: no module owns worktrees today (implement-tasks, the merger and finishing-branch each touch them), and the criteria need investigation before they can be stated.

## 2026-11-03 11:08+08:00 decision
Q: worktree management in pd: which problems should this work item solve? (Clarify: the right problem, and what success looks like)
A (user, verbatim): "One cleanup script (Recommended), Show leftovers in pd-status (Recommended)"
Not chosen: removing worktrees inside the workflow; tidying this repo's `.pd-worktrees/` remnant.

## 2026-11-03 11:19+08:00 review calvin cycle 1 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/calvin-cycle-1.md. Verdict: 7 blockers, 9 warnings, 10 notes; all 26 answered and `## Requirements` rewritten (sections `pd-worktrees` and Callers added).
- R1 blocker shape.md:59 — the wrong-test move and the no-branch-delete rule; the script never deletes task branches, its callers do (wrong-test `-D` after it).
- R2 blocker shape.md:76 — the wrong-test move's per-task scope; `--task <n>` added (B8).
- R3 blocker shape.md:62 — a dirty worktree at the wrong-test move; exit 1, the user keeps or discards, and only the conductor forces on "discard".
- R4 blocker shape.md:78 — Finish's PR path deletes `workitem/<id>` first (`finishing-branch/SKILL.md:30`, checked); a work item is its directory now, not its branch (B10).
- R5 blocker shape.md:40 — strays can't be tied to one work item; they are repository-wide, deleted with `-d` only.
- R6 blocker shape.md:100 — strays need no ancestry check now, so `pd-status` keeps two git calls.
- R7 blocker shape.md:99 — a gone worktree is cleared by its path: `git worktree remove <gone path>` clears that entry only (scratch repo, git 2.54.0, 2026-11-03), B5.
To the user: none (row 26, why a shared script, is answered from the owner's Clarify ruling and the "Done means" line).
To the conductor (wording or consistency, each answered by a revision):
- rows 8, 15: the fixer's own forced removal stays (non-goal); strays deleted with `-d`.
- rows 9, 10, 11, 12, 14: the Callers section: exit 1 and exit 2 handling, Execute after every run end, all of `<id>`'s worktrees, the exit-code rule.
- rows 13, 18, 19, 25: five worktree states, dead-session locks, a task worktree defined by its branch wherever it lives, the main checkout case (B13).
- rows 16, 17, 20, 21, 22, 23, 24: any `## Now` line counts (B9), stale lines are a non-goal, the `no work item` reason, B14's line format and order, every session-start source (B16), `pd-status`'s docstring in scope, the Claude Code page sections named.
