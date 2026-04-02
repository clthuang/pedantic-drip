---
last-updated: 2026-04-02T10:30:00Z
source-feature: 075-phase-context-accumulation
---

<!-- AUTO-GENERATED: START - source: 075-phase-context-accumulation -->

# Architecture Overview

A reference map of the plugin's components and how they connect. Read this to orient yourself before diving into a specific area.

## Top-Level Model

```
User
 ├── /command          → Command (.md) → Skill (SKILL.md) → Agents
 └── /secretary <req>  → Secretary routing pipeline → Skill or Agent
```

Everything is prompts. Skills and agents are instruction files that Claude follows — there is no compiled runtime. The workflow state and entity lineage are persisted in SQLite databases (`~/.claude/pd/`), making any session resumable from the files alone.

## Component Locations

| Component | Location | Count |
|-----------|----------|-------|
| Skills | `plugins/pd/skills/{name}/SKILL.md` | ~25 |
| Agents | `plugins/pd/agents/{name}.md` | 29 |
| Commands | `plugins/pd/commands/{name}.md` | ~20 |
| Hooks | `plugins/pd/hooks/` | 13 |
| MCP servers | `plugins/pd/mcp/` | 3 |
| Shared Python libs | `plugins/pd/hooks/lib/` | — |

## Workflow Phases

Features progress through a linear phase sequence managed by the workflow engine:

```
brainstorm → specify → design → create-plan → create-tasks → implement → finish-feature
```

Each phase command calls `validateAndSetup` (from `workflow-transitions` SKILL.md) before doing phase work, and `commitAndComplete` after. These two shared procedures handle transition validation, branch checks, partial-phase recovery, state recording, auto-commit, and phase summary storage.

### workflow-transitions Shared Boilerplate

`validateAndSetup(phaseName)` runs steps in order:

1. **Validate Transition** — reads `.meta.json`, determines if the transition is normal forward, backward (re-running completed phase), or skip. Prompts user if backward or skip.
2. **Phase Context Injection (Step 1b)** — on backward transitions, constructs a `## Phase Context` block containing reviewer referral findings (`backward_context`) and prior phase summaries (`phase_summaries`). Injected into the prompt before any skill invocation. Only present on backward transitions; no block is generated on normal forward transitions.
3. **Check Branch** — verifies the current git branch matches the feature's expected branch.
4. **Check for Partial Phase** — detects interrupted phase work and offers resume/restart options.
5. **Mark Phase Started** — calls `transition_phase` MCP tool to record phase start.
6. **Inject Project Context** — for features linked to a project, prepends PRD, roadmap, and completed dependency context.

`commitAndComplete(phaseName, artifacts[], iterations, capReached, reviewerNotes[])` runs after phase work:

1. **Auto-Commit** — runs frontmatter injection on artifacts, then `git add / commit / push`.
2. **Update State** — calls `complete_phase` MCP tool to record completion and timing.
3. **Phase Summary** — outputs a plain-text summary block (outcome, artifacts, reviewer notes).
4. **Store Phase Summary (Step 3a)** — constructs a structured `summary_dict` (phase, timestamp, outcome, key decisions, reviewer feedback, rework trigger) and appends it to `phase_summaries` in entity metadata via `update_entity`. Capped at 2000 chars total; field truncation order: reviewer_feedback_summary → key_decisions → artifacts_produced → outcome. Best-effort — failures log a warning but do not block completion.
5. **Forward Re-Run Check (Step 3b)** — handles automatic forward re-run when returning from a backward transition chain.

### Phase Context Accumulation (Feature 075)

Feature 075 adds the `phase_summaries` append-list to entity metadata, projected to `.meta.json`. When a backward transition is detected (re-entry into a completed phase), Step 1b reads `phase_summaries` and trims for display (last 2 entries per phase, display-only — full list persists in storage). This gives the re-entering phase visibility into what was decided in prior attempts, reducing rework churn.

## Agents

Agents are isolated subprocesses spawned by skills and commands via Task dispatch. They have a specific focus and return structured JSON results.

**Reviewers (13):** spec-reviewer, design-reviewer, plan-reviewer, task-reviewer, implementation-reviewer, code-quality-reviewer, security-reviewer, phase-reviewer, brainstorm-reviewer, prd-reviewer, project-decomposition-reviewer, ds-analysis-reviewer, ds-code-reviewer

**Workers (7):** implementer, generic-worker, documentation-writer, documentation-researcher, code-simplifier, ras-synthesizer, test-deepener

**Researchers (5):** codebase-explorer, investigation-agent, internet-researcher, skill-searcher, project-decomposer

**Advisory (1):** advisor

**Orchestration (3):** secretary-reviewer, rca-investigator, retro-facilitator

All agent files include a `model:` frontmatter field (`opus`/`sonnet`/`haiku`). Every dispatch must match this tier. Verify with: `grep -rn 'subagent_type:' plugins/pd/ | wc -l`.

## Hooks

Hooks fire automatically at Claude Code lifecycle points and are defined in `plugins/pd/hooks/hooks.json`.

| Hook | Trigger | Purpose |
|------|---------|---------|
| `sync-cache` | SessionStart | Syncs plugin source to Claude cache |
| `cleanup-locks` | SessionStart | Removes stale lock files |
| `session-start` | SessionStart | Injects active feature context, knowledge bank memory, runs doctor auto-fix |
| `inject-secretary-context` | SessionStart | Injects available agent/command context for secretary routing |
| `start-ui-server` | SessionStart | Auto-starts the Kanban board UI server |
| `pre-commit-guard` | PreToolUse (Bash) | Branch protection; warns on commits to main/master |
| `meta-json-guard` | PreToolUse (Write/Edit) | Protects `.meta.json` files from unauthorized edits |
| `yolo-guard` | PreToolUse (.*) | Enforces YOLO mode safety boundaries |
| `post-enter-plan` | PostToolUse (EnterPlanMode) | Injects plan review instructions |
| `post-exit-plan` | PostToolUse (ExitPlanMode) | Injects task breakdown and implementation workflow |
| `pre-exit-plan-review` | PreToolUse (ExitPlanMode) | Gates plan exit behind plan-reviewer dispatch |
| `yolo-stop` | Stop | Detects YOLO mode stop events and chains to next phase |

SessionStart hooks match `startup|resume|clear` only — they do not fire on `compact` events.

## MCP Servers

Three MCP servers provide persistent state to Claude across sessions:

### Memory Server (`mcp/memory_server.py`)

Tools: `store_memory`, `search_memory`, `record_influence`

Stores learnings with optional Gemini embeddings for semantic retrieval. Falls back to FTS5 keyword search when no API key is set. Database: `~/.claude/pd/memory/memory.db`.

### Entity Registry Server (`mcp/entity_server.py`)

Tools: `register_entity`, `set_parent`, `get_entity`, `get_lineage`, `update_entity`, `export_lineage_markdown`, `search_entities`, `export_entities`, `create_key_result`

Tracks lineage of pd artifacts (backlog items, brainstorms, projects, features) in a cross-project SQLite DB at `~/.claude/pd/entities/entities.db`. The `type_id` format is `{entity_type}:{entity_id}` with a colon separator (e.g., `feature:075-phase-context-accumulation`).

The `metadata` field on entities stores structured JSON. Entity-level metadata for features includes: `phase_summaries` (append-list of phase summary dicts), `backward_context` (reviewer referral for rework), `backward_return_target`, and `backward_history`. Always use `parse_metadata()` from `entity_registry.metadata` — never raw `json.loads` on metadata fields.

### Workflow State Server (`mcp/workflow_state_server.py`)

Tools: `get_phase`, `transition_phase`, `complete_phase`, `validate_prerequisites`, `list_features_by_phase`, `list_features_by_status`, `reconcile_check`, `reconcile_apply`, `reconcile_frontmatter`, `reconcile_status`, `init_feature_state`, `init_project_state`, `activate_feature`, `init_entity_workflow`, `transition_entity_phase`

Manages feature lifecycle state as a SQLite-backed state machine. The state engine is defined in `hooks/lib/workflow_engine/`. Drift between the DB and `.meta.json` is detected and repaired by `reconcile_check` / `reconcile_apply`.

## Shared Python Libraries

Located under `plugins/pd/hooks/lib/`:

| Module | Purpose |
|--------|---------|
| `entity_registry/` | Entity DB, metadata parsing, backfill scanner, frontmatter injection |
| `workflow_engine/` | State machine, hydration, transitions, reconciliation |
| `transition_gate/` | Gate functions, constants, and transition models |
| `semantic_memory/` | Embedding generation, memory store, retrieval ranking |
| `reconciliation_orchestrator/` | Entity sync, backlog parsing, brainstorm archive |
| `doctor/` | 10 data consistency checks with auto-fix support |

Use `uv add` to add dependencies — never `pip install`. Run tests with `plugins/pd/.venv/bin/python -m pytest`.

## File Artifacts

Each feature produces a set of files under `{artifacts_root}/features/{id}-{slug}/`:

| File | Produced by |
|------|-------------|
| `prd.md` | brainstorm phase |
| `spec.md` | specify phase |
| `design.md` | design phase |
| `plan.md` | create-plan phase |
| `tasks.md` | create-tasks phase |
| `impl-log.md` | implement phase |
| `.meta.json` | workflow engine (auto-managed) |
| `.review-history.md` | reviewer agents (auto-managed) |

`.meta.json` is the source of truth for workflow state. Modifications to it outside the workflow engine (MCP tools) are blocked by the `meta-json-guard` hook.

## Knowledge Bank

Learnings from retrospectives accumulate in `docs/knowledge-bank/`:

- `constitution.md` — Core principles (KISS, YAGNI, etc.)
- `patterns.md` — Approaches that worked
- `anti-patterns.md` — Things to avoid
- `heuristics.md` — Decision guides

Cross-project universal entries are promoted to `~/.claude/pd/memory/` and injected into every session via the `session-start` hook.

## Design Principles

| Principle | Meaning |
|-----------|---------|
| Everything is prompts | Skills and agents are instruction files; no compiled runtime |
| Files are truth | Artifacts persist in files; any session can resume from them |
| Humans unblock | When stuck, Claude asks — never spins endlessly |
| Composable > Rigid | Phases work independently; combine as needed |
| No backward compatibility | Private tooling — delete old code, no shims |

<!-- AUTO-GENERATED: END -->
