---
last-updated: 2026-10-15T12:00:00Z
source-feature: thin-pd (docs/plans/2026-10-14-thin-pd-native-design.md)
audit-feature: 098-tier-doc-frontmatter-sweep
---

# Workflow Artifacts

Index of the files the pd workflow commits. Templates: `plugins/pd/templates/`. Entry shapes: `plugins/pd/references/log-entries.md`.

## Per-Feature Directory

`{artifacts_root}/features/<id>/`, where `<id>` is `YYYY-MM-DD-slug` (made by `pd-new feature`):

| File | Written by | Holds |
|------|-----------|-------|
| `README.md` | `pd-new`, then every stage | Frontmatter (`id`, `type`, `title`, `status`, `phase`, `mode`, `origin`, `branch`, `risk`, `issue`) and `## Now`, overwritten, never appended |
| `log.md` | every stage | Append-only entries: `decision`, `phase`, `review`, `qa`, `gate`, `run`, `handoff`, `replan`, `metrics`, `defect`, `note`, `capped` |
| `shape.md` | specify (`## Requirements`), design (`## Design`) | B-numbered expectations; then the architecture diagram, contracts pinned once, decisions, risks and test strategy. Express: a mini-spec with one task block |
| `plan.md` | create-plan | `## Plan`: waves of task blocks, each with its contract, files, proving command, JUnit path and test cases |
| `retro.md` | retrospecting (finish) | Only when `log.md` records a retro trigger |

## Other Items

| Path | Made by | Holds |
|------|---------|-------|
| `plans/<id>.md` | `pd-new plan` | A multi-feature plan and its `roadmap:` |
| `brainstorms/<id>.md` | `pd-new brainstorm` | A PRD, with its `## Log` |
| `rca/<id>.md` | `pd-new rca` | A root-cause report, with its `## Log` |
| `backlog.md` | `pd-new backlog` | One line per idea; `pd-lint --archive` moves ticked lines to `backlog-archive.md` |

## Checks

- **`phase-gate.sh <phase> <feature dir> [--express]`** — what each phase hands down: artifacts, sections, the design's diagram and test strategy, duplicate contract blocks, and the `log.md` entries the phase owes. Zero dispatch.
- **`pd-lint`** — the artifact rules, run on staged items by the commit hook; it re-runs the gates for every phase a feature has passed.

## Generated, Never Committed

- `docs/_html/` — `pd-html.py` renders.
- `agent_sandbox/` — QA output, JUnit files, scratch work.
- `.claude/worktrees/` — task worktrees.

Features from before thin pd keep their original layouts until `/pd:adopt` migrates the project.
