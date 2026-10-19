---
last-updated: 2026-10-18T06:00:00Z
source-workitem: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# pd Plugin — Overview

pd is a Claude Code plugin that turns an idea into a merged change through fixed stages. Each stage hands the next one a committed file; from Criteria on, a script checks that hand-off before the stage closes.

## What pd Does

- **Stages in order:** Clarify (brainstorm or RCA), Criteria (`specify`), Contracts (`design`), Plan (`create-plan`), Execute (`implement`), Verify (`verify`), Finish (`finish`).
- **State in committed files:** each work item is a folder under `{pd_artifacts_root}/workitems/<id>/` (default `docs/dev_artifacts/`) holding `README.md` (status, phase, mode, `## Now`), `log.md` (append-only history), `shape.md` and `plan.md`. Nothing lives in a database.
- **Mechanical checks:** `phase-gate.sh` checks what each stage from Criteria to Finish must hand down (Clarify has no exit check); the commit hook runs `pd-lint --staged` before every `git commit` Claude runs. Commits you type in a terminal aren't checked.
- **Review calls** at Contracts, Plan and Verify: Codex first unless your CLAUDE.md says `**Codex reviewer: DISABLED**`, otherwise (or when Codex fails twice) a Claude reviewer; one pass, up to three fix cycles against runnable checks, then you.
- **Three depths:** standard, small (one joint review over design and plan) and express (a mini-spec, straight to implement).

## Key Features

### Tests first, proven per task

`/pd:implement` runs the `implement-tasks` workflow: one `implementer` per plan task, each in its own worktree on a `pd/<id>/task-<n>` branch. The `merger` lands a task only if its tests failed at the task's first commit and pass at its head (`pd-proof`). A `proof: green-only` task (a refactor, infra or fixture task) needs only the passing run at its head.

### Verify: review beside QA

`/pd:verify` runs `verify-change`: the code review and `qa-executor` (which runs your `qa_battery` and reports, fixing nothing) side by side, then up to three cycles of a separate fixer and a QA re-run.

### Long runs with `/goal`

A `/goal` run drives a work item to a target phase. The Stop hook (`pd-stop-gate.sh`) holds the run until the target is reached with no open blocker and `pd-lint` passing, yields to running workflows, and asks "continue or stop?" at the per-work-item token budget.

### Security review at finish

`pd:security-reviewer` runs at `/pd:finish-workitem`, on Anthropic models:

- **Always** for a work item tagged `risk: security`.
- **Otherwise when the branch diff touches a security surface:** auth, secrets, input parsing at a trust boundary, permissions, data deletion, dependency bumps.

A blocker sends the work item back to Verify, where the fixer gets a fresh three fix cycles.

### Retros on a trigger

A retro runs only when `log.md` records a trigger (a second backward move, a cap, a cost overrun, a post-merge defect); otherwise finish writes one `note` entry.

### Domain Knowledge

- **Data science** — methodology assessment, pitfall analysis, modeling approach

## How the Workflow Fits Together

The stages run in the order above. A backward move sets `phase:` back and appends a `phase <from> -> <to> (back)` entry naming its reason and what it invalidates. Express work items skip specify's full criteria, design and create-plan: the mini-spec in `shape.md` carries the one task.
