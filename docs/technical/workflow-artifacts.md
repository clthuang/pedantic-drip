---
last-updated: 2026-04-02T00:00:00Z
source-feature: codebase-analysis
---

<!-- AUTO-GENERATED: START - source: codebase-analysis -->

# Workflow Artifacts

Index of file artifacts produced by the pd workflow and their feature-level documentation.

## Per-Feature Artifact Directory

Each feature has a directory under `docs/features/{feature-id}/` containing:

| File | Produced by | Purpose |
|------|------------|---------|
| `.meta.json` | `_project_meta_json()` | Machine-readable workflow state; regenerated on every phase transition |
| `prd.md` | brainstorm skill | Problem statement, strategic analysis, proposed solution |
| `spec.md` | specifying skill | Acceptance criteria, scope, API contracts |
| `design.md` | designing skill | Architecture, component map, interfaces, technical decisions |
| `plan.md` | planning skill | Ordered implementation plan with dependencies |
| `tasks.md` | breaking-down-tasks skill | Atomic task list with dependency graph |
| `impl-log.md` | implementer agent | Per-task decisions, deviations, and concerns (deleted after retro) |
| `retro.md` | retrospecting skill | AORTA retrospective findings and knowledge bank updates |

## .meta.json Schema

The `.meta.json` file is the primary read surface for a feature's workflow state. It is always regenerated from authoritative sources (entity DB + workflow engine) and must never be written directly. See `docs/technical/api-reference.md` for the full field reference.

## Knowledge Bank

`docs/knowledge-bank/` accumulates learnings from retrospectives:

| File | Content |
|------|---------|
| `constitution.md` | Core principles (KISS, YAGNI, etc.) |
| `patterns.md` | Approaches that have worked |
| `anti-patterns.md` | Things to avoid |
| `heuristics.md` | Decision guides |

## Technical Documentation

| Document | Purpose |
|----------|---------|
| `docs/technical/architecture.md` | Component map, data flow, module interfaces |
| `docs/technical/api-reference.md` | Internal API contracts (MCP tools, metadata schemas) |
| `docs/technical/workflow-artifacts.md` | This file — artifact index |
| `docs/technical/decisions/` | Architecture Decision Records |

## ADRs

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](decisions/ADR-001-phase-summaries-append-list.md) | Phase Summaries Append-List Storage | Accepted |
| [ADR-002](decisions/ADR-002-update-entity-for-summary-storage.md) | update_entity for Summary Storage | Accepted |
| [ADR-003](decisions/ADR-003-backward-transition-detection-via-completed-timestamp.md) | Backward Transition Detection via Completed Timestamp | Accepted |

## Feature Artifacts Index

Recent feature artifacts (latest features):

| Feature | Status | Artifacts |
|---------|--------|----------|
| [075-phase-context-accumulation](../features/075-phase-context-accumulation/) | In progress | prd.md, spec.md, design.md, plan.md, tasks.md |

<!-- AUTO-GENERATED: END -->
