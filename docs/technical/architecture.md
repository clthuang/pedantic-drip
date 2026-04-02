---
last-updated: 2026-04-02T00:00:00Z
source-feature: codebase-analysis
---

<!-- AUTO-GENERATED: START - source: codebase-analysis -->

# Architecture

## Overview

Pedantic Drip (pd) is a Claude Code plugin providing a structured feature development workflow. It is not a standalone application — it runs entirely within Claude Code sessions and extends Claude's behavior through commands, skills, agents, and hooks.

The system is organized around a pipeline of workflow phases (brainstorm → specify → design → create-plan → create-tasks → implement → finish-feature). Each phase produces file artifacts. State is persisted across sessions via SQLite-backed MCP servers and JSON files in the feature directory.

## Component Map

```
User
 │
 ├── /pd:command              Commands — user-invocable entry points
 │        │                   plugins/pd/commands/{name}.md
 │        │
 │        └── Skill           Skills — multi-step procedural instructions
 │               │            plugins/pd/skills/{name}/SKILL.md
 │               │
 │               └── Agent   Subagents — isolated workers with focused scope
 │                            plugins/pd/agents/{name}.md
 │
 ├── Hooks                    Lifecycle scripts — fire on Claude Code events
 │   plugins/pd/hooks/        (SessionStart, PreToolUse, PostToolUse, Stop)
 │
 ├── MCP: workflow-state      Phase transition state machine + .meta.json projection
 │   plugins/pd/mcp/          workflow_state_server.py
 │
 ├── MCP: entity-registry     Cross-project entity lineage + metadata storage
 │   plugins/pd/mcp/          entity_server.py → ~/.claude/pd/entities/entities.db
 │
 └── MCP: memory              Semantic long-term memory
     plugins/pd/mcp/          memory_server.py → ~/.claude/pd/memory/memory.db
```

## Workflow Phase Sequence

```
brainstorm → specify → design → create-plan → create-tasks → implement → finish-feature
```

Each phase transition is guarded by `validateAndSetup` (in `workflow-transitions` skill) and recorded in entity metadata via `complete_phase` MCP. Phase timing, iteration counts, and reviewer notes accumulate in `phase_timing` within entity metadata and are projected to `.meta.json`.

## Key Data Flows

### Feature Lifecycle

1. User invokes `/pd:specify` (or any phase command)
2. `workflow-transitions` skill runs `validateAndSetup`:
   - Reads `.meta.json` from the feature directory
   - Validates phase transition legality
   - Injects phase context (backward travel context, prior phase summaries) if applicable
3. Phase skill executes, producing or updating artifact files (`spec.md`, `design.md`, etc.)
4. Reviewer agents are dispatched and may approve or trigger backward travel
5. `commitAndComplete` in `workflow-transitions` skill:
   - Calls `complete_phase` MCP (Step 2) — updates engine state and projects `.meta.json`
   - Constructs phase summary dict (Step 3a) — appends to `phase_summaries` via `update_entity`
   - Calls `transition_phase` MCP (Step 4) — advances to next phase

### .meta.json Projection

`.meta.json` is the on-disk read surface for workflow state. It is always regenerated from authoritative sources by `_project_meta_json()` in `workflow_state_server.py`. It is never written directly by skills or commands.

Authoritative sources:
- `WorkflowStateEngine` SQLite DB — current phase, last completed phase
- Entity metadata JSON column in `entities.db` — phase timing, phase summaries, backward travel fields, mode, branch, etc.

Fields projected to `.meta.json`:

| Field | Source |
|-------|--------|
| `id`, `slug`, `mode`, `branch` | Entity metadata |
| `status` | Entity status column |
| `lastCompletedPhase` | WorkflowStateEngine (fallback: entity metadata) |
| `phases` | `phase_timing` dict in entity metadata |
| `backward_context` | Entity metadata (feature 073) |
| `backward_return_target` | Entity metadata (feature 073) |
| `phase_summaries` | Entity metadata (feature 075) |

### Backward Travel

When a reviewer determines an upstream phase needs rework, it sets `backward_context` in entity metadata via `update_entity`. `validateAndSetup` Step 1b detects backward transitions by checking whether `phases[targetPhase].completed` exists in `.meta.json`. If so, it injects a `## Phase Context` block prepended to the phase prompt.

## Module Interfaces

### workflow_state_server.py

Primary MCP server for workflow state. Key internal functions:

| Function | Responsibility |
|----------|---------------|
| `_project_meta_json(db, engine, feature_type_id, feature_dir)` | Regenerates `.meta.json` from DB and engine state; called after every state mutation |
| `_process_complete_phase(...)` | Writes `phase_timing[phase].{completed, iterations, reviewerNotes}` to entity metadata |
| `_atomic_json_write(path, data)` | Writes JSON atomically via temp file + rename |

### entity_server.py

Primary MCP server for entity registry. Stores entities (features, projects, brainstorms, backlog items) with parent-child lineage in SQLite.

Key MCP tools used by workflow:

| Tool | Usage |
|------|-------|
| `update_entity(type_id, metadata)` | Shallow-merges metadata dict into existing entity metadata |
| `complete_phase` | Called by `commitAndComplete` Step 2 to record phase completion |
| `transition_phase` | Called by `commitAndComplete` Step 4 to advance workflow state |

### workflow-transitions/SKILL.md

Shared procedural library included by all phase commands. Two primary functions:

- **`validateAndSetup(phaseName)`** — Phase entry guard: validates prerequisites, detects backward transitions, injects phase context
- **`commitAndComplete(phaseName, artifacts, iterations, reviewerNotes)`** — Phase exit procedure: records completion, constructs and stores phase summary, advances state

### metadata.py (entity_registry)

Centralizes metadata parsing and schema validation for entity types. `parse_metadata()` always returns `{}` for None/invalid input. `validate_metadata()` is warn-only.

`METADATA_SCHEMAS['feature']` defines expected keys including `phase_summaries: list` (added in feature 075).

## Phase Summaries (Feature 075)

Feature 075 adds structured phase summary accumulation to the workflow. Each phase completion appends a summary entry to `phase_summaries` in entity metadata. On backward transitions, prior summaries are injected as context.

See `docs/technical/decisions/ADR-001-phase-summaries-append-list.md` for the storage design decision.

### Data Flow

```
commitAndComplete Step 3 (plain-text Phase Summary output)
        │
        ▼
Step 3a: construct summary dict (7 fields)
        │
        ▼
update_entity(type_id, metadata={"phase_summaries": existing + [new_entry]})
        │
        ▼
entities.db (entity metadata JSON column)
        │
        ▼
_project_meta_json() — projects phase_summaries to .meta.json
        │
        ▼
.meta.json (phase_summaries field visible to validateAndSetup)
        │
        ▼
validateAndSetup Step 1b (backward transition detected)
        │
        ▼
## Phase Context block injected into phase prompt
```

### Summary Entry Schema

```python
{
    "phase": str,                        # e.g., "specify", "design"
    "timestamp": str,                    # ISO 8601 UTC, e.g., "2026-04-02T08:00:00Z"
    "outcome": str,                      # e.g., "Approved after 3 iterations."
    "artifacts_produced": list[str],     # filenames only, e.g., ["spec.md"]
    "key_decisions": str,                # free-text paragraph of key choices
    "reviewer_feedback_summary": str,    # brief summary of reviewer feedback
    "rework_trigger": str | None         # rework provenance, or null if first completion
}
```

Constraints: max 2000 chars per entry (serialized JSON). Truncation order: `reviewer_feedback_summary` → `key_decisions` → `artifacts_produced` → `outcome`.

## Hooks

Hooks are shell scripts in `plugins/pd/hooks/` executed by Claude Code at lifecycle points defined in `hooks.json`.

| Hook | Trigger | Key behavior |
|------|---------|-------------|
| `session-start` | SessionStart | Reads active feature `.meta.json`, injects context into session |
| `meta-json-guard` | PreToolUse (Write/Edit) | Blocks unauthorized `.meta.json` modifications |
| `pre-commit-guard` | PreToolUse (Bash) | Branch protection, pd directory protection |
| `pre-exit-plan-review` | PreToolUse (ExitPlanMode) | Gates plan exit behind `plan-reviewer` dispatch |
| `yolo-guard` | PreToolUse (.*) | Enforces YOLO mode safety boundaries |
| `yolo-stop` | Stop | Chains to next phase on YOLO stop events |

## Agent Categories

| Category | Count | Purpose |
|----------|-------|---------|
| Reviewers | 13 | Validate artifacts and gate phase transitions |
| Workers | 6 | Implement, synthesize, or transform content |
| Researchers | 5 | Gather context, scan codebase, search memory |
| Advisory | 1 | Domain advisory for brainstorm problems |
| Orchestration | 3 | Secretary routing, RCA, retro facilitation |

<!-- AUTO-GENERATED: END -->
