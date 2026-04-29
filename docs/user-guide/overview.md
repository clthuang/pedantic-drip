---
last-updated: 2026-04-29T00:00:00Z
source-feature: 075-phase-context-accumulation
audit-feature: 098-tier-doc-frontmatter-sweep
---

<!-- AUTO-GENERATED: START - source: 075-phase-context-accumulation -->
# pd Plugin — Overview

pd is a Claude Code plugin that turns ideas into shipped features through structured phases. It guides work from brainstorming through specification, design, planning, implementation, and merge — with built-in quality gates and semantic memory at every step.

## What pd Does

pd imposes a proven workflow on top of Claude Code:

- Each feature moves through phases in order: brainstorm → specify → design → create-plan → implement → finish
- Every phase has an AI reviewer that challenges the output before progression
- Quality gates catch issues early, before they compound into later phases
- Memory persists learnings across sessions and projects so past decisions inform future work
- A local Kanban board gives a live view of all active work

## Key Features

### Structured Phase Workflow

Features advance through named phases. Each phase produces a specific artifact (spec.md, design.md, plan.md, tasks.md) that feeds the next. Reviewers at each gate must approve before the phase closes.

### Phase Context on Rework

When a reviewer sends a feature backward for rework, pd injects a `## Phase Context` block into the re-entered phase. This block contains:

- The reviewer referral (what triggered the rework)
- Prior phase summaries — key decisions, artifacts produced, and reviewer notes from earlier cycles

This prevents blind rework: the re-entered phase has full knowledge of what was decided before, so reviewers don't re-raise resolved issues and drafters don't contradict prior conclusions.

### Autonomous Operation (YOLO Mode)

YOLO mode lets pd run the full workflow without pausing for confirmation at each phase gate. Quality reviewers still run — only the user confirmation step is bypassed. Three levels are available:

- `manual` — default, confirms at every transition
- `aware` — provides hints about autonomous operation
- `yolo` — fully autonomous end-to-end

### Semantic Memory

pd persists learnings in a global memory store (`~/.claude/pd/memory/`) that accumulates across all projects. At session start, relevant memories are injected automatically. You can also save learnings explicitly with `/pd:remember`.

### Kanban Board

A local web UI starts automatically at `http://localhost:8718/` each session. It shows all features, brainstorms, backlog items, and projects with their current phase — no setup required.

### Pre-Release Adversarial QA Gate

When `/pd:finish-feature` runs, before the merge it dispatches 4 reviewers in parallel against the branch diff: `security-reviewer`, `code-quality-reviewer`, `implementation-reviewer`, and `test-deepener` (Step A mode). Findings are bucketed by severity (HIGH/MED/LOW) using a defined rubric. HIGH findings block merge unless a `qa-override.md` rationale (≥50 chars) is provided; MED findings auto-file to backlog; LOW findings fold into the retro. The gate is idempotent (cached by HEAD SHA) and non-blocking when YOLO mode is active for MED/LOW. See [`docs/dev_guides/qa-gate-procedure.md`](../dev_guides/qa-gate-procedure.md) for full procedure.

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

When a phase reviewer finds issues, the feature travels backward to the appropriate phase. The phase context system ensures prior decisions are visible, keeping rework focused and efficient.
<!-- AUTO-GENERATED: END -->
