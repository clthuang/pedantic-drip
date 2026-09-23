# pd Plugin

Structured feature development workflow with skills, agents, and commands for methodical development from ideation to implementation.

See the [workflow diagram](../../README.md#workflow) in the repository README.

## Components

| Type | Count |
|------|-------|
| Skills | 27 |
| Agents | 24 |
| Commands | 31 |
| MCP Servers | 2 |

## Commands

**Start:**
| Command | Description |
|---------|-------------|
| `/pd:brainstorm [topic]` | Explore an idea into an evidence-backed PRD |
| `/pd:create-feature <desc>` | Start building (creates folder + branch); `--express` records an inline mini-spec and jumps to implement |

**Build phases** (run in order):
| Command | Output |
|---------|--------|
| `/pd:specify [--feature=ID]` | `shape.md` — `## Requirements` |
| `/pd:design` | `shape.md` — `## Design` (+ design review moment) |
| `/pd:create-plan` | `plan.md` — `## Plan` (ordered tasks; no separate tasks.md) |
| `/pd:implement` | Code changes (QA execution + code-quality review) |
| `/pd:abandon-feature` | Transition a feature to abandoned status |
| `/pd:finish-feature` | QA battery, docs sync, retro, merge |
| `/pd:wrap-up` | End the session — commit WIP, report engine state and open items |

**Anytime:**
| Command | Purpose |
|---------|---------|
| `/pd:show-lineage` | Display entity lineage tree for the current feature branch or a specified entity |
| `/pd:show-status` | See current feature state |
| `/pd:list-features` | See all active features |
| `/pd:retrospect` | Capture learnings |
| `/pd:add-to-backlog <idea>` | Capture ideas for later |
| `/pd:cleanup-backlog` | Archive fully-closed backlog sections in the entity DB |
| `/pd:cleanup-brainstorms` | Delete old scratch files |
| `/pd:test-debt-report` | Aggregate deferred test debt across features and the backlog |
| `/pd:doctor` | Run 11 diagnostic checks on pd workspace health (incl. security-review command, stale worktrees, status-parser regression, and severity vocabulary) |
| `/pd:sync-cache` | Reload plugin after changes |
| `/pd:secretary` | Intelligent task routing to commands, agents, and skills |
| `/pd:root-cause-analysis` | Investigate bugs and failures to find all root causes |
| `/pd:create-project <prd>` | Create project from PRD with AI-driven decomposition |
| `/pd:create-specialist-team` | Create ephemeral specialist teams for complex tasks |
| `/pd:init-ds-project <name>` | Scaffold a new data science project |
| `/pd:promptimize [file-path or inline text]` | Review a prompt against best practices and return an improved version |
| `/pd:refresh-prompt-guidelines` | Scout latest prompt engineering best practices and update the guidelines document |
| `/pd:review-ds-analysis <file>` | Review data analysis for statistical pitfalls |
| `/pd:review-ds-code <file>` | Review DS Python code for anti-patterns |
| `/pd:generate-docs` | Generate three-tier documentation scaffold or update existing docs |
| `/pd:subagent-ras` | Research, analyze, and summarize any topic using parallel agents |
| `/pd:yolo [on\|off]` | Toggle YOLO autonomous mode |

## Quality Gates

Quality is enforced in two tiers: **mechanical gates** on every phase boundary, and exactly **two LLM review moments** per deep feature.

### Tier 1 — Mechanical gates (zero dispatch)

`scripts/phase-gate.sh <phase> <feature-dir>` runs at each phase boundary and checks artifact existence, required sections, duplicate contract blocks (the restated-contract class), and uncommitted artifacts at implement entry. Failures print one line per problem; fix and re-run.

### Tier 2 — LLM review moments

| Moment | Phase | Agent | Question |
|--------|-------|-------|----------|
| 1 of 2 | design | `pd:design-reviewer` | Is the design sound and grounded? |
| 2 of 2 | implement | `pd:code-quality-reviewer` | Is the branch diff correct and maintainable? |

Per moment: one reviewer pass → at most one fix round → still-open blockers escalate to the user. There is no iterate-to-a-cap loop. Reviewers run in fresh context, cite `file:line`, and own their return schema (defined only in the agent file).

Two dispatches sit outside the review tier:

- `pd:qa-executor` — execution-grounded QA during implement. Runs the test battery and drives affected flows end-to-end, returning commands plus output evidence. It fixes nothing; it reports.
- `pd:security-reviewer` — dispatched from `/pd:finish-feature` when the branch touches a security surface (auth, secrets, input parsing, permissions, data deletion, dependency bumps). Always an Anthropic-model Task.

**Express mode** (`/pd:create-feature --express`) records an inline mini-spec as a `mini_spec` phase event, skips specify/design/create-plan, and collapses QA and review into a single combined pass during implement.

## Agents

| Agent | Purpose |
|-------|---------|
| advisor | Applies strategic/domain advisory lens to brainstorm problems |
| ds-analysis-reviewer | Reviews data analysis for statistical pitfalls and methodology |
| code-quality-reviewer | Reviews implementation quality by severity |
| codebase-explorer | Analyzes codebase for patterns and constraints |
| design-reviewer | Challenges design assumptions and finds gaps (skeptic) |
| documentation-researcher | Researches documentation state and identifies update needs |
| documentation-writer | Writes and updates documentation |
| ds-code-reviewer | Reviews DS Python code for anti-patterns and best practices |
| generic-worker | General-purpose implementation agent |
| implementer | Task implementation with TDD and self-review |
| internet-researcher | Searches web for best practices and standards |
| investigation-agent | Read-only research before implementation |
| plan-reviewer | Skeptical plan reviewer for failure modes and TDD compliance |
| prd-reviewer | Critical review of PRD drafts |
| project-decomposer | Decomposes project PRD into ordered features with dependencies |
| project-decomposition-reviewer | Validates project decomposition quality |
| qa-executor | Execution-grounded QA — runs suites and drives affected flows, returning evidence |
| ras-synthesizer | Synthesizes multi-source research findings into thematic analysis with confidence calibration |
| rca-investigator | Finds all root causes through 6-phase systematic investigation |
| relevance-verifier | Verifies artifact chain coherence (shape.md → plan.md → code) |
| retro-facilitator | Runs data-driven AORTA retrospective with full intermediate context |
| security-reviewer | Reviews implementation for security vulnerabilities |
| skill-searcher | Finds relevant existing skills |
| test-deepener | Systematically deepens test coverage with spec-driven adversarial testing |

## MCP Tools

Both MCP servers (entity registry, workflow engine) share a common lifecycle layer (`mcp/server_lifecycle.py`) that manages PID files, parent-PID watchdog, and session-lifetime watchdog. Orphaned server processes from previous sessions are cleaned up at session start.

### Entity Registry Server

The entity registry server (`mcp/entity_server.py`) exposes 20 tools for entity lineage tracking:

| Tool | Purpose |
|------|---------|
| `register_entity` | Register a new entity (feature, project, brainstorm) with type and status, identified by `seq`/`slug` (`display_id` for a brainstorm); raises `EntityExistsError` on `(workspace_uuid, type_id)` conflict |
| `allocate_entity_id` | Atomically allocate the next `{seq:03d}-{slug}` id for an entity type, before any filesystem/DB write |
| `issue_spawn` | Capture a mid-flight bug or task as a child entity linked to a parent; appends `spawned_child` phase event without modifying parent workflow state |
| `set_parent` | Set a parent-child relationship between two entities |
| `get_entity` | Retrieve entity details by type_id |
| `get_lineage` | Get the full lineage tree for an entity (ancestors and descendants) |
| `update_entity` | Update entity name, status, or metadata |
| `export_lineage_markdown` | Export lineage tree as a markdown file |
| `export_entities` | Export all entities as structured data |
| `delete_entity` | Delete an entity by type_id or UUID |
| `add_entity_tag` | Add a tag to an entity |
| `get_entity_tags` | Get all tags for an entity |
| `add_dependency` | Add a dependency relationship between two entities |
| `remove_dependency` | Remove a dependency relationship |
| `search_entities` | Search entities by name, type, status, or metadata |
| `add_okr_alignment` | Align an entity to a key result |
| `get_okr_alignments` | Get OKR alignments for an entity |
| `create_key_result` | Create a key result under a project |
| `update_kr_score` | Update the score for a key result |
| `list_projects` | List all registered projects |

The server is bootstrapped by `mcp/run-entity-server.sh` and declared in `plugin.json` via `mcpServers`. If the entity DB is locked at startup, the server starts in degraded mode and recovers automatically once the lock is released.

### Workflow Engine Server

The workflow engine server (`mcp/workflow_state_server.py`) exposes 24 tools for workflow state management:

| Tool | Purpose |
|------|---------|
| `get_phase` | Get current workflow phase for a feature |
| `transition_phase` | Transition a feature to the next workflow phase |
| `complete_phase` | Mark the current phase as complete; optional `closes=[uuid...]` atomically transitions each referenced issue to its terminal status and writes `entity_relations(kind='fixes')` rows |
| `record_mini_spec` | Record the express-lane mini-spec as a `mini_spec` event (FR-7) |
| `get_mini_spec` | Read the latest recorded mini-spec text for a feature |
| `validate_prerequisites` | Check if prerequisites are met for a target phase |
| `reproject_meta_json` | Re-render a feature's `.meta.json` from DB state (e.g. after a status change via `update_entity`, since direct writes to it are denied) |
| `list_features_by_phase` | List all features currently in a given phase |
| `list_features_by_status` | List all features with a given status |
| `reconcile_check` | Check for drift between state file and artifacts |
| `reconcile_apply` | Apply reconciliation fixes for detected drift |
| `reconcile_frontmatter` | Sync frontmatter metadata across feature artifacts |
| `reconcile_status` | Get overall reconciliation status summary |
| `init_feature_state` | Initialize workflow state for a new feature |
| `init_project_state` | Initialize workflow state for a new project |
| `activate_feature` | Activate a planned feature for development |
| `init_entity_workflow` | Initialize entity workflow tracking |
| `transition_entity_phase` | Transition an entity to a new workflow phase |
| `get_notifications` | Drain pending notifications for the current project |
| `promote_task` | Promote a task from plan.md to a tracked task entity |
| `query_ready_tasks` | List task entities ready for execution |
| `get_progress_view` | Get cross-level progress view for an entity's ancestor chain |
| `record_backward_event` | Record a backward phase transition event for analytics |
| `query_phase_analytics` | Query structured phase execution data for analytics |

The server is bootstrapped by `mcp/run-workflow-server.sh` and declared in `plugin.json` via `mcpServers`. Like the entity server, it starts in degraded mode if the workflow state DB is locked and recovers automatically.

## Setup

After installing, run the setup script to configure the plugin environment:

```bash
# Check system health (read-only diagnostics)
bash plugins/pd/scripts/doctor.sh

# Interactive setup (venv, project init)
bash plugins/pd/scripts/setup.sh
```

The setup script:
1. Runs diagnostics to check prerequisites (python3, git, rsync)
2. Creates/verifies the Python venv with core dependencies
3. Initializes project directories and config

Run `doctor.sh` anytime to troubleshoot issues — it provides OS-specific fix instructions.

## Installation

```bash
/plugin marketplace add .
/plugin install pd@pedantic-drip-marketplace
```
