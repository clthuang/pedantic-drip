# Tasks: iflow UI Server + Kanban Board

## Phase 0: Prerequisites

### Task 0.1.1: Fix spec.md inaccuracies (CDN URL + Jinja2 dep)
- **File:** `docs/features/018-unified-iflow-ui-server-with-s/spec.md`
- **Action:** (1) Replace ALL occurrences of `cdn.tailwindcss.com` with `cdn.jsdelivr.net/npm/@tailwindcss/browser@4` — this includes SC-8, AC-9, AND the In Scope section (line 24). (2) Change line 112 from "already available in plugin venv" to "added via `uv add jinja2`"
- **Done when:** `grep cdn.tailwindcss.com spec.md` returns zero matches (across ALL sections) AND `grep "uv add jinja2" spec.md` returns a match
- **Depends on:** none

### Task 0.2.1: Install FastAPI dependency
- **Action:** Run `cd plugins/iflow && uv add "fastapi>=0.128.3"`
- **Done when:** `uv run python -c "import fastapi; print(fastapi.__version__)"` prints a version >= 0.128.3
- **Depends on:** none

### Task 0.2.2: Install Jinja2 dependency
- **Action:** Run `cd plugins/iflow && uv add jinja2`
- **Done when:** `uv run python -c "import jinja2; print('OK')"` prints OK
- **Depends on:** none

### Task 0.2.3: Verify httpx availability
- **Action:** Run `cd plugins/iflow && uv run python -c "import httpx; print('OK')"`. If import fails, run `uv add httpx`
- **Done when:** `uv run python -c "import httpx; print('OK')"` prints OK
- **Depends on:** none (httpx is a pre-existing transitive dep; check can run anytime)

### Task 0.3.1: Write PoC thread safety script
- **File:** `agent_sandbox/018-poc/test_thread_safety.py`
- **Action:** Create ~20-line script with FastAPI app, sync route using `sqlite3.connect(path, check_same_thread=False)`, PRAGMAs (`journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`, `cache_size=-8000`), seed 10 rows, fire 10 concurrent GETs via `asyncio.gather` + `httpx.AsyncClient`
- **Done when:** script file exists AND `cd plugins/iflow && uv run python -m py_compile ../../agent_sandbox/018-poc/test_thread_safety.py` succeeds (syntax + import resolution)
- **Depends on:** 0.2.1, 0.2.2, 0.2.3

### Task 0.3.2: Run PoC and evaluate result
- **Action:** Run `cd plugins/iflow && uv run python ../../agent_sandbox/018-poc/test_thread_safety.py`. If pass (exit 0, all 10 responses HTTP 200, no ProgrammingError in output) → continue with sync routes. If fail → append `# ASYNC_FALLBACK=True` comment to `agent_sandbox/018-poc/test_thread_safety.py` and update tasks 2.3.1/2.3.2 action text to use `async def` instead of `def`.
- **Done when:** (pass) script exits 0 with all 200s OR (fail) `grep ASYNC_FALLBACK agent_sandbox/018-poc/test_thread_safety.py` returns a match
- **Depends on:** 0.3.1

## Phase 1: Foundation

### Task 1.1.1: Add check_same_thread parameter to EntityDatabase
- **File:** `plugins/iflow/hooks/lib/entity_registry/database.py`
- **Action:** Add `check_same_thread: bool = True` as keyword-only parameter to `__init__`. Pass through to `sqlite3.connect(..., check_same_thread=check_same_thread)`
- **Done when:** `grep "check_same_thread" plugins/iflow/hooks/lib/entity_registry/database.py` shows both the parameter and the connect call
- **Depends on:** 0.3.2

### Task 1.1.2: Run entity registry tests for regression
- **Action:** Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- **Done when:** all tests pass with zero failures. If any test fails: revert 1.1.1 and investigate
- **Depends on:** 1.1.1

### Task 1.2.1: Create UI package directories
- **Action:** Create directories: `plugins/iflow/ui/`, `plugins/iflow/ui/routes/`, `plugins/iflow/ui/templates/`, `plugins/iflow/ui/tests/`
- **Done when:** all 4 directories exist
- **Depends on:** 1.1.2

### Task 1.2.2: Create __init__.py files and board router stub
- **Action:** Create empty `__init__.py` files: `plugins/iflow/ui/__init__.py`, `plugins/iflow/ui/routes/__init__.py`, `plugins/iflow/ui/tests/__init__.py`. Also create `plugins/iflow/ui/routes/board.py` with stub: `from fastapi import APIRouter` and `router = APIRouter()` — this allows create_app() (2.2.1) to import and register the router before the full board route implementation (2.3.x) fills in the handler.
- **Done when:** `test -f plugins/iflow/ui/__init__.py && test -f plugins/iflow/ui/routes/__init__.py && test -f plugins/iflow/ui/tests/__init__.py && python -c "import importlib.util; spec=importlib.util.spec_from_file_location('board','plugins/iflow/ui/routes/board.py'); print('OK')"` succeeds
- **Depends on:** 1.2.1

## Phase 2: Core Application — TDD

### Task 2.1.1: Write create_app() unit tests (RED)
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** Write test `test_create_app_returns_fastapi_with_state_attrs` — calls `create_app()` with a temp DB path, asserts return is FastAPI instance with `db`, `db_path`, `templates` attributes on `app.state`
- **Done when:** test file exists, test function defined, test runs and FAILS (ImportError or AttributeError expected)
- **Depends on:** 1.2.2

### Task 2.1.2: Write create_app() missing DB unit test (RED)
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** Write test `test_create_app_missing_db_sets_none` — calls `create_app()` with nonexistent DB path, asserts `app.state.db is None`
- **Done when:** test function defined, runs and FAILS
- **Depends on:** 1.2.2

### Task 2.1.3: Write _group_by_column() empty input test (RED)
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** Write test `test_group_by_column_empty_input` — imports `from ui.routes.board import _group_by_column` (PYTHONPATH includes `$PLUGIN_DIR`), calls `_group_by_column([])`, asserts returns dict with 8 keys each mapping to empty list
- **Done when:** test function defined, runs and FAILS (ImportError expected)
- **Depends on:** 1.2.2

### Task 2.1.4: Write _group_by_column() routing test (RED)
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** Write test `test_group_by_column_routes_to_correct_column` — imports `from ui.routes.board import _group_by_column` (PYTHONPATH includes `$PLUGIN_DIR`), calls with single row `{"kanban_column": "wip", "type_id": "feature:test"}`, asserts row appears in `wip` list and other lists are empty
- **Done when:** test function defined, runs and FAILS
- **Depends on:** 1.2.2

### Task 2.1.5: Write _group_by_column() default and drop tests (RED)
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** Import `from ui.routes.board import _group_by_column` (PYTHONPATH includes `$PLUGIN_DIR`). Write test `test_group_by_column_none_defaults_to_backlog` — row with `kanban_column=None` appears in backlog. Write test `test_group_by_column_unknown_column_dropped` — row with `kanban_column="archived"` appears in no column
- **Done when:** both test functions defined, run and FAIL
- **Depends on:** 1.2.2

### Task 2.2.1: Implement create_app() factory (GREEN)
- **File:** `plugins/iflow/ui/__init__.py`
- **Action:** Implement `create_app(db_path: str | None = None) -> FastAPI`. Resolve DB path from param → `ENTITY_DB_PATH` env → `~/.claude/iflow/entities/entities.db`. Set `app.state.db = EntityDatabase(path, check_same_thread=False)` if file exists else `None`. Set `app.state.db_path` and `app.state.templates = Jinja2Templates(directory=templates_dir)`. Register board router.
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_app.py::test_create_app_returns_fastapi_with_state_attrs plugins/iflow/ui/tests/test_app.py::test_create_app_missing_db_sets_none -v` passes
- **Depends on:** 2.1.1, 2.1.2

### Task 2.3.1: Implement COLUMN_ORDER and _group_by_column() (GREEN)
- **File:** `plugins/iflow/ui/routes/board.py`
- **Action:** Define `COLUMN_ORDER = ["backlog", "prioritised", "wip", "agent_review", "human_review", "blocked", "documenting", "completed"]`. Implement `_group_by_column(rows: list[dict]) -> dict[str, list[dict]]` — iterates rows, uses `row.get("kanban_column", "backlog")`, appends to column if column in COLUMN_ORDER, else drops silently
- **Done when:** all _group_by_column unit tests pass (2.1.3, 2.1.4, 2.1.5)
- **Depends on:** 2.1.3, 2.1.4, 2.1.5, 2.2.1

### Task 2.3.2: Implement board() route handler
- **File:** `plugins/iflow/ui/routes/board.py`
- **Action:** Implement `def board(request: Request)` (or `async def` if PoC failed). Handle 4 code paths: (1) missing DB → error.html, (2) DB query error → error.html, (3) HX-Request header → partial `_board_content.html`, (4) else → full `board.html`. Use keyword args: `templates.TemplateResponse(request=request, name=..., context=...)`. Create `router = APIRouter()` with `@router.get("/")`.
- **Done when:** `grep -c "def board" plugins/iflow/ui/routes/board.py` returns 1 AND `grep -c "error.html" plugins/iflow/ui/routes/board.py` returns at least 2 (missing DB + DB error) AND `grep "HX-Request" plugins/iflow/ui/routes/board.py` returns a match AND `grep "board.html" plugins/iflow/ui/routes/board.py` returns a match
- **Depends on:** 2.3.1

## Phase 3: Templates (Parallel)

### Task 3.1.1: Create base.html template
- **File:** `plugins/iflow/ui/templates/base.html`
- **Action:** Write HTML with CDN tags in order: (1) `daisyui.css` from jsdelivr, (2) `@tailwindcss/browser@4` from jsdelivr, (3) `htmx.org` from unpkg. Navbar with "iflow" title. `{% block content %}{% endblock %}`
- **Done when:** file exists with 3 CDN link/script tags and content block. Validate: `cd plugins/iflow && uv run python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('ui/templates')).get_template('base.html')"`
- **Depends on:** 2.3.2

### Task 3.2.1: Create board.html template
- **File:** `plugins/iflow/ui/templates/board.html`
- **Action:** Extends base.html. Contains `<div id="board-content">{% include "_board_content.html" %}</div>`. Refresh button with `hx-get="/" hx-target="#board-content" hx-swap="innerHTML"`
- **Done when:** file exists, extends base, has board-content div and refresh button. Validate: `cd plugins/iflow && uv run python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('ui/templates')).get_template('board.html')"`
- **Depends on:** 2.3.2

### Task 3.3.1: Create _board_content.html template
- **File:** `plugins/iflow/ui/templates/_board_content.html`
- **Action:** 8-column horizontal layout. Iterate `column_order`, render column headers with name + `{{ columns[col]|length }}` card count. Include `_card.html` for each item. Empty state: "No features yet" when all columns empty
- **Done when:** file exists with column iteration, card include, and empty state. Validate: `cd plugins/iflow && uv run python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('ui/templates')).get_template('_board_content.html')"`
- **Depends on:** 2.3.2

### Task 3.4.1: Create _card.html template
- **File:** `plugins/iflow/ui/templates/_card.html`
- **Action:** Display slug (split from type_id via `item.type_id.split(':')[1]`), type_id (small text), workflow_phase as DaisyUI badge, mode as badge (if not null), last_completed_phase. Badge colors: wip→badge-primary, blocked→badge-error, completed→badge-success, others→badge-ghost
- **Done when:** file exists with all 5 display fields and badge color mapping. Validate: `cd plugins/iflow && uv run python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('ui/templates')).get_template('_card.html')"`
- **Depends on:** 2.3.2

### Task 3.5.1: Create error.html template
- **File:** `plugins/iflow/ui/templates/error.html`
- **Action:** Extends base.html. Display `error_title`, `error_message`, `db_path` with setup instructions directing user to run entity registry MCP server or set ENTITY_DB_PATH
- **Done when:** file exists, extends base, shows error fields and setup instructions. Validate: `cd plugins/iflow && uv run python -c "from jinja2 import Environment, FileSystemLoader; Environment(loader=FileSystemLoader('ui/templates')).get_template('error.html')"`
- **Depends on:** 2.3.2

## Phase 4: Integration Tests + CLI

### Task 4.1.1: Write integration test — full page load (AC-3)
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** Using TestClient with temp DB, GET `/` returns 200, response contains all 8 column header names
- **Done when:** test passes
- **Depends on:** 3.1.1, 3.2.1, 3.3.1, 3.4.1, 3.5.1

### Task 4.1.2: Write integration test — HTMX partial (AC-4)
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** TestClient GET `/` with `HX-Request: true` header returns 200, response does NOT contain `<html>` tag (partial only)
- **Done when:** test passes
- **Depends on:** 3.1.1, 3.2.1, 3.3.1

### Task 4.1.3: Write integration test — missing DB (AC-7)
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** Create app via `create_app(db_path="/nonexistent/path.db")` (returns app with `app.state.db = None` since file doesn't exist). Use `TestClient(app)`, GET `/` returns response containing "ENTITY_DB_PATH" text
- **Done when:** test passes
- **Depends on:** 3.5.1

### Task 4.1.4: Write integration test — DB error
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** Create app via `create_app(db_path=tmp_db_path)` where `tmp_db_path` is a real temp DB file (so `app.state.db` is a real EntityDatabase instance, not None). Then patch the method: `app.state.db.list_workflow_phases = unittest.mock.MagicMock(side_effect=Exception("DB error"))`. Use `TestClient(app)`, GET `/` returns response containing error message text
- **Done when:** test passes
- **Depends on:** 3.5.1

### Task 4.1.5: Write integration test — card content (AC-5)
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** Seed temp DB with a workflow_phases row (type_id="feature:test-slug", workflow_phase="wip", mode="standard", kanban_column="wip"). GET `/`, assert response HTML contains "test-slug", "wip" badge, and "standard"
- **Done when:** test passes
- **Depends on:** 3.4.1, 3.3.1, 3.2.1, 3.1.1

### Task 4.1.6: Write integration test — empty board state (AC-6)
- **File:** `plugins/iflow/ui/tests/test_app.py`
- **Action:** Create app with temp DB that has zero workflow_phases rows (empty table). GET `/`, assert response contains "No features yet" empty state message
- **Done when:** test passes
- **Depends on:** 3.3.1, 3.2.1, 3.1.1

### Task 4.1.7: Run full test suite
- **Action:** Run `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/ -v`
- **Done when:** all unit and integration tests pass
- **Depends on:** 4.1.1, 4.1.2, 4.1.3, 4.1.4, 4.1.5, 4.1.6

### Task 4.2.1: Implement CLI entry point
- **File:** `plugins/iflow/ui/__main__.py`
- **Action:** Implement in this order: (1) parse args via argparse with `--port` (int, default 8718), (2) check port availability via `socket.socket()` bind attempt — exit with error if occupied, (3) call `create_app()` to build the FastAPI app, (4) print startup URL `http://127.0.0.1:{port}/` to stdout, (5) call `uvicorn.run(app, host="127.0.0.1", port=port)`. Use absolute imports resolved via PYTHONPATH: `from ui import create_app` (PYTHONPATH includes `$PLUGIN_DIR`). NOT relative imports, because `__main__.py` is invoked directly by the shell wrapper, not via `-m`
- **Done when:** file exists with argparse, port check before create_app, URL print, and uvicorn.run call
- **Depends on:** 2.3.2

### Task 4.2.2: Write CLI port-conflict unit test (AC-2)
- **File:** `plugins/iflow/ui/tests/test_cli.py`
- **Action:** Bind a socket to a port, then invoke port-conflict detection with that port, assert it raises expected error
- **Done when:** test passes
- **Depends on:** 4.2.1

### Task 4.2.3: Write CLI startup URL output test (AC-1)
- **File:** `plugins/iflow/ui/tests/test_cli.py`
- **Action:** Mock `uvicorn.run`, capture stdout, invoke CLI main, assert stdout contains `http://127.0.0.1:8718/`
- **Done when:** test passes
- **Depends on:** 4.2.1

### Task 4.3.1: Create shell bootstrap wrapper
- **File:** `plugins/iflow/mcp/run-ui-server.sh`
- **Action:** Adapt `run-workflow-server.sh` pattern: resolve PLUGIN_DIR and VENV_DIR, set `PYTHONPATH` to include both `$PLUGIN_DIR/hooks/lib` (for entity_registry imports) and `$PLUGIN_DIR` (for `from ui import create_app`), invoke `exec "$VENV_DIR/bin/python" "$PLUGIN_DIR/ui/__main__.py" "$@"`
- **Done when:** file exists, is executable, and follows run-workflow-server.sh structure
- **Depends on:** 4.2.1

### Task 4.3.2: Verify shell wrapper starts server
- **Action:** Run `bash plugins/iflow/mcp/run-ui-server.sh &` to start server in background, capture PID. Run `sleep 2 && curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8718/` to verify 200 response. Then `kill $PID` to stop.
- **Done when:** curl returns HTTP 200 and kill succeeds
- **Depends on:** 4.3.1

## Phase 5: Verification

### Task 5.1.1: Verify SIGINT clean exit
- **Action:** Run `bash plugins/iflow/mcp/run-ui-server.sh 2>/tmp/018-sigint-stderr.txt & PID=$!; sleep 2; kill -INT $PID; wait $PID; echo "EXIT:$?"`. Verify exit code is 0 and `grep -c Traceback /tmp/018-sigint-stderr.txt` returns 0
- **Done when:** exit code is 0 AND no traceback in stderr
- **Depends on:** 4.1.7

### Task 5.1.2: Verify SIGTERM clean exit
- **Action:** Run `bash plugins/iflow/mcp/run-ui-server.sh 2>/tmp/018-sigterm-stderr.txt & PID=$!; sleep 2; kill -TERM $PID; wait $PID; echo "EXIT:$?"`. Verify exit code is 0 and `grep -c Traceback /tmp/018-sigterm-stderr.txt` returns 0
- **Done when:** exit code is 0 AND no traceback in stderr
- **Depends on:** 4.1.7

### Task 5.1.3: Verify DB integrity after shutdown
- **Action:** After 5.1.1 and 5.1.2, run `DB_PATH="${ENTITY_DB_PATH:-$HOME/.claude/iflow/entities/entities.db}" && sqlite3 "$DB_PATH" 'PRAGMA integrity_check'`
- **Done when:** integrity_check returns "ok"
- **Depends on:** 5.1.1, 5.1.2

### Task 5.2.1: Run entity registry regression tests (AC-10)
- **Action:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- **Done when:** all tests pass
- **Depends on:** 4.1.7

### Task 5.2.2: Run workflow engine regression tests (AC-10)
- **Action:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v`
- **Done when:** all tests pass
- **Depends on:** 4.1.7

### Task 5.2.3: Run transition gate regression tests (AC-10)
- **Action:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/ -v`
- **Done when:** all tests pass
- **Depends on:** 4.1.7

### Task 5.2.4: Run MCP server regression tests (AC-10)
- **Action:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`
- **Done when:** all tests pass
- **Depends on:** 4.1.7

### Task 5.3.1: Manual smoke test
- **Action:** Start server, open browser to `http://127.0.0.1:8718/`. Verify: 8 columns rendered, cards display correct data, refresh button works (HTMX partial), empty state message shown when no data
- **Done when:** visual verification confirms AC-3, AC-4, AC-5, AC-6
- **Depends on:** 4.1.7, 4.3.2

## Dependency Summary

### Parallel Groups
- **Tasks 0.1.1, 0.2.1, 0.2.2, 0.2.3:** can run in parallel (spec fix and package installs are independent)
- **Tasks 2.1.1–2.1.5:** logically independent test functions; write to same test file so execute sequentially for a single engineer, but can be parallelized across multiple engineers
- **Tasks 3.1.1–3.5.1:** can run in parallel (independent template files)
- **Tasks 4.1.1–4.1.6:** can run in parallel after all templates complete (independent test functions)
- **Tasks 4.2.1–4.2.3, 4.3.1–4.3.2:** can run in parallel with 4.1.x (CLI track independent of integration test track)
- **Tasks 5.1.1–5.1.2:** can run in parallel (independent signal tests)
- **Tasks 5.2.1–5.2.4:** can run in parallel (independent test suites)

### Critical Path
```
0.2.x → 0.3.x → 1.1.x → 1.2.x → 2.1.x → 2.2.1 → 2.3.x → 3.x → 4.1.x → 4.1.7 → 5.x
(0.1.1 runs in parallel with 0.2.x — not on critical path)
```
