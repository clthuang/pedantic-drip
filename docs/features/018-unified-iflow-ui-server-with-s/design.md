# Design: iflow UI Server + Kanban Board

## Prior Art Research

### Codebase Patterns
- **EntityDatabase** (`database.py:414-438`): SQLite connection via `sqlite3.connect(db_path, timeout=5.0)`, WAL mode, `busy_timeout=5000`. No `check_same_thread` parameter — must be added.
- **list_workflow_phases()** (`database.py:1325-1360`): Returns `list[dict]` with 7 columns. Supports optional `kanban_column` filter. Index `idx_wp_kanban_column` exists for query performance.
- **DB path resolution** (`workflow_state_server.py:59-64`): `os.environ.get('ENTITY_DB_PATH', os.path.expanduser('~/.claude/iflow/entities/entities.db'))` — reuse exactly.
- **PYTHONPATH injection** (`workflow_state_server.py:17-19`): `os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'hooks', 'lib'))` — reuse for UI server.
- **Shell bootstrap wrapper** (`run-workflow-server.sh`): 4-step venv resolution pattern — adapt for UI server.

### External Research
- **DaisyUI v5 CDN**: Two tags required — `<link href="...daisyui@5" rel="stylesheet">` BEFORE `<script src="...@tailwindcss/browser@4">`. DaisyUI v5 requires `@tailwindcss/browser@4` from jsdelivr (not `cdn.tailwindcss.com`). Spec SC-8 lists `cdn.tailwindcss.com` but this design corrects to `cdn.jsdelivr.net/npm/@tailwindcss/browser@4` per DaisyUI v5 compatibility requirements.
- **FastAPI + HTMX pattern**: Detect `HX-Request` header to serve partial vs full page. Use `Jinja2Templates` with `TemplateResponse`.
- **SQLite thread safety**: `check_same_thread=False` is safe for Uvicorn's thread pool model with WAL mode — each request runs in a thread but shares a single connection. WAL + busy_timeout provides serialization.

## Architecture Overview

### System Context

```
Developer Browser ──HTTP──▶ FastAPI (Uvicorn)
                                │
                                ▼
                          EntityDatabase
                                │
                                ▼
                          entities.db (SQLite)
```

The UI server is a standalone read-only process. It shares the SQLite database file with existing MCP servers via WAL mode (concurrent readers supported). No inter-process communication — the UI server opens its own `EntityDatabase` connection.

### Component Architecture

```
plugins/iflow/ui/
├── __init__.py          # FastAPI app factory + APIRouter registration
├── __main__.py          # CLI entry point (argparse + uvicorn.run)
├── routes/
│   ├── __init__.py      # empty
│   └── board.py         # GET / route — full page or HTMX partial
└── templates/
    ├── base.html        # Layout shell + CDN links
    ├── board.html       # Full board page extending base
    ├── _board_content.html  # HTMX partial — board columns + cards
    ├── _card.html       # Single card fragment
    └── error.html       # Error display (missing DB, etc.)
```

### Components

#### C1: App Factory (`__init__.py`)
Creates and configures the FastAPI application instance.

**Responsibilities:**
- Instantiate `FastAPI(title="iflow UI")`
- Register board router via `app.include_router()`
- Resolve DB path using env var pattern from existing MCP servers
- Create `EntityDatabase` instance with `check_same_thread=False` (if DB exists)
- Store DB instance in `app.state.db` for route access (or `None` if DB missing)
- Store resolved `db_path` in `app.state.db_path` for error reporting
- Configure `Jinja2Templates` pointing at `templates/` directory
- Store templates in `app.state.templates`

**Design decisions:**
- No lifespan context manager needed — `EntityDatabase` uses WAL mode, and the connection persists for the process lifetime. The DB is closed when the process terminates (OS cleanup).
- No static file mounting — all assets served via CDN (SC-8).
- No CORS middleware — localhost-only server, no cross-origin requests.
- `create_app()` does NOT raise `FileNotFoundError` for missing DB. Instead, `app.state.db` is set to `None` and the board route renders `error.html` with setup instructions (AC-7). This allows the server to start and display a helpful error page rather than crashing at startup.
- The UI server expects a pre-existing, already-migrated database. `EntityDatabase.__init__` calls `_migrate()` but this is idempotent on an existing schema — no new tables or columns are created by the UI server. The MCP servers are responsible for initial schema creation.

#### C2: CLI Entry Point (`__main__.py`)
Handles `python -m plugins.iflow.ui` invocation. Not invoked directly by users — the shell bootstrap wrapper (`run-ui-server.sh`) sets up PYTHONPATH and activates the venv before calling this module.

**Responsibilities:**
- Parse `--port` argument (default: 8718)
- Detect port conflicts and display actionable error
- Print startup URL to stdout
- Start `uvicorn.run()` with the app

**Design decisions:**
- No DB validation at startup — `create_app()` handles missing DB gracefully by setting `app.state.db = None`. The board route renders an error page (AC-7).
- No `--reload` flag — this is a tool, not a dev server for the UI itself. Reload adds complexity for negligible benefit.
- Port conflict detection via `socket.bind()` attempt before Uvicorn — provides immediate user-friendly error instead of Uvicorn's stack trace.
- PYTHONPATH injection is handled by the shell wrapper (`run-ui-server.sh`), not by `__main__.py`. This matches the existing pattern where `run-workflow-server.sh` sets up `PYTHONPATH` before invoking the Python module.

#### C2b: Shell Bootstrap Wrapper (`run-ui-server.sh`)
Shell script that sets up the environment and starts the UI server.

**Responsibilities:**
- Resolve venv path (same 4-step pattern as `run-workflow-server.sh`)
- Set PYTHONPATH to include `hooks/lib` directory
- Forward CLI arguments (e.g., `--port`) to `python -m plugins.iflow.ui`

**Design decisions:**
- Adapts the existing `run-workflow-server.sh` pattern — no new conventions.

#### C3: Board Route (`routes/board.py`)
Single route handler serving the Kanban board.

**Responsibilities:**
- `GET /` — fetch all workflow_phases rows, group by `kanban_column`, render
- Detect `HX-Request` header: if present, return `_board_content.html` partial; otherwise return `board.html` full page
- Handle missing DB (`app.state.db is None`) — render `error.html` with DB path and setup instructions (AC-7)
- Handle DB query errors gracefully (return error template)
- Handle empty board state (all columns empty)

**Design decisions:**
- Fetch all rows with `db.list_workflow_phases()` (no filter) and group in Python. One query, O(n) grouping. Simpler than 8 filtered queries and well within performance budget for 100 features.
- The route is synchronous (`def` not `async def`) because `EntityDatabase` uses synchronous SQLite. Uvicorn runs sync endpoints in a thread pool — this is the standard FastAPI pattern for sync I/O.
- Template access: `templates = request.app.state.templates` — obtained from app state, not imported directly. This enables test isolation via `TestClient`.

#### C4: EntityDatabase Modification (`database.py`)
Minimal change to existing `EntityDatabase.__init__`.

**Responsibilities:**
- Accept optional `check_same_thread` parameter (default=True)
- Pass through to `sqlite3.connect()`

**Design decisions:**
- Default `True` preserves backward compatibility for all existing callers (MCP servers, hooks, tests).
- Only the UI server passes `False` — it creates its own instance at startup.

#### C5: Jinja2 Templates (`templates/`)
HTML templates rendering the Kanban board.

**Responsibilities:**
- `base.html`: HTML5 skeleton with CDN links (DaisyUI CSS, Tailwind CSS v4, HTMX), navbar with title + refresh button
- `board.html`: Extends base, contains `<div id="board-content">` target for HTMX swap, includes `_board_content.html`
- `_board_content.html`: 8-column grid layout, iterates columns, includes `_card.html` for each feature
- `_card.html`: Card with type_id, slug, workflow_phase badge, mode badge, last_completed_phase
- `error.html`: Error message display with DB path and setup instructions

**Design decisions:**
- Column rendering order matches spec SC-2: backlog, prioritised, wip, agent_review, human_review, blocked, documenting, completed (left to right).
- Cards extract slug from `type_id` via Jinja2 filter or inline split: `{{ item.type_id.split(':')[1] }}`.
- HTMX refresh button: `hx-get="/" hx-target="#board-content" hx-swap="innerHTML"` — triggers `GET /` with `HX-Request` header, server returns `_board_content.html` partial.
- Workflow phase displayed as DaisyUI badge with color coding based on phase name (visual differentiation without custom CSS).

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| App structure | App factory in `__init__.py` | Matches FastAPI convention; enables test client creation via `from plugins.iflow.ui import create_app` |
| Router pattern | APIRouter in `routes/board.py` | Supports future route modules (020 entity views, 021 lineage DAG) without modifying `__init__.py` |
| DB access | Synchronous `EntityDatabase` direct access | Existing API is synchronous; async wrapper adds complexity with no benefit for SQLite reads |
| Template engine | Jinja2 via `fastapi.templating` | Added via `uv add jinja2`; native FastAPI integration |
| Styling | DaisyUI v5 + Tailwind CSS v4 via CDN | Zero build step (SC-8); 3 CDN tags — daisyui.css, @tailwindcss/browser@4, htmx.org |
| HTMX refresh | Manual button, no auto-polling | Spec explicitly excludes auto-polling; keeps implementation minimal |
| Column order | Hardcoded list in Python | 8 fixed columns per spec; no need for dynamic ordering |
| Error handling | Template-based error pages | User-friendly; consistent with board UI |
| Port conflict | Socket pre-check before Uvicorn | Immediate, actionable error message vs Uvicorn stack trace |

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| FastAPI version conflict with MCP's Starlette pin | Low | High (blocks implementation) | `uv add` fails fast; escalate before proceeding |
| SQLite `check_same_thread=False` causes data corruption | Very Low | Medium | WAL mode + busy_timeout provide isolation; PoC validates before full impl |
| CDN unavailability breaks board rendering | Low | Low (local dev tool) | Acceptable risk for a localhost tool; CDN outages are rare and temporary |
| Uvicorn thread pool exhaustion under heavy load | Very Low | Low | Single-user local tool; default thread pool (40 threads) is sufficient |

## Interfaces

### C1: App Factory — `create_app(db_path: str | None = None) -> FastAPI`

```python
# plugins/iflow/ui/__init__.py

def create_app(db_path: str | None = None) -> FastAPI:
    """Create the iflow UI FastAPI application.

    Parameters
    ----------
    db_path:
        Path to the entity database. If None, resolves from ENTITY_DB_PATH
        env var or default ~/.claude/iflow/entities/entities.db.

    Returns
    -------
    FastAPI application instance. If the DB file does not exist,
    app.state.db is set to None (board route renders error page).
    """
```

**App state contract:**
- `app.state.db: EntityDatabase | None` — database instance with `check_same_thread=False`, or `None` if DB file missing
- `app.state.db_path: str` — resolved path to entity database (for error reporting)
- `app.state.templates: Jinja2Templates` — template renderer

### C2: CLI Entry Point — `__main__.py`

```python
# plugins/iflow/ui/__main__.py

# Invocation: python -m plugins.iflow.ui [--port PORT]
# Default port: 8718
# Default host: 127.0.0.1

# Exit codes:
#   0 — clean shutdown
#   1 — port conflict or DB missing
```

**CLI arguments:**
- `--port PORT` (int, default 8718): Server port

**Stdout output on startup:**
```
iflow UI server running at http://127.0.0.1:{port}/
```

**Stderr output on port conflict:**
```
Error: Port {port} is already in use.
Use --port to specify an alternative: python -m plugins.iflow.ui --port 8719
```

### C3: Board Route — `GET /`

```python
# plugins/iflow/ui/routes/board.py

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def board(request: Request) -> HTMLResponse:
    """Serve the Kanban board.

    Access pattern:
        db = request.app.state.db          # EntityDatabase | None
        db_path = request.app.state.db_path  # str
        templates = request.app.state.templates  # Jinja2Templates

    Behavior:
    - If db is None: return error.html with db_path and setup instructions
    - If HX-Request header present: return _board_content.html partial
    - If HX-Request header absent: return board.html full page
    - If DB query error: return error.html with details

    Template rendering (modern FastAPI convention):
        templates.TemplateResponse(request, "board.html", context)

    Template context:
    - columns: dict[str, list[dict]]
        Keys: 8 kanban_column values
        Values: list of workflow_phases row dicts
    - column_order: list[str]
        Ordered column names for rendering
    """
```

**Column grouping logic:**
```python
COLUMN_ORDER = [
    "backlog", "prioritised", "wip", "agent_review",
    "human_review", "blocked", "documenting", "completed",
]

def _group_by_column(rows: list[dict]) -> dict[str, list[dict]]:
    """Group workflow_phases rows by kanban_column.

    Returns dict with all 8 columns as keys (empty list if no rows).
    """
    columns = {col: [] for col in COLUMN_ORDER}
    for row in rows:
        col = row.get("kanban_column", "backlog")
        if col in columns:
            columns[col].append(row)
    return columns
```

### C4: EntityDatabase Modification

```python
# Change in plugins/iflow/hooks/lib/entity_registry/database.py

class EntityDatabase:
    def __init__(
        self,
        db_path: str,
        *,
        check_same_thread: bool = True,
    ) -> None:
        self._conn = sqlite3.connect(
            db_path,
            timeout=5.0,
            check_same_thread=check_same_thread,
        )
        self._conn.row_factory = sqlite3.Row
        self._set_pragmas()
        self._migrate()
```

**Backward compatibility:** Default `True` means all existing callers are unaffected. No signature changes for existing usage.

### C5: Template Contracts

#### base.html
```
Input context: None (static layout)
CDN tags (in order — DaisyUI v5 requires this specific order):
  1. <link href="https://cdn.jsdelivr.net/npm/daisyui@5/daisyui.css" rel="stylesheet">
  2. <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
  3. <script src="https://unpkg.com/htmx.org"></script>
Note: Spec SC-8 lists cdn.tailwindcss.com but DaisyUI v5 requires
      @tailwindcss/browser@4 from jsdelivr for compatibility.
Block: {% block content %}{% endblock %}
```

#### board.html
```
Extends: base.html
Input context: columns (dict), column_order (list)
Contains: <div id="board-content"> with {% include "_board_content.html" %}
Contains: Refresh button with hx-get="/" hx-target="#board-content" hx-swap="innerHTML"
```

#### _board_content.html
```
Input context: columns (dict), column_order (list)
Renders: 8 columns in a horizontal flex/grid layout
Each column: header with column name + card count, then card list
Empty state: "No features yet" message when all columns empty
```

#### _card.html
```
Input context: item (dict with keys: type_id, workflow_phase, kanban_column,
               last_completed_phase, mode, backward_transition_reason, updated_at)
Displays:
  - Slug: item.type_id.split(":")[1]
  - type_id (full, smaller text)
  - workflow_phase (badge, color-coded)
  - mode (badge if not null)
  - last_completed_phase (text)
Not displayed: backward_transition_reason, updated_at (per AC-5)
```

#### error.html
```
Extends: base.html
Input context: error_title (str), error_message (str), db_path (str, optional)
Displays: error title, message, and optional DB path with setup instructions
```

## Data Flow

```
1. Browser → GET / (full page or HX-Request partial)
2. board() route handler:
   a. db = request.app.state.db
   b. If db is None:
        return templates.TemplateResponse(request, "error.html", {db_path, setup instructions})
   c. rows = db.list_workflow_phases()        # All rows, no filter
   d. columns = _group_by_column(rows)        # O(n) grouping
   e. context = {"columns": columns, "column_order": COLUMN_ORDER}
   f. If HX-Request header:
        return templates.TemplateResponse(request, "_board_content.html", context)
      Else:
        return templates.TemplateResponse(request, "board.html", context)
3. Browser renders HTML with CDN-loaded CSS/JS
```

## File Change Summary

| File | Change |
|------|--------|
| `plugins/iflow/ui/__init__.py` | NEW — App factory, router registration, DB/template setup |
| `plugins/iflow/ui/__main__.py` | NEW — CLI entry point, argparse, port check, uvicorn.run |
| `plugins/iflow/ui/routes/__init__.py` | NEW — Empty |
| `plugins/iflow/ui/routes/board.py` | NEW — GET / route, column grouping, HTMX detection |
| `plugins/iflow/ui/templates/base.html` | NEW — HTML5 layout + CDN links |
| `plugins/iflow/ui/templates/board.html` | NEW — Full board page |
| `plugins/iflow/ui/templates/_board_content.html` | NEW — HTMX partial |
| `plugins/iflow/ui/templates/_card.html` | NEW — Card fragment |
| `plugins/iflow/ui/templates/error.html` | NEW — Error display |
| `plugins/iflow/ui/run-ui-server.sh` | NEW — Shell bootstrap wrapper (venv resolution, PYTHONPATH, forwarding args) |
| `plugins/iflow/hooks/lib/entity_registry/database.py` | MODIFY — Add `check_same_thread` parameter to `__init__` |
| `plugins/iflow/pyproject.toml` | MODIFY — Add `fastapi>=0.128.3` and `jinja2` dependencies |
