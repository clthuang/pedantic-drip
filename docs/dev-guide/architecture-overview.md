---
last-updated: 2026-10-15T12:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
---

# Architecture Overview

A map of the plugin's components and how they connect. Read this before diving into one area.

## Top-Level Model

```
User
 ├── /pd:<stage>        → Command (thin entry point) → Stage skill (the conductor's playbook)
 │                            ├── scripts (pd-new, phase-gate.sh, pd-lint, pd-status, …)
 │                            └── workflows (implement-tasks, verify-change, …) → Agents
 └── /pd:secretary <req> → triage → a stage command, or a specialist agent
```

The main session is the **conductor**: it asks the user, writes the files and commits. Workflows and agents return results; they never write state. State lives in committed files under `{artifacts_root}` (default `docs/dev_artifacts/`); everything else is computed from them by `pd-status`.

## Component Locations

| Component | Location | Count |
|-----------|----------|-------|
| Skills | `plugins/pd/skills/{name}/SKILL.md` | 24 |
| Agents | `plugins/pd/agents/{name}.md` | 21 |
| Commands | `plugins/pd/commands/{name}.md` | 25 |
| Hooks | `plugins/pd/hooks/*.sh` | 8 scripts, all registered |
| Workflows | `plugins/pd/workflows/*.js` | 4 |
| Scripts | `plugins/pd/scripts/` | see [api-reference.md](../technical/api-reference.md) |
| References | `plugins/pd/references/` | entry shapes, result schemas, the review call |
| Templates | `plugins/pd/templates/` | README, log, shape, plan, roadmap, retro |

## Stages and Phases

```
Clarify (brainstorm | rca) → specify → design → create-plan → implement → verify → finish
```

A feature's README frontmatter holds `phase:`, one of `specify`, `design`, `create-plan`, `implement`, `verify`, `finish`. Clarify happens on a brainstorm or rca item, before the feature exists.

`workflow-transitions` is the contract every stage skill shares:

- **Phase entry:** resolve the feature (argument, branch, or `pd-status`), check out its branch, read the README, `## Now` and the open blockers.
- **Phase exit:** `phase-gate.sh <phase> <feature dir>` passes; set `phase:` to the next phase, append a `phase <from> -> <to>` entry, overwrite `## Now`, commit `<phase>: <summary>`.
- **Backward move:** set `phase:` back and append `phase <from> -> <to> (back)` with `Reason:` and `Invalidates:`.
- **Review call** (`references/review-call.md`): Codex first with one retry, else the stage's Claude reviewer; one pass, up to three fix cycles against runnable checks, then the user.
- **Workflow runs:** write `run in flight:` to `## Now` before launching; append the `run`, `review`, `qa` entries from the result.
- **Goal runs:** `goal: <id> target <phase> session <id>` in `## Now`; the Stop hook decides when the run may stop.

## Workflows

| Workflow | Stage | What it does |
|----------|-------|--------------|
| `implement-tasks` | Execute | One `implementer` per plan task in its own worktree; the `merger` lands each in plan order after `pd-proof`; up to three fix cycles |
| `verify-change` | Verify | The review call beside `qa-executor`, then up to three cycles of a separate fixer and a QA re-run |
| `research-fanout` | Clarify | Researchers, one `advisor` per lens, then `ras-synthesizer` |
| `rca-fanout` | Clarify | One investigator per hypothesis, then a refuter for each supported one |

Each checks `workflow_output_cap` before every agent and returns `stopped: "budget"` with partial results at the cap. Results are pinned in `references/workflow-results.md`.

## Agents

- **Reviewers:** `design-reviewer`, `plan-reviewer`, `code-quality-reviewer` (each preloads its stage skill's `## Review checklist`), `security-reviewer` (finish), `ds-analysis-reviewer`, `ds-code-reviewer`.
- **Workers:** `implementer`, `qa-executor`, `generic-worker`, `documentation-writer`, `ras-synthesizer`.
- **Researchers:** `codebase-explorer`, `documentation-researcher`, `internet-researcher`, `investigation-agent`, `skill-searcher`.
- **Advisory:** `advisor`.
- **Orchestration:** `merger`, `calvin-runner`, `rca-investigator`, `retro-facilitator`.

Each agent's frontmatter sets its `model:`, `effort:` and `tools:`; `validate.sh` checks the roles' tool limits.

## Hooks

Defined in `plugins/pd/hooks/hooks.json`.

| Hook | Trigger | Purpose |
|------|---------|---------|
| `cleanup-stale-versions` | SessionStart (startup\|resume\|clear) | Deletes cached pd versions other than the active one, except one a running session still uses |
| `pd-session-start` | SessionStart (startup\|resume\|clear\|compact) | The `{pd_*}` values, active and blocked items, next ready items, retros owed; offers `/pd:init` or `/pd:adopt` |
| `pre-commit-guard` | PreToolUse (Bash) | Warns on commits to `main`/`master` |
| `pd-commit-lint` | PreToolUse (Bash) | `pd-lint --staged` before a `git commit`; an error blocks it |
| `pre-edit-unicode-guard` | PreToolUse (Write\|Edit) | Warns on risky Unicode codepoints |
| `pd-agent-write-guard` | PreToolUse (Write\|Edit) | QA writes only under `agent_sandbox/`; `calvin-runner` only its ledger path |
| `pd-stop-gate` | Stop | Holds a `/goal` run until its target is reached; yields to running workflows; the per-feature token cap |

## Design Principles

| Principle | Meaning |
|-----------|---------|
| Everything is prompts | Skills and agents are instruction files; the scripts only check and compute |
| Files are truth | State is committed markdown; any session resumes from it |
| Checks over prose | A rule a script can check lives in `phase-gate.sh` or `pd-lint`, not in a skill |
| Humans unblock | Every hard stop is an AskUserQuestion, never a loop to a cap |
| No backward compatibility | Private tooling — delete old code, no shims |
