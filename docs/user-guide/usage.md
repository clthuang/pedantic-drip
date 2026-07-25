---
last-updated: 2026-07-25T12:00:00Z
source-feature: 134-workflow-rebuild
audit-feature: 098-tier-doc-frontmatter-sweep
---

<!-- AUTO-GENERATED: START - source: 134-workflow-rebuild -->
# Usage

## Quick Start

The easiest entry point is `/pd:secretary`. It triages your request into a mode — deep, express, or specialist — states its rationale, and routes:

```bash
/pd:secretary "add email validation to the signup form"
```

Or start directly:

```bash
/pd:brainstorm "your idea here"    # Explore an idea, produce a PRD
/pd:create-feature "add user auth" # Start a deep feature
/pd:create-feature --express "fix the off-by-one in pagination"  # Express lane
```

## The Deep Workflow

Features move through phases in sequence; the workflow engine validates every transition and owns all state:

```bash
/pd:specify        # shape.md ## Requirements
/pd:design         # shape.md ## Design  → design review (1 of 2)
/pd:create-plan    # plan.md (tasks derive at dispatch time)
/pd:implement      # code + tests → QA agent + code review (2 of 2)
/pd:finish-feature # QA battery, retro, merge, cleanup
```

Phase boundaries are checked mechanically (`scripts/phase-gate.sh`: artifact existence, required sections, duplicate-contract detection) at zero dispatch cost. LLM review happens at exactly two moments — design review and adversarial code review — each running one pass, at most one fix round, then escalating anything left to you. Security-surface diffs get a conditional third review (`pd:security-reviewer`) at finish.

**`/pd:implement` — parallel task execution:** parallel-safe tasks are dispatched in git worktrees under `.pd-worktrees/` (gitignored); merge conflicts halt with details for manual resolution. The `qa-executor` agent then verifies by RUNNING — suites, end-to-end flows, edge cases — and returns evidence, not opinions.

### Rework

Backward moves are engine-recorded: `record_backward_event` captures source, target, and reason, and reviewer notes live on each phase's completed event. Re-entering a phase, the engine's event history is the context — query it via `/pd:show-status` or `get_phase`; there is no injected prose block to maintain.

## The Express Lane

For small, low-uncertainty changes:

```bash
/pd:create-feature --express "the change, stated as a mini-spec"
/pd:implement      # mini-spec is the plan; one combined QA+review pass
/pd:finish-feature
```

The mini-spec is recorded as a `mini_spec` event (the audit record — no artifact files exist); skipped phases are recorded as `skipped` events. Same entity, same tracking, same finish. If the change turns out bigger than it looked, escalation goes backward to specify with the mini-spec as input — no restart penalty.

## Check Progress

```bash
/pd:show-status      # Engine state for active features, brainstorms, backlog
/pd:list-features    # All features by status
```

## Autonomous Mode (YOLO)

```bash
/pd:yolo on                                # Enable
/pd:secretary "add user auth"              # Triage + run end-to-end
/pd:yolo off                               # Back to manual
```

One global rule (workflow-transitions skill): auto-select recommended options, propagate the flag into every dispatch, keep going through recoverable errors. Hard stops in every mode: engine transition rejection, merge conflicts, a review gate still failing after its fix round, and safety keywords.

## Project-Level Work

```bash
/pd:create-project "prd description"   # Decompose a PRD into planned features
```

## Utilities

| Command | What it does |
|---------|-------------|
| `/pd:add-to-backlog <idea>` | Capture an idea without starting a feature |
| `/pd:retrospect` | Run a retrospective on a feature |
| `/pd:show-lineage` | Display entity relationships |
| `/pd:doctor` | Check workspace health |
| `/pd:cleanup-brainstorms` | Archive old brainstorm files |

## File Layout

pd creates files under your project's `docs/` directory (configurable via `artifacts_root`):

```
docs/
├── brainstorms/           # Brainstorm PRDs
├── features/{id}-{name}/  # Feature artifacts
│   ├── prd.md             # Promoted brainstorm (when one existed)
│   ├── shape.md           # ## Requirements + ## Design (one document)
│   ├── plan.md            # Ordered tasks with per-task verification
│   ├── retro.md           # Retrospective (written before cleanup)
│   └── .meta.json         # READ-ONLY projection of engine state
└── projects/{id}-{name}/  # Project PRDs and roadmaps
```

Express features have no artifact files — their record is the event stream (mini_spec + skipped events), which `.meta.json` projects. State lives in the entity DB; `.meta.json` is a generated projection — never hand-edit it.
<!-- AUTO-GENERATED: END -->
