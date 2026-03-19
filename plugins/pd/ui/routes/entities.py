"""Entities route — entity list and detail views."""

import json
import sys

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.mermaid import build_mermaid_dag
from ui.routes.helpers import DB_ERROR_USER_MESSAGE, missing_db_response

router = APIRouter(prefix="/entities")

ENTITY_TYPES = ["backlog", "brainstorm", "project", "feature"]


def _build_workflow_lookup(db) -> dict:
    """Return {type_id: workflow_phase_row} from db.list_workflow_phases()."""
    return {wp["type_id"]: wp for wp in db.list_workflow_phases()}


def _strip_self_from_lineage(lineage: list[dict], type_id: str) -> list[dict]:
    """Remove the entry whose type_id matches from a lineage list."""
    return [e for e in lineage if e["type_id"] != type_id]


def _format_metadata(metadata: str | None) -> str:
    """Pretty-print metadata JSON, or return raw string on parse failure."""
    if not metadata:
        return ""
    try:
        return json.dumps(json.loads(metadata), indent=2)
    except (json.JSONDecodeError, TypeError):
        return metadata


@router.get("", response_class=HTMLResponse)
def entity_list(
    request: Request,
    type: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> HTMLResponse:
    """Serve the entity list page.

    5 code paths:
    1. Missing DB (app.state.db is None) -> error.html
    2. DB query error -> error.html with stderr logging
    3. Search with FTS unavailable (ValueError) -> fallback to list_entities
    4. HX-Request header -> _entities_content.html partial
    5. Normal request -> entities.html full page
    """
    db = request.app.state.db
    db_path = request.app.state.db_path
    templates = request.app.state.templates

    # Path 1: Missing DB
    if db is None:
        return missing_db_response(templates, request, db_path)

    # Path 2: DB query error (wraps all DB calls)
    try:
        search_available = True
        type_filter = type if type in ENTITY_TYPES else None

        # Path 3: Search with FTS fallback
        if q:
            try:
                entities = db.search_entities(q, entity_type=type_filter, limit=100)
            except ValueError:
                search_available = False
                entities = db.list_entities(entity_type=type_filter)
        else:
            entities = db.list_entities(entity_type=type_filter)

        # Apply status filter in-memory (DB doesn't support combined filtering)
        if status:
            entities = [e for e in entities if e.get("status") == status]

        # Sort by updated_at DESC (most recently updated first)
        entities = sorted(entities, key=lambda e: e.get("updated_at", ""), reverse=True)

        # Annotate entities with kanban_column from workflow phase data
        workflow_lookup = _build_workflow_lookup(db)
        for e in entities:
            e["kanban_column"] = workflow_lookup.get(e["type_id"], {}).get("kanban_column")

    except Exception as exc:
        print(f"DB query error: {exc}", file=sys.stderr)
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "error_title": "Database Error",
                "error_message": DB_ERROR_USER_MESSAGE,
                "db_path": db_path,
            },
        )

    context = {
        "entities": entities,
        "current_type": type_filter,
        "current_status": status,
        "search_query": q,
        "search_available": search_available,
        "entity_types": ENTITY_TYPES,
        "active_page": "entities",
    }

    # Path 4: HTMX partial refresh
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="_entities_content.html",
            context=context,
        )

    # Path 5: Full page load
    return templates.TemplateResponse(
        request=request,
        name="entities.html",
        context=context,
    )


@router.get("/{identifier:path}", response_class=HTMLResponse)
def entity_detail(request: Request, identifier: str) -> HTMLResponse:
    """Serve the entity detail page.

    4 code paths:
    1. Missing DB (app.state.db is None) -> error.html
    2. DB query error -> error.html with stderr logging
    3. Entity not found -> 404.html with status_code=404
    4. Normal -> entity_detail.html
    """
    db = request.app.state.db
    db_path = request.app.state.db_path
    templates = request.app.state.templates

    # Path 1: Missing DB
    if db is None:
        return missing_db_response(templates, request, db_path)

    # Path 2: DB query error (wraps all DB calls)
    try:
        entity = db.get_entity(identifier)

        # Path 3: Entity not found
        if entity is None:
            return templates.TemplateResponse(
                request=request,
                name="404.html",
                context={"active_page": "entities"},
                status_code=404,
            )

        # Path 4: Full detail — lineage, workflow, metadata
        type_id = entity["type_id"]

        ancestor_lineage = db.get_lineage(type_id, "up", 10)
        ancestors = _strip_self_from_lineage(ancestor_lineage, type_id)

        child_lineage = db.get_lineage(type_id, "down", 10)
        children = _strip_self_from_lineage(child_lineage, type_id)

        mermaid_dag = build_mermaid_dag(entity, ancestors, children)
        workflow = db.get_workflow_phase(type_id)
        metadata_formatted = _format_metadata(entity.get("metadata"))

        return templates.TemplateResponse(
            request=request,
            name="entity_detail.html",
            context={
                "entity": entity,
                "workflow": workflow,
                "ancestors": ancestors,
                "children": children,
                "mermaid_dag": mermaid_dag,
                "metadata_formatted": metadata_formatted,
                "active_page": "entities",
            },
        )

    except Exception as exc:
        print(f"DB query error: {exc}", file=sys.stderr)
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "error_title": "Database Error",
                "error_message": DB_ERROR_USER_MESSAGE,
                "db_path": db_path,
            },
        )
