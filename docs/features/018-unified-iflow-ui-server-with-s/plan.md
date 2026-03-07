# Plan: iflow UI Server + Kanban Board

## Implementation Order

### Phase 0: Prerequisites (Sequential)

**0.1: Correct spec inaccuracies**
- Why: Design identified CDN URL and Jinja2 dependency errors in spec. Must fix before implementation references spec.
- Update spec.md SC-8 and AC-9 CDN URLs from `cdn.tailwindcss.com` to `cdn.jsdelivr.net/npm/@tailwindcss/browser@4`
- Fix spec Dependencies line 112: change "already available in plugin venv" to "added via `uv add jinja2`"
- Done when: `grep cdn.tailwindcss.com spec.md` returns zero matches; Jinja2 line corrected

**0.2: Install dependencies**
- Why: FastAPI, Jinja2, and httpx must be available before any code or tests. Added as main dependencies for simplicity — the plugin already has heavy deps (mcp, etc.) and splitting into optional groups adds complexity without benefit for private tooling.
- Run `uv add fastapi>=0.128.3` and `uv add jinja2` in `plugins/iflow/`
- If FastAPI or Jinja2 version resolution fails: STOP and escalate
- Verify httpx is available (required by FastAPI TestClient): `uv run python -c "import httpx"`. If import fails, run `uv add httpx`
- Done when: `uv run python -c "import fastapi; import jinja2; import httpx; print('OK')"` prints OK

**0.3: PoC Validation Gate (pass/fail)**
- Why: Must validate SQLite thread safety before committing to sync vs async route design.
- Create `agent_sandbox/018-poc/test_thread_safety.py` — 20-line script:
  - FastAPI app with sync route using `sqlite3.connect(path, check_same_thread=False)` on temp DB
  - Must replicate EntityDatabase's PRAGMA settings: `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`, `cache_size=-8000` (same as `_set_pragmas()`)
  - Note: Uses raw sqlite3 because EntityDatabase's `check_same_thread` parameter is not yet added (that's 1.1). The PRAGMAs are what matter for concurrency behavior.
  - Seed 10 workflow_phases rows
  - Fire 10 concurrent GET requests via `asyncio.gather` + `httpx.AsyncClient`
- Pass: all 10 return HTTP 200, zero `ProgrammingError` in stderr, script exits 0
- **If pass → continue to Phase 1 (sync route as designed)**
- **If fail → apply async fallback:** convert C3 board route to `async def board()`, wrap DB calls with `asyncio.to_thread(db.list_workflow_phases)`. Continue to Phase 1 with async variant.
- **Async fallback impact analysis:** The fallback affects ONLY the route handler signature in 2.3 (`async def` instead of `def`). Templates are unaffected (same context contract). CLI and shell wrapper are unaffected (`create_app()` signature unchanged). All downstream items remain valid under both PoC outcomes.
- Done when: script runs and exits 0

### Phase 1: Foundation (Sequential)

**1.1: EntityDatabase modification (C4)**
- Why: C4 design requirement — UI server needs `check_same_thread=False`. Must precede 2.2 (app factory) which instantiates EntityDatabase with the new parameter.
- File: `plugins/iflow/hooks/lib/entity_registry/database.py`
- Add `check_same_thread` as keyword-only parameter (after `*` in signature): `def __init__(self, db_path: str, *, check_same_thread: bool = True)`
- Pass through to `sqlite3.connect(..., check_same_thread=check_same_thread)`
- Run existing entity registry tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- If any existing test fails: revert the change and investigate before proceeding. The default=True preserves all existing behavior — a test failure indicates an unexpected interaction.
- Done when: all existing tests pass (no regressions)

**1.2: Create package structure**
- Why: Directory and module structure must exist before any code or test files.
- Create directories: `plugins/iflow/ui/`, `plugins/iflow/ui/routes/`, `plugins/iflow/ui/templates/`, `plugins/iflow/ui/tests/`
- Create `__init__.py` files: `plugins/iflow/ui/__init__.py`, `plugins/iflow/ui/routes/__init__.py`, `plugins/iflow/ui/tests/__init__.py`
- Done when: `test -f plugins/iflow/ui/__init__.py && test -f plugins/iflow/ui/routes/__init__.py && test -f plugins/iflow/ui/tests/__init__.py` succeeds

### Phase 2: Core Application — TDD (Sequential)

**2.1: Unit tests (RED — write tests first against design contracts)**
- Why: TDD — tests written against design contracts before implementation, ensuring interface compliance.
- File: `plugins/iflow/ui/tests/test_app.py`
- Unit test for `create_app()`: returns FastAPI with `db`, `db_path`, `templates` state attrs
- Unit test for `create_app()` with missing DB path: `app.state.db` is `None`
- Unit test for `_group_by_column()` with three distinct cases:
  - Empty input returns 8 empty lists
  - Single-column input routes to correct column
  - Rows with missing/None `kanban_column` default to 'backlog' (per design `row.get('kanban_column', 'backlog')`)
  - Rows with unknown non-None `kanban_column` values (e.g., 'archived') are silently dropped (per design lines 283-287: only appends if `col in columns`)
- These tests will FAIL initially — that's expected (RED phase)
- Done when: tests are written and run (failures expected)

**2.2: App Factory implementation (GREEN)**
- Why: C1 design component. Makes create_app unit tests pass.
- File: `plugins/iflow/ui/__init__.py`
- Implement `create_app(db_path: str | None = None) -> FastAPI`
- DB path resolution from `ENTITY_DB_PATH` env var or default `~/.claude/iflow/entities/entities.db`
- `app.state.db = EntityDatabase(path, check_same_thread=False)` if file exists, else `None`
- Note: EntityDatabase.__init__ calls `_migrate()` which is idempotent on an already-migrated schema. Concurrent startup with MCP servers is safe due to WAL mode + busy_timeout=5000.
- `app.state.db_path = resolved_path`
- `app.state.templates = Jinja2Templates(directory=templates_dir)`
- Register board router via `app.include_router()`
- Done when: create_app unit tests pass

**2.3: Board Route implementation (GREEN)**
- Why: C3 design component. Makes _group_by_column unit tests pass.
- File: `plugins/iflow/ui/routes/board.py`
- Implement `COLUMN_ORDER` list, `_group_by_column()` helper, `board()` route handler
- Route: sync `def board(request: Request)` (or `async def` if PoC failed)
- Use keyword arguments for TemplateResponse: `templates.TemplateResponse(request=request, name="board.html", context=context)` — this supersedes design line 260's positional convention, which is the deprecated Starlette signature incompatible with FastAPI >=0.128.3
- Handle: missing DB → error.html, DB error → error.html, HX-Request → partial, else → full page
- Done when: _group_by_column unit tests pass, route function exists with all 4 code paths

### Phase 3: Templates (Parallel group)

Why: Templates must exist before integration tests can verify full request/response cycle.

All 5 templates can be written in parallel — they have no code dependencies on each other.

**3.1: base.html**
- CDN tags in correct order: daisyui.css → @tailwindcss/browser@4 → htmx.org
- Navbar with "iflow" title
- `{% block content %}{% endblock %}`

**3.2: board.html**
- Extends base.html
- `<div id="board-content">` with `{% include "_board_content.html" %}`
- Refresh button: `hx-get="/" hx-target="#board-content" hx-swap="innerHTML"`

**3.3: _board_content.html**
- 8-column horizontal grid/flex layout
- Iterate `column_order`, render column headers with name + card count
- Include `_card.html` for each item in column
- Empty state: "No features yet" when all columns empty

**3.4: _card.html**
- Display: slug (split from type_id), type_id (small), workflow_phase (DaisyUI badge), mode (badge if not null), last_completed_phase
- Badge color mapping: wip→badge-primary, blocked→badge-error, completed→badge-success, others→badge-ghost

**3.5: error.html**
- Extends base.html
- Display: error_title, error_message, db_path with setup instructions

Done when: all templates have valid Jinja2 syntax

### Phase 4: Integration Tests + CLI (Sequential)

**4.1: Integration tests (require templates from Phase 3)**
- Why: TestClient integration tests need templates to render. Separated from unit tests (2.1) to avoid circular dependency. No dependency on 4.2/4.3 — TestClient creates the app in-process, bypassing CLI and shell wrapper entirely.
- File: `plugins/iflow/ui/tests/test_app.py` (append to existing test file)
- TestClient GET `/` full page: returns 200, contains 8 column headers
- TestClient GET `/` with `HX-Request: true` header: returns 200, partial HTML (no `<html>` wrapper)
- TestClient GET `/` with missing DB (`app.state.db = None`): returns error page with setup instructions
- TestClient GET `/` with DB error: returns error page with error message
- TestClient GET `/` with seeded data: response HTML contains expected slug, workflow_phase badge, and mode values from seeded row (AC-5 card content verification)
- Run: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/ -v`
- Done when: all unit and integration tests pass

**4.2: CLI Entry Point + CLI tests (C2)**
- Why: C2 design component — user-facing entry point. CLI port-conflict test written here alongside implementation (not in 2.1) to avoid a permanently-RED test through Phases 2-3.
- File: `plugins/iflow/ui/__main__.py`
- argparse: `--port` (int, default 8718)
- Port conflict detection via `socket.bind()` attempt
- Print startup URL to stdout
- `uvicorn.run(create_app(), host="127.0.0.1", port=port)`
- Write unit test for CLI port-conflict detection (socket.bind on occupied port raises expected error) in `plugins/iflow/ui/tests/test_cli.py`
- Done when: CLI port-conflict unit test passes; `python -c "from plugins.iflow.ui import create_app; print(create_app())"` succeeds with correct PYTHONPATH. Full server startup verification deferred to 4.3 (wrapper) and 5.3 (smoke test).

**4.3: Shell Bootstrap Wrapper (C2b)**
- Why: C2b design component — co-located with sibling `run-*-server.sh` scripts in `mcp/` directory.
- File: `plugins/iflow/mcp/run-ui-server.sh`
- Adapt `run-workflow-server.sh` pattern: venv resolution, forward args
- PYTHONPATH must include `$PLUGIN_DIR/hooks/lib` (for entity_registry imports)
- Invocation: `exec "$VENV_DIR/bin/python" "$PLUGIN_DIR/ui/__main__.py" "$@"` — this is the established pattern used by `run-workflow-server.sh` (direct script path with `SERVER_SCRIPT`, never `-m`). The `__main__.py` must use absolute imports resolved via PYTHONPATH (e.g., `from entity_registry.database import EntityDatabase`), not relative imports (which require `-m` invocation).
- Done when: `bash plugins/iflow/mcp/run-ui-server.sh` starts the server and `create_app` import resolves correctly

### Phase 5: Verification (Sequential)

**5.1: Verify Uvicorn signal handling**
- Start server, send SIGINT — confirm exit code 0 and no traceback on stderr
- Start server, send SIGTERM — confirm exit code 0 and no traceback on stderr
- Verify DB integrity after shutdown: `sqlite3 <db_path> 'PRAGMA integrity_check'`
- Done when: both signals produce clean exit with no DB corruption

**5.2: Run existing test suites (AC-10 regression)**
- Entity registry tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/entity_registry/ -v`
- Workflow engine tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/workflow_engine/ -v`
- Transition gate tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/hooks/lib/transition_gate/ -v`
- MCP server tests: `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/mcp/test_workflow_state_server.py -v`
- Done when: all test suites pass with zero failures

**5.3: Manual smoke test**
- Start server, open browser to `http://127.0.0.1:8718/`
- Verify: 8 columns rendered, cards display correct data, refresh button works (HTMX partial), empty state message shown when no data
- Done when: visual verification confirms AC-3, AC-4, AC-5, AC-6

## Dependency Graph

```
0.1 (spec fix) ──┐
0.2 (deps)    ───┤
                 ├──▶ 0.3 (PoC gate) ──▶ 1.1 (C4 DB mod) ──▶ 1.2 (package) ──▶ 2.1 (unit tests RED)
                                                                                       │
                                                                                       ▼
                                                                                 2.2 (app factory GREEN)
                                                                                       │
                                                                                       ▼
                                                                                 2.3 (board route GREEN)
                                                                                       │
                                                                          ┌────────────┤
                                                                          ▼            ▼
                                                                    3.1-3.5       4.2 (CLI)
                                                                    (templates)        │
                                                                          │            ▼
                                                                          ▼       4.3 (wrapper)
                                                                    4.1 (integ tests)  │
                                                                          │            │
                                                                          ▼            ▼
                                                                       5.1-5.3 (verify)
                                                                    (requires both 4.1 and 4.3)
```

## Acceptance Criteria Coverage

| AC | Plan Item | Verification |
|----|-----------|-------------|
| AC-1 | 4.2 CLI Entry Point | Server binds, prints URL |
| AC-2 | 4.2 CLI Entry Point + test | Port conflict error (unit test) |
| AC-3 | 4.1 + 3.1-3.3 | Full page with 8 columns (TestClient + smoke) |
| AC-4 | 4.1 + 3.2-3.3 | HTMX partial refresh (TestClient + smoke) |
| AC-5 | 3.4 + 4.1 integration test | Card displays correct fields (TestClient + smoke) |
| AC-6 | 4.1 + 3.3 | Empty state message (TestClient + smoke) |
| AC-7 | 4.1 + 3.5 | Error page with DB path (TestClient) |
| AC-8 | 0.3 PoC + 1.1 C4 | Concurrent requests pass |
| AC-9 | 3.1 base.html | 3 CDN tags load |
| AC-10 | 5.2 regression tests | All existing tests pass |

## Risk Mitigations

| Risk | Plan Response |
|------|--------------|
| FastAPI version conflict | 0.2 fails fast — escalate before proceeding |
| Jinja2 version conflict | 0.2 fails fast — escalate before proceeding |
| httpx missing | 0.2 verifies availability, adds if missing |
| SQLite thread safety | 0.3 PoC gate validates before implementation |
| PoC failure | Async fallback path defined in 0.3 with impact analysis |
| EntityDatabase regression | 1.1 revert-and-investigate clause |
| Signal handling | 5.1 explicit verification with PRAGMA integrity_check |
| Template-test circular dep | Integration tests (4.1) separated from unit tests (2.1), run after templates |
| PoC fidelity vs real DB | 0.3 uses raw sqlite3 with same PRAGMAs as EntityDatabase._set_pragmas() |
| Shell wrapper portability | 4.3 uses direct script path (not module invocation) to work from both dev and cache locations |
| Concurrent _migrate() | WAL mode + busy_timeout=5000 handles brief lock contention; _migrate() is idempotent |
