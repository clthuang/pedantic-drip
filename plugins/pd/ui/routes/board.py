"""Board route — Kanban board view."""

import sys

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ui.routes.helpers import DB_ERROR_USER_MESSAGE, missing_db_response

router = APIRouter()

COLUMN_ORDER = [
    "backlog",
    "prioritised",
    "wip",
    "agent_review",
    "human_review",
    "blocked",
    "documenting",
    "completed",
]


def _group_by_column(rows: list[dict]) -> dict[str, list[dict]]:
    """Group workflow_phases rows by kanban_column.

    Returns dict with all 8 columns as keys (empty list if no rows).
    Rows with kanban_column=None default to 'backlog'.
    Rows with unknown kanban_column values are silently dropped.
    """
    columns: dict[str, list[dict]] = {col: [] for col in COLUMN_ORDER}
    for row in rows:
        col = row.get("kanban_column") or "backlog"
        if col in columns:
            columns[col].append(row)
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
    try:
        rows = db.list_workflow_phases()
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
        },
    )
