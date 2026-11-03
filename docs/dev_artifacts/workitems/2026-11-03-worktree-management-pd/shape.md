# Shape: worktree management in pd

<!-- Requirements (specify), then Design (design). Format: plugins/pd/references/doc-format.md. -->

## Requirements

### Goals

- One pd script, `pd-worktrees`, lists a work item's task worktrees and branches and removes the clean worktrees, never forcing. Every place pd cleans up worktrees calls it instead of its own git commands: Execute once a run ends, Finish, `/pd:abandon-workitem`, and the wrong-test move back to plan.
- `pd-status` lists leftover worktrees and stale task branches, and session start shows that list, so the next session sees them without running git.

Owner ruling, Clarify (`decision@2026-11-03 11:08+08:00`): "One cleanup script (Recommended), Show leftovers in pd-status (Recommended)".

**Why** (the investigation of 2026-11-03):
- **Task worktrees outlive Execute:** implementers commit, and Claude Code removes only unchanged worktrees (https://code.claude.com/docs/en/worktrees). Its 30-day sweep keeps any worktree with unpushed commits, and task branches are never pushed. Both probe runs of 2026-11-01 left them (`bake-off.md:181`, F20).
- **Only Finish removes them** (`finishing-branch/SKILL.md:33`); until then every run's worktrees pile up.
- **Abandon can't delete its branches:** `abandon-workitem.md:12` runs `git branch -D` on `pd/<id>/task-*`, which git refuses while a worktree holds the branch.
- **Fix cycles leak branches:** a fixer checks out the task branch in a new worktree (`implement-tasks.js:54`), so Claude Code's auto-made `worktree-wf_<run>-<n>` branch is left behind (`bake-off.md:168`, F9).
- **Nothing lists them:** no pd script reads `git worktree list`.

### Non-goals

- Removing worktrees inside the `implement-tasks` workflow (owner ruling: not chosen).
- This repository's `.pd-worktrees/` remnant and its `.gitignore` comment (not chosen), and any worktree or branch outside the patterns below.
- Replacing Claude Code's worktree creation (`WorktreeCreate` hooks, `worktree.*` settings) or its 30-day sweep.
- Pushing, or deleting remote branches.

### User stories

- As the conductor at the end of an Execute run, I run one command and the run's clean task worktrees are gone, while the task branches stay for resume and the retro.
- As the user abandoning a work item, the cleanup deletes its branches instead of failing on a worktree I never saw.
- As the user opening a session, I see that two worktrees from last week's run are still on disk, and where.

### Terms

- **A work item's task worktree:** a linked worktree whose branch is `pd/<id>/task-<n>`.
- **A work item's stray branch:** a branch named `worktree-wf_<anything>` with no worktree holding it, whose tip is an ancestor of `workitem/<id>` (so it carries no commit of its own).
- **Clean:** `git status --porcelain` in the worktree prints nothing (no changes, no untracked files).
- **Locked:** `git worktree list --porcelain` shows a `locked` line (Claude Code locks a worktree while its agent runs).
- **Gone:** git lists the worktree as `prunable` (its directory no longer exists).
- **Leftover**, for `pd-status`:
  - a task worktree of a work item whose `## Now` has no `run in flight:` line;
  - a `pd/<id>/task-*` branch of a work item whose status is `done` or `abandoned`;
  - a stray `worktree-wf_*` branch of any work item.

### Expectations

Each runs in a scratch git repository with an adopted pd layout, a work item `<id>` on `workitem/<id>`, and task worktrees made with `git worktree add` under `.claude/worktrees/`.

B1: `pd-worktrees <id>` with two task worktrees (one clean, one with an untracked file) -> prints one line per worktree with its path, branch and state (`clean` or `dirty`), and changes nothing (the same `git worktree list --porcelain` before and after); exit 0.
B2: `pd-worktrees <id> --remove` with two clean task worktrees -> both directories gone and absent from `git worktree list`; both `pd/<id>/task-*` branches still exist; exit 0.
B3: `pd-worktrees <id> --remove` with one clean and one dirty task worktree -> the clean one removed, the dirty one kept and printed as `kept (dirty): <path>`; exit 1.
B4: `pd-worktrees <id> --remove` with a locked task worktree -> it is kept, printed as `kept (locked): <path>`, and stays locked; exit 1.
B5: `pd-worktrees <id> --remove` with a task worktree whose directory was deleted by hand -> its entry is gone from `git worktree list` and its branch can then be deleted with `git branch -D`; exit 0.
B6: `pd-worktrees <id> --remove` with a stray `worktree-wf_r-2` branch whose tip is an ancestor of `workitem/<id>` -> the branch is deleted and printed; a `worktree-wf_r-3` branch with a commit of its own is kept.
B7: `pd-worktrees <id> --remove` in a repository that also has a worktree on `worktree-thin-pd-release`, one under `.pd-worktrees/`, and task worktrees of another work item `<other>` -> none of those is removed or printed; only `<id>`'s are.
B8: `pd-worktrees <id>` with no task worktrees and no stray branches -> prints `no worktrees for <id>`; exit 0.
B9: `pd-worktrees` with no id, or an id with no `workitem/<id>` branch -> a usage or `unknown work item` message on stderr; exit 2; nothing changed.
B10: `pd-status` with a leftover task worktree, a `pd/<done-id>/task-1` branch of a done work item, and a stray branch -> prints a `Leftover worktrees` section with one line each (work item, path or branch, why it is a leftover); with none, no such section.
B11: `pd-status` with a task worktree of a work item whose `## Now` has `run in flight:` -> that worktree is not listed.
B12: the session-start hook in a repository with a leftover worktree -> its context includes the `Leftover worktrees` section.
B13: `pd-status` and `pd-worktrees` in a directory that is not a git repository, or where `git` fails -> `pd-status` prints its usual report without the section (exit 0); `pd-worktrees` prints the git error on stderr (exit 2).
B14: the `implementing`, `finishing-branch` and `abandon-workitem` instructions -> each cleanup step runs `pd-worktrees <id> --remove` before any branch deletion, and on exit 1 stops and asks the user (AskUserQuestion) instead of forcing.

### Scope

- **In:** the new `plugins/pd/scripts/pd-worktrees` with its tests; `pd-status`'s new section and its self-test; the session-start filter (`pd-session-start.sh`) and its hook test; the cleanup steps in `plugins/pd/skills/implementing/SKILL.md` (after a run, the wrong-test move), `plugins/pd/skills/finishing-branch/SKILL.md` step 9 and `plugins/pd/commands/abandon-workitem.md`; the fixer prompt in `plugins/pd/workflows/implement-tasks.js` if the design stops the stray branch at its source; docs that list pd's scripts; the CHANGELOG line.
- **Out:** everything under Non-goals; worktrees made by `claude -w` or by hand; `cleanupPeriodDays`.

### Edge cases and must-nots

- **A run still in flight** (`## Now` has `run in flight:`): `pd-worktrees <id> --remove` removes nothing and exits 1 with `run in flight: <line>`; locked worktrees are kept anyway (B4).
- **Two work items share a task number** (`pd/a/task-1`, `pd/b/task-1`): only the named id's are touched (B7).
- **The main checkout on a task branch** (someone ran `git checkout pd/<id>/task-1`): it is never removed; it is printed as `kept (main checkout)`.
- **Must not force:** no `--force`, `-f` or `git worktree unlock`; a dirty or locked worktree is the user's to decide, since forcing loses uncommitted work.
- **Must not delete task branches:** branch deletion stays with Finish (`-d`) and abandon (`-D`), after the script; Execute keeps the branches because resume and the retro read them (`finishing-branch/SKILL.md:10`).
- **Must not touch other worktrees:** nothing outside the two patterns in Terms is removed, so the owner's own worktrees (`.claude/worktrees/thin-pd-release`, `.pd-worktrees/followups-phase-r`) stay.
- **Must not slow session start noticeably:** `pd-status` adds at most two git calls (`git worktree list --porcelain`, `git branch --list`), not one per work item.
