---
description: Mark a work item abandoned, with the user's reason, and offer branch cleanup
argument-hint: "[--workitem=<id>]"
---

# /pd:abandon-workitem

Ends a work item outside the phase sequence. The work item is resolved as the `pd:workflow-transitions` skill's phase entry does.

1. **Confirm and ask the reason** through AskUserQuestion. An already `done` or `abandoned` work item is reported, not abandoned again.
2. **Record it:** append a `decision` entry (`Q: abandon <id>?` with the user's answer, verbatim), set `status: abandoned`, overwrite `## Now` with the reason, and commit `abandon: <id>`. A work item listed in a plan's `roadmap:` becomes a `dropped:` item there, with the reason, in the same commit.
3. **Offer branch cleanup** through AskUserQuestion. When the user accepts, first run `pd-worktrees <id> --remove` on the work item's branch. On exit 1 ask as `implementing` step 5 does; a kept worktree's `pd/<id>/task-*` branch is left out of the `-D` deletes. On exit 2, a hard stop before any branch delete. Then switch off the branch, then `git branch -D workitem/<id>` and any other `pd/<id>/task-*` branches. Abandoned branches are unmerged, so this one place uses `-D`.
