---
from_shape: 7306ee0d519185feb2ea2b477f1e2ce71871afbd
---
# Plan: worktree management in pd

<!-- from_shape is `git hash-object shape.md` when this plan was derived. Format: plugins/pd/references/doc-format.md. -->

## Plan

Shared terms for every case:
- **`pd_repo`:** the fixture in `plugins/pd/scripts/conftest.py` (shape.md `### Test strategy`): an adopted repository with work item `<id>` committed on `main` and branch `workitem/<id>`, the main checkout on `main`.
- **`task_worktree(n, state)`:** `git worktree add -b pd/<id>/task-<n> .claude/worktrees/task-<n>`, then `clean` (nothing), `dirty` (an untracked file), `locked` (`git worktree lock`) or `gone` (its directory deleted).
- **`wt(args)`:** runs `plugins/pd/scripts/pd-worktrees <args>` with the repository root as cwd; returns stdout lines, stderr and the exit code.
- **"unchanged":** `git worktree list --porcelain` and `git for-each-ref refs/heads/` print the same before and after.
- **`logging git` / `moving git`:** a `git` script first on `PATH` that appends its arguments to a log and runs the real git; the moving one also commits onto the stray named in the test just after the `for-each-ref --contains` call; the occupying one instead checks that stray out in a new worktree at that moment.

### Wave 1

#### Task 1: `pd-worktrees` and the shared worktree helpers
- contract: shape.md ## Design, plugins/pd/scripts/pd_common.py, plugins/pd/scripts/pd-worktrees
- files: plugins/pd/scripts/pd_common.py, plugins/pd/scripts/pd-worktrees, plugins/pd/scripts/conftest.py, plugins/pd/scripts/test_pd_worktrees.py, .github/workflows/ci.yml, CHANGELOG.md
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_pd_worktrees.py --junitxml=agent_sandbox/junit/task-1.xml`
- junit: agent_sandbox/junit/task-1.xml
- test cases:
  - C1 [B1] (fixture: pd_repo): with `task_worktree(1, clean)`, `(2, dirty)`, `(3, locked)`, `(4, gone)` and a branch `worktree-wf_r-1` no worktree holds, given `wt(<id>)`, expect exactly the lines `clean <path 1> pd/<id>/task-1`, `dirty <path 2> pd/<id>/task-2`, `locked <path 3> pd/<id>/task-3`, `gone <path 4> pd/<id>/task-4` and `stray worktree-wf_r-1`; unchanged; exit 0.
  - C2 [B2] (fixture: pd_repo): with `task_worktree(1, clean)` and `(2, clean)`, given `wt(<id> --remove)`, expect `removed <path 1>` and `removed <path 2>`, both directories gone and absent from `git worktree list --porcelain`, both `pd/<id>/task-*` branches still present; exit 0.
  - C3 [B3] (fixture: pd_repo): with `task_worktree(1, clean)` and `(2, dirty)`, given `wt(<id> --remove)`, expect `removed <path 1>` and `kept (dirty): <path 2>`, the dirty directory and its untracked file still there; exit 1.
  - C4 [B4] (fixture: pd_repo): with `task_worktree(1, locked)` whose directory is then deleted, given `wt(<id> --remove)`, expect `kept (locked): <path 1>`, and the porcelain still showing it `locked`; exit 1.
  - C5 [B5] (fixture: pd_repo): with `task_worktree(1, gone)` and a worktree on a branch `other` whose directory is also deleted, given `wt(<id> --remove)`, expect `removed <path 1>`, its entry gone from the porcelain, `git branch -D pd/<id>/task-1` then succeeding, and `other`'s entry still listed; exit 0.
  - C6 [B6] (fixture: pd_repo): with a stray `worktree-wf_r-2` whose tip only `workitem/<id>` contains (the main checkout on `main`, which doesn't, so `git branch -d` would refuse it) and a stray `worktree-wf_r-3` holding a commit no other branch has, given `wt(<id> --remove)`, expect `deleted worktree-wf_r-2` and `kept (unique commits): worktree-wf_r-3`; `git rev-parse --verify -q refs/heads/worktree-wf_r-2` then failing and `worktree-wf_r-3` still at its tip; exit 0.
  - C7 [B7] (fixture: pd_repo): with a worktree at `.claude/worktrees/thin-pd-release` on branch `worktree-thin-pd-release`, one at `.pd-worktrees/followups` on branch `followups`, clean task worktrees of a second work item `<other>`, and `task_worktree(1, clean)`, given `wt(<id> --remove)`, expect only `removed <path 1>` printed, and the other three worktrees and their branches still present.
  - C8 [B8] (fixture: pd_repo): with `task_worktree(1, clean)`, `(2, clean)` and a stray that `workitem/<id>` contains, given `wt(<id> --remove --task 2)`, expect only `removed <path 2>`, path 2's directory gone and absent from `git worktree list --porcelain`, `pd/<id>/task-2` still present; task 1's worktree and the stray still present; exit 0.
  - C9 [B9] (fixture: pd_repo): with `<id>`'s `## Now` set to a first line and then `run in flight: implement-tasks session x`, and `task_worktree(1, clean)`, given `wt(<id> --remove)`, expect exactly `run in flight: implement-tasks session x`; unchanged; exit 1.
  - C10 [B10] (fixture: pd_repo): with `task_worktree(1, clean)` and `workitem/<id>` deleted (the directory on `main`), given `wt(<id> --remove)`, expect `removed <path 1>`, its directory gone and absent from `git worktree list --porcelain`, `pd/<id>/task-1` still present; exit 0.
  - C11 [B11] (fixture: pd_repo): with no task worktrees and no strays, given `wt(<id>)`, expect exactly `no worktrees for <id>`; exit 0.
  - C12 [B12] (fixture: pd_repo): given `wt()`, `wt(--remove)`, `wt(<id> --task 1)`, and `wt(<ghost>)` where only a `pd/<ghost>/task-1` branch exists, and `wt(<id>)` run in a temporary directory outside any git repository, expect each: stdout empty, stderr starting `pd-worktrees:`, exit 2, and unchanged.
  - C13 [B13] (fixture: pd_repo): with the main checkout switched to a new branch `pd/<id>/task-1`, given `wt(<id> --remove)`, expect `kept (main checkout): <repository root>`, the main checkout still on `pd/<id>/task-1`; exit 1.
  - C14 [B19] (fixture: pd_repo): with no work item directory checked out (the main checkout on an orphan branch holding one commit and no `docs/`), a stray `worktree-wf_r-2` whose tip `main` contains, and strays `worktree-wf_r-3` and `worktree-wf_r-4` on one tip no other branch has, given `wt(--strays --remove)`, expect `deleted worktree-wf_r-2`, `kept (unique commits): worktree-wf_r-3` and `kept (unique commits): worktree-wf_r-4`; `refs/heads/worktree-wf_r-2` then absent, the other two still at their tip; exit 0.
  - C15 [B6] (fixture: pd_repo): with a stray `worktree-wf_r-2` whose tip `workitem/<id>` contains, and the `moving git` on `PATH`, given `wt(<id> --remove)`, expect `kept (unique commits): worktree-wf_r-2`, the branch present at its new commit; exit 0 (the compare-and-delete).
  - C16 [B1, B2] (fixture: pd_repo): with a clean task worktree at a path holding a newline (`.claude/worktrees/task-1\nlocked`), given `wt(<id>)`, expect one line `clean <path with \n escaped> pd/<id>/task-1`; given `wt(<id> --remove)`, expect it removed; exit 0.
  - C17 [B2] (fixture: pd_repo): with `task_worktree(1, clean)` and `(2, clean)`, given `wt(<id> --remove)` run with task 1's directory as cwd, expect both removed and both printed; exit 0 (git runs from the main checkout).
  - C18 [B3] (fixture: pd_repo): with a clean task worktree holding an initialized submodule (a local repository added with `git -c protocol.file.allow=always submodule add`), given `wt(<id> --remove)`, expect `kept (clean): <path>`, the worktree still there; exit 1.
  - C19 [B12] (fixture: pd_repo): with a `git` script first on `PATH` that fails `for-each-ref`, and a stray present, given `wt(<id> --remove)`, expect stderr starting `pd-worktrees:`; exit 2.
  - C20 [B6, B7] (fixture: pd_repo): with a symbolic ref `refs/heads/worktree-wf_alias` pointing at `refs/heads/workitem/<id>`, given `wt(<id> --remove)`, expect `deleted worktree-wf_alias`, the alias gone, and `workitem/<id>` still at its tip (`--no-deref`).
  - C21 [B6] (fixture: pd_repo): with a stray `worktree-wf_r-2` whose tip `workitem/<id>` contains, and the occupying `git` on `PATH`, given `wt(<id> --remove)`, expect no line naming `worktree-wf_r-2` and the branch still present, held by the new worktree; exit 0.
  - C22 [B7] (fixture: pd_repo): with a clean task worktree at `.claude/worktrees/a\rb` and a clean worktree on branch `other` at `.claude/worktrees/a\nb`, given `wt(<id> --remove)`, expect only the first removed, and the second still listed by `git worktree list --porcelain -z` (the transport is lossless).
  - C23 [B2, B3, B4, B7] (fixture: pd_repo): with the `logging git` on `PATH`, run every `wt` call of C1 to C22; expect no logged call to carry `--force`, `-f`, `unlock` or `prune`, no `branch -d` or `branch -D` at all, no `update-ref -d` of a `pd/*` or `workitem/*` ref, and every `update-ref` carrying `--no-deref` (the must-nots on forcing, unlocking and deleting task branches).
  - C24 [B1] (fixture: none): read `.github/workflows/ci.yml`; expect its `uv run --project plugins/pd pytest` line to name `plugins/pd/scripts/test_pd_worktrees.py`, `plugins/pd/scripts/test_pd_status_leftovers.py` and `plugins/pd/scripts/test_worktree_callers.py`.

### Wave 2

#### Task 2: the `Leftover worktrees` section and session start [parallel-safe]
- contract: shape.md ## Design, plugins/pd/scripts/pd-status, plugins/pd/hooks/pd-session-start.sh
- files: plugins/pd/scripts/pd-status, plugins/pd/hooks/pd-session-start.sh, plugins/pd/scripts/test_pd_status_leftovers.py
- uses: plugins/pd/scripts/pd_common.py, plugins/pd/scripts/pd-worktrees, plugins/pd/scripts/conftest.py
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_pd_status_leftovers.py --junitxml=agent_sandbox/junit/task-2.xml`
- junit: agent_sandbox/junit/task-2.xml
- test cases:
  - C25 [B14] (fixture: pd_repo): with work items A (active, `task_worktree(1, clean)`, its log.md holding a `review` entry with an unclosed blocker), B (`status: done`, a branch `pd/B/task-1`, its log.md holding a `capped` entry and no `retro.md`), C (`status: abandoned`, a branch `pd/C/task-1`), a branch `pd/ghost/task-1` with no directory and no `workitem/ghost`, and a stray `worktree-wf_r-1`, given `pd-status`, expect the `Open blockers` and `Retros owed` sections present and `Leftover worktrees` after both, as the last section, its first line exactly ``clear with `pd-worktrees <id> --remove` (a work item's worktrees) or `pd-worktrees --strays --remove`; delete other listed branches by hand``, then exactly `A: <path 1> — worktree after its run`, `B: pd/B/task-1 — branch of a done work item`, `C: pd/C/task-1 — branch of an abandoned work item`, `ghost: pd/ghost/task-1 — no work item` and `-: worktree-wf_r-1 — stray branch` (A's branch not listed again); with A's worktree also locked, expect its line `A: <path 1> (locked) — worktree after its run`.
  - C26 [B14] (fixture: pd_repo): with no leftovers, expect no `Leftover worktrees` line. With a stray `worktree-wf_r-1` present in each: a repository with no items, expect the report to end with `no items under docs/dev_artifacts`; and an unadopted one (`docs/features/` present, no `sop: 1` in `.claude/pd.local.md`), expect the report to start `run /pd:adopt`; neither holding `Leftover worktrees` or `worktree-wf_r-1`.
  - C27 [B15] (fixture: pd_repo): with a task worktree of a work item whose `## Now` holds `run in flight: implement-tasks session y`, and one of a work item D whose directory is only on branch `workitem/D`, expect no `Leftover worktrees` section.
  - C28 [B16] (fixture: pd_repo): with one leftover, run `plugins/pd/hooks/pd-session-start.sh` with hook JSON for each source `startup`, `resume`, `clear` and `compact`; expect each context to contain `Leftover worktrees` and the leftover's line.
  - C29 [B17] (fixture: pd_repo): with the adopted layout copied into a directory outside any git repository, and, separately, with each of three `git` scripts first on `PATH` (one exiting 1 on every call, one only on `worktree list`, one only on `branch --list`, the others running the real git), with a leftover present, expect `pd-status` to exit 0, its `Items` section unchanged and no `Leftover worktrees` section.
  - C30 [B14] (fixture: pd_repo): with the `logging git` on `PATH`, run `pd-status` once with one work item and one leftover, and once with three work items, each with a task worktree after its run and a done item's `pd/*` branch; expect each run's logged calls, as a multiset, to equal exactly a literal in the test: `rev-parse --show-toplevel` (the one call `pd-status` makes before this change, logged 2026-11-03 at b230ae35), one `worktree list --porcelain -z` and one `branch --list 'pd/*' 'workitem/*' 'worktree-wf_*'` (the must-not on session-start cost: two calls added in all, none per work item or per branch; a literal, not a baseline read from a moving ref, so the test holds on `main` after the merge).
  - C31 [B14] (fixture: none): parse `plugins/pd/scripts/pd-worktrees` and `plugins/pd/scripts/pd-status` with `ast`; expect each to import `worktrees` and `run_in_flight` from `pd_common` and to call both by those names, and neither to hold a string constant containing `worktree list` nor a list or tuple whose string elements hold `"worktree"` followed by `"list"` (the shared-helper invariant). Negative control: a copy of `pd-status` that imports both but calls `subprocess.run(["git", "worktree", "list", "--porcelain", "-z"])` fails it.

#### Task 3: the callers and the docs [parallel-safe]
- contract: shape.md ## Design, plugins/pd/skills/implementing/SKILL.md, plugins/pd/skills/finishing-branch/SKILL.md, plugins/pd/commands/abandon-workitem.md
- files: plugins/pd/skills/implementing/SKILL.md, plugins/pd/skills/finishing-branch/SKILL.md, plugins/pd/commands/abandon-workitem.md, README_FOR_DEV.md, docs/dev-guide/commands-reference.md, docs/technical/architecture.md, docs/technical/api-reference.md, plugins/pd/scripts/test_worktree_callers.py
- uses: none
- command: `uv run --project plugins/pd pytest plugins/pd/scripts/test_worktree_callers.py --junitxml=agent_sandbox/junit/task-3.xml`
- junit: agent_sandbox/junit/task-3.xml
- test cases:
  - C32 [B18] (fixture: none): in `implementing` step 5, expect `pd-worktrees <id> --remove` after the sentence clearing `run in flight:`, the exit-1 ask (AskUserQuestion; keep or discard a `dirty` one or a `clean` one git refused; `git worktree remove --force <path>` only on "discard"; `locked` and `main checkout` ones reported, not asked; no question when no dirty or refused one is listed), a run in flight named as stopping the caller, a kept worktree's task branch named as not deleted, and exit 2 named a hard stop before step 6.
  - C33 [B18] (fixture: none): in `implementing` step 6's wrong-test bullet, expect `pd-worktrees <id> --remove --task <n>` before `git branch -D pd/<id>/task-<n>`, a kept worktree named as stopping the move, and no hand-run `git worktree remove --force` outside the discard path.
  - C34 [B18] (fixture: none): in `finishing-branch` step 9, expect `pd-worktrees <id> --remove` before `git branch -d`, the ask of `implementing` step 5 named for exit 1, a kept worktree's `pd/<id>/task-*` branch named as left out of the deletes, exit 2 named a hard stop before any branch delete, and no hand-run `git worktree remove <path>` left.
  - C35 [B18] (fixture: none): in `abandon-workitem` step 3, expect `pd-worktrees <id> --remove` after the user accepts cleanup, before "switch off" the branch, and before `git branch -D`; the ask of `implementing` step 5 named for exit 1; a kept worktree's `pd/<id>/task-*` branch named as left out of the `-D` deletes; and exit 2 named a hard stop before any branch delete.
  - C36 [B18] (fixture: none): expect each of `README_FOR_DEV.md`, `docs/dev-guide/commands-reference.md`, `docs/technical/architecture.md` and `docs/technical/api-reference.md` to name `pd-worktrees` where it lists pd's scripts (the lines naming `pd-review-filter`).
