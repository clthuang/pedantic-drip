---
name: retrospecting
description: The retro playbook — on a retro trigger, one retro-facilitator dispatch over the work item's log.md and git, written to retro.md with each lesson landing where it acts. Use when finish's exit check reports a retro trigger, or a defect owes a retro.
---

# Retrospecting

A full retro runs only on a trigger: a second backward move, a `capped` entry, a cost overrun, or a post-merge `defect`. `phase-gate.sh finish` names the triggers, and `pd-status` lists done work items that owe a retro. Without a trigger, finish writes one `note` entry instead (`finishing-branch` skill).

It runs while the branch and the task branches still exist, because they are inputs. Entry and commits follow the `workflow-transitions` skill.

## Steps

1. **Assemble the inputs as pointers, not copies:**
   - the work item directory: `README.md`, `log.md`, `shape.md` and `plan.md`;
   - the trigger list from `phase-gate.sh finish`;
   - `git log --oneline {pd_base_branch}..workitem/<id>` and `git diff --stat {pd_base_branch}...workitem/<id>`;
   - the earlier `retro.md` files under `{pd_artifacts_root}/workitems/`, so self-labels ("first", "only", "Nth") can be checked.
2. **Dispatch one `pd:retro-facilitator`.** The prompt carries those pointers and the template `${CLAUDE_PLUGIN_ROOT}/templates/retro.md`, and ends with the dispatch-hygiene line. The agent re-derives every figure from `log.md` and git, and every figure cites its entry or commit. A count copied from a briefing or an earlier artifact is a defect.
3. **Write `{pd_artifacts_root}/workitems/<id>/retro.md`** from its result, in the template's sections.
4. **Land each lesson where it acts,** in this order of preference:
   - a `pd-lint` or hook check, if it can be checked;
   - otherwise one line in the CLAUDE.md of the project where the work item ran;
   - otherwise an edit to the stage skill. A lesson about pd itself goes into pd's skill.

   Name each landing in `## Takeaways`, with its commit. A follow-up gets a `pd-new backlog "<title>" --from workitems/<id>` line, listed in `## Actions`.
5. **Commit `retro.md`** before any cleanup.

## Never
- **Never ask the user how the work item went.** The record is the input.
- **Never write to `knowledge-bank/`.** It is a frozen, read-only archive.
