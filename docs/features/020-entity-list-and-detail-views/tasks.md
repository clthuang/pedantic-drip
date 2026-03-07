# Tasks: Entity List and Detail Views

## Phase 1: Entity Routes + Helper Tests (TDD Cycle)

### Task 1.1: Create entities.py scaffold with router and constants
- **File:** `plugins/iflow/ui/routes/entities.py` (NEW)
- **Action:** Create file with imports (`json`, `sys`, `APIRouter`, `Request`, `HTMLResponse`), `router = APIRouter(prefix="/entities")`, and `ENTITY_TYPES = ["backlog", "brainstorm", "project", "feature"]` constant. Add empty route stubs for `entity_list` and `entity_detail` that return placeholder HTMLResponse.
- **Done when:** `cd plugins/iflow && PYTHONPATH=.:hooks/lib .venv/bin/python -c "from ui.routes.entities import router, ENTITY_TYPES; print(len(ENTITY_TYPES))"` prints `4`
- **Depends on:** none

### Task 1.2: Implement _build_workflow_lookup helper + unit tests
- **File:** `plugins/iflow/ui/routes/entities.py` (helper function), `plugins/iflow/ui/tests/test_entities.py` (NEW)
- **Action:** Add `_build_workflow_lookup(db)` to entities.py: `{wp["type_id"]: wp for wp in db.list_workflow_phases()}`. Write unit tests in test_entities.py: (1) empty list returns empty dict, (2) list with entries returns correct dict keyed by type_id, (3) last entry wins on key collision.
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -k "build_workflow" -v` passes all 3 tests
- **Depends on:** 1.1

### Task 1.3: Implement _strip_self_from_lineage helper + unit tests
- **File:** `plugins/iflow/ui/routes/entities.py`, `plugins/iflow/ui/tests/test_entities.py`
- **Action:** Add `_strip_self_from_lineage(lineage, type_id)` to entities.py: `[e for e in lineage if e["type_id"] != type_id]`. Write unit tests: (1) empty list returns empty, (2) self present is removed, (3) self absent returns all entries unchanged.
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -k "strip_self" -v` passes all 3 tests
- **Depends on:** 1.1

### Task 1.4: Implement _format_metadata helper + unit tests
- **File:** `plugins/iflow/ui/routes/entities.py`, `plugins/iflow/ui/tests/test_entities.py`
- **Action:** Add `_format_metadata(metadata)` to entities.py: if not metadata return ""; try json.dumps(json.loads(metadata), indent=2); except return raw metadata. Write unit tests: (1) None returns "", (2) empty string returns "", (3) valid JSON returns pretty-printed, (4) invalid JSON returns raw string.
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -k "format_metadata" -v` passes all 4 tests
- **Depends on:** 1.1

### Task 1.5a: Implement entity_list error and fallback code paths
- **File:** `plugins/iflow/ui/routes/entities.py`
- **Action:** Replace entity_list stub with error-handling skeleton: (1) `db is None` → error.html, (2) DB query exception → error.html with `print(..., file=sys.stderr)`, (3) search with `ValueError` → fallback to `list_entities` with `search_available=False`. Add a temporary success return (empty entities list → `entities.html`) so function is importable and runnable.
- **Done when:** `cd plugins/iflow && PYTHONPATH=.:hooks/lib .venv/bin/python -c "from ui.routes.entities import entity_list; print('OK')"` prints OK AND `grep -cE "db is None|search_available|ValueError" plugins/iflow/ui/routes/entities.py` returns at least 3
- **Depends on:** 1.2, 1.4

### Task 1.5b: Implement entity_list success paths (filter/sort/HTMX)
- **File:** `plugins/iflow/ui/routes/entities.py`
- **Action:** Complete entity_list success logic: validate type param against ENTITY_TYPES (invalid → None), post-filter by status, sort by `updated_at` DESC, build workflow lookup via `_build_workflow_lookup`, annotate entities with `kanban_column`, (4) `HX-Request` header → `_entities_content.html` partial, (5) normal → `entities.html` full page. Pass `active_page: "entities"` in context.
- **Done when:** Function signature matches `(request: Request, type: str | None = None, status: str | None = None, q: str | None = None)` AND `grep -cE "HX-Request|kanban_column|sorted.*updated_at" plugins/iflow/ui/routes/entities.py` returns at least 3. Note: Grep gate is a loose sanity check on shared file. Full code-path verification deferred to Phase 4 integration tests (4.1, 4.3).
- **Depends on:** 1.5a

### Task 1.6a: Implement entity_detail error and 404 code paths
- **File:** `plugins/iflow/ui/routes/entities.py`
- **Action:** Replace entity_detail stub with error-handling skeleton: (1) `db is None` → error.html, (2) entity not found → 404.html with `status_code=404`, (3) DB query exception → error.html. Add a temporary success return so function is importable.
- **Done when:** `cd plugins/iflow && PYTHONPATH=.:hooks/lib .venv/bin/python -c "from ui.routes.entities import entity_detail; print('OK')"` prints OK AND `grep -cE "db is None|status_code=404" plugins/iflow/ui/routes/entities.py` returns at least 2
- **Depends on:** 1.3, 1.4

### Task 1.6b: Implement entity_detail success path (lineage/workflow/metadata)
- **File:** `plugins/iflow/ui/routes/entities.py`
- **Action:** Complete entity_detail success logic: extract `type_id` from entity dict, call `get_lineage` up/down with `_strip_self_from_lineage`, call `get_workflow_phase(type_id)`, format metadata via `_format_metadata`. Return entity_detail.html with `status_code=200`. Pass `active_page: "entities"` in context. All DB calls wrapped in single try/except — no partial degradation.
- **Done when:** Function signature matches `(request: Request, identifier: str)` AND `grep -cE "get_lineage|get_workflow_phase|_format_metadata" plugins/iflow/ui/routes/entities.py` returns at least 3. Note: Grep gate is a loose sanity check on shared file. Full code-path verification deferred to Phase 4 integration tests (4.2, 4.3).
- **Depends on:** 1.6a

### Task 1.7: Register entities router in __init__.py
- **File:** `plugins/iflow/ui/__init__.py` (MODIFIED)
- **Action:** Add `from ui.routes.entities import router as entities_router` and `app.include_router(entities_router)` after existing board router registration.
- **Done when:** `cd plugins/iflow && PYTHONPATH=.:hooks/lib .venv/bin/python -c "from ui import create_app; app = create_app('/tmp/test.db'); paths = [r.path for r in app.routes]; assert any(p.startswith('/entities') for p in paths); print('OK')"` prints OK
- **Depends on:** 1.5b, 1.6b

## Phase 2: Templates

### Task 2.1: Create 404.html template
- **File:** `plugins/iflow/ui/templates/404.html` (NEW)
- **Action:** Create template extending base.html. Centered card with "Entity not found" heading, descriptive message, and `<a href="/entities">` link back to entity list. Similar structure to existing error.html but with 404-specific messaging.
- **Done when:** File exists AND contains `{% extends "base.html" %}` AND contains `Entity not found` AND contains `href="/entities"`
- **Depends on:** none

### Task 2.2: Create _entities_content.html HTMX partial
- **File:** `plugins/iflow/ui/templates/_entities_content.html` (NEW)
- **Action:** Create partial template containing ALL filter controls AND table inside a single fragment:
  - Filter tabs: "All" + one per entity type as `<a>` links with `hx-get="/entities?type=X"`, `hx-target="#entities-content"`, `hx-replace-url="true"`. Active tab highlighted based on `current_type`.
  - Hidden input: `<input type="hidden" name="type" value="{{ current_type or '' }}">`
  - Search input: `<input name="q" value="{{ search_query or '' }}" hx-get="/entities" hx-trigger="input changed delay:300ms" hx-target="#entities-content" hx-sync="this:replace" hx-include="[name='type'],[name='status']" hx-replace-url="true">`. Show "Search unavailable" when `search_available` is False.
  - Status dropdown: `<select name="status" hx-get="/entities" hx-trigger="change" hx-target="#entities-content" hx-include="[name='type'],[name='q']" hx-replace-url="true">` with All/active/completed/planned options. Pre-select `current_status`.
  - Table: columns Name (clickable link to `/entities/{{ entity.type_id }}`), Type ID, Type, Status, Kanban Column (`entity.kanban_column`, blank when None), Updated.
  - Row count: `{{ entities|length }} entities`
  - Empty state: "No entities found" / "No entities match your search"
- **Done when:** File exists AND contains `hx-get="/entities"` AND contains `hx-trigger="input changed delay:300ms"` AND contains `hx-replace-url="true"` AND contains `entities|length`
- **Depends on:** none

### Task 2.3: Create entities.html full page wrapper
- **File:** `plugins/iflow/ui/templates/entities.html` (NEW)
- **Action:** Create template extending base.html. Content block contains page heading "Entities" and `<div id="entities-content">{% include "_entities_content.html" %}</div>`. No filter controls here — all in _entities_content.html partial.
- **Done when:** File exists AND contains `{% extends "base.html" %}` AND contains `id="entities-content"` AND contains `{% include "_entities_content.html" %}`
- **Depends on:** 2.2

### Task 2.4: Create entity_detail.html template
- **File:** `plugins/iflow/ui/templates/entity_detail.html` (NEW)
- **Action:** Create template extending base.html with sections:
  - Back link: `<a href="/entities">` back to entity list
  - Entity Info card: name, type_id, uuid, entity_type, entity_id, status, artifact_path, created_at, updated_at
  - Workflow State card (conditional on `workflow` not None): kanban_column, workflow_phase, last_completed_phase, mode, backward_transition_reason
  - Lineage card: ancestors list as clickable links (`<a href="/entities/{{ a.type_id }}">`) with "No parent" fallback; children list as clickable links with "No children" fallback
  - Metadata card: `<pre>` block with `{{ metadata_formatted }}`
  Use DaisyUI card components (`card bg-base-200 shadow-sm`).
- **Done when:** File exists AND contains `{% extends "base.html" %}` AND contains `workflow` conditional AND contains `metadata_formatted` AND contains `href="/entities/{{ a.type_id }}"`
- **Depends on:** none

## Phase 3: Existing File Modifications

### Task 3.1: Add navbar links to base.html
- **File:** `plugins/iflow/ui/templates/base.html` (MODIFIED)
- **Action:** Add "Board" (`href="/"`) and "Entities" (`href="/entities"`) links to the navbar. Use `{{ active_page|default('') }}` for active state styling — apply DaisyUI `btn-active` class when `active_page` matches. Defensive `|default('')` prevents NameError if `active_page` not in context.
- **Done when:** File contains `href="/entities"` AND contains `href="/"` with "Board" text AND contains `active_page|default`
- **Depends on:** none

### Task 3.2: Add active_page context to board.py
- **File:** `plugins/iflow/ui/routes/board.py` (MODIFIED)
- **Action:** Add `"active_page": "board"` to all template context dicts in the board route handler. Minimal change — add one key-value to each existing context dict.
- **Done when:** `grep -c "active_page" plugins/iflow/ui/routes/board.py` returns at least 2 (one per success-path context dict — the HTMX partial return and the full-page return; error-path returns do not need active_page) AND `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_app.py -v` passes all existing board tests
- **Depends on:** none

### Task 3.3: Wrap _card.html in clickable link
- **File:** `plugins/iflow/ui/templates/_card.html` (MODIFIED)
- **Action:** Wrap entire card `<div>` in `<a href="/entities/{{ item.type_id }}" class="block no-underline [color:inherit]">`. `block` fills card area, `no-underline` prevents text decoration, `[color:inherit]` prevents link color override on card text.
- **Done when:** File contains `href="/entities/{{ item.type_id }}"` AND contains `[color:inherit]` AND contains `no-underline`
- **Depends on:** none (soft dependency on 1.7 for link destination)

## Phase 4: Integration Tests

### Task 4.0: Create integration test fixture
- **File:** `plugins/iflow/ui/tests/test_entities.py` (MODIFIED — append to file from Phase 1)
- **Action:** Add integration test section with a shared pytest fixture for DB + app setup matching test_app.py patterns:
  - Instantiate `EntityDatabase(tmp_path / "test.db")` (import from `entity_registry.database`)
  - Seed entities: `db.register_entity("feature", "feat-alpha", "Alpha Feature", status="active")`, `db.register_entity("feature", "feat-beta", "Beta Feature", status="completed")`, `db.register_entity("brainstorm", "bs-one", "Brainstorm One", status="active")`, `db.register_entity("project", "proj-one", "Project One", status="active")`
  - Set parent: `db.set_parent("feature:feat-alpha", "project:proj-one")`
  - Disable FK enforcement: `db.conn.execute("PRAGMA foreign_keys = OFF")`
  - Seed workflow phases via raw SQL: `db.conn.execute("INSERT INTO workflow_phases (type_id, kanban_column, workflow_phase) VALUES (?, ?, ?)", ("feature:feat-alpha", "In Progress", "implement"))`
  - Create app: `app = create_app(str(tmp_path / "test.db"))` and use `httpx.AsyncClient(transport=ASGITransport(app=app))` or `TestClient(app)`
  - Return client (and optionally app) for use by test functions
- **Done when:** `cd plugins/iflow && PYTHONPATH=.:hooks/lib .venv/bin/python -c "from ui.tests.test_entities import *; print('OK')"` prints OK (fixture importable, no syntax errors)
- **Depends on:** 1.7, 2.1, 2.2, 2.3, 2.4

### Task 4.1: Write entity list integration tests
- **File:** `plugins/iflow/ui/tests/test_entities.py`
- **Action:** Write 3 test functions using the fixture from 4.0:
  1. **Entity list (FR-1):** GET /entities returns HTTP 200 with all seeded entities in table
  2. **Type filtering (FR-2):** GET /entities?type=feature returns only feature entities
  3. **Status filtering (FR-3):** GET /entities?status=active returns only active entities
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -k "test_entity_list or test_type_filter or test_status_filter" -v` passes all 3 tests
- **Depends on:** 4.0

### Task 4.2: Write entity detail + lineage integration tests
- **File:** `plugins/iflow/ui/tests/test_entities.py`
- **Action:** Write tests:
  4. **Entity detail (FR-4):** GET /entities/feature:xxx returns HTTP 200 with all entity fields + workflow data (kanban_column, workflow_phase, last_completed_phase, mode)
  5. **Entity detail 404 (FR-4):** GET /entities/nonexistent:xxx returns HTTP 404 with "Entity not found"
  6. **Lineage (FR-5):** Detail page for entity with parent shows ancestors list and children list, self stripped from both
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -k "test_entity_detail or test_entity_404 or test_lineage" -v` passes all 3 tests
- **Depends on:** 4.0

### Task 4.3: Write search, HTMX, and error handling integration tests
- **File:** `plugins/iflow/ui/tests/test_entities.py`
- **Action:** Write tests:
  7. **Search (FR-8):** GET /entities?q=term returns FTS matches; for FTS fallback test, mock `db.search_entities` to raise `ValueError("FTS index not available")` using `app.state.db.search_entities = unittest.mock.MagicMock(side_effect=ValueError("FTS index not available"))`. Verify fallback returns all entities with search input disabled.
  8. **HTMX partial (FR-9):** GET /entities with `HX-Request: true` header returns content partial only (no `<html>` tag, has table)
  9. **Missing DB:** Create a separate app instance or set `app.state.db = None` before the request. Verify GET /entities returns error.html content (check for "error" or "Database" text).
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -k "test_search or test_htmx or test_missing_db" -v` passes all 3 tests
- **Depends on:** 4.0

## Dependency Graph

```
Phase 1 (TDD Cycle):
  1.1 (scaffold)
    ├── 1.2 (workflow lookup helper + tests)
    ├── 1.3 (lineage strip helper + tests)
    └── 1.4 (metadata format helper + tests)
  1.2 + 1.4 → 1.5a (entity_list error/fallback paths)
  1.5a → 1.5b (entity_list success paths)
  1.3 + 1.4 → 1.6a (entity_detail error/404 paths)
  1.6a → 1.6b (entity_detail success path)
  1.5b + 1.6b → 1.7 (router registration)

Phase 2 (Templates — independent of Phase 1):
  2.1 (404.html) — independent
  2.2 (_entities_content.html) — independent
  2.2 → 2.3 (entities.html)
  2.4 (entity_detail.html) — independent

Phase 3 (Modifications — independent):
  3.1 (base.html navbar) — independent
  3.2 (board.py active_page) — independent
  3.3 (_card.html link) — independent (soft dep on 1.7)

Phase 4 (Integration Tests — after all above):
  1.7 + 2.1-2.4 → 4.0 (fixture setup)
  4.0 → 4.1 (list tests)
  4.0 → 4.2 (detail + lineage tests)
  4.0 → 4.3 (search + HTMX + error tests)
```

**Parallel groups:**
- Group A (no dependencies): 1.1, 2.1, 2.2, 2.4, 3.1, 3.2, 3.3
- Group B (after 1.1): 1.2, 1.3, 1.4
- Group C (after Group B): 1.5a, 1.6a, 2.3
- Group D (after 1.5a/1.6a): 1.5b, 1.6b
- Group E (after 1.5b+1.6b): 1.7
- Group F (after all code): 4.0
- Group G (after 4.0): 4.1, 4.2, 4.3
