# Specification: iflow UI Server + Kanban Board

## Problem Statement
iflow provides zero visual observability into the feature pipeline — developers must run CLI commands to understand what's in progress, blocked, or complete, with no at-a-glance dashboard view.

## Success Criteria
- [ ] SC-1: Single FastAPI server process serves a Kanban board at `http://127.0.0.1:8718/`
- [ ] SC-2: Board displays 8 columns matching `kanban_column` values: backlog, prioritised, wip, agent_review, human_review, blocked, documenting, completed
- [ ] SC-3: Feature cards show type_id, slug (extracted from type_id), mode, workflow_phase, and last_completed_phase
- [ ] SC-4: Server responds with complete HTML in <200ms for 100 features (TTFB measured on warm server after at least one prior request, with 100 pre-seeded workflow_phases rows, via server middleware timing); full page render including CDN assets completes in <2s on localhost
- [ ] SC-5: HTMX partial refresh (manual button click) updates board content without full page reload
- [ ] SC-6: Server starts with `python -m plugins.iflow.ui` from the project root, with zero configuration (note: PRD FR-5 references `iflow ui` CLI command; the CLI wrapper is intentionally deferred to Out of Scope — this release uses direct Python module invocation)
- [ ] SC-7: CLI workflow (MCP servers, hooks, skills) is completely unaffected when UI server is not running
- [ ] SC-8: All client-side JS/CSS served from CDN — zero JavaScript build step
- [ ] SC-9: Server process uses <50MB RSS memory at idle (no active requests)

## Scope

### In Scope
- FastAPI application at `plugins/iflow/ui/` with `__main__.py` entry point
- Kanban board routes: `GET /` serves full page or HTMX partial based on `HX-Request` header
- SQLite database access via `EntityDatabase` with new optional `check_same_thread` parameter (default=True); UI server passes `check_same_thread=False`
- HTMX-powered board refresh via manual refresh button (no auto-polling)
- CDN assets: `https://cdn.jsdelivr.net/npm/daisyui@5/daisyui.css` + `https://cdn.tailwindcss.com` for styling, `https://unpkg.com/htmx.org` for HTMX (3 CDN tags)
- Jinja2 HTML templates at `plugins/iflow/ui/templates/`: base.html (layout + CDN links), board.html (full board page extending base), _board_content.html (HTMX partial for refresh), _card.html (single card fragment), error.html (error display)
- Database path resolved via `ENTITY_DB_PATH` env var, falling back to `~/.claude/iflow/entities/entities.db` (matching existing MCP server pattern in workflow_state_server.py)
- CLI startup: `python -m plugins.iflow.ui` with defaults (host=127.0.0.1, port=8718, --port flag for override)
- FastAPI app uses APIRouter-based structure to support future route modules for features 020 and 021
- Error pages for missing database and port conflicts
- Empty board state with guidance message
- `FastAPI>=0.128.3` added to `plugins/iflow/pyproject.toml` via `uv add`. If version resolution fails due to Starlette conflict, escalate before proceeding

### Out of Scope
- Entity list and detail views (feature 020)
- Lineage DAG visualization (feature 021)
- Click-through from Kanban card to entity detail (feature 021)
- Drag-and-drop column reassignment / write-back operations
- Real-time SSE/WebSocket live updates
- Authentication or authorization
- Mobile-responsive layout
- Project-level grouping on board
- iflow CLI command wrapper (e.g., /iflow:ui) for server startup — future enhancement; this release uses direct Python module invocation

## Acceptance Criteria

### AC-1: Server Startup
- Given the iflow plugin venv has FastAPI installed
- When the developer runs the server startup command
- Then the server binds to 127.0.0.1:8718, prints the URL to stdout, and serves HTTP requests

### AC-2: Server Startup — Port Conflict
- Given port 8718 is already in use
- When the developer runs the server startup command
- Then a clear error message is displayed with instructions to use `--port` flag for an alternative port

### AC-3: Kanban Board — Full Page Load
- Given the UI server is running and the browser navigates to `/`
- When the page loads (no HX-Request header)
- Then a full HTML page is returned containing 8 Kanban columns with feature cards grouped by `kanban_column`

### AC-4: Kanban Board — HTMX Partial Refresh
- Given the UI server is running and the board is already displayed
- When the user clicks the refresh button in the board header
- Then only the `_board_content.html` partial is returned (HX-Request header detected), replacing the board area without full page reload. No auto-polling interval in this release.

### AC-5: Feature Card Content
- Given features exist in the `workflow_phases` table
- When a card is rendered
- Then it displays workflow_phases columns only: type_id (e.g., "feature:018-slug"), workflow_phase (current phase or null), mode (standard/full or null), and last_completed_phase. No JOIN to entities table — type_id is the primary identifier shown. The slug is extracted from type_id by splitting on ":". Columns backward_transition_reason and updated_at are returned by the query but not displayed on cards in this release.

### AC-6: Empty Board State
- Given no features exist in the `workflow_phases` table
- When the board loads
- Then all 8 columns are displayed with a "No features yet" guidance message

### AC-7: Database Missing
- Given the entity database file does not exist at the expected path
- When the board loads
- Then an error page is displayed showing the expected database path and setup instructions (instructions direct the user to run the entity registry MCP server to initialize the database, or set `ENTITY_DB_PATH` env var to point to an existing database)

### AC-8: Thread-Safe Database Access
- Given the UI server is running with Uvicorn
- When 10 concurrent HTTP requests to `/` are made via asyncio.gather or threading pool
- Then all return HTTP 200 with valid HTML and no `ProgrammingError` is logged. Implementation: add optional `check_same_thread` parameter (default=True) to `EntityDatabase.__init__`, pass through to `sqlite3.connect()`. UI server instantiates `EntityDatabase(db_path, check_same_thread=False)`.

### AC-9: CDN Asset Delivery
- Given the UI server is running
- When the page loads
- Then 3 CDN resources load: daisyui.css from jsdelivr, Tailwind CSS v4 from cdn.tailwindcss.com, and htmx.org from unpkg. No local JS/CSS build artifacts exist.

### AC-10: Graceful CLI Independence
- Given the UI server is NOT running
- When a developer runs iflow CLI commands (specify, design, implement, etc.)
- Then all CLI workflows function identically — no error, no warning, no dependency on the UI server. Verified by running existing test suite (entity registry, workflow engine, transition gate, MCP server tests) with UI server NOT running.

## Feasibility Assessment

**Verdict: Feasible — Go.**

- **Evidence:** Starlette 0.52.1 and Uvicorn 0.41.0 already exist in `uv.lock` as transitive MCP dependencies. FastAPI >=0.128.3 accepts Starlette <1.0.0, so `uv add fastapi>=0.128.3` will resolve without conflict.
- **Evidence:** `EntityDatabase` already uses WAL mode (`PRAGMA journal_mode=WAL`) and `busy_timeout=5000`, supporting concurrent readers. Adding `check_same_thread=False` to the UI server's own connection is a one-line change in connection construction.
- **Evidence:** DaisyUI v5 + Tailwind CSS v4 CDN delivery requires 3 HTML tags (daisyui.css, tailwindcss CDN, htmx.org), verified from DaisyUI and HTMX documentation.
- **Assumption:** Uvicorn's default thread pool for sync endpoint handlers will work correctly with `check_same_thread=False` — the Pre-Mortem recommends a 20-line PoC to validate this before full implementation. PoC success criteria: 10 concurrent requests all return HTTP 200 without ProgrammingError. **PoC is a prerequisite gate — if it fails, escalate before proceeding with full implementation.** The PoC validation is an implementation prerequisite — it must be the first task in the implementation plan, before any other code is written.
- **Risk:** FastAPI version constraint may conflict with other packages in the venv. Mitigation: `uv add` will fail fast if there's a conflict. If Starlette version conflict occurs with MCP's pinned 0.52.1, escalate before proceeding.

## Dependencies
- Feature 009 (workflow state MCP tools) — confirmed implemented
- Feature 001 (UUID primary key migration) — confirmed implemented
- `EntityDatabase.list_workflow_phases(kanban_column=...)` method at database.py:1325 — returns `list[dict]` with columns: type_id, workflow_phase, kanban_column, last_completed_phase, mode, backward_transition_reason, updated_at
- FastAPI >= 0.128.3 (to be added via `uv add`)
- Uvicorn 0.41.0 (already in uv.lock)
- Jinja2 (already available in plugin venv)

## Open Questions
None — all questions resolved during brainstorm phase.
