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
