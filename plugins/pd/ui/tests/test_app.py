"""Unit tests for create_app() and _group_by_column()."""

from fastapi import FastAPI
from entity_registry.database import (
    EntityDatabase,
    _UNKNOWN_WORKSPACE_UUID,
    _derive_type_and_lifecycle,
)


# ---------------------------------------------------------------------------
# Task 2.1.1: create_app() returns FastAPI with state attrs
# ---------------------------------------------------------------------------
def test_create_app_returns_fastapi_with_state_attrs(tmp_path):
    """create_app() with a valid DB path returns a FastAPI instance whose
    app.state has db, db_path, and templates attributes."""
    db_file = str(tmp_path / "test.db")
    # Create a real database so the file exists with schema
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)

    assert isinstance(app, FastAPI)
    assert hasattr(app.state, "db")
    assert app.state.db is not None
    assert hasattr(app.state, "db_path")
    assert app.state.db_path == db_file
    assert hasattr(app.state, "templates")


# ---------------------------------------------------------------------------
# Task 2.1.2: create_app() missing DB sets None
# ---------------------------------------------------------------------------
def test_create_app_missing_db_sets_none():
    """create_app() with a nonexistent DB path sets app.state.db to None."""
    from ui import create_app

    app = create_app(db_path="/nonexistent/path/entities.db")

    assert app.state.db is None
    assert app.state.db_path == "/nonexistent/path/entities.db"


# ---------------------------------------------------------------------------
# Task 2.1.3: _group_by_column() empty input
# ---------------------------------------------------------------------------
def test_group_by_column_empty_input():
    """_group_by_column([]) returns dict with 8 keys, all mapping to []."""
    from ui.routes.board import _group_by_column

    result = _group_by_column([])

    assert len(result) == 8
    expected_keys = {
        "backlog", "prioritised", "wip", "agent_review",
        "human_review", "blocked", "documenting", "completed",
    }
    assert set(result.keys()) == expected_keys
    for key in expected_keys:
        assert result[key] == []


# ---------------------------------------------------------------------------
# Task 2.1.4: _group_by_column() routes to correct column
# ---------------------------------------------------------------------------
def test_group_by_column_routes_to_correct_column():
    """A row with kanban_column='wip' appears in the wip list only."""
    from ui.routes.board import _group_by_column

    row = {"kanban_column": "wip", "type_id": "feature:test"}
    result = _group_by_column([row])

    assert result["wip"] == [row]
    for col_name, col_items in result.items():
        if col_name != "wip":
            assert col_items == [], f"Expected {col_name} to be empty"


# ---------------------------------------------------------------------------
# Task 2.1.5: _group_by_column() default and drop
# ---------------------------------------------------------------------------
def test_group_by_column_none_defaults_to_backlog():
    """A row with kanban_column=None falls into backlog."""
    from ui.routes.board import _group_by_column

    row = {"kanban_column": None, "type_id": "feature:no-col"}
    result = _group_by_column([row])

    assert result["backlog"] == [row]


def test_group_by_column_unknown_column_dropped():
    """A row with kanban_column='archived' (not in COLUMN_ORDER) is dropped."""
    from ui.routes.board import _group_by_column

    row = {"kanban_column": "archived", "type_id": "feature:archive-test"}
    result = _group_by_column([row])

    for col_items in result.values():
        assert col_items == []


# ===========================================================================
# Integration Tests — Phase 4
# ===========================================================================
import sqlite3
import unittest.mock
from starlette.testclient import TestClient
from ui.routes.board import COLUMN_ORDER


# ---------------------------------------------------------------------------
# Helper: seed a workflow_phases row with required FK + NOT NULL columns
# ---------------------------------------------------------------------------
def _seed_workflow_row(db_file, type_id, kanban_column="backlog",
                       workflow_phase=None, mode=None):
    """Insert an orphan workflow_phases row (no matching entities row).

    Passes workspace_uuid explicitly so the wp_reject_orphaned_insert
    trigger (which aborts inserts with no matching entity and no explicit
    workspace_uuid) does not fire.
    """
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = OFF")
    now = "2026-03-08T00:00:00Z"
    conn.execute(
        "INSERT OR IGNORE INTO workflow_phases "
        "(type_id, kanban_column, workflow_phase, mode, updated_at, "
        "workspace_uuid) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (type_id, kanban_column, workflow_phase, mode, now,
         _UNKNOWN_WORKSPACE_UUID),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Task 4.1.1: Full page load (AC-3) — all 8 column headers rendered
# ---------------------------------------------------------------------------
def test_integration_full_page_load_contains_all_columns(tmp_path):
    """GET / returns 200 with all 8 column header names in the HTML."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    # Seed one row so columns render (empty board shows "No features yet")
    _seed_workflow_row(db_file, "feature:col-test", kanban_column="backlog")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    for col in COLUMN_ORDER:
        # Column names have underscores replaced with spaces in the template
        display_name = col.replace("_", " ")
        assert display_name in response.text, (
            f"Column header '{display_name}' not found in response"
        )


# ---------------------------------------------------------------------------
# Task 4.1.2: HTMX partial (AC-4) — no <html> tag in partial response
# ---------------------------------------------------------------------------
def test_integration_htmx_partial_no_html_tag(tmp_path):
    """GET / with HX-Request header returns partial without <html> tag."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "<html" not in response.text


# ---------------------------------------------------------------------------
# Task 4.1.3: Missing DB (AC-7) — error page with ENTITY_DB_PATH mention
# ---------------------------------------------------------------------------
def test_integration_missing_db_shows_entity_db_path():
    """GET / with nonexistent DB renders error page mentioning ENTITY_DB_PATH."""
    from ui import create_app

    app = create_app(db_path="/nonexistent/path.db")
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "ENTITY_DB_PATH" in response.text


# ---------------------------------------------------------------------------
# Task 4.1.4: DB error — error page on query failure
# ---------------------------------------------------------------------------
def test_integration_db_error_shows_error_message(tmp_path):
    """GET / renders error page when DB query raises an exception."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.db.list_workflow_phases = unittest.mock.MagicMock(
        side_effect=Exception("DB error")
    )
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "An error occurred while querying the database" in response.text


# ---------------------------------------------------------------------------
# Task 4.1.5: Card content (AC-5) — seeded row appears in response
# ---------------------------------------------------------------------------
def test_integration_card_content_rendered(tmp_path):
    """GET / renders card with seeded feature data (slug, phase, mode)."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    # workflow_phase must be a valid CHECK value (implement, not wip)
    # kanban_column=wip is valid for the kanban column
    _seed_workflow_row(
        db_file, "feature:test-slug",
        kanban_column="wip", workflow_phase="implement", mode="standard",
    )

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "test-slug" in response.text
    assert "implement" in response.text
    assert "standard" in response.text


# ---------------------------------------------------------------------------
# Task 4.1.6: Empty board state (AC-6) — "No features yet" message
# ---------------------------------------------------------------------------
def test_integration_empty_board_shows_no_features(tmp_path):
    """GET / with empty DB shows 'No features yet' message."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "No features yet" in response.text


# ===========================================================================
# HTMX Polling — Real-Time UI Updates
# ===========================================================================


# ---------------------------------------------------------------------------
# Behaviour 1: Board auto-refreshes every 3 seconds
# ---------------------------------------------------------------------------
def test_board_full_page_has_polling_trigger(tmp_path):
    """GIVEN a board full page load
    WHEN the HTML is rendered
    THEN the #board-content div has hx-trigger='every 3s' for auto-refresh."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app
    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert 'hx-trigger="every 3s"' in response.text
    assert 'hx-get="/"' in response.text
    assert 'hx-target="#board-content"' in response.text


def test_board_polling_returns_partial_without_full_page(tmp_path):
    """GIVEN the board is polling via HTMX
    WHEN the HX-Request arrives
    THEN the response is a partial (no <html> tag) suitable for innerHTML swap."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_workflow_row(db_file, "feature:poll-test", kanban_column="wip",
                       workflow_phase="implement")
    from ui import create_app
    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get("/", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert "<html" not in response.text
    assert "poll-test" in response.text


# ---------------------------------------------------------------------------
# Behaviour 2: Entities list auto-refreshes every 5 seconds
# ---------------------------------------------------------------------------
def test_entities_full_page_has_polling_trigger(tmp_path):
    """GIVEN an entities full page load
    WHEN the HTML is rendered
    THEN the #entities-content div has hx-trigger='every 5s' for auto-refresh."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app
    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get("/entities")

    assert response.status_code == 200
    assert 'hx-trigger="every 5s"' in response.text
    assert 'hx-get="/entities"' in response.text
    assert 'hx-target="#entities-content"' in response.text


def test_entities_polling_preserves_filter_params(tmp_path):
    """GIVEN the entities page has polling configured
    WHEN the HTML is rendered
    THEN hx-include forwards filter inputs so polls preserve active view."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app
    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get("/entities")

    assert response.status_code == 200
    assert "hx-include=" in response.text


# ---------------------------------------------------------------------------
# Behaviour 3: Board reflects DB changes on next poll cycle
# ---------------------------------------------------------------------------
def test_board_reflects_new_data_on_htmx_refresh(tmp_path):
    """GIVEN a board with one feature in backlog
    WHEN a new feature is added to DB and HTMX polls
    THEN the partial response includes the new feature."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_workflow_row(db_file, "feature:original", kanban_column="backlog")
    from ui import create_app
    app = create_app(db_path=db_file)
    client = TestClient(app)

    # First poll — only original
    r1 = client.get("/", headers={"HX-Request": "true"})
    assert "original" in r1.text
    assert "new-feature" not in r1.text

    # Add new feature to DB (simulates MCP server write)
    _seed_workflow_row(db_file, "feature:new-feature", kanban_column="wip",
                       workflow_phase="implement")

    # Second poll — both visible
    r2 = client.get("/", headers={"HX-Request": "true"})
    assert "original" in r2.text
    assert "new-feature" in r2.text


# ===========================================================================
# Entity name display on kanban cards
# ===========================================================================


def _seed_entity_and_workflow_row(
    db_file, type_id, name, kanban_column="backlog",
    workflow_phase=None, mode=None,
):
    """Insert both an entities row and a workflow_phases row."""
    import uuid
    entity_type, entity_id = type_id.split(":", 1)
    kind_type, lifecycle_class = _derive_type_and_lifecycle(entity_type)
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = OFF")
    now = "2026-03-08T00:00:00Z"
    conn.execute(
        "INSERT OR IGNORE INTO entities "
        "(uuid, workspace_uuid, type_id, kind, entity_id, name, created_at, "
        "updated_at, type, lifecycle_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), _UNKNOWN_WORKSPACE_UUID, type_id, entity_type,
         entity_id, name, now, now, kind_type, lifecycle_class),
    )
    conn.execute(
        "INSERT OR IGNORE INTO workflow_phases "
        "(type_id, kanban_column, workflow_phase, mode, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (type_id, kanban_column, workflow_phase, mode, now),
    )
    conn.commit()
    conn.close()


def test_card_renders_entity_name(tmp_path):
    """Card shows entity_name when available via LEFT JOIN."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_entity_and_workflow_row(
        db_file, "feature:test-slug", name="My Human Readable Feature",
        kanban_column="wip", workflow_phase="implement", mode="standard",
    )

    from ui import create_app
    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "My Human Readable Feature" in response.text


def test_card_fallback_null_entity_name(tmp_path):
    """Card falls back to type_id segment when entity_name is NULL."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    # Seed only workflow_phases (no entity row) — entity_name will be NULL
    _seed_workflow_row(
        db_file, "feature:fallback-slug",
        kanban_column="backlog", workflow_phase=None,
    )

    from ui import create_app
    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "fallback-slug" in response.text


def test_board_renders_with_join_data(tmp_path):
    """Board loads successfully with enriched entity data from JOIN."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_entity_and_workflow_row(
        db_file, "feature:f1", name="Feature One",
        kanban_column="wip", workflow_phase="design", mode="standard",
    )
    _seed_entity_and_workflow_row(
        db_file, "brainstorm:b1", name="Brainstorm Title",
        kanban_column="backlog",
    )

    from ui import create_app
    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "Feature One" in response.text
    assert "Brainstorm Title" in response.text


# ===========================================================================
# Feature 129 Task 5: workspace-scoped board (design D6)
# ===========================================================================


def _bootstrap_workspace(db_file, project_root=None):
    """Insert a fresh workspaces row directly (FKs disabled); returns its uuid."""
    import uuid
    ws_uuid = str(uuid.uuid4())
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = OFF")
    now = "2026-03-08T00:00:00Z"
    conn.execute(
        "INSERT INTO workspaces "
        "(uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_uuid, None, project_root, now, now),
    )
    conn.commit()
    conn.close()
    return ws_uuid


def test_board_workspace_scoping(tmp_path):
    """GIVEN two workspaces with cards plus an orphan workflow_phases row
    WHEN app.state.workspace_uuid is set to one workspace
    THEN the board shows only that workspace's card and the orphan row;
    with None it shows all rows (unchanged unscoped behavior)."""
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    ws_a = _bootstrap_workspace(db_file)
    ws_b = _bootstrap_workspace(db_file)
    db.register_entity("feature", "1-alpha", "Alpha Card", workspace_uuid=ws_a)
    db.create_workflow_phase("feature:1-alpha", kanban_column="wip")
    db.register_entity("feature", "2-beta", "Beta Card", workspace_uuid=ws_b)
    db.create_workflow_phase("feature:2-beta", kanban_column="wip")
    # Orphan row: no matching entity anywhere.
    _seed_workflow_row(db_file, "feature:orphan-card", kanban_column="backlog")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    app.state.workspace_uuid = ws_a
    scoped = client.get("/")
    assert scoped.status_code == 200
    assert "Alpha Card" in scoped.text
    assert "orphan-card" in scoped.text
    assert "Beta Card" not in scoped.text

    app.state.workspace_uuid = None
    unscoped = client.get("/")
    assert unscoped.status_code == 200
    assert "Alpha Card" in unscoped.text
    assert "Beta Card" in unscoped.text
    assert "orphan-card" in unscoped.text


def test_create_app_resolves_workspace_uuid_matching_project_root(
    tmp_path, monkeypatch
):
    """GIVEN a workspaces row whose project_root matches the process cwd
    WHEN create_app() runs its startup resolution
    THEN app.state.workspace_uuid is set to that row's uuid."""
    import os

    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    real_cwd = os.path.abspath(os.getcwd())
    ws_uuid = _bootstrap_workspace(db_file, project_root=real_cwd)

    from ui import create_app

    app = create_app(db_path=db_file)

    assert app.state.workspace_uuid == ws_uuid


def test_create_app_missing_db_workspace_uuid_none_and_warns(capsys):
    """GIVEN a nonexistent DB path
    WHEN create_app() runs its startup resolution
    THEN app.state.workspace_uuid is None and a WARN is logged to stderr."""
    from ui import create_app

    app = create_app(db_path="/nonexistent/path/entities.db")

    assert app.state.workspace_uuid is None
    captured = capsys.readouterr()
    assert "WARN" in captured.err
