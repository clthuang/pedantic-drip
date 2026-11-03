# Shape: worktree management in pd

<!-- Requirements (specify), then Design (design). Format: plugins/pd/references/doc-format.md. -->

## Requirements

### Goals

- One pd script, `pd-worktrees`, lists a work item's task worktrees and the repository's stray `worktree-wf_*` branches, and removes the clean worktrees and the merged strays, never forcing. Every place pd removes task worktrees calls it instead of its own git commands: Execute after each run, the wrong-test move back to plan, Finish, and `/pd:abandon-workitem`.
- `pd-status` lists leftover worktrees and stale task branches, and session start shows that list, so the next session sees them without running git.

Owner ruling, Clarify (`decision@2026-11-03 11:08+08:00`): "One cleanup script (Recommended), Show leftovers in pd-status (Recommended)". The option chosen named Execute, Finish, abandon and the wrong-test move as the script's callers.

**Why** (the investigation of 2026-11-03):
- **Abandon fails:** `abandon-workitem.md:12` runs `git branch -D` on `pd/<id>/task-*`, which git refuses while a worktree holds the branch, and every Execute run leaves such worktrees.
- **Task worktrees outlive Execute:** implementers commit, and Claude Code removes a subagent's worktree only when it is unchanged; its 30-day sweep keeps any worktree with unpushed commits (https://code.claude.com/docs/en/worktrees, "Isolate subagents with worktrees" and "Clean up subagent and background-session worktrees"). Task branches are never pushed. Both probe runs of 2026-11-01 left theirs (`bake-off.md:181`, F20).
- **Three cleanups, three rules:** Finish removes without `--force` (`finishing-branch/SKILL.md:33`), the wrong-test move with it (`implementing/SKILL.md:30`), abandon not at all.
- **Fix cycles leak branches:** a fixer checks out the task branch in a new worktree (`implement-tasks.js:54`), leaving Claude Code's auto-made `worktree-wf_<run>-<n>` branch behind (`bake-off.md:168`, F9).
- **Nothing lists them:** no pd script reads `git worktree list`.
- **Done means:** after a run plus Finish or abandon, `git worktree list` shows no worktree on a `pd/<id>/task-*` branch and no `worktree-wf_*` branch is left, unless the user chose to keep a dirty one; and anything left shows at session start.

### Non-goals

- Removing worktrees inside the `implement-tasks` workflow, the fixer prompt included (owner ruling: not chosen). The fixer's forced removal of its own failed attempt (`implement-tasks.js:54`) stays as it is.
- This repository's `.pd-worktrees/` remnant and its `.gitignore` comment (not chosen).
- Replacing Claude Code's worktree creation (`WorktreeCreate` hooks, `worktree.*` settings) or its 30-day sweep.
- Clearing a stale `run in flight:` line; that stays the conductor's relaunch rule (`workflow-transitions` "Workflow runs").
- Pushing, or deleting remote branches.

### User stories

- As the conductor at the end of an Execute run, I run one command and the work item's clean task worktrees are gone, while the task branches stay for resume and the retro.
- As the user abandoning a work item, the cleanup deletes its branches instead of failing on a worktree I never saw; a dirty one is shown to me to keep or discard.
- As the user opening a session, I see that two worktrees from last week's run are still on disk, and where.

### Terms

- **A work item:** the directory `{artifacts_root}/workitems/<id>/` with its `README.md`; its branch may already be deleted (Finish's PR path deletes `workitem/<id>` before cleanup, `finishing-branch/SKILL.md:30`).
- **A task worktree of `<id>`:** a linked worktree, wherever it lives, whose branch is `pd/<id>/task-<n>`.
- **A stray branch:** a branch named `worktree-wf_<anything>` that no worktree holds. Strays belong to the repository, not to one work item: one commit can sit on several work items' branches, so the script doesn't attribute them.
- **States of a task worktree:** `clean` (`git status --porcelain` in it prints nothing), `dirty` (it prints something), `locked` (`git worktree list --porcelain` shows `locked`; Claude Code locks a worktree while its agent runs, per the worktrees page above), `gone` (git shows `prunable`: its directory no longer exists), `main checkout` (the repository's main working tree is on that branch).
- **A run in flight for `<id>`:** any line of the work item's `README.md` `## Now` starting with `run in flight:`.
- **Leftovers**, for `pd-status`, each with its reason:
  - `worktree after its run`: a task worktree of a work item with no run in flight;
  - `branch of a done work item` or `branch of an abandoned work item`: a `pd/<id>/task-*` branch whose work item's status is `done` or `abandoned`;
  - `no work item`: a `pd/<id>/task-*` branch or task worktree whose `<id>` has no work item directory;
  - `stray branch`: a stray branch.

### `pd-worktrees`

- `pd-worktrees <id>` (list) prints one line per task worktree of `<id>` (`<state> <path> <branch>`) and per stray branch (`stray <branch>`), or `no worktrees for <id>`; it changes nothing; exit 0.
- `pd-worktrees <id> --remove [--task <n>]...` removes each `clean` and `gone` task worktree of `<id>` (only tasks `<n>` when `--task` is given) with `git worktree remove <path>`, and deletes each stray branch with `git branch -d`. It never forces, unlocks or deletes a task branch. It prints `removed <path>`, `deleted <branch>`, or `kept (<state>): <path>` for a `dirty`, `locked` or `main checkout` worktree, and `kept (unmerged): <branch>` for a stray that `-d` refuses.
- **Exit codes:** 0 when every task worktree it was asked to remove is gone; 1 when one was kept, or when a run is in flight for `<id>` (then it removes nothing and prints `run in flight: <line>`); 2 on a usage error, an unknown work item, or a git failure (message on stderr, nothing changed). A stray kept as unmerged doesn't change the exit code.

### Callers

Each runs `pd-worktrees <id> --remove` before any branch deletion, and acts on its exit code:
- **Execute** (`implementing` step 5), after the run's result is recorded, whatever stopped the run; it deletes no branch.
- **The wrong-test move** (`implementing` step 6), with `--task <n>` for each task to re-run, then `git branch -D pd/<id>/task-<n>` for each.
- **Finish** (`finishing-branch` step 9), then its branch deletes with `-d`, as today.
- **Abandon** (`abandon-workitem` step 3), then its branch deletes with `-D`, as today.
- **On exit 1,** the caller stops and asks the user (AskUserQuestion), listing each kept worktree: for a `dirty` one, keep it (the cleanup stops there, its branch stays) or discard it (the conductor runs `git worktree remove --force <path>` on that answer); a `locked` or `main checkout` one is reported with why, and kept. Execute's ask doesn't block the rest of step 6.
- **On exit 2,** the caller reports the message and stops: a hard stop for the user.

### Expectations

Each runs in a scratch git repository with an adopted pd layout, a work item `<id>` (directory and `workitem/<id>` branch), and task worktrees made with `git worktree add` under `.claude/worktrees/`.

B1: `pd-worktrees <id>` with task worktrees in each state (`clean`, `dirty`, `locked`, `gone`) and a stray branch -> one line each with its state, path and branch, and `stray <branch>`; `git worktree list --porcelain` and `git branch` are the same before and after; exit 0.
B2: `pd-worktrees <id> --remove` with two clean task worktrees -> both directories gone and absent from `git worktree list`; both `pd/<id>/task-*` branches still exist; exit 0.
B3: `pd-worktrees <id> --remove` with one clean and one dirty task worktree -> the clean one removed, the dirty one kept and printed as `kept (dirty): <path>`; exit 1.
B4: `pd-worktrees <id> --remove` with a locked task worktree -> printed as `kept (locked): <path>`, still locked; exit 1.
B5: `pd-worktrees <id> --remove` with a task worktree whose directory was deleted by hand, plus a gone worktree on another branch -> the task one's entry is gone from `git worktree list` and its branch then deletes with `git branch -D`; the other gone entry is still listed; exit 0.
B6: `pd-worktrees <id> --remove` with a stray `worktree-wf_r-2` whose tip is merged into `HEAD` and a stray `worktree-wf_r-3` with a commit of its own -> the first deleted and printed, the second printed as `kept (unmerged): worktree-wf_r-3` and still present; exit 0 when no task worktree was kept.
B7: `pd-worktrees <id> --remove` in a repository that also has a worktree on `worktree-thin-pd-release`, one under `.pd-worktrees/` on another branch, and task worktrees of another work item `<other>` -> none of those removed or printed; `<id>`'s are.
B8: `pd-worktrees <id> --remove --task 2` with clean task worktrees for tasks 1 and 2 -> only task 2's removed.
B9: `pd-worktrees <id> --remove` with `run in flight: implement-tasks session x` in `## Now` (not its first line) -> nothing removed; prints `run in flight: implement-tasks session x`; exit 1.
B10: `pd-worktrees <id> --remove` after `workitem/<id>` was deleted, with the work item directory still there -> removes its clean task worktrees as in B2; exit 0.
B11: `pd-worktrees <id>` with no task worktrees and no stray branches -> prints `no worktrees for <id>`; exit 0.
B12: `pd-worktrees` with no id, with an id that has no work item directory, or outside a git repository -> a message on stderr; exit 2; nothing changed.
B13: the main checkout on `pd/<id>/task-1` -> `pd-worktrees <id> --remove` prints `kept (main checkout): <path>`, leaves the checkout as it was; exit 1.
B14: `pd-status` with a leftover of each reason -> a `Leftover worktrees` section, after every other section, one line per leftover: `<id>: <path or branch> — <reason>`, the reason one of the five in Terms; with none, no such section.
B15: `pd-status` with a task worktree of a work item that has a run in flight -> that worktree is not listed.
B16: the session-start hook, on each source (startup, resume, clear, compact), in a repository with a leftover -> its context includes the `Leftover worktrees` section.
B17: `pd-status` outside a git repository, or where `git` fails -> its usual report without the section; exit 0.
B18: the `implementing`, `finishing-branch` and `abandon-workitem` instructions -> each cleanup step runs `pd-worktrees <id> --remove` (the wrong-test step with `--task`) before any branch deletion, and handles exit 1 and exit 2 as Callers says.

### Scope

- **In:** the new `plugins/pd/scripts/pd-worktrees` with its tests; `pd-status`'s new section, its docstring (it now reads live git state, not only committed files) and its self-test; the session-start filter (`pd-session-start.sh`) and its hook test; the cleanup steps in `plugins/pd/skills/implementing/SKILL.md` (steps 5 and 6), `plugins/pd/skills/finishing-branch/SKILL.md` step 9 and `plugins/pd/commands/abandon-workitem.md`; CI's script list and the docs that list pd's scripts; the CHANGELOG line.
- **Out:** everything under Non-goals; worktrees on other branches, whoever made them; `cleanupPeriodDays`.

### Edge cases and must-nots

- **Two work items share a task number** (`pd/a/task-1`, `pd/b/task-1`): only the named id's are touched (B7).
- **A lock left by a dead session:** shown as `locked` by both scripts and kept; the user unlocks it by hand or waits for Claude Code's sweep, which releases dead sessions' locks.
- **Must not force or unlock** inside the script: no `--force`, `-f` or `git worktree unlock`. Only the conductor forces, and only on the user's explicit "discard" for that path, since forcing loses uncommitted work.
- **Must not delete task branches** inside the script: callers delete them after it (wrong-test and abandon with `-D`, Finish with `-d`). Execute deletes none, because resume and the retro read them (`finishing-branch/SKILL.md:10`).
- **Must not touch other worktrees:** nothing outside a task worktree of the named id and the stray-branch pattern is removed or deleted, so the owner's own worktrees (`.claude/worktrees/thin-pd-release`, `.pd-worktrees/followups-phase-r`) stay; a gone worktree is cleared by its path, never by `git worktree prune`.
- **Must not slow session start noticeably:** `pd-status` adds two git calls in all (`git worktree list --porcelain` and one `git branch --list`), not one per work item.
