---
description: End the session — commit WIP, write ## Now and a handoff entry
---

# /pd:wrap-up

A session bookend, not a phase. The next session resumes from `## Now` and the `handoff` entry; merging and phase moves belong to the phase commands.

1. **Branch:** `git branch --show-current`. On `{pd_base_branch}`, say so and stop: wrap-up never commits there.
2. **The feature:** the one on the checked-out `workitem/<id>` branch. None: commit any WIP (`wip: <summary>`) and report the open items only.
3. **Write the resume point:**
   - overwrite `## Now` with the next step and anything blocking, keeping its `goal:` and `run in flight:` lines;
   - append a `handoff` entry with what the next session needs that `## Now` can't hold: verification commands last seen failing, decisions pending with the user, uncommitted experiments.
4. **Commit** `wip: <summary>`, with the WIP, `log.md` and the README. A push failure is reported, not retried or worked around.
5. **Report** the `pd-status` line for the feature and its open blockers.
