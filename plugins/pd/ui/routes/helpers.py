"""Shared helpers for UI route handlers."""

import os
import uuid

# Generic message for DB errors shown to users. Detailed error goes to stderr.
DB_ERROR_USER_MESSAGE = (
    "An error occurred while querying the database. "
    "Check server logs for details."
)

# Cookie carrying the user's workspace-scope selection (feature 130, D2).
# One definition -- the select route's set_cookie call and every read site
# (effective_workspace_uuid, switcher_context, tests) reference this
# constant, never the string literal.
COOKIE_NAME = "pd_workspace_uuid"


def missing_db_response(templates, request, db_path):
    """Return error.html response for missing database."""
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "error_title": "Database Not Found",
            "error_message": (
                "The entity database was not found. "
                "Run the entity registry MCP server to initialize it, "
                "or set ENTITY_DB_PATH to point to an existing database."
            ),
            "db_path": db_path,
        },
    )


def _is_uuid_shaped(v: str) -> bool:
    """True if `v` parses as a UUID in canonical 36-char hyphenated form.

    The ``len(v) == 36`` check is load-bearing: ``uuid.UUID()`` also
    accepts non-canonical forms (e.g. a bare 32-char hex string) that this
    function must reject -- feature 130's cookie/query-param value is only
    "shaped" when it is the canonical form.
    """
    try:
        uuid.UUID(v)
        return len(v) == 36
    except ValueError:
        return False


def effective_workspace_uuid(request):
    """Resolve the workspace scope that should filter the current request.

    Precedence (feature 130, D5): cookie ``"*"`` -> ``None`` (unscoped, all
    workspaces); a shaped-uuid cookie -> that uuid, honored even when it
    names an unknown workspace (an empty board is truthful, per spec);
    absent or malformed cookie -> the startup default resolved once in
    ``create_app()`` (feature 129's ``app.state.workspace_uuid``).
    """
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie == "*":
        return None
    if cookie and _is_uuid_shaped(cookie):
        return cookie
    return request.app.state.workspace_uuid


def switcher_context(request, db) -> dict:
    """Build the workspace-switcher dropdown context for base.html (D5/D6).

    Call ONLY from full-page (non-HX-Request) branches, inside the same
    DB-error try/except as the page's other reads -- the polling partials
    never need the cross-workspace directory, and a
    ``list_workspaces_with_entities`` failure should render the page's
    existing error.html path rather than a distinct one.

    Labels are built from ``basename(project_root)`` (D3): a NULL
    project_root workspace is labeled by its uuid's first 8 chars outright;
    a basename shared by more than one workspace gets a `` · {uuid[:8]}``
    suffix appended to every workspace sharing it, for disambiguation.
    Labels are structurally basenames/uuid-prefixes/counts only -- never
    entity names.

    Returns
    -------
    dict
        ``workspaces`` (each with a ``label`` key added), ``selected``
        (the raw cookie state -- ``"*"``, a shaped uuid, or ``None`` when
        absent/malformed), ``default_uuid`` (the startup default), and
        ``effective_unmatched`` (the effective scope uuid when it matches
        no listed workspace, else ``None`` -- the D6 fourth-state key).
    """
    workspaces = db.list_workspaces_with_entities()

    basenames = {
        ws["uuid"]: os.path.basename(ws["project_root"].rstrip("/"))
        for ws in workspaces
        if ws["project_root"]
    }
    basename_counts: dict[str, int] = {}
    for name in basenames.values():
        basename_counts[name] = basename_counts.get(name, 0) + 1

    labeled = []
    for ws in workspaces:
        name = basenames.get(ws["uuid"])
        if name is None:
            label = ws["uuid"][:8]
        elif basename_counts[name] > 1:
            label = f"{name} · {ws['uuid'][:8]}"
        else:
            label = name
        labeled.append({**ws, "label": label})

    cookie = request.cookies.get(COOKIE_NAME)
    if cookie == "*":
        selected = "*"
    elif cookie and _is_uuid_shaped(cookie):
        selected = cookie
    else:
        selected = None

    listed_uuids = {ws["uuid"] for ws in workspaces}
    effective = effective_workspace_uuid(request)
    effective_unmatched = (
        effective if effective is not None and effective not in listed_uuids
        else None
    )

    return {
        "workspaces": labeled,
        "selected": selected,
        "default_uuid": request.app.state.workspace_uuid,
        "effective_unmatched": effective_unmatched,
    }


# Stored v1 Kanban-column values with no v2 EXECUTION_STATUSES home.
# agent_review is defensive-only (zero live producers — brainstorm
# reviewing now writes wip via workflow_engine/router.py's LifecycleMachine,
# FR123-4); human_review is defensive too (zero producers, but the v1
# CHECK still admits stored rows). DELETE at 132 once the backfill
# translates stored values at source (this mapping is its display precedent).
LEGACY_VALUE_REMAP: dict[str, str] = {
    "agent_review": "wip",
    "human_review": "wip",
}


def resolve_execution_status(value: str | None) -> str | None:
    """Map a stored v1 Kanban-column value to its v2 execution_status.

    Vocabulary values pass through; legacy values remap; None/unknown pass
    through unchanged (the CALLER decides defaulting/warning — board
    grouping defaults None->backlog and warns on unknowns per FR125-4;
    the entities annotation/detail render whatever comes back).
    """
    if value in LEGACY_VALUE_REMAP:
        return LEGACY_VALUE_REMAP[value]
    return value
