"""pd UI server — FastAPI app factory."""

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

# Badge color maps — used as Jinja2 globals across templates.
STATUS_COLORS = {
    "active": "badge-primary",
    "completed": "badge-success",
    "planned": "badge-warning",
    "abandoned": "badge-neutral",
}

# Matches DB CHECK constraint for workflow_phase column.
PHASE_COLORS = {
    # Feature phases
    "brainstorm": "badge-info",
    "specify": "badge-secondary",
    "design": "badge-accent",
    "create-plan": "badge-warning",
    "create-tasks": "badge-warning",
    "implement": "badge-primary",
    "finish": "badge-success",
    # Brainstorm lifecycle phases
    "draft": "badge-info",
    "reviewing": "badge-secondary",
    "promoted": "badge-success",
    "abandoned": "badge-neutral",
    # Backlog lifecycle phases
    "open": "badge-ghost",
    "triaged": "badge-info",
    "dropped": "badge-neutral",
}

# Kanban columns — separate from workflow phases.
COLUMN_COLORS = {
    "backlog": "badge-ghost",
    "prioritised": "badge-info",
    "wip": "badge-primary",
    "agent_review": "badge-secondary",
    "human_review": "badge-accent",
    "blocked": "badge-error",
    "documenting": "badge-warning",
    "completed": "badge-success",
}


def timeago(value: str | None) -> str:
    """Jinja2 filter: convert ISO timestamp to relative time string.

    Returns empty string for None/empty, raw string on parse failure,
    and formatted date for future timestamps or dates older than 30 days.
    """
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
        # Ensure timezone-aware comparison
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - dt
        seconds = delta.total_seconds()

        if seconds < 0:
            # Future timestamp — show formatted date
            return dt.strftime("%b %-d")

        if seconds < 60:
            return "just now"
        minutes = int(seconds // 60)
        if minutes < 60:
            return f"{minutes}m ago"
        hours = int(minutes // 60)
        if hours < 24:
            return f"{hours}h ago"
        days = int(hours // 24)
        if days <= 30:
            return f"{days}d ago"
        return dt.strftime("%b %-d")
    except (ValueError, TypeError):
        return str(value)


def create_app(db_path: str | None = None) -> FastAPI:
    """Create the pd UI FastAPI application.

    Parameters
    ----------
    db_path:
        Path to the entity database. If None, resolves from ENTITY_DB_PATH
        env var or default ~/.claude/pd/entities/entities.db.

    Returns
    -------
    FastAPI application instance. If the DB file does not exist,
    app.state.db is set to None (board route renders error page).
    """
    # Resolve DB path: param -> env -> default
    if db_path is None:
        db_path = os.environ.get(
            "ENTITY_DB_PATH",
            os.path.expanduser("~/.claude/pd/entities/entities.db"),
        )

    app = FastAPI(title="pd UI")

    # Database: open if file exists, else None (board route shows error page)
    from entity_registry.database import EntityDatabase

    if os.path.isfile(db_path):
        app.state.db = EntityDatabase(db_path, check_same_thread=False)
    else:
        app.state.db = None

    app.state.db_path = db_path

    # Templates
    templates_dir = Path(__file__).parent / "templates"
    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    # Jinja2 globals — badge color maps
    app.state.templates.env.globals["status_colors"] = STATUS_COLORS
    app.state.templates.env.globals["phase_colors"] = PHASE_COLORS
    app.state.templates.env.globals["column_colors"] = COLUMN_COLORS

    # Jinja2 filters
    app.state.templates.env.filters["timeago"] = timeago

    # Routes
    from ui.routes.board import router as board_router
    from ui.routes.entities import router as entities_router

    app.include_router(board_router)
    app.include_router(entities_router)

    return app
