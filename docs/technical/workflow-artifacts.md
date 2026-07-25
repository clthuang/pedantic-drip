---
last-updated: 2026-07-25T12:00:00Z
source-feature: 134-workflow-rebuild
audit-feature: 098-tier-doc-frontmatter-sweep
---

<!-- AUTO-GENERATED: START - source: 134-workflow-rebuild -->

# Workflow Artifacts

Index of file artifacts produced by the pd workflow. Feature 134 cut the deep-mode inventory to three documents plus the projection; everything else the old flow maintained (tasks.md, implementation-log.md, .review-history.md, the .qa-gate sidecar family) is retired — their information now lives in the engine's event stream or in git.

## Per-Feature Artifact Directory

`{artifacts_root}/features/{id}-{slug}/`:

| File | Produced by | Purpose |
|------|-------------|---------|
| `prd.md` | brainstorm promotion (`create-feature --prd=`) | Problem statement and proposed solution, when a brainstorm preceded the feature |
| `shape.md` | specify (`## Requirements`) + design (`## Design`) | One document: mechanically checkable success criteria, scope, edge cases; then decisions with rationale, contracts pinned once, risks, test strategy |
| `plan.md` | create-plan | Ordered tasks derived from `## Design` at dispatch time — deliverable, files, verification command, `[parallel-safe]` markers |
| `retro.md` | retrospecting skill (finish, before cleanup) | Retrospective assembled from engine events, git, and the workaround extractor |
| `.meta.json` | `_project_meta_json()` (MCP mutations only) | READ-ONLY projection of engine state for humans and tooling; never hand-edited (deny-by-default guard) |

Express features produce no artifact files: the mini-spec is a `mini_spec` phase event (text in metadata, read back via `get_mini_spec`), and skipped phases are `skipped` events. `retro.md` is still expected at finish.

## Where the Old Artifacts' Information Went

| Retired file | Now lives in |
|--------------|--------------|
| `spec.md` / `design.md` | `shape.md` (two sections, one document) |
| `tasks.md` | `plan.md` tasks, derived at dispatch time |
| `implementation-log.md` | commit messages + phase events |
| `.review-history.md` | reviewer notes on each phase's `completed` event |
| `.qa-gate.json` / `.qa-gate.log` / `.qa-gate-low-findings.md` / `qa-override.md` | the two review moments' findings land as reviewer notes; test debt arrives as backlog rows (`test-debt-report` still reads historical `.qa-gate.json` files) |

## Mechanical Gates

`scripts/phase-gate.sh <phase> <feature-dir> [--express]` checks artifact existence, required sections, and duplicate contract blocks at each phase boundary — zero dispatch cost. `--express` skips the artifact checks that express features never have.

## Technical Documentation

Feature-level docs live in `docs/features/{id}-{slug}/` alongside the artifacts; historical features keep their original artifact sets (spec.md-era layouts are not migrated).
<!-- AUTO-GENERATED: END -->
