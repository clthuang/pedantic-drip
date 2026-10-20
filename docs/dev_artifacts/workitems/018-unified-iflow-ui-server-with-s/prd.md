# PRD: iflow UI Server + Kanban Board

## Status
- Created: 2026-03-08
- Last updated: 2026-03-08
- Status: Draft
- Problem Type: Product/Feature
- Archetype: building-something-new

## Scope Note
This PRD covers **Module 1 of 3** from the original unified iflow UI server brainstorm. The full vision is split into:
- **018 (this feature):** Server infrastructure + Kanban board view
- **020-entity-list-and-detail-views:** Entity list and detail pages (depends on 018)
- **021-lineage-dag-visualization:** Cytoscape.js DAG + click-through navigation (depends on 018, 020)

## Problem Statement
iflow orchestrates feature development through a structured CLI workflow (specify, design, plan, tasks, implement, finish), but provides zero visual observability into the state of features and their workflow phases. Developers must run `/iflow:show-status` to see feature pipeline state, with no way to see all features at a glance or identify where work is blocked.

### Evidence
- No web application HTML/CSS/JS files exist in the codebase (render-graphs.js is a CLI build tool for Graphviz diagrams, not a web UI) — Evidence: Codebase analysis
- The parent PRD (iflow Architectural Evolution) identifies FR-16 as a Release 2 requirement for a unified web UI — Evidence: docs/brainstorms/20260301-144141-iflow-arch-evolution.prd.md
- Users must run CLI commands to understand workspace state — Evidence: User input

## Goals
1. Provide a single web-based dashboard showing all features organized by workflow phase (Kanban board view)
2. Establish the FastAPI server infrastructure that future features (entity explorer, lineage DAG) will build on
3. Zero JavaScript build toolchain — all client-side assets from CDN
4. Integrate with existing SQLite databases (entities.db, workflow state) as the data source

## Success Criteria
- [ ] Single FastAPI/Starlette server process serves Kanban board view
- [ ] Kanban board displays features in 8 columns (backlog, prioritised, WIP, agent review, human review, blocked, documenting, completed)
- [ ] Feature cards show ID, slug, mode, and current phase
- [ ] UI loads in <2 seconds for up to 100 features
- [ ] Zero JavaScript build step — all JS/CSS served from CDN
- [ ] Server starts with a single CLI command (`iflow ui` or equivalent)
- [ ] System degrades gracefully when UI server is not running (CLI workflow unaffected)
- [ ] HTMX partial page updates work for board refresh

## User Stories

### Story 1: View Feature Pipeline
**As a** developer using iflow **I want** to see all my features organized by workflow phase on a Kanban board **So that** I can quickly identify what's in progress, what's blocked, and what needs attention.
**Acceptance criteria:**
- Features appear as cards in their current kanban column
- Cards show feature ID, slug, mode, and current phase
- Board updates reflect the latest workflow state from the database

### Story 2: Start the UI Server
**As a** developer **I want** to start the UI server with a single command **So that** I don't need to remember complex invocations or configure anything.
**Acceptance criteria:**
- `iflow ui` (or plugin command equivalent) starts the server
- Server binds to localhost:8718 by default
- Terminal shows the URL to open

## Use Cases

### UC-1: Daily Standup Review
**Actors:** Developer | **Preconditions:** UI server running, features exist in workflow
**Flow:** 1. Open browser to localhost:8718 2. View Kanban board showing all features by phase 3. Identify blocked features needing attention
**Postconditions:** Developer has full visibility into feature pipeline state
**Edge cases:** No features exist — show empty board with guidance message

## Edge Cases & Error Handling

| Scenario | Expected Behavior | Rationale |
|----------|-------------------|-----------|
| Database file missing | Show error page with path to expected DB location | User may not have run entity registry setup |
| Empty Kanban board | Display empty columns with "No features yet" message | Avoid blank page confusion |
| Browser refresh during navigation | Restore current view (full page reload) | HTMX partial loads must degrade to full page |
| Concurrent DB access from MCP + UI | WAL mode handles concurrent reads; busy_timeout=5000 for write contention | SQLite WAL allows multiple readers with one writer |
| Server port already in use | Display clear error with alternative port flag | Common developer scenario |

## Constraints

### Behavioral Constraints (Must NOT do)
- Must NOT require a JavaScript build step (no webpack, vite, esbuild) — Rationale: Adds toolchain complexity for a single-developer tool; CDN delivery is sufficient
- Must NOT modify existing MCP server behavior or entity database schema — Rationale: UI is a read-only consumer
- Must NOT block CLI workflow when UI server is not running — Rationale: UI is supplemental observability, not a dependency

### Technical Constraints
- SQLite concurrent access requires WAL mode and check_same_thread=False or thread confinement — Evidence: Codebase analysis (EntityDatabase uses single connection without thread-safety flag)
- Must use Python packages available in the existing plugin venv — Evidence: Codebase analysis (starlette 0.52.1, uvicorn 0.41.0 already in uv.lock)
- FastAPI must be >=0.128.3 to accept Starlette 0.52.1 — Evidence: FastAPI release notes (relaxed Starlette upper bound to <1.0.0)
- Depends on feature 009 (workflow state MCP tools) and feature 001 (UUID primary key migration) — Evidence: Feature .meta.json; both confirmed implemented

## Requirements

### Functional
- FR-1: Single FastAPI application serves Kanban board routes (board view, card partial, board refresh). The server architecture must be extensible for future entity explorer routes (features 020, 021).
- FR-2: Kanban board view queries `workflow_phases` table via `EntityDatabase.list_workflow_phases(kanban_column=...)` (database.py:1325), grouping features by `kanban_column` (8 columns). The UI server accesses the database directly — it does NOT use MCP tools for data retrieval.
- FR-3: HTMX-powered partial page updates for board refresh without full reloads
- FR-4: HX-Request header detection serves partial HTML fragments for HTMX requests, full pages for direct browser navigation
- FR-5: Server startup via CLI command with sensible defaults (host=127.0.0.1, port=8718)
- FR-6: DaisyUI + Tailwind CSS v4 loaded via CDN (2 HTML tags, ~42kB) for styling
- FR-7: UI server opens its own `EntityDatabase` connection with `check_same_thread=False` (or uses aiosqlite). The UI server does NOT share a connection with MCP servers. This is the architectural resolution of the thread-safety risk identified in the Pre-Mortem.
- FR-8: Add FastAPI>=0.128.3 to `pyproject.toml` via `uv add fastapi>=0.128.3` as a prerequisite before implementation.

### Non-Functional
- NFR-1: Page load time <2 seconds for up to 100 features — Evidence: Parent PRD NFR-3
- NFR-2: Zero JavaScript build toolchain — all client-side JS from CDN (HTMX)
- NFR-3: Server memory footprint <50MB at idle
- NFR-4: Graceful degradation — CLI workflow fully functional without UI server running

## Non-Goals
- Entity list and detail views — Rationale: Deferred to feature 020-entity-list-and-detail-views
- Lineage DAG visualization — Rationale: Deferred to feature 021-lineage-dag-visualization
- Click-through from Kanban card to entity detail — Rationale: Deferred to feature 021 (requires entity detail from 020)
- Drag-and-drop Kanban column reassignment (write-back) — Rationale: Read-only observability first; design data access layer to support future writes
- Real-time SSE live updates — Rationale: Manual browser refresh is acceptable for Phase 1
- Multi-user authentication or authorization — Rationale: Single-developer desktop tool; localhost binding sufficient
- Mobile-responsive layout — Rationale: Desktop-only; Kanban board needs horizontal space

## Out of Scope (This Release)
- Kanban drag-and-drop with Sortable.js — Future consideration: Phase 2 after read-only board is stable
- SSE-based live board updates — Future consideration: When multiple features change state rapidly
- Entity search from UI — Future consideration: Feature 020+
- Project-level grouping on Kanban board — Future consideration: When project workflows mature

## Research Summary

### Internet Research
- FastAPI + HTMX multi-view routing uses HX-Request header to serve partial vs full page responses — Source: HTMX documentation and community patterns
- sprint-dash: production reference implementation of FastAPI + HTMX + SQLite + Sortable.js Kanban board — Source: GitHub sprint-dash repository
- DaisyUI v5 + Tailwind CSS v4 available via CDN with 2 HTML tags (~42kB), zero build step — Source: DaisyUI documentation

### Codebase Analysis
- `EntityDatabase` opens single `sqlite3.connect(db_path, timeout=5.0)` without `check_same_thread=False` — Location: plugins/iflow/hooks/lib/entity_registry/database.py
- WAL mode enabled with `PRAGMA journal_mode=WAL` and `busy_timeout=5000` — Location: plugins/iflow/hooks/lib/entity_registry/database.py
- `workflow_phases` table schema: `type_id`, `workflow_phase`, `kanban_column` (8 values: backlog, prioritised, wip, agent_review, human_review, blocked, documenting, completed), `last_completed_phase`, `mode`, `updated_at` — Location: plugins/iflow/hooks/lib/workflow_engine/
- `EntityDatabase.list_workflow_phases(kanban_column=...)` supports kanban_column filtering — primary query for Kanban board data — Location: database.py:1325 (note: no MCP tool wraps this method; UI server accesses DB directly)
- Starlette 0.52.1, Uvicorn 0.41.0 already in `uv.lock` as transitive MCP dependencies — Location: uv.lock
- No web application HTML/CSS/JS files exist in the codebase — greenfield UI — Location: full-codebase grep

### Existing Capabilities
- `detecting-kanban` skill: Detects Vibe-Kanban availability — provides fallback pattern for UI detection
- `show-status` command: CLI dashboard showing features, branches, brainstorms — data queries overlap with Kanban view
- `workflow_state_server.py` MCP server: Exposes `get_phase`, `list_features_by_phase`, `list_workflow_phases` tools — data layer for Kanban view

## Structured Analysis

### Problem Type
Product/Feature — Building the server infrastructure and first view (Kanban board) for iflow's web UI layer.

### SCQA Framing
- **Situation:** iflow manages feature development through a CLI-based workflow with workflow phase management backed by SQLite databases.
- **Complication:** Developers lack visual observability into the state of their feature pipeline. Understanding what's in progress, blocked, or complete requires running CLI commands.
- **Question:** How can we provide at-a-glance visual observability into the feature pipeline without adding build-toolchain complexity?
- **Answer:** Build a FastAPI server that reads from the existing SQLite database and serves an HTMX-powered Kanban board, using CDN-delivered CSS/JS with zero build step.

### Decomposition
```
iflow UI Server + Kanban Board (Feature 018)
├── Server Infrastructure
│   ├── FastAPI application setup
│   ├── SQLite connection management (thread-safe)
│   ├── CLI startup command
│   └── CDN integration (DaisyUI + HTMX)
├── Kanban Board View
│   ├── Board layout (8 columns from kanban_column values)
│   ├── Feature card rendering (ID, slug, mode, phase)
│   ├── Column data queries (EntityDatabase.list_workflow_phases)
│   └── Empty state handling
└── Cross-Cutting
    ├── HTMX partial vs full page rendering (HX-Request detection)
    ├── Error handling (DB missing, port conflict)
    └── Graceful degradation (CLI unaffected)
```

## Strategic Analysis

### Pre-Mortem
- **Core Finding:** The most likely failure mode is a SQLite `ProgrammingError: SQLite objects created in a thread can only be used in that same thread` when Uvicorn's thread pool accesses an `EntityDatabase` connection created on a different thread.
- **Analysis:** EntityDatabase uses a single `sqlite3.connect()` call without `check_same_thread=False`. In a long-lived async web server, Uvicorn may dispatch sync endpoint handlers to a thread pool, causing cross-thread connection access. The fix is either: (a) pass `check_same_thread=False` and ensure proper locking, (b) use `aiosqlite` for async access, or (c) confine all DB access to the event loop thread via `asyncio.to_thread`.
- **Key Risks:** Thread-safety violation on first concurrent request
- **Recommendation:** Build a 20-line proof-of-concept to validate the concurrency model before full implementation.
- **Evidence Quality:** strong

### Adoption-Friction
- **Core Finding:** The UI is opt-in supplemental tooling — activation friction is the primary adoption barrier.
- **Analysis:** The UI must be a single-command launch (`iflow ui`) with the URL printed to terminal on start. Zero-config defaults (localhost:8718, auto-detect DB paths) eliminate setup friction. The DaisyUI + Tailwind CDN approach means no `npm install` step.
- **Key Risks:** Developer forgets to start server; port conflicts
- **Recommendation:** Add an `iflow ui` CLI command with zero arguments.
- **Evidence Quality:** moderate

### Flywheel
- **Core Finding:** A read-only Kanban board provides snapshot value but doesn't compound — design the data access layer to support future write-back.
- **Recommendation:** While this feature is read-only, use abstractions that allow future writes (feature 020+).
- **Evidence Quality:** moderate

### Feasibility
- **Core Finding:** Technically feasible with existing venv dependencies. FastAPI must be added via `uv add`.
- **Recommendation:** Go. Build PoC first to validate SQLite thread-safety.
- **Evidence Quality:** strong

## Review History

### Review 1 (2026-03-08)
**Findings:**
- [blocker] FR-2 incorrectly attributed `list_workflow_phases()` to workflow_state_server.py → corrected to EntityDatabase direct access
- [blocker] FastAPI dependency not captured as prerequisite → added FR-8
- [warning] 6 additional issues corrected (render-graphs.js qualification, depth guard reference, connection management, Sortable.js scope, Flywheel tension, port resolution)

**Corrections Applied:**
All blockers and warnings resolved. See original brainstorm for full correction history.

### Scope Reduction (2026-03-08)
Narrowed from full unified UI server (11 FRs) to server infrastructure + Kanban board only (8 FRs). Entity views and lineage DAG deferred to features 020 and 021.

## Open Questions
None.

## Resolved Questions
- **Server bind address:** 127.0.0.1 (localhost only) — single-developer desktop tool
- **Port number:** 8718 — canonical value from parent PRD FR-16
- **Entity database path discovery:** Use `ENTITY_DB_PATH` env var with fallback to `~/.claude/iflow/entities/entities.db`

## Next Steps
1. Build 20-line Uvicorn + EntityDatabase PoC to validate `check_same_thread=False` resolves cross-thread access
2. Ready for /iflow:create-feature to begin implementation
