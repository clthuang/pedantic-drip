# Plan: Entity List and Detail Views

## Implementation Order

The implementation follows a bottom-up approach: backend route logic first (testable independently), then templates (depend on route context), then integration (modifications to existing files). Tests are written alongside each phase — helper unit tests in Phase 1, integration tests in Phase 4 after all code exists.

```
Phase 1: Entity Routes (backend) + Helper Tests
    ├─ 1a. entities.py route module with entity_list and entity_detail
    ├─ 1b. Helper functions (_build_workflow_lookup, _strip_self_from_lineage, _format_metadata)
    ├─ 1c. Unit tests for helper functions (pure functions, testable immediately)
    └─ 1d. Router registration in __init__.py

Phase 2: Templates (frontend)
    ├─ 2a. 404.html (simplest, no dependencies)
    ├─ 2b. _entities_content.html (filter tabs, search, status dropdown, table)
    ├─ 2c. entities.html (full page wrapper, includes _entities_content.html)
    └─ 2d. entity_detail.html (entity info, workflow state, lineage, metadata)

Phase 3: Existing File Modifications
    ├─ 3a. base.html — navbar with Board/Entities links and active state (defensive: use |default(''))
    ├─ 3b. board.py — add active_page: "board" to all template contexts
    └─ 3c. _card.html — wrap card in clickable <a> link

Phase 4: Integration Tests
    └─ 4a. test_entities.py — all 9 test scenarios from design (requires all code)
```

## Phase 1: Entity Routes

### 1a. Create `entities.py` route module

**File:** `plugins/iflow/ui/routes/entities.py` (NEW)

**What:** Implement both route handlers (`entity_list` and `entity_detail`) in a single file with `APIRouter(prefix="/entities")`.

**Key implementation details:**
- `ENTITY_TYPES = ["backlog", "brainstorm", "project", "feature"]` — constant at module level, matching DB CHECK constraint.
- `entity_list`: Follow 5-code-path pattern per design. Code paths: (1) missing DB → error.html, (2) DB query error → error.html with stderr logging, (3) search with FTS unavailable (ValueError) → fallback to list_entities with search disabled, (4) HX-Request header → _entities_content.html partial, (5) normal request → entities.html full page. Validate type param against ENTITY_TYPES constant. Post-filter by status. Sort by updated_at DESC. Build workflow lookup dict via `_build_workflow_lookup(db)` — call `list_workflow_phases()` with no arguments.
- `entity_detail`: Check DB not None. Call `get_entity(identifier)` — None → 404.html with status_code=404. Extract type_id from entity dict. Call get_lineage up/down with self-stripping via `_strip_self_from_lineage()`. Call `get_workflow_phase(type_id)`. Format metadata JSON via `_format_metadata()`. Return full page only.
- Both routes pass `active_page: "entities"` in template context.

**Dependencies:** None (uses only existing DB methods via `request.app.state.db`).

**Acceptance:** Route handlers parse params, call DB methods correctly, return appropriate template responses for all 5 code paths (entity_list) and 4 code paths (entity_detail).

### 1b. Helper functions

**File:** Same `entities.py` file (module-level private functions).

**What:** Three helpers defined at module level:
- `_build_workflow_lookup(db)` — `{wp["type_id"]: wp for wp in db.list_workflow_phases()}` (call with no arguments)
- `_strip_self_from_lineage(lineage, type_id)` — `[e for e in lineage if e["type_id"] != type_id]`
- `_format_metadata(metadata)` — JSON parse + re-format with indent=2, with fallback to raw string

**Dependencies:** 1a (same file, but logically independent).

**Acceptance:** Each helper handles edge cases (empty input, invalid JSON, missing type_id).

### 1c. Unit tests for helper functions

**File:** `plugins/iflow/ui/tests/test_entities.py` (NEW — tests added first, integration tests appended in Phase 4)

**What:** Unit tests for the three pure helper functions. These are testable immediately without templates or full app setup:
- `_build_workflow_lookup`: empty list, list with entries, key collision
- `_strip_self_from_lineage`: empty list, self present, self absent
- `_format_metadata`: None input, valid JSON, invalid JSON, empty string

**Dependencies:** 1a+1b (helpers must exist to import).

**Acceptance:** All helper unit tests pass. Tests import helpers directly from entities module.

### 1d. Router registration

**File:** `plugins/iflow/ui/__init__.py` (MODIFIED)

**What:** Add import and `app.include_router(entities_router)` after existing board router registration.

**Dependencies:** 1a (entities.py must exist).

**Acceptance:** App starts without errors with both board and entities routers registered.

## Phase 2: Templates

### 2a. Create `404.html`

**File:** `plugins/iflow/ui/templates/404.html` (NEW)

**What:** Extends base.html. Centered card with "Entity not found" message and link back to `/entities`. Similar structure to error.html but with 404-specific messaging. Passes `active_page: "entities"` for navbar state.

**Dependencies:** None (uses existing base.html).

**Acceptance:** Renders standalone with entity not found message and back link.

### 2b. Create `_entities_content.html`

**File:** `plugins/iflow/ui/templates/_entities_content.html` (NEW)

**What:** HTMX partial containing ALL filter controls AND table (so HTMX partial refresh re-renders everything including active tab state):
- Filter tabs: "All" + one per entity type, `<a>` links with hx-get/hx-target="#entities-content"/hx-replace-url="true"
- Hidden `<input type="hidden" name="type" value="{{ current_type or '' }}">` for hx-include state carrying (this is the single owner of the hidden type input)
- Search input with debounce (hx-trigger="input changed delay:300ms", hx-sync="this:replace", hx-include="[name='type'],[name='status']")
- Status dropdown with hx-trigger="change", hx-include="[name='type'],[name='q']"
- Table with columns: Name, Type ID, Type, Status, Kanban Column, Updated
- Name cell as clickable link to detail page: `<a href="/entities/{{ entity.type_id }}">`
- Kanban Column cell: shows value from workflow lookup for feature entities, blank for others
- Empty state messaging ("No entities found" / "No entities match your search")
- Row count display: `{{ entities | length }} entities`
- Search unavailable indicator when search_available is False

**Dependencies:** None (template standalone, rendered by route).

**Acceptance:** Renders entity table with all filter controls. Active tab highlighted. Empty states shown correctly.

### 2c. Create `entities.html`

**File:** `plugins/iflow/ui/templates/entities.html` (NEW)

**What:** Extends base.html. Contains `<div id="entities-content">{% include "_entities_content.html" %}</div>`. This is the full page wrapper — HTMX replaces #entities-content on filter/search. No filter controls here (all in 2b partial).

**Dependencies:** 2b (_entities_content.html must exist for include).

**Acceptance:** Full page renders with navbar + entity content. HTMX target div wraps content partial.

### 2d. Create `entity_detail.html`

**File:** `plugins/iflow/ui/templates/entity_detail.html` (NEW)

**What:** Extends base.html. Sections:
- Back link to /entities
- Entity Info: all fields (name, type_id, uuid, entity_type, entity_id, status, artifact_path, created_at, updated_at)
- Workflow State (conditional on `workflow` not None): kanban_column, workflow_phase, last_completed_phase, mode, backward_transition_reason
- Lineage: ancestors list (clickable links) with "No parent" fallback, children list (clickable links) with "No children" fallback
- Metadata: `<pre>` block with metadata_formatted

**Dependencies:** None (uses existing base.html).

**Acceptance:** Detail page renders all entity fields. Workflow section only appears for features. Lineage entries are clickable. Metadata displays formatted JSON.

## Phase 3: Existing File Modifications

### 3a. Modify `base.html` — navbar

**File:** `plugins/iflow/ui/templates/base.html` (MODIFIED)

**What:** Add Board and Entities links to navbar. Use `active_page` template variable for active state styling (DaisyUI `btn-active` or equivalent class). Use `{{ active_page|default('') }}` to prevent NameError if active_page is not in context — this makes the change safe to deploy before board.py is updated (3b).

**Dependencies:** None. Defensive template with `|default('')` eliminates hard dependency on 3b.

**Acceptance:** Navbar shows both links. Active page visually distinguished. No error if active_page not provided.

### 3b. Modify `board.py` — active_page context

**File:** `plugins/iflow/ui/routes/board.py` (MODIFIED)

**What:** Add `"active_page": "board"` to all template context dicts in the board route handler. Minimal change — just add one key-value to existing context dicts.

**Dependencies:** None (independent code change; 3a is defensive with `|default`).

**Acceptance:** Board page renders with "Board" link active in navbar.

### 3c. Modify `_card.html` — clickable link

**File:** `plugins/iflow/ui/templates/_card.html` (MODIFIED)

**What:** Wrap entire card `<div>` in `<a href="/entities/{{ item.type_id }}" class="block no-underline [color:inherit]">`. Preserves all existing card styling while making entire card clickable. If the linked entity doesn't exist in the entities table (e.g., a workflow_phases-only row), the click navigates to the 404 page — this is expected and acceptable behavior.

**Dependencies:** Soft dependency on 1d (entity detail route should be registered so link destination works, but card renders correctly regardless — link simply won't resolve until route exists).

**Acceptance:** Kanban cards are clickable, navigate to entity detail. Card visual appearance unchanged.

## Phase 4: Integration Tests

### 4a. Create integration tests in `test_entities.py`

**File:** `plugins/iflow/ui/tests/test_entities.py` (MODIFIED — append to file created in 1c)

**What:** Integration tests using httpx TestClient (matching existing test_app.py patterns). Append to the test file created in Phase 1 (which already has helper unit tests). Test scenarios from design:

1. **Entity list (FR-1):** GET /entities returns all entities in table
2. **Type filtering (FR-2):** GET /entities?type=feature returns only features
3. **Status filtering (FR-3):** GET /entities?status=active returns only active entities
4. **Entity detail (FR-4):** GET /entities/feature:xxx returns detail page with all fields + workflow data
5. **Entity detail 404 (FR-4):** GET /entities/nonexistent returns 404 page
6. **Lineage (FR-5):** Detail page shows ancestors and children, self stripped
7. **Search (FR-8):** GET /entities?q=term returns FTS matches; ValueError fallback shows all with search disabled
8. **HTMX partial (FR-9):** HX-Request header returns content partial only
9. **Missing DB:** When db is None, returns error.html

Test infrastructure: reuse existing conftest.py fixtures for DB setup. Seed test data using direct DB calls (register_entity, set_parent) matching test_app.py patterns.

**Dependencies:** Phases 1-3 (all code must exist for integration tests).

**Acceptance:** All tests pass. Coverage of all 9 spec acceptance criteria areas.

## Dependency Graph

```
1a+1b ──→ 1c (helper tests)
  │
  └──→ 1d (registration)
2a (independent)
2b (independent)
2c ──→ depends on 2b
2d (independent)
3a (independent, defensive with |default)
3b (independent)
3c (soft dependency on 1d)

4a ──→ depends on all above (integration tests)
```

**Parallel groups:**
- Group A (no dependencies): 1a+1b, 2a, 2b, 2d, 3a, 3b — all can be built independently
- Group B (after Group A): 1c, 1d, 2c, 3c
- Group C (after Group B): 4a
