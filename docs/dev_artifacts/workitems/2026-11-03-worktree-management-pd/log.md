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

## 2026-11-03 11:28+08:00 review calvin cycle 2 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/calvin-cycle-2.md. Verdict: 3 blockers, 10 warnings, 11 notes; cycle 1: 22 rows answered, 4 partly (3, 24, 25, 26), now answered. All 24 answered and `## Requirements` revised.
Closes: review@2026-11-03 11:19+08:00#R1, review@2026-11-03 11:19+08:00#R2, review@2026-11-03 11:19+08:00#R3, review@2026-11-03 11:19+08:00#R4, review@2026-11-03 11:19+08:00#R5, review@2026-11-03 11:19+08:00#R6, review@2026-11-03 11:19+08:00#R7
- R1 blocker shape.md:66 — abandon's work item directory lives only on its branch; abandon calls the script before switching off it, and a known work item now includes one with only branches.
- R2 blocker shape.md:42 — `-d` against `HEAD` keeps strays of an abandoned branch; a stray is deleted when another branch contains its tip (loses no commit), else kept and printed.
- R3 blocker shape.md:91 — a stray's line has no id; it prints `-`.
To the user: none.
To the conductor (wording or consistency, each answered by a revision):
- rows 4, 5, 6, 7, 8, 9, 10: Callers: Execute calls after the line is cleared; run-in-flight exit 1 stops for the user; only a kept worktree's branch stays, the rest goes on; after "discard" the caller goes on; the wrong-test move offers discard or stop, never keep-and-continue.
- rows 11, 12, 13, 15, 16, 17, 18: state precedence; the main checkout counts as a task worktree; exit 2 on a mid-way git failure with the lines printed so far; "removed" wording; strays only without `--task` (B8); another run's strays; strays come from any Workflow-tool agent.
- rows 14, 19, 20, 21: the gone-entry check cited (scratch repo, git 2.54.0); "done" excuses anything reported and kept; one line per leftover, a held branch not repeated; the dead-lock release quoted from the worktrees page.
- rows 22, 23, 24: only work items visible in this checkout are judged (B15); the section opens with what to run; the four docs that list scripts named (grep for `pd-review-filter`).

## 2026-11-03 11:34+08:00 review calvin cycle 3 — calvin-runner
Ledger: agent_sandbox/2026-11-03/2026-11-03-worktree-management-pd/calvin-cycle-3.md. Verdict: 2 blockers, 7 warnings, 13 notes; cycle 2: 21 rows answered, 3 partly (9, 13, 19), and cycle 1's row 26 open; all now answered. This is the third cycle: the cap.
Closes: review@2026-11-03 11:28+08:00#R1, review@2026-11-03 11:28+08:00#R2, review@2026-11-03 11:28+08:00#R3
- R1 blocker shape.md:41 — a task branch made its id known, so `no work item` could never apply; a known work item is now its directory in this checkout, and `no work item` also needs no `workitem/<id>` branch.
- R2 blocker shape.md:44 — two strays sharing a tip would vouch for each other; only a branch that isn't a stray counts (B19).
To the user: whether this revision ends the loop (the cap question).
To the conductor (each answered by the same revision):
- rows 3, 5, 21: the id must have its directory here; `pd-worktrees --strays [--remove]` clears strays with no work item; why every stray qualifies.
- rows 4, 10, 11, 19: B14's first line names both commands and "by hand" for other branches; the state shows in `pd-worktrees <id>`; the section is in the full report only.
- rows 6, 7: abandon calls only when the user accepts cleanup; its run-in-flight check finds nothing, a live run's worktree is `locked`.
- rows 8, 9, 22: any kept worktree of a re-run task stops the wrong-test move; Execute asks at step 5 and exit 2 stops before step 6.
- rows 12, 13, 14, 15: no question without a dirty one; a discarded worktree's branch is deleted; "unexpected" git failures defined; Done excepts anything reported kept.
- rows 16, 17, 18, 20: Goals say clean or gone and name strays; a main checkout on a task branch is a real leftover; the removal-site grep is cited in Why; cycle 1's row 26 answered by "What they cost".
- pd-status's branch call adds `workitem/*`, which the `no work item` rule needs.

## 2026-11-03 11:34+08:00 capped specify
Deferred: none
Follow-ups: none
Decisions:
- whether the revision answering cycle 3's blockers ends the calvin loop, or a fourth cycle runs: asked of the user.
Assumptions: none
Closes: review@2026-11-03 11:34+08:00#R1, review@2026-11-03 11:34+08:00#R2

## 2026-11-03 11:58+08:00 decision
Q: does the revision answering calvin cycle 3 end the calvin loop?
A (user, verbatim): "Accept the fixes (Recommended)"
answers: capped@2026-11-03 11:34+08:00
