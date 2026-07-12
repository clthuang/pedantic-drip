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
    """_group_by_column([]) returns a dict with one key per
    EXECUTION_STATUSES column, all mapping to []."""
    from entity_registry.axes import EXECUTION_STATUSES
    from ui.routes.board import _group_by_column

    result = _group_by_column([])

    expected_keys = set(EXECUTION_STATUSES)
    assert len(result) == len(expected_keys)
    assert set(result.keys()) == expected_keys
    for key in expected_keys:
        assert result[key] == []


# ---------------------------------------------------------------------------
# Task 2.1.4: _group_by_column() routes to correct column
# ---------------------------------------------------------------------------
def test_group_by_column_routes_to_correct_column():
    """A row with execution_status='wip' appears in the wip list only."""
    from ui.routes.board import _group_by_column

    row = {"execution_status": "wip", "type_id": "feature:test"}
    result = _group_by_column([row])

    assert result["wip"] == [row]
    for col_name, col_items in result.items():
        if col_name != "wip":
            assert col_items == [], f"Expected {col_name} to be empty"


# ---------------------------------------------------------------------------
# Task 2.1.5: _group_by_column() default (None -> backlog)
# ---------------------------------------------------------------------------
def test_group_by_column_none_defaults_to_backlog():
    """A row with execution_status=None falls into backlog."""
    from ui.routes.board import _group_by_column

    row = {"execution_status": None, "type_id": "feature:no-col"}
    result = _group_by_column([row])

    assert result["backlog"] == [row]


# ---------------------------------------------------------------------------
# SC3b / design D7 :94-102 inversion (RED-FIRST): unknown execution_status
# values bucket to backlog WITH a stderr warning -- never silently dropped
# (FR125-4). Pre-rewire, unknown values are silently dropped instead.
# ---------------------------------------------------------------------------
def test_group_by_column_unknown_value_bucketed_to_backlog_with_warning(capsys):
    """A row with execution_status='archived' (unknown, not in
    EXECUTION_STATUSES) lands in 'backlog' WITH one stderr warning."""
    from ui.routes.board import _group_by_column

    row = {"execution_status": "archived", "type_id": "feature:archive-test"}
    result = _group_by_column([row])

    assert result["backlog"] == [row]
    captured = capsys.readouterr()
    assert "archived" in captured.err
    assert "feature:archive-test" in captured.err


# ---------------------------------------------------------------------------
# SC3a (RED-FIRST -- dropped today): _group_by_column() 'ready' bucket
# ---------------------------------------------------------------------------
def test_group_by_column_ready_bucket_synthetic():
    """A synthetic row with execution_status='ready' lands in the 'ready'
    bucket. 'ready' is not a pre-rewire COLUMN_ORDER key, so the read uses
    a KeyError-safe `.get()` -- this fails today (the row is dropped)."""
    from ui.routes.board import _group_by_column

    row = {"execution_status": "ready", "type_id": "feature:ready-test"}
    result = _group_by_column([row])

    assert row in result.get("ready", [])


# ---------------------------------------------------------------------------
# D7 helper unit matrix: resolve_execution_status passthrough/remap/None
# ---------------------------------------------------------------------------
def test_resolve_execution_status_passthrough_remap_and_none_matrix():
    """Vocabulary/unknown values pass through unchanged; legacy values
    remap via LEGACY_VALUE_REMAP; None passes through unchanged (helpers.py
    D1 -- the caller decides defaulting/warning)."""
    from ui.routes.helpers import LEGACY_VALUE_REMAP, resolve_execution_status

    assert resolve_execution_status("wip") == "wip"
    assert resolve_execution_status("totally-unknown") == "totally-unknown"
    for legacy, expected in LEGACY_VALUE_REMAP.items():
        assert resolve_execution_status(legacy) == expected
    assert resolve_execution_status(None) is None


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
# SC3c (RED-FIRST -- renders in agent_review today): DB-seeded agent_review
# row renders under the 'wip' board column with no stderr warning
# ---------------------------------------------------------------------------
def _column_card_html(html: str, column_label: str) -> str:
    """Return the card-container HTML slice for one rendered board column,
    located by its header text (e.g. 'wip') -- the header is unique per
    column-order iteration, so slicing from this column's <h2> to the next
    column's opening <div> (or end of string) isolates just its cards."""
    marker = (
        '<h2 class="text-sm font-semibold uppercase tracking-wide">'
        f"{column_label}</h2>"
    )
    start = html.index(marker)
    next_col = html.find('<div class="flex-shrink-0 w-56', start + len(marker))
    end = next_col if next_col != -1 else len(html)
    return html[start:end]


def test_group_by_column_seeded_agent_review_renders_in_wip(tmp_path, capsys):
    """A DB-seeded agent_review row (CHECK-legal v1 value) renders under
    the 'wip' board column with no stderr warning. Pre-rewire it lands
    under its own 'agent review' column instead (agent_review is still a
    COLUMN_ORDER member today)."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_workflow_row(db_file, "feature:legacy-review", kanban_column="agent_review")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    wip_section = _column_card_html(response.text, "wip")
    assert "legacy-review" in wip_section

    captured = capsys.readouterr()
    assert "[board] unknown execution_status" not in captured.err


# ---------------------------------------------------------------------------
# SC1: rendered board column headers appear in EXECUTION_STATUSES order
# ---------------------------------------------------------------------------
def test_board_column_headers_render_in_execution_statuses_order(tmp_path):
    """The board's column headers render in EXECUTION_STATUSES order -- a
    route-level check of actual rendering, not just the COLUMN_ORDER
    constant (spec SC1)."""
    from entity_registry.axes import EXECUTION_STATUSES

    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_workflow_row(db_file, "feature:sc1-test", kanban_column="backlog")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    positions = [
        response.text.index(
            '<h2 class="text-sm font-semibold uppercase tracking-wide">'
            f'{col.replace("_", " ")}</h2>'
        )
        for col in EXECUTION_STATUSES
    ]
    assert positions == sorted(positions)


# ---------------------------------------------------------------------------
# Task 4.1.1: Full page load (AC-3) — all 8 column headers rendered
# ---------------------------------------------------------------------------
def test_integration_full_page_load_contains_all_columns(tmp_path):
    """GET / returns 200 with all EXECUTION_STATUSES column header names in
    the HTML."""
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


def test_create_app_database_error_during_lookup_workspace_uuid_none_and_warns(
    monkeypatch, tmp_path, capsys,
):
    """GIVEN the read-only workspace lookup raises sqlite3.DatabaseError
    (e.g. the db file became corrupted/invalid between the read-write
    open at line ~120 and the read-only lookup -- a DISTINCT sqlite3.Error
    subtype from the OperationalError a merely-missing file raises, which
    test_create_app_missing_db_workspace_uuid_none_and_warns above already
    covers)
    WHEN create_app() runs its startup resolution
    THEN app.state.workspace_uuid is None and a WARN is logged -- pins that
    the except clause catches sqlite3.Error broadly (DatabaseError
    included), not just the narrower OperationalError subtype. Kills a
    mutation that narrows `except (sqlite3.Error, ValueError)` to
    `except (sqlite3.OperationalError, ValueError)`."""
    import sqlite3

    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)  # valid db -- app.state.db construction succeeds

    def _raise_database_error(conn, project_root_abs):
        raise sqlite3.DatabaseError("file is not a database")

    monkeypatch.setattr(
        "entity_registry.project_identity._lookup_workspace_uuid_by_project_root",
        _raise_database_error,
    )

    from ui import create_app

    app = create_app(db_path=db_file)

    assert app.state.workspace_uuid is None
    captured = capsys.readouterr()
    assert "WARN" in captured.err


# ===========================================================================
# Feature 130 Task 2: Workspace switcher UI — dropdown states + poll guard
# ===========================================================================

import uuid

from ui.routes.helpers import COOKIE_NAME


def _option_element(html: str, value: str) -> str:
    """Return the full <option value="{value}" ...>...</option> element
    (attributes AND inner text), so assertions can check `selected` and
    rendered label text without false-positiving on unrelated 'selected'
    occurrences elsewhere in the page."""
    start = html.index(f'<option value="{value}"')
    end = html.index("</option>", start)
    return html[start:end + len("</option>")]


def test_board_full_page_switcher_selection_states(tmp_path):
    """Full-page board <select name="uuid"> pre-selects the right option
    across three normal states plus the fourth-state 'unknown cookie' path,
    all against one two-workspace fixture + a shared client:
      1. cookie names a listed workspace -> that option selected.
      2. cookie='*' -> 'All workspaces' selected.
      3. no cookie, startup default matches a listed workspace -> that
         option selected AND its label gains ' (current dir)'.
      4a. cookie names an unknown (unlisted, but shaped) workspace -> the
          transient disabled 'unknown workspace' option is selected, and
          no listed option (nor 'All workspaces') is."""
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    ws_a = _bootstrap_workspace(db_file, project_root=str(tmp_path / "proj-a"))
    ws_b = _bootstrap_workspace(db_file, project_root=str(tmp_path / "proj-b"))
    db.register_entity("feature", "1-alpha", "Alpha Card", workspace_uuid=ws_a)
    db.register_entity("feature", "2-beta", "Beta Card", workspace_uuid=ws_b)

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    # State 1: cookie names a listed workspace (ws_b).
    client.cookies.set(COOKIE_NAME, ws_b)
    r1 = client.get("/")
    assert r1.status_code == 200
    assert '<select name="uuid"' in r1.text
    assert "selected" in _option_element(r1.text, ws_b)
    assert "selected" not in _option_element(r1.text, ws_a)
    assert "selected" not in _option_element(r1.text, "*")
    client.cookies.clear()

    # State 2: cookie='*' -> All workspaces.
    client.cookies.set(COOKIE_NAME, "*")
    r2 = client.get("/")
    assert "selected" in _option_element(r2.text, "*")
    assert "selected" not in _option_element(r2.text, ws_a)
    assert "selected" not in _option_element(r2.text, ws_b)
    client.cookies.clear()

    # State 3: no cookie, startup default matches ws_a -> "(current dir)".
    app.state.workspace_uuid = ws_a
    r3 = client.get("/")
    element_a = _option_element(r3.text, ws_a)
    assert "selected" in element_a
    assert "(current dir)" in element_a
    assert "selected" not in _option_element(r3.text, "*")

    # State 4a: cookie names an unknown (shaped, unlisted) workspace.
    unknown_uuid = str(uuid.uuid4())
    client.cookies.set(COOKIE_NAME, unknown_uuid)
    r4a = client.get("/")
    unmatched_element = _option_element(r4a.text, unknown_uuid)
    assert "selected" in unmatched_element
    assert "disabled" in unmatched_element
    assert f"unknown workspace · {unknown_uuid[:8]}" in unmatched_element
    assert "selected" not in _option_element(r4a.text, ws_a)
    assert "selected" not in _option_element(r4a.text, ws_b)
    assert "selected" not in _option_element(r4a.text, "*")
    client.cookies.clear()


def test_board_full_page_switcher_unpopulated_default_shows_unmatched_option(
    tmp_path,
):
    """Fourth state, path B: no cookie, but the startup default names a
    workspace with zero entities (absent from the populated listing) ->
    the transient disabled 'unknown workspace' option is selected, and
    neither the populated workspace's option nor 'All workspaces' is."""
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    ws_populated = _bootstrap_workspace(
        db_file, project_root=str(tmp_path / "proj-populated")
    )
    db.register_entity(
        "feature", "1-only", "Only Card", workspace_uuid=ws_populated
    )
    ws_empty = _bootstrap_workspace(
        db_file, project_root=str(tmp_path / "proj-empty")
    )

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.workspace_uuid = ws_empty
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    unmatched_element = _option_element(response.text, ws_empty)
    assert "selected" in unmatched_element
    assert "disabled" in unmatched_element
    assert f"unknown workspace · {ws_empty[:8]}" in unmatched_element
    assert "selected" not in _option_element(response.text, ws_populated)
    assert "selected" not in _option_element(response.text, "*")


def test_board_htmx_partial_has_no_switcher_select(tmp_path):
    """HX-Request board partial never renders the switcher <select> —
    the builder is confined to the full-page branch (hot-path cost)."""
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    ws_a = _bootstrap_workspace(db_file, project_root=str(tmp_path / "proj-a"))
    db.register_entity("feature", "1-alpha", "Alpha Card", workspace_uuid=ws_a)

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get("/", headers={"HX-Request": "true"})

    assert response.status_code == 200
    assert '<select name="uuid"' not in response.text


def test_board_missing_db_page_has_no_switcher_select():
    """The board's missing-DB error.html never renders the switcher (no
    context is passed at all on that path)."""
    from ui import create_app

    app = create_app(db_path="/nonexistent/path.db")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert '<select name="uuid"' not in response.text


def test_board_error_page_has_no_switcher_select(tmp_path):
    """The board's DB-query-error error.html never renders the switcher."""
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
    assert '<select name="uuid"' not in response.text


def test_board_poll_guard_switcher_builder_scoped_to_full_page(tmp_path):
    """PAIRED (non-vacuous) poll-path guard: with list_workspaces_with_entities
    monkeypatched to raise on the SAME app —
    (a) an HX-Request board partial still renders 200 with a seeded card's
        text and does NOT contain the error copy (the builder never runs
        on the poll path);
    (b) a full-page board GET renders the error page (the builder DID run
        and its failure is caught by the page's existing DB-error handling).
    The contrast is the proof: a never-wired or exception-swallowing
    builder would pass leg (a) trivially but would ALSO wrongly pass
    leg (b)."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_workflow_row(db_file, "feature:poll-guard", kanban_column="wip",
                       workflow_phase="implement")

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.db.list_workspaces_with_entities = unittest.mock.MagicMock(
        side_effect=Exception("workspace directory query failed")
    )
    client = TestClient(app)

    # Leg (a): HX-Request partial — builder never runs, page renders fine.
    partial = client.get("/", headers={"HX-Request": "true"})
    assert partial.status_code == 200
    assert "poll-guard" in partial.text
    assert "An error occurred while querying the database" not in partial.text

    # Leg (b): full-page GET — builder runs; its failure surfaces as the
    # SAME error.html path as any other DB read failure.
    full_page = client.get("/")
    assert full_page.status_code == 200
    assert "An error occurred while querying the database" in full_page.text


# ===========================================================================
# Feature 130 Task 2, test group #2: /workspace/select route
# ===========================================================================


def test_select_route_wildcard_sets_cookie_with_d2_attributes(tmp_path):
    """uuid=* sets the D2-attributed cookie and 303-redirects to the
    referer's path+query."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get(
        "/workspace/select",
        params={"uuid": "*"},
        headers={"referer": "http://testserver/entities?type=feature"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/entities?type=feature"
    assert response.cookies.get(COOKIE_NAME) == "*"
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "max-age=2592000" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_select_route_canonical_uuid_sets_cookie_with_d2_attributes(tmp_path):
    """A canonical 36-char uuid sets the cookie to that uuid, with the
    same D2 attributes, and honors the referer's path+query."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    ws_uuid = str(uuid.uuid4())

    response = client.get(
        "/workspace/select",
        params={"uuid": ws_uuid},
        headers={"referer": "http://testserver/?foo=bar"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/?foo=bar"
    assert response.cookies.get(COOKIE_NAME) == ws_uuid
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "max-age=2592000" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_select_route_xss_uuid_sets_no_cookie(tmp_path):
    """A `<script>` payload is neither '*' nor uuid-shaped -> no Set-Cookie
    header, but the redirect still happens (fail quiet)."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get(
        "/workspace/select",
        params={"uuid": "<script>alert(1)</script>"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "set-cookie" not in response.headers


def test_select_route_32char_hex_sets_no_cookie(tmp_path):
    """A bare 32-char hex string parses via uuid.UUID() but is not the
    canonical 36-char form -> rejected, no Set-Cookie header."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get(
        "/workspace/select",
        params={"uuid": "a" * 32},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "set-cookie" not in response.headers


def test_select_route_empty_uuid_sets_no_cookie(tmp_path):
    """An empty uuid value -> rejected, no Set-Cookie header, still 303."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get(
        "/workspace/select",
        params={"uuid": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "set-cookie" not in response.headers


def test_select_route_protocol_relative_referer_redirects_home(tmp_path):
    """A `//evil.com`-style referer (protocol-relative) redirects to '/' —
    a bare startswith('/') check would wrongly accept it."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get(
        "/workspace/select",
        params={"uuid": "*"},
        headers={"referer": "http://localhost//evil.com"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_select_route_absent_referer_redirects_home(tmp_path):
    """No referer header -> redirect target is '/'."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get(
        "/workspace/select",
        params={"uuid": "*"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


# ===========================================================================
# Feature 130 Task 2, test group #3: cookie-scoped board e2e
# ===========================================================================


def test_board_scoping_via_cookie_names_workspace(tmp_path):
    """Client cookie naming W2 -> board shows only W2's card (+ orphan
    rows, per 129's existing non-None-scope retention behavior)."""
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    ws_a = _bootstrap_workspace(db_file)
    ws_b = _bootstrap_workspace(db_file)
    db.register_entity("feature", "1-alpha", "Alpha Card", workspace_uuid=ws_a)
    db.create_workflow_phase("feature:1-alpha", kanban_column="wip")
    db.register_entity("feature", "2-beta", "Beta Card", workspace_uuid=ws_b)
    db.create_workflow_phase("feature:2-beta", kanban_column="wip")
    _seed_workflow_row(db_file, "feature:orphan-cookie", kanban_column="backlog")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, ws_b)

    response = client.get("/")

    assert response.status_code == 200
    assert "Beta Card" in response.text
    assert "orphan-cookie" in response.text
    assert "Alpha Card" not in response.text


def test_board_scoping_via_cookie_wildcard_shows_all(tmp_path):
    """Client cookie='*' -> board shows every workspace's cards (unscoped),
    overriding a non-None startup default."""
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    ws_a = _bootstrap_workspace(db_file)
    ws_b = _bootstrap_workspace(db_file)
    db.register_entity("feature", "1-alpha", "Alpha Card", workspace_uuid=ws_a)
    db.create_workflow_phase("feature:1-alpha", kanban_column="wip")
    db.register_entity("feature", "2-beta", "Beta Card", workspace_uuid=ws_b)
    db.create_workflow_phase("feature:2-beta", kanban_column="wip")

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.workspace_uuid = ws_a  # startup default would otherwise scope
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, "*")

    response = client.get("/")

    assert response.status_code == 200
    assert "Alpha Card" in response.text
    assert "Beta Card" in response.text


def test_board_scoping_shaped_unknown_cookie_shows_empty_board(tmp_path):
    """A shaped-but-unknown cookie is honored (not silently ignored) ->
    200 with no W1/W2 entity cards; the orphan row still renders because
    the 129 orphan-retention predicate applies to ANY non-None scope
    (truthful, not a silent fallback)."""
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    ws_a = _bootstrap_workspace(db_file)
    ws_b = _bootstrap_workspace(db_file)
    db.register_entity("feature", "1-alpha", "Alpha Card", workspace_uuid=ws_a)
    db.create_workflow_phase("feature:1-alpha", kanban_column="wip")
    db.register_entity("feature", "2-beta", "Beta Card", workspace_uuid=ws_b)
    db.create_workflow_phase("feature:2-beta", kanban_column="wip")
    _seed_workflow_row(db_file, "feature:orphan-unknown", kanban_column="backlog")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, str(uuid.uuid4()))

    response = client.get("/")

    assert response.status_code == 200
    assert "Alpha Card" not in response.text
    assert "Beta Card" not in response.text
    assert "orphan-unknown" in response.text


def test_board_scoping_malformed_cookie_falls_back_to_startup_default(tmp_path):
    """A malformed cookie value (not shaped like a uuid) is NOT honored --
    the read-side effective_workspace_uuid fallback renders the startup
    default's cards, the functional OPPOSITE of the shaped-unknown case
    above (spec SC3's malformed-vs-default clause)."""
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    ws_a = _bootstrap_workspace(db_file)
    ws_b = _bootstrap_workspace(db_file)
    db.register_entity("feature", "1-alpha", "Alpha Card", workspace_uuid=ws_a)
    db.create_workflow_phase("feature:1-alpha", kanban_column="wip")
    db.register_entity("feature", "2-beta", "Beta Card", workspace_uuid=ws_b)
    db.create_workflow_phase("feature:2-beta", kanban_column="wip")

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.workspace_uuid = ws_a
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, "not-a-uuid")

    response = client.get("/")

    assert response.status_code == 200
    assert "Alpha Card" in response.text
    assert "Beta Card" not in response.text


# ===========================================================================
# Test deepening: verified thin-spot coverage (referer edge cases, cookie
# case sensitivity, cookie-injection boundary, cookie path attribute,
# empty-listing render) -- see docs/features/130-workspace-switcher-ui/
# ===========================================================================

import http.cookies


def test_safe_referer_path_drops_fragment(tmp_path):
    """A referer with a URL fragment redirects to path+query ONLY -- the
    fragment is silently dropped (D4: "urlsplit(referer).path (+query)",
    fragment is never in the kept set). Kills a mutation that appends
    `#{fragment}` onto `dest`."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get(
        "/workspace/select",
        params={"uuid": "*"},
        headers={
            "referer": "http://testserver/entities?type=feature#section-anchor"
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/entities?type=feature"
    assert "#" not in response.headers["location"]


def test_safe_referer_path_no_leading_slash_redirects_home(tmp_path):
    """A referer whose urlsplit().path is EMPTY (a bare origin with no
    path segment, e.g. 'http://testserver') is neither protocol-relative
    ('//...') nor leading-slash -- falls back to '/'. Every existing
    referer test either starts with '/' (accepted) or with '//' (rejected
    by the second clause) or omits the header entirely (short-circuited by
    the `if not referer` guard before this line ever runs) -- none
    exercise `dest.startswith("/")` being False. Kills a mutation that
    swaps the `and` to `or`: under that mutation, dest='' would wrongly
    pass because `not dest.startswith("//")` is True for an empty
    string."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get(
        "/workspace/select",
        params={"uuid": "*"},
        headers={"referer": "http://testserver"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_select_route_uppercase_hex_uuid_sets_cookie_verbatim(tmp_path):
    """An uppercase-hex canonical uuid is accepted by `_is_uuid_shaped`
    (uuid.UUID() parses case-insensitively) and the cookie is set to the
    EXACT uppercase string -- no lowercasing/normalization happens at the
    write site. Every other select-route test uses str(uuid.uuid4()),
    which the stdlib always renders lowercase, so none of them exercise
    this branch of the case-insensitive parse. Kills a mutation that
    normalizes the value (e.g. `.lower()`) before storing it."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    upper_uuid = str(uuid.uuid4()).upper()

    response = client.get(
        "/workspace/select",
        params={"uuid": upper_uuid},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.cookies.get(COOKIE_NAME) == upper_uuid


def test_board_scoping_uppercase_cookie_case_mismatch_is_unmatched(tmp_path):
    """A cookie holding the SAME uuid as a real, populated workspace but in
    UPPERCASE is honored as shaped (passes _is_uuid_shaped) yet never
    matches that workspace's lowercase-stored uuid: SQLite TEXT equality is
    case-sensitive by default (no COLLATE NOCASE anywhere in the schema)
    and neither _is_uuid_shaped nor effective_workspace_uuid normalize
    case. Board scoping therefore treats it as an unknown scope (Alpha
    Card's workflow row is excluded -- same class of behavior as the
    shaped-but-unknown-uuid case, but reached via case mismatch rather than
    a nonexistent uuid) and the switcher renders the fourth-state 'unknown
    workspace' option keyed on the UPPERCASE value -- ws_a's real
    (lowercase) option is not selected. Kills a mutation that lowercases
    the cookie, or introduces case-insensitive comparison, anywhere in
    this chain."""
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    ws_a = _bootstrap_workspace(db_file, project_root=str(tmp_path / "proj-a"))
    db.register_entity("feature", "1-alpha", "Alpha Card", workspace_uuid=ws_a)
    db.create_workflow_phase("feature:1-alpha", kanban_column="wip")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    client.cookies.set(COOKIE_NAME, ws_a.upper())

    response = client.get("/")

    assert response.status_code == 200
    assert "Alpha Card" not in response.text
    unmatched_element = _option_element(response.text, ws_a.upper())
    assert "selected" in unmatched_element
    assert "disabled" in unmatched_element
    assert "selected" not in _option_element(response.text, ws_a)
    assert "selected" not in _option_element(response.text, "*")


def test_select_route_36char_semicolon_injected_uuid_sets_no_cookie(tmp_path):
    """A value that is exactly 36 characters (matching the canonical-length
    check) but has its final hex digit replaced with ';' fails
    uuid.UUID()'s parse -- no Set-Cookie header, redirect still happens.
    Complements test_select_route_32char_hex_sets_no_cookie, which kills
    the mutation "drop the len==36 check, keep only UUID() parsing" (a
    32-char value passes UUID() but is caught by the length check): THIS
    test kills the other half, "drop the UUID() parse, keep only
    len(v)==36" -- a mutant missing the parse call would see this 36-char
    value and wrongly treat it as shaped, feeding a ';'-containing value
    into response.set_cookie(). Documents that a cookie/header-injection
    payload can never reach set_cookie via this param."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    near_uuid = str(uuid.uuid4())
    injected = near_uuid[:-1] + ";"
    assert len(injected) == 36  # sanity: exact canonical length preserved

    response = client.get(
        "/workspace/select",
        params={"uuid": injected},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "set-cookie" not in response.headers


def test_select_route_cookie_path_attribute_is_root(tmp_path):
    """The D2 cookie contract includes path="/" -- pinned separately from
    the existing D2-attribute tests, which check max-age/httponly/samesite
    but never assert on path. Starlette's set_cookie() already DEFAULTS
    path to "/", so dropping the kwarg entirely is not a live mutation;
    the real risk is path being set to something ELSE (e.g. "/workspace",
    matching the route's own path -- a plausible copy-paste mistake from a
    handler that scopes a cookie to itself). Parses the Set-Cookie header
    with http.cookies.SimpleCookie for an EXACT attribute match rather
    than substring-matching "path=/", which would false-pass a mutant
    "path=/workspace" (that string still contains "path=/" as a
    prefix)."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get(
        "/workspace/select",
        params={"uuid": "*"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    parsed_cookie = http.cookies.SimpleCookie()
    parsed_cookie.load(response.headers["set-cookie"])
    assert parsed_cookie[COOKIE_NAME]["path"] == "/"


def test_board_full_page_switcher_zero_populated_workspaces_unmatched_default(
    tmp_path,
):
    """switcher_context() when list_workspaces_with_entities() returns a
    truly EMPTY list (no populated workspaces at all -- the existing
    unpopulated-default test always has ONE other populated workspace in
    the list), combined with a non-None startup default: the dropdown
    still renders (no crash on the empty `workspaces` loop), contains NO
    per-workspace <option> besides '*' and the transient unmatched one,
    'All workspaces' is NOT selected, and the fourth-state 'unknown
    workspace' option IS selected for the default's uuid. Kills a mutation
    that assumes `workspaces` is non-empty (e.g. an unguarded
    `workspaces[0]` access) or that only sets effective_unmatched when the
    listing is non-empty."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)  # zero entities, zero workspaces rows

    from ui import create_app

    app = create_app(db_path=db_file)
    default_uuid = str(uuid.uuid4())
    app.state.workspace_uuid = default_uuid
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert '<select name="uuid"' in response.text
    unmatched_element = _option_element(response.text, default_uuid)
    assert "selected" in unmatched_element
    assert "disabled" in unmatched_element
    assert "selected" not in _option_element(response.text, "*")
    # Only '*' and the transient unmatched option -- no populated-workspace
    # <option> elements exist since list_workspaces_with_entities() is [].
    assert response.text.count("<option value=") == 2


def test_safe_referer_path_backslash_redirects_home(tmp_path):
    """A referer whose path contains a backslash (`/\\evil.com`) redirects
    to '/' -- browsers normalize `/\\host` to protocol-relative `//host`,
    so the guard must reject it itself rather than lean on Starlette's
    Location percent-encoding (security review, defense-in-depth). Kills
    a mutation that drops the `"\\\\" not in dest` conjunct."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    response = client.get(
        "/workspace/select",
        params={"uuid": "*"},
        headers={"referer": "http://localhost/\\evil.com"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_board_full_page_switcher_none_default_no_cookie_selects_all(tmp_path):
    """No cookie AND app.state.workspace_uuid is None (129's WARN path --
    the default runtime state when the server starts outside any known
    workspace): 'All workspaces' is the selected option and no transient
    'unknown workspace' option renders (implementation review: the
    `switcher.selected is none and switcher.default_uuid is none` template
    clause was previously untested -- a mutation dropping the second
    conjunct went uncaught)."""
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    ws_a = _bootstrap_workspace(db_file, project_root=str(tmp_path / "proj-a"))
    db.register_entity("feature", "1-alpha", "Alpha Card", workspace_uuid=ws_a)

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.workspace_uuid = None
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "selected" in _option_element(response.text, "*")
    assert "selected" not in _option_element(response.text, ws_a)
    assert "unknown workspace" not in response.text
