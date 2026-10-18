---
last-updated: 2026-10-18T06:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# Architecture Overview

A map of the plugin's components and how they connect. Read this before diving into one area.

## Top-Level Model

```
User
 ├── /pd:<stage>        → Command (thin entry point) → Stage skill (the conductor's playbook)
 │                            ├── scripts (pd-new, phase-gate.sh, pd-lint, pd-status, …)
 │                            ├── workflows (implement-tasks, verify-change, …) → Agents
 │                            └── direct dispatches (the review call, calvin-runner, security-reviewer, retro-facilitator, …) → Agents
 └── /pd:secretary <req> → triage → a stage command, or a specialist agent, skill or command
```

The main session is the **conductor**: it asks the user, writes the files and commits. Workflows and agents return results; they never write state. State lives in committed files under `{pd_artifacts_root}` (default `docs/dev_artifacts/`); everything else is computed from them by `pd-status`.

## Component Locations

| Component | Location | Notes |
|-----------|----------|-------|
| Skills | `plugins/pd/skills/{name}/SKILL.md` | |
| Agents | `plugins/pd/agents/{name}.md` | |
| Commands | `plugins/pd/commands/{name}.md` | |
| Hooks | `plugins/pd/hooks/` | each `.sh` is registered in `hooks.json`; `pre-edit-unicode-guard.py` is a worker its `.sh` wrapper runs |
| Workflows | `plugins/pd/workflows/*.js` | listed under [Workflows](#workflows) |
| Scripts | `plugins/pd/scripts/` | see [api-reference.md](../technical/api-reference.md) |
| References | `plugins/pd/references/` | entry shapes, result schemas, the review call |
| Templates | `plugins/pd/templates/` | README, log, shape, plan, roadmap, retro, and `doc.css` (the stylesheet `pd-html.py` embeds) |

The component counts live in [plugins/pd/README.md](../../plugins/pd/README.md#components), checked by `scripts/check-doc-drift.sh`.

## Stages and Phases

```
Clarify (brainstorm | rca) → specify → design → create-plan → implement → verify → finish
```

A feature's README frontmatter holds `phase:`, one of `specify`, `design`, `create-plan`, `implement`, `verify`, `finish`. Clarify happens on a brainstorm or rca item, before the feature exists.

`workflow-transitions` is the contract every stage skill shares:

- **Phase entry:** resolve the feature (argument, branch, or `pd-status`), check out its branch, read the README, `## Now` and the open blockers.
- **Phase exit:** `phase-gate.sh <phase> <feature dir>` passes; set `phase:` to the next phase, append a `phase <from> -> <to>` entry, overwrite `## Now`, commit `<phase>: <summary>`.
- **Backward move:** set `phase:` back and append `phase <from> -> <to> (back)` with `Reason:` and `Invalidates:`.
- **Review call** (`references/review-call.md`): Codex first with one retry unless the user's CLAUDE.md says `**Codex reviewer: DISABLED**`, else the stage's Claude reviewer; one pass, up to three fix cycles against runnable checks, then the user.
- **Workflow runs:** write `run in flight:` to `## Now` before launching; append the `run`, `review`, `qa` and `gate` entries from the result.
- **Goal runs:** `goal: <id> target <phase> session <id>` in `## Now`; the Stop hook decides when the run may stop.

## Workflows

| Workflow | Stage | What it does |
|----------|-------|--------------|
| `implement-tasks` | Execute | One `implementer` per plan task in its own worktree; the `merger` lands each in plan order after `pd-proof`; up to three fix cycles |
| `verify-change` | Verify | The review call beside `qa-executor`, then up to three cycles of a separate fixer and a QA re-run |
| `research-fanout` | Clarify | Researchers, one `advisor` per lens, then `ras-synthesizer` |
| `rca-fanout` | Clarify | One investigator per hypothesis, then a refuter for each supported one |

Each checks `workflow_output_cap` before every agent and returns `stopped: "budget"` with partial results at the cap. Each script pins its result schema, and `references/workflow-results.md` restates it; `test-workflows.mjs` checks they agree.

## Agents

- **Reviewers:** `design-reviewer`, `plan-reviewer`, `code-quality-reviewer` (each preloads its stage skill's `## Review checklist`), `security-reviewer` (finish), `ds-analysis-reviewer`, `ds-code-reviewer`.
- **Workers:** `implementer`, `qa-executor`, `generic-worker`, `documentation-writer`, `ras-synthesizer`.
- **Researchers:** `codebase-explorer`, `documentation-researcher`, `internet-researcher`, `investigation-agent`, `skill-searcher`, `rca-investigator` (the investigator and refuter `rca-fanout` runs).
- **Advisory:** `advisor`.
- **Orchestration:** `merger`, `calvin-runner`, `retro-facilitator`.

Each agent's frontmatter sets its `model:` and `tools:` (and `effort:` where its role requires one); `validate.sh` checks the roles' limits.

## Hooks

Each hook, its trigger and what it does: [README_FOR_DEV.md](../../README_FOR_DEV.md#hooks). They are registered in `plugins/pd/hooks/hooks.json`.

## Design Principles

| Principle | Meaning |
|-----------|---------|
| Everything is prompts | Skills and agents are instruction files; the scripts only check and compute |
| Files are truth | State is committed markdown; any session resumes from it |
| Checks over prose | A rule a script can check lives in `phase-gate.sh` or `pd-lint`, not in a skill |
| Humans unblock | Every hard stop is an AskUserQuestion, never a loop to a cap |
| No backward compatibility | Private tooling — delete old code, no shims |
