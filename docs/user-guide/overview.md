---
last-updated: 2026-10-15T12:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
audit-feature: 098-tier-doc-frontmatter-sweep
---

# pd Plugin — Overview

pd is a Claude Code plugin that turns an idea into a merged feature through fixed stages. Each stage hands the next one a committed file, and a script checks that hand-off before the stage closes.

## What pd Does

- **Stages in order:** Clarify (brainstorm or RCA), Criteria (`specify`), Contracts (`design`), Plan (`create-plan`), Execute (`implement`), Verify (`verify`), Finish (`finish-feature`).
- **State in committed files:** each feature is a folder under `docs/dev_artifacts/features/<id>/` holding `README.md` (status, phase, mode, `## Now`), `log.md` (append-only history), `shape.md` and `plan.md`. Nothing lives in a database.
- **Mechanical checks:** `phase-gate.sh` checks what each stage must hand down; the commit hook runs `pd-lint --staged` before every `git commit`.
- **Review calls** at Contracts, Plan and Verify: Codex first, else a Claude reviewer; one pass, up to three fix cycles against runnable checks, then you.
- **Three depths:** standard, small (one joint review over design and plan) and express (a mini-spec, straight to implement).

## Key Features

### Tests first, proven per task

`/pd:implement` runs the `implement-tasks` workflow: one `implementer` per plan task, each in its own worktree on a `pd/<id>/task-<n>` branch. The `merger` lands a task only if its tests failed at the task's first commit and pass at its head (`pd-proof`).

### Verify: review beside QA

`/pd:verify` runs `verify-change`: the code review and `qa-executor` (which runs your `qa_battery` and reports, fixing nothing) side by side, then up to three cycles of a separate fixer and a QA re-run.

### Long runs with `/goal`

A `/goal` run drives a feature to a target phase. The Stop hook (`pd-stop-gate.sh`) holds the run until the target is reached with no open blocker and `pd-lint` passing, yields to running workflows, and asks "continue or stop?" at the per-feature token budget.

### Security review at finish

`pd:security-reviewer` runs at `/pd:finish-feature`, on Anthropic models; it is mandatory for a feature tagged `risk: security`. Its findings block the merge until fixed or waived in a `decision` entry.

### Retros on a trigger

A retro runs only when `log.md` records a trigger (a second backward move, a cap, a cost overrun, a post-merge defect); otherwise finish writes one `note` entry.

### Domain Knowledge

- **Game design** — core loop analysis, engagement strategy, feasibility
- **Crypto/DeFi** — protocol comparison, tokenomics, risk assessment
- **Data science** — methodology assessment, pitfall analysis, modeling approach

## How the Workflow Fits Together

```
brainstorm / rca → specify → design → create-plan → implement → verify → finish
                      ↑______________ backward move (phase <from> -> <to> (back)) ___|
```

A backward move sets `phase:` back and appends a `phase` entry naming its reason and what it invalidates. Express features skip specify's full criteria, design and create-plan: the mini-spec in `shape.md` carries the one task.
