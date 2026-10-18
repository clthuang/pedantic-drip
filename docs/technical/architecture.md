---
last-updated: 2026-10-18T06:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# Architecture

## Overview

pd is a Claude Code plugin: commands, skills, agents, workflows, hooks and scripts (stdlib Python and bash; only `pd-html.py` needs a package, markdown-it-py, run through `uv`). It runs inside Claude Code sessions; there is no server and no database. A feature's state is committed markdown under `{pd_artifacts_root}` (default `docs/dev_artifacts/`), and everything derived — progress, open blockers, retros owed — is computed from those files on demand.

## Component Map

```
User
 │
 ├── /pd:<command>            Thin entry points           plugins/pd/commands/{name}.md
 │        └── Stage skill     The conductor's playbook    plugins/pd/skills/{name}/SKILL.md
 │               ├── Scripts  Create, check, compute      plugins/pd/scripts/
 │               └── Workflow Fan-outs, one agent each    plugins/pd/workflows/{name}.js
 │                      └── Agent                         plugins/pd/agents/{name}.md
 │
 └── Hooks                    SessionStart, PreToolUse, Stop   plugins/pd/hooks/
```

**The conductor** (the main session) owns every user decision (through AskUserQuestion), every state write (`README.md`, `log.md`) and the phase commits. Agents commit code only: implementers on their task branches, the merger and Verify's fixer on the feature branch. Workflows and agents return JSON results; the conductor writes `log.md` from them.

## Key Data Flows

Stage names map to `phase:` values: Criteria = `specify`, Contracts = `design`, Plan = `create-plan`, Execute = `implement`, Verify = `verify`, Finish = `finish`.

### A phase, start to finish

1. `/pd:<phase>` invokes its stage skill.
2. Phase entry (`workflow-transitions`): resolve the feature, check out `feature/<id>`, read `README.md`, `## Now` and `pd-status`'s open blockers.
3. The skill writes its artifact (`shape.md` or `plan.md`) and, at Contracts and Plan, makes the review call; each review is a `review` entry in `log.md`.
4. Exit: `phase-gate.sh <phase> <dir>` passes; `phase:` moves on; a `phase <from> -> <to>` entry is appended; the commit runs `pd-lint --staged` through `pd-commit-lint`.

### Execute: `implement-tasks`

1. The conductor derives the args from `plan.md` (waves of task blocks) and writes `run in flight:` to `## Now`.
2. Each task runs as one `implementer` in a Claude Code worktree (base: the feature branch's HEAD, via `worktree.baseRef: "head"`), committing its tests first on `pd/<id>/task-<n>`.
3. The `merger` lands each task ([merger.md](../../plugins/pd/agents/merger.md)):
   - **First commit:** holds only test files, plus source additions; `pd-lint --isolation` passes over it.
   - **At the first commit:** `pd-proof first` sees every test fail as a test, with no load or collection errors.
   - **At HEAD:** `pd-proof head` sees them pass, and no later commit touches the test files the first commit added or changed.
   - **Merge:** `git merge --no-ff` onto the feature branch, in plan order. A conflict aborts the merge and stops the run for the user.
   - **After the merge:** every merged task's proving command and `pd-lint` re-run; a break fails the task just merged.
   - **`proof: green-only` tasks** (refactor, infra, fixture): skip the first-commit checks and the test-file check; the rest stays.
4. A failed task gets up to three fix cycles (cycles 2 and 3 on opus), reusing its branch; still failing, the run stops for the user.
5. The conductor appends a `run` entry with one `task <n>: merged, proof pass, …` line per task, which `phase-gate.sh implement` reads.

### Verify: `verify-change`

- **The review call** ([review-call.md](../../plugins/pd/references/review-call.md)): Codex, one retry, else `code-quality-reviewer`. It runs beside `qa-executor`.
- **QA:** `qa-executor` runs the `qa_battery`, and on its first run `pd-lint --risk` and `pd-lint --isolation` over the branch diff.
- **Fix cycles:** open blockers or a failing battery start up to three cycles of a separate fixer and a QA re-run.
- **Exit:** the conductor writes the `review` and `qa` entries. `phase-gate.sh verify` passes when the latest `qa` entry has a passing `Ran:` line for every `qa_battery` command and a `Commit:` hash that exists, no source, test or fixture file changed since that commit, and no blocker is open.

### Goal runs and the Stop gate

`pd-stop-gate.sh` fires on every stop:

- **Charge:** it adds the session's new token usage to the checked-out feature.
- **Arm:** it acts only while a feature's `## Now` holds this session's `goal:` line.
- **Yield:** it lets the stop through while a background workflow or subagent is running.
- **Block** (exit 2, one reason on stderr), checked in this order:
  - **budget:** the feature has used its `feature_token_budget` (or the latest raise recorded in a `decision` entry): ask the user to continue or stop.
  - **stuck:** no commit on the feature branch and no change to `log.md` or the README since the last block: ask the user.
  - **unmet:** an open blocker, a `pd-lint` failure, or the target phase not reached: keep working.
  - **met:** clear the `goal:` line from `## Now`, commit, then stop.

State, outside git:
- `~/.claude/pd/gate/<session id>.json` — the progress snapshot and `calvin_ledger` (the one path `calvin-runner` may write, enforced by `pd-agent-write-guard.sh`).
- `~/.claude/pd/gate/<repo key>/<feature id>.json` — the running token total and the original budget. `<repo key>` is the first 16 hex characters of the sha256 of the origin URL, or of the repository path when there is no origin.

## Module Interfaces

- **`scripts/pd_common.py`** — the shared library: config (`load_config`, `artifacts_dir`), items (`find_items`, `split_frontmatter`), logs (`split_log`, `parse_log`, `parse_tasks`) and the computed views (`open_blockers`, `open_assumptions`, `retro_triggers`). Every Python script and `phase-gate.sh` import it (`pd-proof` and `pd-review-filter` only for its self-test helper `Checks`); none keeps a cache.
- **The scripts' CLIs** — [api-reference.md](api-reference.md).
- **Workflow results** — each workflow script pins its own `RESULT` schema, `plugins/pd/references/workflow-results.md` restates it, and `test-workflows.mjs` checks that the two agree.
- **Log entries** — pinned once in `plugins/pd/references/log-entries.md`; `pd-lint` checks each entry's shape.

## Hooks

The hooks, their events and their purpose: [README_FOR_DEV.md's hooks table](../../README_FOR_DEV.md#hooks). Which ones block, and how:

- **Block with exit 2, the reason on stderr:**
  - **`pd-commit-lint`** (PreToolUse Bash): a `git commit` whose staged artifacts fail `pd-lint --staged`. A linter crash or usage error is reported and never blocks.
  - **`pd-agent-write-guard`** (PreToolUse Write|Edit): a `qa-executor` write outside `agent_sandbox/`, or a `calvin-runner` write anywhere but its recorded ledger path. It fails closed: when its own check fails, the write is refused.
  - **`pd-stop-gate`** (Stop): the stop, for the reasons in [Goal runs and the Stop gate](#goal-runs-and-the-stop-gate).
- **Never block:** `cleanup-stale-versions`, `pd-session-start`, `pre-commit-guard` (its reminders reach Claude as `additionalContext`) and `pre-edit-unicode-guard` (it warns on stderr).

**Broken-pipe rule:** a hook that writes JSON keeps `trap '' PIPE` and writes through `safe_emit_hook_json` (`hooks/lib/session-start-helpers.sh`). `pre-edit-unicode-guard.sh` doesn't follow it yet. See [hook-development.md](../dev-guide/hook-development.md).
