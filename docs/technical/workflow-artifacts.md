---
last-updated: 2026-10-18T06:00:00Z
source-workitem: thin-pd (docs/dev_artifacts/plans/2026-10-14-thin-pd-native-design.md)
---

# Workflow Artifacts

Index of the files the pd workflow commits. Templates: `plugins/pd/templates/`. Entry shapes: `plugins/pd/references/log-entries.md`.

## Per-Work-Item Directory

`{pd_artifacts_root}/workitems/<id>/` (default root `docs/dev_artifacts`), where `<id>` is `YYYY-MM-DD-slug` (made by `pd-new workitem`):

| File | Written by | Holds |
|------|-----------|-------|
| `README.md` | `pd-new`, then every stage | Frontmatter (`id`, `type`, `title`, `status`, `phase`, `mode`, `origin`, `branch`, `risk`, `issue`) and `## Now`, overwritten, never appended |
| `log.md` | every stage | Append-only entries: `decision`, `phase`, `review`, `qa`, `gate`, `run`, `handoff`, `replan`, `metrics`, `defect`, `note`, `capped` |
| `shape.md` | specify (`## Requirements`), design (`## Design`) | B-numbered expectations; then the architecture diagram, contracts pinned once, decisions, risks and test strategy. Express: a mini-spec with one task block |
| `plan.md` | create-plan | `from_shape:` frontmatter (`git hash-object shape.md` when the plan was derived; `pd-lint` fails a stale one), then `## Plan`: waves of task blocks, each with its contract, files, `uses:`, proving command, JUnit path and test cases |
| `retro.md` | retrospecting (finish) | Only when `log.md` records a retro trigger |

## Other Items

| Path | Made by | Holds |
|------|---------|-------|
| `plans/<id>.md` | `pd-new plan` | A multi-item plan: `pd-new` writes the frontmatter, `## Now`, `## Links` and `## Log`; the `roadmap:` frontmatter follows `templates/plan-roadmap.md` |
| `brainstorms/<id>.md` | `pd-new brainstorm` | A PRD, with its `## Log` |
| `rca/<id>.md` | `pd-new rca` | A root-cause report, with its `## Log` |
| `backlog.md` | `pd-new backlog` | One line per idea; `pd-lint --archive` moves ticked lines to `backlog-archive.md` |

## Checks

- **`phase-gate.sh <phase> <work item dir> [--express]`** — what each phase hands down: artifacts, sections, the design's diagram and test strategy, duplicate contract blocks, and the `log.md` entries the phase owes. Runs no agent.
- **`pd-lint`** — the artifact rules, run on staged items by the commit hook; it re-runs the gates for every phase a work item has passed, except the verify gate on a done or abandoned work item. An express work item runs the mini-spec check in place of the specify, design and create-plan gates.

## Generated, Never Committed

- `docs/_html/` — `pd-html.py` renders.
- `agent_sandbox/` — QA output, JUnit files, scratch work.
- `.claude/worktrees/` — task worktrees.

Work items from before thin pd keep their original layouts until `/pd:adopt` migrates the project.
