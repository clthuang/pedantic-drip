---
name: implementing
description: The Execute stage's playbook — derive the implement-tasks workflow's args from plan.md, launch it, and record its result in log.md. Use when a feature is in phase implement.
---

# Implementing

The Execute stage (`phase: implement`) turns the plan's tasks into merged, proven code. The conductor writes no code here: every task, the small and sequential ones included, runs as one `implementer` in its own worktree inside the `implement-tasks` workflow, and the `merger` lands it after checking its proof. Shared mechanics: the `workflow-transitions` skill.

## Steps

1. **Phase entry** per `workflow-transitions`.
2. **Check out the feature branch** in this checkout (the README's `branch:`), with a clean tree. `worktree.baseRef: "head"` makes its HEAD every task worktree's base; without that setting, task worktrees start from the default branch (`/pd:init` proposes it).
3. **Derive the args** from the committed files, never from memory:
   - `feature_id`; `shape` and `plan` (the files' paths); `workflow_output_cap` from `.claude/pd.local.md`, raised by any `decision` entry that raised it for this feature;
   - `waves`: one list per `### Wave n` of `plan.md`, each task `{n, title, parallel_safe, command, junit, green_only}` (the executor reads its block in `plan.md` itself): `command` the backticked `- command:`, `junit` the `- junit:` path, `green_only` the reason in `- proof: green-only (<reason>)` or `null`;
   - **express** (`mode: express`): `plan: null`, and one wave holding task 1, read from the task block in `shape.md` `## Requirements`;
   - **resume:** for each existing `pd/<feature id>/task-<n>` branch, `merged` lists it only when a committed `run` entry records it `merged, proof pass`. Otherwise `finished` gets `{n, branch, head, first_commit, case_map}`, a branch already merged without that line included (a crash before the run entry): the merger re-checks it and returns its row. `first_commit` is the first commit of `git rev-list --reverse <fork>..<branch>`, where `<fork>` is `git merge-base HEAD <branch>`, or, for a merged branch, `git merge-base <merge>^1 <branch>` with `<merge>` the merge commit whose second parent is the branch's tip. `case_map` comes from the earlier `run` entry's `case_map:` line, else `{}`.
4. **Launch `implement-tasks`** per `workflow-transitions` "Workflow runs": write `run in flight:` to `## Now` and commit first. On a goal's first run, its `run` entry records `Budget: feature_token_budget=<n|unset>`.
5. **Record the result** (`references/workflow-results.md`, `implement-tasks`) in one `run` entry, in the shape of `references/log-entries.md`:
   - one line per task, exactly `- task <n>: merged, proof pass, cycles <k>, branch <branch>` for a merged task (`phase-gate.sh implement` reads it), or `- task <n>: <status>, cycles <k>, branch <branch>` otherwise;
   - under each task line, `  case_map: C1=<test>, C2=<test>; greens: <tests or none>; skipped: <tests or none>`, which Verify passes to its reviewer;
   - `Agents:` and `Tokens:` from the result's `agents_used` and `tokens`;
   - one `note` entry per flake (`Flaky: <test> — <runs>`).
   Clear `run in flight:` and commit.
6. **Act on what stopped the run:**
   - **`stopped: "budget"`:** per `workflow-transitions`; the resume list is step 3's, re-derived.
   - **a merge conflict:** a hard stop. Ask the user through AskUserQuestion; never resolve it here.
   - **a task `failed` after its three fix cycles:** a hard stop for the user, with the merger's reason and the branch. Their ruling is a `decision` entry.
   - **a task `wrong-test`** (the test case itself is wrong): move back to `create-plan` (`phase implement -> create-plan (back)`, `Invalidates:` the task's test cases). Merged tasks stay merged, and resume skips them, so a change to a merged task's cases goes into a new task. The plan's fix re-runs the unmerged tasks whose contract or cases changed. Before relaunching, remove each one's worktree (`git worktree remove --force <path>`, from `git worktree list`) and then delete its `pd/<feature id>/task-<n>` branch (`git branch -D`); git won't delete a branch a worktree holds. Its tests and its copy of `plan.md` hold the old cases, so resuming it would hand the merger and the fixer the wrong test.
   - **every task merged:** go on.
7. **Exit check:** `bash ${CLAUDE_PLUGIN_ROOT}/scripts/phase-gate.sh implement <feature dir>`, which needs every plan task (express: the one task) on a `merged, proof pass` line. Then phase exit per `workflow-transitions` (`phase implement -> verify`).

**Entries this stage writes:** `run` (each launch's result), `note` (each flake), `decision` (each user ruling at a hard stop or budget stop), `phase` (the exit, or a move back to `create-plan`).

## What the conductor never does here

- **Write or fix code** in the main checkout, or run a task "inline" because it is small.
- **Merge a task branch itself,** or edit a test after a task's first commit: the merger and the fix cycles own those.
- **Count a task done** on a red or unrun proof. The run entry's figures come from the workflow result, never from an agent's prose.
