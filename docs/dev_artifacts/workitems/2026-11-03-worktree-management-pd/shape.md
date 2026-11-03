# Shape: worktree management in pd

<!-- Requirements (specify), then Design (design). Format: plugins/pd/references/doc-format.md. -->

## Requirements

### Goals

- One pd script, `pd-worktrees`, lists a work item's task worktrees and the repository's stray `worktree-wf_*` branches, and removes the clean worktrees and the strays that lose no commit, never forcing. Every place pd removes task worktrees calls it instead of its own git commands: Execute after each run, the wrong-test move back to plan, Finish, and `/pd:abandon-workitem`.
- `pd-status` lists leftover worktrees and stale task branches, and session start shows that list, so the next session sees them without running git.

Owner ruling, Clarify (`decision@2026-11-03 11:08+08:00`): "One cleanup script (Recommended), Show leftovers in pd-status (Recommended)". The option chosen named Execute, Finish, abandon and the wrong-test move as the script's callers.

**Why** (the investigation of 2026-11-03):
- **Abandon fails:** `abandon-workitem.md:12` runs `git branch -D` on `pd/<id>/task-*`, which git refuses while a worktree holds the branch, and every Execute run leaves such worktrees.
- **Task worktrees outlive Execute:** implementers commit, and Claude Code removes a subagent's worktree only when it is unchanged; its 30-day sweep keeps any worktree with unpushed commits (https://code.claude.com/docs/en/worktrees, "Isolate subagents with worktrees" and "Clean up subagent and background-session worktrees"). Task branches are never pushed. Both probe runs of 2026-11-01 left theirs (`bake-off.md:181`, F20).
- **Three cleanups, three rules:** Finish removes without `--force` (`finishing-branch/SKILL.md:33`), the wrong-test move with it (`implementing/SKILL.md:30`), abandon not at all.
- **Fix cycles leak branches:** a fixer checks out the task branch in a new worktree (`implement-tasks.js:54`), leaving Claude Code's auto-made `worktree-wf_<run>-<n>` branch behind (`bake-off.md:168`, F9).
- **Nothing lists them:** no pd script reads `git worktree list`.
- **Done means:** after a run plus Finish or abandon, no worktree is on a `pd/<id>/task-*` branch and no stray that loses no commit is left, except what the script reported as kept and the user chose to keep; anything left shows at session start.

### Non-goals

- Removing worktrees inside the `implement-tasks` workflow, the fixer prompt included (owner ruling: not chosen). The fixer's forced removal of its own failed attempt (`implement-tasks.js:54`) stays as it is.
- This repository's `.pd-worktrees/` remnant and its `.gitignore` comment (not chosen).
- Replacing Claude Code's worktree creation (`WorktreeCreate` hooks, `worktree.*` settings) or its 30-day sweep.
- Clearing a stale `run in flight:` line; that stays the conductor's relaunch rule (`workflow-transitions` "Workflow runs").
- Work items whose directory is only on another, unmerged branch: their worktrees and branches aren't judged (their `## Now` can't be read from here).
- Pushing, or deleting remote branches.

### User stories

- As the conductor at the end of an Execute run, I run one command and the work item's clean task worktrees are gone, while the task branches stay for resume and the retro.
- As the user abandoning a work item, the cleanup deletes its branches instead of failing on a worktree I never saw; a dirty one is shown to me to keep or discard.
- As the user opening a session, I see that two worktrees from last week's run are still on disk, and where, and which command clears them.

### Terms

- **A known work item `<id>`:** its directory `{artifacts_root}/workitems/<id>/` exists in this checkout, or a `workitem/<id>` or `pd/<id>/task-*` branch exists. Finish's PR path deletes `workitem/<id>` before cleanup (`finishing-branch/SKILL.md:30`); the directory is on the base branch by then.
- **A task worktree of `<id>`:** any worktree of the repository, the main checkout included, wherever it lives, whose branch is `pd/<id>/task-<n>`.
- **Its state,** the first that holds: `main checkout` (it is the repository's main working tree), `locked` (`git worktree list --porcelain` shows `locked`; Claude Code locks a worktree while its agent runs, per the worktrees page above), `gone` (git shows `prunable`: its directory no longer exists), `dirty` (`git status --porcelain` in it prints something), `clean`.
- **A stray branch:** a branch named `worktree-wf_<anything>` that no worktree holds: Claude Code's auto-made branch for a Workflow-tool agent's worktree, pd's or another workflow's. Strays belong to the repository, not to one work item. A stray **loses no commit** when another branch contains its tip.
- **A run in flight for `<id>`:** any line of `<id>`'s `README.md` `## Now`, in this checkout, starting with `run in flight:`.
- **Leftovers**, for `pd-status`, one line each, by these rules in order; a branch a listed worktree holds isn't listed again:
  - `worktree after its run`: a task worktree of a work item whose directory is in this checkout, with no run in flight;
  - `branch of a done work item` or `branch of an abandoned work item`: a `pd/<id>/task-*` branch whose work item's directory, in this checkout, says `status: done` or `abandoned`;
  - `no work item`: a task worktree or `pd/<id>/task-*` branch whose `<id>` isn't a known work item;
  - `stray branch`: a stray branch.

### `pd-worktrees`

- `pd-worktrees <id>` (list) prints one line per task worktree of `<id>` (`<state> <path> <branch>`) and per stray branch (`stray <branch>`), or `no worktrees for <id>`; it changes nothing; exit 0.
- `pd-worktrees <id> --remove [--task <n>]...` removes each `clean` and `gone` task worktree of `<id>` (only tasks `<n>` when `--task` is given) with `git worktree remove <path>`, which clears a gone worktree's entry alone (checked in a scratch repository, git 2.54.0, 2026-11-03). Without `--task` it also deletes each stray branch that loses no commit. It never forces a worktree, never unlocks one, and never deletes a task branch. It prints `removed <path>`, `deleted <branch>`, `kept (<state>): <path>` for a `main checkout`, `locked` or `dirty` worktree, and `kept (unique commits): <branch>` for a stray another branch doesn't contain.
- **Exit codes:**
  - 0: every task worktree it was asked to remove was removed;
  - 1: one was kept, or a run is in flight for `<id>` (then it removes nothing and prints `run in flight: <line>`);
  - 2: a usage error, an id that isn't a known work item, or git failing unexpectedly. The message goes to stderr. A usage or unknown-id error changes nothing; on a git failure the lines already printed say what was done.
  - A stray kept for its unique commits doesn't change the exit code.

### Callers

Each runs `pd-worktrees <id> --remove` before deleting any branch:
- **Execute** (`implementing` step 5), after `run in flight:` is cleared and committed, whatever stopped the run; it deletes no branch. Its exit-1 question comes after step 6's own hard stops.
- **The wrong-test move** (`implementing` step 6), with `--task <n>` for each task to re-run, then `git branch -D pd/<id>/task-<n>` for each.
- **Finish** (`finishing-branch` step 9), then its branch deletes with `-d`, as today.
- **Abandon** (`abandon-workitem` step 3), on the work item's branch before switching off it, then its branch deletes with `-D`, as today.
- **On exit 1,** the caller asks the user (AskUserQuestion), listing each kept worktree or the run-in-flight line:
  - a `dirty` one: keep it, or discard it (the conductor then runs `git worktree remove --force <path>` and goes on). At the wrong-test move the choices are discard, or stop the move and stay in `implement`, since re-running a task whose old branch survives would hand the merger the old tests (`implementing/SKILL.md:30`).
  - a `locked` or `main checkout` one: reported with why, and kept.
  - a kept worktree's task branch isn't deleted; every other step of the caller goes on.
  - a run in flight: reported; the caller stops, and the user decides.
- **On exit 2,** the caller reports the message and stops: a hard stop for the user.

### Expectations

Each runs in a scratch git repository with an adopted pd layout, a work item `<id>` (directory and `workitem/<id>` branch), and task worktrees made with `git worktree add` under `.claude/worktrees/`.

B1: `pd-worktrees <id>` with task worktrees in each linked state (`clean`, `dirty`, `locked`, `gone`) and a stray branch -> one line each with its state, path and branch, and `stray <branch>`; `git worktree list --porcelain` and `git branch` are the same before and after; exit 0.
B2: `pd-worktrees <id> --remove` with two clean task worktrees -> both directories gone and absent from `git worktree list`; both `pd/<id>/task-*` branches still exist; exit 0.
B3: `pd-worktrees <id> --remove` with one clean and one dirty task worktree -> the clean one removed, the dirty one kept and printed as `kept (dirty): <path>`; exit 1.
B4: `pd-worktrees <id> --remove` with a locked task worktree whose directory is also gone -> printed as `kept (locked): <path>`, still locked; exit 1.
B5: `pd-worktrees <id> --remove` with a task worktree whose directory was deleted by hand, plus a gone worktree on another branch -> the task one's entry is gone from `git worktree list` and its branch then deletes with `git branch -D`; the other gone entry is still listed; exit 0.
B6: `pd-worktrees <id> --remove` with a stray `worktree-wf_r-2` whose tip `workitem/<id>` contains, and a stray `worktree-wf_r-3` with a commit no other branch has -> the first deleted and printed `deleted worktree-wf_r-2`, the second printed as `kept (unique commits): worktree-wf_r-3` and still present; exit 0.
B7: `pd-worktrees <id> --remove` in a repository that also has a worktree on `worktree-thin-pd-release`, one under `.pd-worktrees/` on another branch, and task worktrees of another work item `<other>` -> none of those removed or printed; `<id>`'s are.
B8: `pd-worktrees <id> --remove --task 2` with clean task worktrees for tasks 1 and 2 and a stray that loses no commit -> only task 2's worktree removed; the stray still present.
B9: `pd-worktrees <id> --remove` with `run in flight: implement-tasks session x` in `## Now` (not its first line) -> nothing removed; prints `run in flight: implement-tasks session x`; exit 1.
B10: `pd-worktrees <id> --remove` after `workitem/<id>` was deleted, with the work item directory still there -> removes its clean task worktrees as in B2; exit 0.
B11: `pd-worktrees <id>` with no task worktrees and no stray branches -> prints `no worktrees for <id>`; exit 0.
B12: `pd-worktrees` with no id, with an id that isn't a known work item, or outside a git repository -> a message on stderr; exit 2; nothing changed.
B13: the main checkout on `pd/<id>/task-1` -> `pd-worktrees <id> --remove` prints `kept (main checkout): <path>`, leaves the checkout as it was; exit 1.
B14: `pd-status` with a leftover of each reason -> a `Leftover worktrees` section, after every other section, whose first line is ``clear a work item's with `pd-worktrees <id> --remove`; remove `no work item` and unique-commit strays by hand``, then one line per leftover: `<id>: <path or branch> — <reason>`, with `-` for the id of a stray; with none, no such section.
B15: `pd-status` with a task worktree of a work item that has a run in flight, and one of a work item whose directory is only on another branch -> neither is listed.
B16: the session-start hook, on each source (startup, resume, clear, compact), in a repository with a leftover -> its context includes the `Leftover worktrees` section.
B17: `pd-status` outside a git repository, or where `git` fails -> its usual report without the section; exit 0.
B18: the `implementing`, `finishing-branch` and `abandon-workitem` instructions -> each cleanup step runs `pd-worktrees <id> --remove` (the wrong-test step with `--task`, abandon's before switching off the branch) before any branch deletion, and handles exit 1 and exit 2 as Callers says.

### Scope

- **In:** the new `plugins/pd/scripts/pd-worktrees` with its tests; `pd-status`'s new section, its docstring (it now reads live git state, not only committed files) and its self-test; the session-start filter (`pd-session-start.sh`) and its hook test; the cleanup steps in `plugins/pd/skills/implementing/SKILL.md` (steps 5 and 6), `plugins/pd/skills/finishing-branch/SKILL.md` step 9 and `plugins/pd/commands/abandon-workitem.md`; CI's script list (`.github/workflows/ci.yml`); the four docs that list pd's scripts (`README_FOR_DEV.md`, `docs/dev-guide/commands-reference.md`, `docs/technical/architecture.md`, `docs/technical/api-reference.md`, found by grepping for `pd-review-filter`); the CHANGELOG line.
- **Out:** everything under Non-goals; worktrees on other branches, whoever made them; `cleanupPeriodDays`.

### Edge cases and must-nots

- **Two work items share a task number** (`pd/a/task-1`, `pd/b/task-1`): only the named id's are touched (B7).
- **A stray another workflow run just left** while that run continues: deleting it loses nothing, since the run's worktree is on its task branch by then.
- **A lock left by a dead session:** shown as `locked` by both scripts and kept; the user unlocks it by hand, or Claude Code's sweep releases it ("The sweep releases locks left by dead sessions", worktrees page above).
- **Must not force or unlock** inside the script: no `--force`, `-f` or `git worktree unlock`. Only the conductor forces, and only on the user's explicit "discard" for that path, since forcing loses uncommitted work. A stray is deleted only when another branch contains its tip, so no commit is lost.
- **Must not delete task branches** inside the script: callers delete them after it (wrong-test and abandon with `-D`, Finish with `-d`). Execute deletes none, because resume and the retro read them (`finishing-branch/SKILL.md:10`).
- **Must not touch other worktrees:** nothing outside a task worktree of the named id and the stray-branch pattern is removed or deleted, so the owner's own worktrees (`.claude/worktrees/thin-pd-release`, `.pd-worktrees/followups-phase-r`) stay; a gone worktree is cleared by its path, never by `git worktree prune`.
- **Must not slow session start noticeably:** `pd-status` adds two git calls in all (`git worktree list --porcelain` and one `git branch --list 'pd/*' 'worktree-wf_*'`), not one per work item or per branch; it lists every stray without checking containment.
