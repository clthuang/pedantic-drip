"""Board route — Kanban board view."""

import sys

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from entity_registry.axes import EXECUTION_STATUSES

from ui.routes.helpers import (
    DB_ERROR_USER_MESSAGE,
    effective_workspace_uuid,
    missing_db_response,
    resolve_execution_status,
    switcher_context,
)

router = APIRouter()

COLUMN_ORDER = list(EXECUTION_STATUSES)


def _group_by_column(rows: list[dict]) -> dict[str, list[dict]]:
    """Group rows by execution_status (v2 vocabulary).

    Returns dict with every EXECUTION_STATUSES column as a key (empty list
    if no rows). None defaults to 'backlog'; unknown values (including the
    pre-feature-132 agent_review/human_review legacy values, now unmapped
    since the backfill translates stored values at source) land in
    'backlog' WITH one stderr warning (never silently dropped).
    """
    columns: dict[str, list[dict]] = {col: [] for col in COLUMN_ORDER}
    for row in rows:
        status = resolve_execution_status(row.get("execution_status")) or "backlog"
        if status not in columns:
            print(
                f"[board] unknown execution_status {status!r} on "
                f"{row.get('type_id')!r} — bucketed to backlog",
                file=sys.stderr,
            )
            status = "backlog"
        columns[status].append(row)
    return columns


@router.get("/", response_class=HTMLResponse)
def board(request: Request) -> HTMLResponse:
    """Serve the Kanban board.

    4 code paths:
    1. Missing DB (app.state.db is None) -> error.html
    2. DB query error -> error.html
    3. HX-Request header present -> _board_content.html partial
    4. Normal request -> board.html full page
    """
    db = request.app.state.db
    db_path = request.app.state.db_path
    templates = request.app.state.templates

    # Path 1: Missing DB
    if db is None:
        return missing_db_response(templates, request, db_path)

    # Path 2: DB query error
    switcher = None
    try:
        rows = db.list_workflow_phases(
            workspace_uuid=effective_workspace_uuid(request)
        )
        if not request.headers.get("HX-Request"):
            switcher = switcher_context(request, db)
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

    columns = _group_by_column(rows)

    # Path 3: HTMX partial refresh
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request=request,
            name="_board_content.html",
            context={
                "columns": columns,
                "column_order": COLUMN_ORDER,
                "active_page": "board",
            },
        )

    # Path 4: Full page load
    return templates.TemplateResponse(
        request=request,
        name="board.html",
        context={
            "columns": columns,
            "column_order": COLUMN_ORDER,
            "active_page": "board",
            "switcher": switcher,
        },
    )
