---
last-updated: 2026-07-25T12:00:00Z
source-feature: 075-phase-context-accumulation
audit-feature: 098-tier-doc-frontmatter-sweep
---

<!-- AUTO-GENERATED: START - source: 075-phase-context-accumulation -->
# pd Plugin — Overview

pd is a Claude Code plugin that turns ideas into shipped features through structured phases. It guides work from brainstorming through specification, design, planning, implementation, and merge — with built-in quality gates at every step.

## What pd Does

pd imposes a proven workflow on top of Claude Code:

- Each feature moves through phases in order: brainstorm → specify → design → create-plan → implement → finish
- Every phase boundary runs a mechanical gate that checks the artifacts before progression
- Two AI review moments — design review, then adversarial code review — catch issues early, before they compound into later phases
- Small changes take an express lane that skips straight to implement
- A local Kanban board gives a live view of all active work

## Key Features

### Structured Phase Workflow

Features advance through named phases. Two artifacts carry a feature: `shape.md` (requirements from specify, design from design) and `plan.md` (the ordered task list). Each phase boundary runs `scripts/phase-gate.sh`, which must pass before the phase closes.

### Rework

Backward moves are engine-recorded (`record_backward_event`: source, target, reason), and reviewer notes ride each phase's completed event. Re-entering a phase, the event history IS the context — nothing is injected or hand-maintained, and nothing goes stale.

### Autonomous Operation (YOLO Mode)

YOLO mode lets pd run the full workflow without pausing for confirmation at each phase gate. Every gate — mechanical gates, both review moments, QA execution — still runs; only the user confirmation step is bypassed. Three levels are available:

- `manual` — default, confirms at every transition
- `aware` — provides hints about autonomous operation
- `yolo` — fully autonomous end-to-end

### Kanban Board

A local web UI starts automatically at `http://localhost:8718/` each session. It shows all features, brainstorms, backlog items, and projects with their current phase, except archived ones — no setup required.

### Execution-Grounded QA

During `/pd:implement`, the `qa-executor` agent verifies by running, not by reading: it executes the project's test battery, drives every flow the change touches end-to-end, and flags tests that cannot fail. It returns commands and their output as evidence, and fixes nothing. The adversarial `code-quality-reviewer` pass on the branch diff follows it.

At `/pd:finish-feature`, the same battery is re-run on the branch before merge, and `security-reviewer` is dispatched when the change touches a security surface (auth, secrets, input parsing, permissions, data deletion, dependency bumps). Security findings block the merge until fixed or waived in writing.

### Domain Knowledge

Built-in specialist knowledge is available for:

- **Game design** — core loop analysis, engagement strategy, feasibility
- **Crypto/DeFi** — protocol comparison, tokenomics, risk assessment
- **Data science** — methodology assessment, pitfall analysis, modeling approach

## How the Workflow Fits Together

```
brainstorm → specify → design → create-plan → implement → finish
               ↑___________backward rework (with context)___|
```

When a gate or review moment finds issues that belong to an earlier phase, the feature travels backward to that phase. The phase context system ensures prior decisions are visible, keeping rework focused and efficient.

Express features skip specify, design, and create-plan entirely: `/pd:create-feature --express` records an inline mini-spec and hands straight to `/pd:implement`, where QA and review collapse into a single combined pass.
<!-- AUTO-GENERATED: END -->
