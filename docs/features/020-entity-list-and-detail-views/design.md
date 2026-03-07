# Design: Entity List and Detail Views

## Prior Art Research

### Codebase Patterns (from feature 018)

- **4-code-path route pattern**: board.py implements: (1) missing DB → error.html, (2) DB query error → error.html with stderr logging, (3) HX-Request header → partial template, (4) normal request → full page. Entity routes replicate this.
- **DB/template access**: `request.app.state.db`, `request.app.state.db_path`, `request.app.state.templates` — no imports of DB classes in route files.
- **HTMX partial refresh**: `if request.headers.get("HX-Request"):` returns content partial; full page wraps it with `{% include "_content.html" %}`.
- **Template inheritance**: `{% extends "base.html" %}` with `{% block content %}{% endblock %}`.
- **Router registration**: `from ui.routes.board import router as board_router` then `app.include_router(board_router)` in `create_app()`.
- **DaisyUI components**: cards (`card bg-base-200 shadow-sm`), badges (`badge badge-xs badge-ghost`), buttons (`btn btn-sm btn-outline`), navbar (`navbar bg-base-100 shadow-lg`).

### External Patterns

- **HTMX URL state**: `hx-push-url="true"` on filter/search for bookmarkable URLs; `hx-replace-url` preferred for filters to avoid history bloat.
- **Search debounce**: `hx-trigger="input changed delay:300ms"` with `hx-sync="this:replace"` to cancel in-flight requests.
- **DaisyUI v5 tables**: `<table class="table table-zebra">` inside `<div class="overflow-x-auto">`. Dark mode automatic via CSS variables.
- **Path converter**: `{identifier:path}` Starlette converter handles colon-containing type_ids.

## Architecture Overview

### Component Map

```
plugins/iflow/ui/
├── __init__.py              # create_app() — registers entity router
├── routes/
│   ├── board.py             # MODIFIED: add active_page context variable
│   └── entities.py          # NEW: GET /entities, GET /entities/{identifier:path}
└── templates/
    ├── base.html            # MODIFIED: add navbar links
    ├── board.html            # Existing
    ├── _board_content.html   # Existing
    ├── _card.html            # MODIFIED: wrap in <a> link
    ├── error.html            # Existing (reused)
    ├── entities.html         # NEW: entity list full page
    ├── _entities_content.html # NEW: entity list HTMX partial
    ├── entity_detail.html    # NEW: entity detail full page
    └── 404.html              # NEW: not found page
```

### Data Flow

```
Browser Request
    │
    ├─ GET /entities[?type=X&status=Y&q=Z]
    │   └─ entities.py:entity_list()
    │       ├─ If q param: search_entities(q, type, limit=100)
    │       │   └─ ValueError? → fallback to list_entities(type)
    │       ├─ Else: list_entities(entity_type=type)
    │       ├─ Python post-filter by status
    │       ├─ Python sort by updated_at DESC
    │       ├─ list_workflow_phases() → dict by type_id (for kanban_column)
    │       ├─ HX-Request? → _entities_content.html
    │       └─ Full page? → entities.html
    │
    └─ GET /entities/{identifier:path}
        └─ entities.py:entity_detail()
            ├─ get_entity(identifier) → None? → 404.html (status_code=404)
            ├─ type_id = entity["type_id"]
            ├─ get_lineage(type_id, "up", 10) → _strip_self_from_lineage → ancestors
            ├─ get_lineage(type_id, "down", 1) → _strip_self_from_lineage → children
            ├─ get_workflow_phase(type_id) → workflow data (features only)
            └─ entity_detail.html (full page only)
```

### Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Entity list route prefix | `/entities` (no trailing slash) | Consistent with REST conventions; board uses `/` |
| Router prefix | `APIRouter(prefix="/entities")` | Clean route grouping; `entity_list` at `""`, `entity_detail` at `"/{identifier:path}"` |
| Status filtering | Python post-filter | No DB method param; avoids new DB code |
| Sorting | Python `sorted()` by `updated_at` DESC | `list_entities()` has no ORDER BY |
| Workflow annotation (list) | Build dict from `list_workflow_phases()` | O(1) lookup per entity row |
| Workflow lookup (detail) | `get_workflow_phase(type_id)` | Efficient single-row fetch |
| Search fallback | Catch `ValueError` → `list_entities()` | FTS index may not exist |
| Detail page | Full page only (no HTMX partial) | Single-entity view; no filter/refresh use case |
| Navbar active state | Template variable `active_page` | Each route passes its page name in context |
| 404 page | Separate template, not error.html | Semantic distinction: missing entity vs system error |
| URL state attribute | `hx-replace-url` (spec says `hx-push-url`) | Intentional deviation: `hx-replace-url` avoids history bloat on repeated filter changes; URLs remain bookmarkable either way |
| 404 response status | `status_code=404` on TemplateResponse | Semantically correct HTTP status for missing entity; error.html keeps default 200 per board route precedent |

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Performance with large entity counts | Low | Medium | `search_entities` limit=100; no pagination needed (dev tool, <1000 entities expected) |
| FTS index unavailable | Medium | Low | Graceful fallback to list_entities with search disabled |
| Metadata JSON rendering XSS | Low | High | Jinja2 auto-escapes by default; use `<pre>` for formatted JSON display |
| Colon in URL path not matching | Low | High | `{identifier:path}` converter handles this; verified in Starlette docs |

## Interfaces

### Route Module: `entities.py`

```python
# entities.py — entity list and detail routes

router = APIRouter(prefix="/entities")

ENTITY_TYPES = ["backlog", "brainstorm", "project", "feature"]

@router.get("", response_class=HTMLResponse)
def entity_list(
    request: Request,
    type: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> HTMLResponse:
    """Entity list with filtering and search.

    Code paths:
    1. Missing DB → error.html
    2. DB query error → error.html
    3. Search with FTS unavailable → fallback to list_entities, search disabled
    4. HX-Request → _entities_content.html partial
    5. Normal → entities.html full page
    """

@router.get("/{identifier:path}", response_class=HTMLResponse)
def entity_detail(request: Request, identifier: str) -> HTMLResponse:
    """Entity detail view.

    Code paths:
    1. Missing DB → error.html
    2. Entity not found → 404.html
    3. DB query error → error.html
    4. Normal → entity_detail.html full page
    """
```

### Route Contract: `entity_list`

**Input:** Query params `type`, `status`, `q` (all optional).

**Processing:**
1. Validate `type` — if not in `ENTITY_TYPES`, treat as None (show all)
2. If `q` is provided:
   - Call `search_entities(q, entity_type=type, limit=100)`
   - On `ValueError`: set `search_available = False`, fall back to `list_entities(entity_type=type)`
3. Else: call `list_entities(entity_type=type)`
4. Post-filter by `status` if provided: `[e for e in entities if e.get("status") == status]`
5. Sort: `sorted(entities, key=lambda e: e.get("updated_at", ""), reverse=True)`
6. Build workflow lookup: `{wp["type_id"]: wp for wp in db.list_workflow_phases()}`
7. Annotate entities with `kanban_column` from workflow lookup

**Template context:**
```python
{
    "entities": list[dict],          # sorted, filtered entity rows
    "entity_types": list[str],       # ENTITY_TYPES constant for filter tabs
    "current_type": str | None,      # active type filter
    "current_status": str | None,    # active status filter
    "search_query": str | None,      # current search term
    "search_available": bool,        # False when FTS index unavailable
    "active_page": "entities",       # for navbar active state
}
```

### Route Contract: `entity_detail`

**Input:** Path param `identifier` (type_id or UUID).

**Processing:**
1. Call `get_entity(identifier)` → None means 404
2. Extract `type_id = entity["type_id"]` (handles UUID-to-type_id resolution when `identifier` is a UUID)
3. Call `get_lineage(type_id, "up", 10)`, then `_strip_self_from_lineage(result, type_id)` → ancestors
4. Call `get_lineage(type_id, "down", 1)`, then `_strip_self_from_lineage(result, type_id)` → children
5. Call `get_workflow_phase(type_id)` → workflow data dict or None
6. Format metadata as pretty-printed JSON string
7. Return `entity_detail.html` with `status_code=404` if entity not found, otherwise `status_code=200`

**Template context:**
```python
{
    "entity": dict,                  # full entity record
    "ancestors": list[dict],         # parent chain (root first), self stripped
    "children": list[dict],          # direct children, self stripped
    "workflow": dict | None,         # workflow_phases row (features only)
    "metadata_formatted": str,       # pretty-printed JSON
    "active_page": "entities",       # for navbar active state
}
```

### Template Contracts

**`base.html` (modified):**
- Navbar adds two links: "Board" (`href="/"`) and "Entities" (`href="/entities"`)
- Active link determined by `active_page` context variable
- Active link styled with DaisyUI `btn-active` or equivalent
- Board route must also pass `active_page: "board"` in context

**`entities.html`:**
- Extends `base.html`
- `<div id="entities-content">` wraps BOTH the filter controls AND the table — `{% include "_entities_content.html" %}` renders the full filter bar + table, so HTMX partial refresh re-renders everything including active tab state
- Hidden input `<input type="hidden" name="type" value="{{ current_type or '' }}">` carries type state for hx-include selectors
- Filter tabs: `<a>` links with `href="/entities?type=X"` and `hx-get="/entities?type=X" hx-target="#entities-content" hx-replace-url="true"`
- Search input: `<input name="q" hx-get="/entities" hx-trigger="input changed delay:300ms" hx-target="#entities-content" hx-sync="this:replace" hx-include="[name='type'],[name='status']" hx-replace-url="true">`
- Status dropdown: `<select name="status" hx-get="/entities" hx-trigger="change" hx-target="#entities-content" hx-include="[name='type'],[name='q']" hx-replace-url="true">`

**`_entities_content.html`:**
- Contains filter tabs (type), status dropdown, search input, hidden type input, AND the table — all inside `#entities-content` so HTMX partial refresh re-renders filter active state
- Filter tabs highlight active tab based on `current_type` context variable
- Table with columns: Name, Type ID, Type, Status, Kanban Column, Updated
- Each row links to entity detail: name cell is `<a href="/entities/{{ entity.type_id }}">`
- Empty state: "No entities found" or "No entities match your search"
- Row count displayed: `{{ entities | length }} entities`

**`entity_detail.html`:**
- Extends `base.html`
- Sections: Entity Info (all fields), Workflow State (if workflow data), Lineage (ancestors + children), Metadata (formatted JSON)
- Back link to entity list
- Lineage entries as clickable links to their detail pages
- Metadata in `<pre class="...">` block

**`404.html`:**
- Extends `base.html`
- "Entity not found" message with link back to entity list
- Centered card layout (similar to error.html but with different messaging)

**`_card.html` (modified):**
- Wrap entire card `<div>` in `<a href="/entities/{{ item.type_id }}" class="block no-underline text-inherit">`
- Preserves all existing card styling
- `block` class ensures the link fills the card area
- `no-underline` prevents text decoration on hover
- `text-inherit` prevents link color override on card text

### Helper Functions

```python
def _build_workflow_lookup(db) -> dict[str, dict]:
    """Build type_id → workflow_phases dict for O(1) annotation."""
    return {wp["type_id"]: wp for wp in db.list_workflow_phases()}

def _strip_self_from_lineage(lineage: list[dict], type_id: str) -> list[dict]:
    """Remove the queried entity from lineage results."""
    return [e for e in lineage if e["type_id"] != type_id]

def _format_metadata(metadata: str | None) -> str:
    """Format metadata JSON string for display."""
    if not metadata:
        return ""
    try:
        return json.dumps(json.loads(metadata), indent=2)
    except (json.JSONDecodeError, TypeError):
        return metadata
```

### Registration in `__init__.py`

Add after board router registration:
```python
from ui.routes.entities import router as entities_router
app.include_router(entities_router)
```

### Board Route Modification

Board route must pass `active_page: "board"` in all template contexts for navbar active state to work correctly. This is a minimal change: add `"active_page": "board"` to each context dict.
