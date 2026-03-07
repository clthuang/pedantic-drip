"""iflow UI server — FastAPI app factory."""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates


def create_app(db_path: str | None = None) -> FastAPI:
    """Create the iflow UI FastAPI application.

    Parameters
    ----------
    db_path:
        Path to the entity database. If None, resolves from ENTITY_DB_PATH
        env var or default ~/.claude/iflow/entities/entities.db.

    Returns
    -------
    FastAPI application instance. If the DB file does not exist,
    app.state.db is set to None (board route renders error page).
    """
    # Resolve DB path: param -> env -> default
    if db_path is None:
        db_path = os.environ.get(
            "ENTITY_DB_PATH",
            os.path.expanduser("~/.claude/iflow/entities/entities.db"),
        )

    app = FastAPI(title="iflow UI")

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

    # Routes
    from ui.routes.board import router as board_router

    app.include_router(board_router)

    return app
