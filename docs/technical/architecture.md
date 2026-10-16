---
last-updated: 2026-10-15T12:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
audit-feature: 098-tier-doc-frontmatter-sweep
---

# Architecture

## Overview

pd is a Claude Code plugin: commands, skills, agents, workflows, hooks and a few stdlib scripts. It runs inside Claude Code sessions; there is no server and no database. A feature's state is committed markdown under `{artifacts_root}` (default `docs/dev_artifacts/`), and everything derived — progress, open blockers, retros owed — is computed from those files on demand.

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

**The conductor** (the main session) owns every user decision (through AskUserQuestion) and every file write and commit. Workflows and agents return JSON results; the conductor writes `log.md` from them.

## Key Data Flows

### A phase, start to finish

1. `/pd:<phase>` invokes its stage skill.
2. Phase entry (`workflow-transitions`): resolve the feature, check out `feature/<id>`, read `README.md`, `## Now` and `pd-status`'s open blockers.
3. The skill writes its artifact (`shape.md` or `plan.md`) and, at Contracts and Plan, makes the review call; each review is a `review` entry in `log.md`.
4. Exit: `phase-gate.sh <phase> <dir>` passes; `phase:` moves on; a `phase <from> -> <to>` entry is appended; the commit runs `pd-lint --staged` through `pd-commit-lint`.

### Execute: `implement-tasks`

1. The conductor derives the args from `plan.md` (waves of task blocks) and writes `run in flight:` to `## Now`.
2. Each task runs as one `implementer` in a Claude Code worktree (base: the feature branch's HEAD, via `worktree.baseRef: "head"`), committing its tests first on `pd/<id>/task-<n>`.
3. The `merger` checks the task: the first commit holds only tests and source additions; `pd-proof first` sees every test fail at that commit; `pd-proof head` sees them pass at HEAD; no later commit touches those tests. Then `git merge --no-ff` in plan order, re-running every earlier task's proof and `pd-lint`.
4. A failed task gets up to three fix cycles (cycles 2 and 3 on opus), reusing its branch.
5. The conductor appends a `run` entry with one `task <n>: merged, proof pass, …` line per task, which `phase-gate.sh implement` reads.

### Verify: `verify-change`

The review call (Codex, one retry, else `code-quality-reviewer`) runs beside `qa-executor` (the `qa_battery`, `pd-lint --risk`, `pd-lint --isolation`). Open blockers or a failing battery start up to three cycles of a separate fixer and a QA re-run. The conductor writes the `review` and `qa` entries; `phase-gate.sh verify` needs a passing `qa` entry at the current commit.

### Goal runs and the Stop gate

`pd-stop-gate.sh` fires on every stop. It charges the session's new token usage to the checked-out feature, then blocks (exit 2) only while `## Now` holds this session's `goal:` line and the goal is unmet (target not reached, open blockers, or `pd-lint` failing). It yields to running background workflows and subagents. At `feature_token_budget`, or with no progress since the last block, it tells the conductor to ask the user.

State, outside git:
- `~/.claude/pd/gate/<session id>.json` — the progress snapshot and `calvin_ledger` (the one path `calvin-runner` may write, enforced by `pd-agent-write-guard.sh`).
- `~/.claude/pd/gate/<repo key>/<feature id>.json` — the running token total and the original budget.

## Module Interfaces

- **`scripts/pd_common.py`** — the shared library: config (`load_config`, `artifacts_dir`), items (`find_items`, `split_frontmatter`), logs (`split_log`, `parse_log`, `parse_tasks`) and the computed views (`open_blockers`, `open_assumptions`, `retro_triggers`). Every script imports it; none keeps a cache.
- **The scripts' CLIs** — [api-reference.md](api-reference.md).
- **Workflow results** — pinned once in `plugins/pd/references/workflow-results.md`; `test-workflows.mjs` checks each script's result against it.
- **Log entries** — pinned once in `plugins/pd/references/log-entries.md`; `pd-lint` checks each entry's shape.

## Hooks

| Hook | Event | Blocks? |
|------|-------|---------|
| `cleanup-stale-versions` | SessionStart | no |
| `pd-session-start` | SessionStart | no — injects the `{pd_*}` values and the project summary |
| `pre-commit-guard` | PreToolUse Bash | no — warns on `main`/`master` |
| `pd-commit-lint` | PreToolUse Bash | yes — a `pd-lint --staged` error |
| `pre-edit-unicode-guard` | PreToolUse Write\|Edit | no — warns |
| `pd-agent-write-guard` | PreToolUse Write\|Edit | yes — `qa-executor` outside `agent_sandbox/`, `calvin-runner` outside its ledger path |
| `pd-stop-gate` | Stop | yes — an unmet goal of this session |

Hooks emitting JSON keep `trap '' PIPE` and write through `safe_emit_hook_json` (`hooks/lib/session-start-helpers.sh`).
