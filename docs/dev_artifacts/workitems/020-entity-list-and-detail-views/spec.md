# Spec: Entity List and Detail Views

## Overview

Add entity list and detail views to the iflow-ui web application, enabling users to browse all entities by type, view individual entity details (lineage, metadata, artifact paths), and navigate between related entities. Feature entities additionally display workflow phase data including current Kanban column, workflow phase, and mode. Builds on the existing Kanban board UI (feature 018) using the same FastAPI + Jinja2 + HTMX + DaisyUI stack.

## Scope

### In Scope
- Entity list page showing all entities with filtering by type and status
- Entity detail page showing full entity information including lineage and workflow state
- Navigation between board view and entity views (navbar links)
- Kanban card click-through to entity detail view
- HTMX-powered partial refreshes for filter changes
- Search functionality using existing FTS index

### Out of Scope
- DAG/tree visualization with Cytoscape.js (feature 021)
- Per-phase history with started/completed timestamps (PRD FR-17 requests phase history; this feature delivers current phase state only — workflow_phases table stores only current state, not per-phase timestamps; full phase history requires schema extension and is deferred to a future feature)
- Phase filtering on entity list (entity list already shows kanban_column; phase filter adds complexity without strong use case for this iteration)
- Drag-and-drop Kanban column changes from entity views
- Entity creation/editing via the UI
- Cross-project entity browsing
- Real-time updates via WebSocket/SSE

## Dependencies / Modified Artifacts

This feature creates new files and modifies existing feature 018 artifacts:

**New files:**
- `plugins/iflow/ui/routes/entities.py` — entity list and detail routes
- `plugins/iflow/ui/templates/entities.html` — entity list full page
- `plugins/iflow/ui/templates/_entities_content.html` — entity list HTMX partial
- `plugins/iflow/ui/templates/entity_detail.html` — entity detail full page
- `plugins/iflow/ui/templates/404.html` — not found page

**Modified files (from feature 018):**
- `plugins/iflow/ui/templates/base.html` — add navbar links (Board, Entities)
- `plugins/iflow/ui/templates/_card.html` — wrap card in clickable link to entity detail
- `plugins/iflow/ui/__init__.py` — register entities router

## Requirements

### FR-1: Entity List Route
The application SHALL serve an entity list page at `/entities` that displays all entities from the database in a table layout.

**Acceptance Criteria:**
- GET `/entities` returns a full HTML page listing all entities in a table with one entity per row
- Each entity row shows: name, type_id, entity_type, status, kanban_column (for feature entities; blank for others), updated_at
- Entity list is sorted by updated_at descending in Python after fetching from `list_entities()` (which has no ORDER BY clause)
- Empty state shows a clear "No entities found" message when DB has no entities
- Error state shows the existing error.html template when DB is unavailable
- Filter tabs are hardcoded to the entity_type CHECK constraint values (backlog, brainstorm, project, feature); if entity types change in the DB schema, filter tabs must be updated in the template accordingly

### FR-2: Entity Type Filtering
The entity list SHALL support filtering by entity_type via query parameter.

**Acceptance Criteria:**
- GET `/entities?type=feature` returns only feature entities
- GET `/entities?type=brainstorm` returns only brainstorm entities
- Filter tabs/buttons for each entity type (backlog, brainstorm, project, feature) plus "All"
- Clicking a filter tab uses HTMX to refresh only the entity list content (not the full page)
- Invalid type parameter shows all entities (no error)

### FR-3: Entity Status Filtering
The entity list SHALL support filtering by status via query parameter.

**Acceptance Criteria:**
- GET `/entities?status=active` returns only entities with status "active"
- Combinable with type filter: `/entities?type=feature&status=active`
- Status filter is a dropdown or secondary filter control
- HTMX partial refresh on filter change
- Status filtering is performed via Python-side post-filtering on the results from `list_entities()` and `search_entities()`

### FR-4: Entity Detail Route
The application SHALL serve an entity detail page at `/entities/{identifier}` showing full information for a single entity.

**Acceptance Criteria:**
- GET `/entities/feature:020-entity-list-and-detail-views` returns the entity detail page
- Detail page shows all entity fields: name, type_id, uuid, entity_type, entity_id, status, artifact_path, created_at, updated_at, metadata (formatted JSON)
- For feature entities, detail page additionally shows workflow data: workflow_phase, last_completed_phase, kanban_column, mode, and backward_transition_reason (all fields available in workflow_phases table)
- 404 page returned if entity not found
- Route uses a catch-all path parameter (`{identifier:path}`) to accept the full type_id including colons (e.g., `feature:020-entity-list-and-detail-views`) and delegates to `get_entity()` which internally distinguishes UUID vs type_id format
- Entity detail page is full page load only — no HTMX partial needed (unlike entity list which has a `_content` partial)

### FR-5: Entity Lineage Display
The entity detail page SHALL display the entity's lineage (ancestors and children).

**Acceptance Criteria:**
- Ancestors section shows parent chain from root to current entity using `get_lineage(direction="up", max_depth=10)`; the route strips the current entity (depth 0) from the result before rendering since `get_lineage` includes self
- Children section shows direct children of the current entity using `get_lineage(direction="down", max_depth=1)`; the route strips the current entity (depth 0) from the result before rendering since `get_lineage` includes self
- Each lineage entry is a clickable link to that entity's detail page
- Empty ancestors (after stripping self) shows "No parent" indicator
- Empty children (after stripping self) shows "No children" indicator
- If ancestor chain exceeds max_depth, display is truncated (no error)

### FR-6: Kanban Card Click-Through
Kanban board cards SHALL link to the entity detail page.

**Acceptance Criteria:**
- Clicking a card on the Kanban board navigates to `/entities/{type_id}`
- Card remains visually a card (not just a link) — the entire card area is clickable via wrapping `<a>` tag
- Browser back button returns to the board view

### FR-7: Navigation Bar
The application navbar SHALL include links to both the board view and entity list.

**Acceptance Criteria:**
- Navbar shows "Board" and "Entities" links
- Current page link is visually distinguished (active state)
- Navigation uses standard `<a>` tags (full page reload between views)

### FR-8: Entity Search
The entity list page SHALL support text search using the existing FTS index.

**Acceptance Criteria:**
- Search input field on the entity list page
- GET `/entities?q=search+term` filters entities using `search_entities()` method
- When `search_entities()` raises `ValueError` (FTS index unavailable), the route falls back to displaying all entities with the search field disabled and a "Search unavailable" indicator
- Search passes `limit=100` to `search_entities()` to reduce silent truncation when combining with post-filters; the UI does not paginate (all results shown)
- Search is combinable with type and status filters; status post-filtering on search results may reduce the result count below the FTS limit — no truncation warning is shown; the displayed row count reflects what is actually rendered
- HTMX partial refresh on search input, debounced at 300ms using `hx-trigger="input changed delay:300ms"`
- Empty search results show "No entities match your search" message

### FR-9: HTMX Partial Refresh Support
All entity list filtering and search operations SHALL support HTMX partial refresh.

**Acceptance Criteria:**
- When `HX-Request` header is present, routes return only the content partial (not the full page with navbar)
- Filter/search state is reflected in the URL (via hx-push-url) for bookmarkability
- Page is functionally navigable without JavaScript (full page reload fallback): filter tabs are `<a>` links with href query params, search requires pressing Enter to submit a form; styling may degrade since Tailwind CSS v4 uses a browser-only script tag in the existing base.html

## Data Access

All data access uses the existing `EntityDatabase` class methods:
- `list_entities(entity_type=None)` — entity list with optional type filter
- `get_entity(type_id)` — single entity detail (supports UUID and type_id)
- `get_lineage(type_id, direction, max_depth)` — ancestor/descendant traversal
- `search_entities(query, entity_type, limit)` — FTS search with ranking
- `list_workflow_phases()` — all workflow phase rows (used for entity list batch lookup)
- `get_workflow_phase(type_id)` — single entity workflow phase lookup (used for entity detail)

No new database methods are needed. Status filtering is performed via Python-side post-filtering on the results from `list_entities()` and `search_entities()`. Workflow phase data for the entity list (kanban_column) is obtained by calling `list_workflow_phases()` and building a dict keyed by type_id; for entity detail, `get_workflow_phase(type_id)` is called directly.

**Data access strategy:**
- Sorting: `list_entities()` returns rows without ORDER BY; the route sorts results by `updated_at` descending in Python before rendering.
- Workflow join (entity list): Call `list_workflow_phases()` once per request, build a `dict[str, dict]` keyed by `type_id` for O(1) lookup when annotating entity rows with kanban_column.
- Workflow lookup (entity detail): Call `get_workflow_phase(type_id)` for single-entity lookup instead of fetching all workflow rows.
- FTS fallback: If `search_entities()` raises `ValueError`, fall back to `list_entities()` with search field disabled.
- Search limit: Pass `limit=100` to `search_entities()` to reduce truncation when combining with status post-filtering.

## Feasibility

All required DB methods (list_entities, get_entity, get_lineage, search_entities, list_workflow_phases, get_workflow_phase) exist in EntityDatabase (verified in database.py). HTMX partial refresh pattern is established in the existing board route. No new dependencies required.

## UI Design Constraints

- Use the same DaisyUI v5 + Tailwind CSS v4 + HTMX stack as the existing board view
- Extend `base.html` for all new pages
- Follow the existing template pattern: full page template + `_content` partial for HTMX
- Dark theme (data-theme="dark") as established in base.html
- Responsive is not required (desktop-only dev tool per PRD NFR)

## Success Criteria

- Given a database with N entities, when GET `/entities` is requested, then the response returns HTTP 200 and contains exactly N entity rows
- Given a database with M feature entities, when GET `/entities?type=feature` is requested, then the response contains exactly M rows
- Given a database with K entities with status "active", when GET `/entities?status=active` is requested, then the response contains exactly K rows
- Given a feature entity with type_id "feature:020-entity-list-and-detail-views", when GET `/entities/feature:020-entity-list-and-detail-views` is requested, then the response returns HTTP 200 and displays all entity fields plus workflow phase data
- Given a feature entity with workflow_phases data, when viewing its detail page, then the page displays kanban_column, workflow_phase, last_completed_phase, and mode
- Given a Kanban card with type_id "feature:001", when the card is clicked, then the browser navigates to `/entities/feature:001`
- Given the search term "auth", when GET `/entities?q=auth` is requested, then the response contains entities matching the FTS query
- Given the FTS index is unavailable, when GET `/entities?q=test` is requested, then the response falls back to showing all entities with the search field disabled
- Given the DB is unavailable (app.state.db is None), when any entity route is requested, then the error.html template is rendered
- Given an HX-Request header is present, when any entity list route is requested, then only the content partial is returned
