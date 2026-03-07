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

### Task 1.5: Implement entity_list route handler
- **File:** `plugins/iflow/ui/routes/entities.py`
- **Action:** Replace entity_list stub with full implementation following design Route Contract. 5 code paths: (1) `db is None` → error.html, (2) DB query exception → error.html with `print(..., file=sys.stderr)`, (3) search with `ValueError` → fallback to `list_entities` with `search_available=False`, (4) `HX-Request` header → `_entities_content.html` partial, (5) normal → `entities.html` full page. Validate type param against ENTITY_TYPES (invalid → None). Post-filter by status. Sort by `updated_at` DESC. Build workflow lookup. Annotate entities with `kanban_column`. Pass `active_page: "entities"` in context.
- **Done when:** `cd plugins/iflow && PYTHONPATH=.:hooks/lib .venv/bin/python -c "from ui.routes.entities import entity_list; print('OK')"` prints OK AND function signature matches `(request: Request, type: str | None = None, status: str | None = None, q: str | None = None)`. Note: This is import-level validation only. Full code-path verification is deferred to Phase 4 integration tests (4.1, 4.3).
- **Depends on:** 1.2, 1.4

### Task 1.6: Implement entity_detail route handler
- **File:** `plugins/iflow/ui/routes/entities.py`
- **Action:** Replace entity_detail stub with full implementation following design Route Contract. 4 code paths: (1) `db is None` → error.html, (2) entity not found → 404.html with `status_code=404`, (3) DB query exception → error.html, (4) normal → entity_detail.html with `status_code=200`. Extract `type_id` from entity dict. Call `get_lineage` up/down with `_strip_self_from_lineage`. Call `get_workflow_phase(type_id)`. Format metadata. Pass `active_page: "entities"` in context. All DB calls wrapped in single try/except — no partial degradation.
- **Done when:** `cd plugins/iflow && PYTHONPATH=.:hooks/lib .venv/bin/python -c "from ui.routes.entities import entity_detail; print('OK')"` prints OK AND function signature matches `(request: Request, identifier: str)`. Note: This is import-level validation only. Full code-path verification is deferred to Phase 4 integration tests (4.2, 4.3).
- **Depends on:** 1.3, 1.4

### Task 1.7: Register entities router in __init__.py
- **File:** `plugins/iflow/ui/__init__.py` (MODIFIED)
- **Action:** Add `from ui.routes.entities import router as entities_router` and `app.include_router(entities_router)` after existing board router registration.
- **Done when:** `cd plugins/iflow && PYTHONPATH=.:hooks/lib .venv/bin/python -c "from ui import create_app; app = create_app('/tmp/test.db'); paths = [r.path for r in app.routes]; assert any(p.startswith('/entities') for p in paths); print('OK')"` prints OK
- **Depends on:** 1.5, 1.6

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
- **Done when:** `grep -c "active_page" plugins/iflow/ui/routes/board.py` returns at least 2 (one per context dict — normal and HX-Request paths) AND all existing board tests still pass
- **Depends on:** none

### Task 3.3: Wrap _card.html in clickable link
- **File:** `plugins/iflow/ui/templates/_card.html` (MODIFIED)
- **Action:** Wrap entire card `<div>` in `<a href="/entities/{{ item.type_id }}" class="block no-underline [color:inherit]">`. `block` fills card area, `no-underline` prevents text decoration, `[color:inherit]` prevents link color override on card text.
- **Done when:** File contains `href="/entities/{{ item.type_id }}"` AND contains `[color:inherit]` AND contains `no-underline`
- **Depends on:** none (soft dependency on 1.7 for link destination)

## Phase 4: Integration Tests

### Task 4.1: Write integration test infrastructure + entity list tests
- **File:** `plugins/iflow/ui/tests/test_entities.py` (MODIFIED — append to file from Phase 1)
- **Action:** Add integration test section using httpx TestClient matching test_app.py patterns. Create a pytest fixture for DB + app setup:
  - Instantiate `EntityDatabase(tmp_path / "test.db")` (import from `entity_registry.database`)
  - Seed entities: `db.register_entity("feature", "feat-alpha", "Alpha Feature", status="active")`, `db.register_entity("feature", "feat-beta", "Beta Feature", status="completed")`, `db.register_entity("brainstorm", "bs-one", "Brainstorm One", status="active")`, `db.register_entity("project", "proj-one", "Project One", status="active")`
  - Set parent: `db.set_parent("feature:feat-alpha", "project:proj-one")`
  - Seed workflow phases via raw SQL: `db.conn.execute("INSERT INTO workflow_phases (type_id, kanban_column, workflow_phase) VALUES (?, ?, ?)", ("feature:feat-alpha", "In Progress", "implement"))`
  - Create app: `app = create_app(str(tmp_path / "test.db"))` and use `httpx.AsyncClient(transport=ASGITransport(app=app))` or `TestClient(app)`
  Write tests:
  1. **Entity list (FR-1):** GET /entities returns HTTP 200 with all seeded entities in table
  2. **Type filtering (FR-2):** GET /entities?type=feature returns only feature entities
  3. **Status filtering (FR-3):** GET /entities?status=active returns only active entities
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -k "test_entity_list or test_type_filter or test_status_filter" -v` passes all 3 tests
- **Depends on:** 1.7, 2.1, 2.2, 2.3, 2.4

### Task 4.2: Write entity detail + lineage integration tests
- **File:** `plugins/iflow/ui/tests/test_entities.py`
- **Action:** Write tests:
  4. **Entity detail (FR-4):** GET /entities/feature:xxx returns HTTP 200 with all entity fields + workflow data (kanban_column, workflow_phase, last_completed_phase, mode)
  5. **Entity detail 404 (FR-4):** GET /entities/nonexistent:xxx returns HTTP 404 with "Entity not found"
  6. **Lineage (FR-5):** Detail page for entity with parent shows ancestors list and children list, self stripped from both
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -k "test_entity_detail or test_entity_404 or test_lineage" -v` passes all 3 tests
- **Depends on:** 4.1

### Task 4.3: Write search, HTMX, and error handling integration tests
- **File:** `plugins/iflow/ui/tests/test_entities.py`
- **Action:** Write tests:
  7. **Search (FR-8):** GET /entities?q=term returns FTS matches; for FTS fallback test, mock `db.search_entities` to raise `ValueError("FTS index not available")` using `monkeypatch.setattr(app.state.db, "search_entities", lambda *a, **kw: (_ for _ in ()).throw(ValueError("FTS")))` or `unittest.mock.patch.object(app.state.db, "search_entities", side_effect=ValueError("FTS"))`. Verify fallback returns all entities with search input disabled.
  8. **HTMX partial (FR-9):** GET /entities with `HX-Request: true` header returns content partial only (no `<html>` tag, has table)
  9. **Missing DB:** Create a separate app instance or set `app.state.db = None` before the request. Verify GET /entities returns error.html content (check for "error" or "Database" text).
- **Done when:** `plugins/iflow/.venv/bin/python -m pytest plugins/iflow/ui/tests/test_entities.py -k "test_search or test_htmx or test_missing_db" -v` passes all 3 tests
- **Depends on:** 4.1

## Dependency Graph

```
Phase 1 (TDD Cycle):
  1.1 (scaffold)
    ├── 1.2 (workflow lookup helper + tests)
    ├── 1.3 (lineage strip helper + tests)
    └── 1.4 (metadata format helper + tests)
  1.2 + 1.4 → 1.5 (entity_list route)
  1.3 + 1.4 → 1.6 (entity_detail route)
  1.5 + 1.6 → 1.7 (router registration)

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
  1.7 + 2.1-2.4 → 4.1 (list tests)
  4.1 → 4.2 (detail + lineage tests)
  4.1 → 4.3 (search + HTMX + error tests)
```

**Parallel groups:**
- Group A (no dependencies): 1.1, 2.1, 2.2, 2.4, 3.1, 3.2, 3.3
- Group B (after 1.1): 1.2, 1.3, 1.4
- Group C (after Group B): 1.5, 1.6, 2.3
- Group D (after 1.5+1.6): 1.7
- Group E (after all code): 4.1
- Group F (after 4.1): 4.2, 4.3
