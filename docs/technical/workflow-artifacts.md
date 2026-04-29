---
last-updated: 2026-04-29T00:00:00Z
source-feature: 078-cc-native-integration
audit-feature: 098-tier-doc-frontmatter-sweep
---

<!-- AUTO-GENERATED: START - source: 078-cc-native-integration -->

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
| `implementation-log.md` | implementer agent (or direct-orchestrator per feature 096 retro Tune #2) | Per-task decisions, deviations, concerns, T0 baselines, tooling-friction notes (deleted after retro per finish-feature Step 6b) |
| `retro.md` | retrospecting skill | AORTA retrospective findings and knowledge bank updates; folds `.qa-gate-low-findings.md` and `.qa-gate.log` sidecars per Step 2c (FR-7b) |
| `qa-override.md` | finish-feature Step 5b (manual) | Required when QA gate produces HIGH findings; ≥50-char user-authored rationale unblocks merge (feature 094) |
| `.qa-gate.log` / `.qa-gate.json` / `.qa-gate-low-findings.md` | finish-feature Step 5b (transient sidecars, gitignored) | Per-reviewer audit log + idempotency cache (head_sha) + LOW-finding deferral; folded into retro.md by retrospecting skill |

## .meta.json Schema

The `.meta.json` file is the primary read surface for a feature's workflow state. It is always regenerated from authoritative sources (entity DB + workflow engine) and must never be written directly. See `docs/technical/api-reference.md` for the full field reference.

Notable schema fields added since the source feature (078):
- `phase_summaries` (array) — per workflow-transitions skill Step 3a; one entry per completed phase with key decisions, artifacts, reviewer notes
- `backward_context` (object) — populated when a reviewer triggers backward travel; contains the referral message and target phase
- `backward_return_target` (string) — phase to return to after rework completes
- `backward_history` (array) — historical record of all backward transitions for the feature

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
| [ADR-004](decisions/ADR-004-parallel-worktree-dispatch.md) | Parallel Worktree Dispatch for Implementing Skill | Accepted |
| [ADR-005](decisions/ADR-005-two-tier-worktree-fallback.md) | Two-Tier Fallback Strategy for Worktree Dispatch | Accepted |
| [ADR-006](decisions/ADR-006-security-review-integration-via-natural-language.md) | Security Review Integration via Natural Language Instruction | Accepted |

## Feature Artifacts Index

Recent feature artifacts (latest features):

| Feature | Status | Artifacts | Notes |
|---------|--------|----------|-------|
| [094-pre-release-qa-gate](../features/094-pre-release-qa-gate/) | Completed | prd.md, spec.md, design.md, plan.md, tasks.md, retro.md | Introduced finish-feature Step 5b adversarial QA gate (4 reviewers parallel). |
| [095-test-hardening-iso8601](../features/095-test-hardening-iso8601/) | Completed | prd.md, spec.md, design.md, plan.md, tasks.md, retro.md | Test hardening sweep: source-pin tests for `_ISO8601_Z_PATTERN`. First production exercise of feature 094 QA gate. |
| [096-iso8601-pattern-relocation](../features/096-iso8601-pattern-relocation/) | Completed | prd.md, spec.md, design.md, plan.md, tasks.md, retro.md, implementation-log.md | Relocated `_ISO8601_Z_PATTERN` to `_config_utils.py`. Closed recursive test-hardening cycle. SECOND QA gate exercise. |
| [097-iso8601-test-pin-v2](../features/097-iso8601-test-pin-v2/) | Completed | spec.md, design.md, plan.md, tasks.md, retro.md, implementation-log.md, qa-override.md | TestIso8601PatternSourcePins v2 refactor (8 sub-items + bonus identity-pin). THIRD QA gate exercise; HIGH findings overridden as recursive test-hardening per anti-pattern. |
| [098-tier-doc-frontmatter-sweep](../features/098-tier-doc-frontmatter-sweep/) | In progress | (this audit) | Tier-doc frontmatter drift sweep using parallel audit subagents. |

<!-- AUTO-GENERATED: END -->
