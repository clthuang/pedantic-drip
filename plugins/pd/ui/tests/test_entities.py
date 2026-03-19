"""Unit tests for entity route helpers."""


# ===========================================================================
# Task 1.2: _build_workflow_lookup
# ===========================================================================


class _StubDB:
    """Minimal stub with a list_workflow_phases() method."""

    def __init__(self, phases: list[dict]):
        self._phases = phases

    def list_workflow_phases(self) -> list[dict]:
        return self._phases


def test_build_workflow_lookup_empty_list():
    """Empty phase list returns empty dict."""
    from ui.routes.entities import _build_workflow_lookup

    db = _StubDB([])
    assert _build_workflow_lookup(db) == {}


def test_build_workflow_lookup_correct_keys():
    """Entries are keyed by type_id."""
    from ui.routes.entities import _build_workflow_lookup

    phases = [
        {"type_id": "feature:alpha", "workflow_phase": "design"},
        {"type_id": "feature:beta", "workflow_phase": "implement"},
    ]
    db = _StubDB(phases)
    result = _build_workflow_lookup(db)

    assert len(result) == 2
    assert result["feature:alpha"] == phases[0]
    assert result["feature:beta"] == phases[1]


def test_build_workflow_lookup_last_wins_on_collision():
    """When two entries share a type_id, the last one wins."""
    from ui.routes.entities import _build_workflow_lookup

    phases = [
        {"type_id": "feature:dup", "workflow_phase": "first"},
        {"type_id": "feature:dup", "workflow_phase": "second"},
    ]
    db = _StubDB(phases)
    result = _build_workflow_lookup(db)

    assert len(result) == 1
    assert result["feature:dup"]["workflow_phase"] == "second"


# ===========================================================================
# Task 1.3: _strip_self_from_lineage
# ===========================================================================


def test_strip_self_from_lineage_empty():
    """Empty lineage list returns empty list."""
    from ui.routes.entities import _strip_self_from_lineage

    assert _strip_self_from_lineage([], "feature:x") == []


def test_strip_self_from_lineage_self_removed():
    """Entry matching type_id is removed."""
    from ui.routes.entities import _strip_self_from_lineage

    lineage = [
        {"type_id": "project:parent", "name": "Parent"},
        {"type_id": "feature:self", "name": "Self"},
        {"type_id": "feature:sibling", "name": "Sibling"},
    ]
    result = _strip_self_from_lineage(lineage, "feature:self")

    assert len(result) == 2
    assert all(e["type_id"] != "feature:self" for e in result)


def test_strip_self_from_lineage_absent_returns_all():
    """When type_id is not in lineage, all entries are returned unchanged."""
    from ui.routes.entities import _strip_self_from_lineage

    lineage = [
        {"type_id": "project:a", "name": "A"},
        {"type_id": "feature:b", "name": "B"},
    ]
    result = _strip_self_from_lineage(lineage, "feature:missing")

    assert result == lineage


# ===========================================================================
# Task 1.4: _format_metadata
# ===========================================================================


def test_format_metadata_none():
    """None returns empty string."""
    from ui.routes.entities import _format_metadata

    assert _format_metadata(None) == ""


def test_format_metadata_empty_string():
    """Empty string returns empty string."""
    from ui.routes.entities import _format_metadata

    assert _format_metadata("") == ""


def test_format_metadata_valid_json():
    """Valid JSON string returns pretty-printed JSON."""
    from ui.routes.entities import _format_metadata
    import json

    raw = '{"key": "value", "num": 42}'
    result = _format_metadata(raw)
    expected = json.dumps({"key": "value", "num": 42}, indent=2)

    assert result == expected


def test_format_metadata_invalid_json():
    """Invalid JSON returns the raw string unchanged."""
    from ui.routes.entities import _format_metadata

    raw = "not valid json {{"
    assert _format_metadata(raw) == raw


# ===========================================================================
# Task 1.5a: entity_list error and fallback code paths
# ===========================================================================

import sqlite3
import unittest.mock
from starlette.testclient import TestClient
from entity_registry.database import EntityDatabase


def _seed_entity(db_file, type_id, entity_type="feature", name=None,
                 status="active", entity_id=None):
    """Insert an entity row for testing (FKs disabled)."""
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = OFF")
    now = "2026-03-08T00:00:00Z"
    conn.execute(
        "INSERT OR IGNORE INTO entities "
        "(type_id, uuid, entity_type, entity_id, name, status, "
        "artifact_path, metadata, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (type_id, f"uuid-{type_id}", entity_type, entity_id or type_id,
         name or type_id, status, None, None, now, now),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Task 1.5a.1: entity_list — missing DB returns error page
# ---------------------------------------------------------------------------
def test_entity_list_missing_db_shows_error():
    """GET /entities with no DB renders error.html with ENTITY_DB_PATH."""
    from ui import create_app

    app = create_app(db_path="/nonexistent/path.db")
    client = TestClient(app)
    response = client.get("/entities")

    assert response.status_code == 200
    assert "Database Not Found" in response.text
    assert "ENTITY_DB_PATH" in response.text


# ---------------------------------------------------------------------------
# Task 1.5a.2: entity_list — DB query error renders error page
# ---------------------------------------------------------------------------
def test_entity_list_db_error_shows_error_message(tmp_path):
    """GET /entities renders error page when DB query raises exception."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.db.list_entities = unittest.mock.MagicMock(
        side_effect=Exception("entity query failed")
    )
    client = TestClient(app)
    response = client.get("/entities")

    assert response.status_code == 200
    assert "An error occurred while querying the database" in response.text


# ---------------------------------------------------------------------------
# Task 1.5a.3: entity_list — DB error logged to stderr
# ---------------------------------------------------------------------------
def test_entity_list_db_error_logged_to_stderr(tmp_path, capsys):
    """DB query error in entity_list is printed to stderr."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.db.list_entities = unittest.mock.MagicMock(
        side_effect=Exception("stderr test")
    )
    client = TestClient(app)
    client.get("/entities")

    captured = capsys.readouterr()
    assert "stderr test" in captured.err


# ---------------------------------------------------------------------------
# Task 1.5a.4: entity_list — search ValueError falls back to list_entities
# ---------------------------------------------------------------------------
def test_entity_list_search_valueerror_falls_back(tmp_path):
    """When search_entities raises ValueError, falls back to list_entities."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_entity(db_file, "feature:fallback-test", name="Fallback Feature")

    from ui import create_app

    app = create_app(db_path=db_file)
    # search_entities raises ValueError (FTS unavailable)
    app.state.db.search_entities = unittest.mock.MagicMock(
        side_effect=ValueError("fts_not_available")
    )
    client = TestClient(app)
    response = client.get("/entities?q=test")

    assert response.status_code == 200
    # Should show "Search unavailable" in the partial content
    assert "Search unavailable" in response.text
    # Should still render entities from list_entities fallback
    assert "Fallback Feature" in response.text


# ---------------------------------------------------------------------------
# Task 1.5a.5: entity_list — empty entities returns page with no crash
# ---------------------------------------------------------------------------
def test_entity_list_empty_returns_page(tmp_path):
    """GET /entities with empty DB returns entities.html without error."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities")

    assert response.status_code == 200
    assert "Entities" in response.text


# ===========================================================================
# Task 1.6a: entity_detail error and 404 code paths
# ===========================================================================


# ---------------------------------------------------------------------------
# Task 1.6a.1: entity_detail — missing DB returns error page
# ---------------------------------------------------------------------------
def test_entity_detail_missing_db_shows_error():
    """GET /entities/<id> with no DB renders error.html."""
    from ui import create_app

    app = create_app(db_path="/nonexistent/path.db")
    client = TestClient(app)
    response = client.get("/entities/feature:test")

    assert response.status_code == 200
    assert "Database Not Found" in response.text


# ---------------------------------------------------------------------------
# Task 1.6a.2: entity_detail — entity not found returns 404
# ---------------------------------------------------------------------------
def test_entity_detail_not_found_returns_404(tmp_path):
    """GET /entities/<nonexistent> returns 404.html with status_code=404."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities/feature:nonexistent")

    assert response.status_code == 404
    assert "Entity not found" in response.text


# ---------------------------------------------------------------------------
# Task 1.6a.3: entity_detail — DB error renders error page
# ---------------------------------------------------------------------------
def test_entity_detail_db_error_shows_error(tmp_path):
    """GET /entities/<id> renders error page when get_entity raises."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.db.get_entity = unittest.mock.MagicMock(
        side_effect=Exception("detail query failed")
    )
    client = TestClient(app)
    response = client.get("/entities/feature:test")

    assert response.status_code == 200
    assert "An error occurred while querying the database" in response.text


# ---------------------------------------------------------------------------
# Task 1.6a.4: entity_detail — DB error logged to stderr
# ---------------------------------------------------------------------------
def test_entity_detail_db_error_logged_to_stderr(tmp_path, capsys):
    """DB query error in entity_detail is printed to stderr."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.db.get_entity = unittest.mock.MagicMock(
        side_effect=Exception("detail stderr test")
    )
    client = TestClient(app)
    client.get("/entities/feature:test")

    captured = capsys.readouterr()
    assert "detail stderr test" in captured.err


# ===========================================================================
# Task 2.3: entities.html template
# ===========================================================================


# ---------------------------------------------------------------------------
# Task 2.3.1: entities.html extends base.html
# ---------------------------------------------------------------------------
def test_entities_html_extends_base():
    """entities.html contains {% extends 'base.html' %}."""
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "templates" / "entities.html"
    content = template_path.read_text()

    assert '{% extends "base.html" %}' in content


# ---------------------------------------------------------------------------
# Task 2.3.2: entities.html contains entities-content div
# ---------------------------------------------------------------------------
def test_entities_html_has_entities_content_div():
    """entities.html contains <div id='entities-content'>."""
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "templates" / "entities.html"
    content = template_path.read_text()

    assert 'id="entities-content"' in content


# ---------------------------------------------------------------------------
# Task 2.3.3: entities.html includes _entities_content.html
# ---------------------------------------------------------------------------
def test_entities_html_includes_partial():
    """entities.html contains {% include '_entities_content.html' %}."""
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "templates" / "entities.html"
    content = template_path.read_text()

    assert '{% include "_entities_content.html" %}' in content


# ---------------------------------------------------------------------------
# Task 2.3.4: entities.html has page heading
# ---------------------------------------------------------------------------
def test_entities_html_has_page_heading():
    """entities.html has a heading with 'Entities'."""
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "templates" / "entities.html"
    content = template_path.read_text()

    assert "Entities" in content


# ===========================================================================
# Phase 4: Integration Tests — entity list, detail, lineage, search, HTMX
# ===========================================================================

import pytest


@pytest.fixture()
def integration_client(tmp_path):
    """Create a DB seeded with entities and workflow data, return TestClient.

    Entities seeded:
    - feature:feat-alpha  (active, parent=project:proj-one, workflow_phase=implement)
    - feature:feat-beta   (completed, no parent, no workflow)
    - brainstorm:bs-one   (active, no parent, no workflow)
    - project:proj-one    (active, no parent, no workflow)
    """
    db = EntityDatabase(str(tmp_path / "test.db"))

    # Seed entities via the DB API
    db.register_entity("feature", "feat-alpha", "Alpha Feature", status="active")
    db.register_entity("feature", "feat-beta", "Beta Feature", status="completed")
    db.register_entity("brainstorm", "bs-one", "Brainstorm One", status="active")
    db.register_entity("project", "proj-one", "Project One", status="active")

    # Set parent relationship: feat-alpha -> proj-one
    db.set_parent("feature:feat-alpha", "project:proj-one")

    # Disable FK enforcement for raw workflow_phases insert
    db._conn.execute("PRAGMA foreign_keys = OFF")

    # Seed workflow phase for feat-alpha
    # kanban_column must be a valid CHECK value (wip, not "In Progress")
    db._conn.execute(
        "INSERT INTO workflow_phases "
        "(type_id, kanban_column, workflow_phase, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("feature:feat-alpha", "wip", "implement", "2026-03-08T00:00:00Z"),
    )
    db._conn.commit()

    # Build the app and test client
    from ui import create_app

    app = create_app(str(tmp_path / "test.db"))
    client = TestClient(app)
    return client


# ---------------------------------------------------------------------------
# Task 4.1.1: Entity list returns all seeded entities (FR-1)
# ---------------------------------------------------------------------------
def test_integration_entity_list_returns_all_entities(integration_client):
    """GET /entities returns HTTP 200 with all 4 seeded entities in the table."""
    response = integration_client.get("/entities")

    assert response.status_code == 200
    assert "Alpha Feature" in response.text
    assert "Beta Feature" in response.text
    assert "Brainstorm One" in response.text
    assert "Project One" in response.text
    # Verify entity count indicator
    assert "4 entities" in response.text


# ---------------------------------------------------------------------------
# Task 4.1.2: Type filtering returns only matching entities (FR-2)
# ---------------------------------------------------------------------------
def test_integration_entity_list_type_filter(integration_client):
    """GET /entities?type=feature returns only feature entities."""
    response = integration_client.get("/entities?type=feature")

    assert response.status_code == 200
    assert "Alpha Feature" in response.text
    assert "Beta Feature" in response.text
    # Non-feature entities should NOT appear in the table rows
    assert "Brainstorm One" not in response.text
    assert "Project One" not in response.text
    assert "2 entities" in response.text


# ---------------------------------------------------------------------------
# Task 4.1.3: Status filtering returns only matching entities (FR-3)
# ---------------------------------------------------------------------------
def test_integration_entity_list_status_filter(integration_client):
    """GET /entities?status=active returns only active entities."""
    response = integration_client.get("/entities?status=active")

    assert response.status_code == 200
    assert "Alpha Feature" in response.text
    assert "Brainstorm One" in response.text
    assert "Project One" in response.text
    # Beta Feature has status=completed, should be filtered out
    assert "Beta Feature" not in response.text
    assert "3 entities" in response.text


# ---------------------------------------------------------------------------
# Task 4.2.1: Entity detail returns full data with workflow fields (FR-4)
# ---------------------------------------------------------------------------
def test_integration_entity_detail_with_workflow(integration_client):
    """GET /entities/feature:feat-alpha returns 200 with entity + workflow data."""
    response = integration_client.get("/entities/feature:feat-alpha")

    assert response.status_code == 200
    # Entity fields
    assert "Alpha Feature" in response.text
    assert "feature:feat-alpha" in response.text
    assert "active" in response.text
    # Workflow fields from the template (kanban_column, workflow_phase)
    assert "wip" in response.text
    assert "implement" in response.text
    # Workflow State section should be rendered
    assert "Workflow State" in response.text


# ---------------------------------------------------------------------------
# Task 4.2.2: Entity detail 404 for nonexistent entity (FR-4)
# ---------------------------------------------------------------------------
def test_integration_entity_detail_not_found(integration_client):
    """GET /entities/nonexistent:xxx returns HTTP 404 with 'Entity not found'."""
    response = integration_client.get("/entities/nonexistent:xxx")

    assert response.status_code == 404
    assert "Entity not found" in response.text


# ---------------------------------------------------------------------------
# Task 4.2.3: Lineage — ancestors and children displayed (FR-5)
# ---------------------------------------------------------------------------
def test_integration_entity_detail_lineage(integration_client):
    """Detail page for feat-alpha shows ancestors (proj-one) and no children.
    Detail page for proj-one shows no ancestors and children (feat-alpha).
    Self is stripped from both lists."""
    # feat-alpha has parent proj-one
    response = integration_client.get("/entities/feature:feat-alpha")
    assert response.status_code == 200
    # Ancestors section should show the parent
    assert "project:proj-one" in response.text
    # feat-alpha has no children, so "No children" should appear
    assert "No children" in response.text

    # proj-one is a parent, should show feat-alpha as child
    response_parent = integration_client.get("/entities/project:proj-one")
    assert response_parent.status_code == 200
    # Children section should show the child
    assert "feature:feat-alpha" in response_parent.text
    # proj-one has no parent, so "No parent" should appear
    assert "No parent" in response_parent.text


# ---------------------------------------------------------------------------
# Task 4.3.1: Search returns FTS matches; fallback on FTS unavailable (FR-8)
# ---------------------------------------------------------------------------
def test_integration_search_returns_fts_matches(integration_client):
    """GET /entities?q=Alpha returns entities matching the FTS query."""
    response = integration_client.get("/entities?q=Alpha")

    assert response.status_code == 200
    assert "Alpha Feature" in response.text


def test_integration_search_fts_fallback(tmp_path):
    """When search_entities raises ValueError, fallback returns all entities
    with search input disabled."""
    db = EntityDatabase(str(tmp_path / "test.db"))
    db.register_entity("feature", "fb-test", "Fallback Test", status="active")

    from ui import create_app

    app = create_app(str(tmp_path / "test.db"))
    # Mock search_entities to raise ValueError (FTS unavailable)
    app.state.db.search_entities = unittest.mock.MagicMock(
        side_effect=ValueError("FTS index not available")
    )
    client = TestClient(app)
    response = client.get("/entities?q=term")

    assert response.status_code == 200
    # Fallback shows all entities (from list_entities)
    assert "Fallback Test" in response.text
    # Search should be marked as unavailable
    assert "Search unavailable" in response.text


# ---------------------------------------------------------------------------
# Task 4.3.2: HTMX partial — no <html> tag, has table content (FR-9)
# ---------------------------------------------------------------------------
def test_integration_htmx_partial_entities(integration_client):
    """GET /entities with HX-Request header returns content partial only.
    No <html> tag, but has the table."""
    response = integration_client.get(
        "/entities", headers={"HX-Request": "true"}
    )

    assert response.status_code == 200
    # Partial should NOT contain <html> (no full page wrapper)
    assert "<html" not in response.text
    # Partial SHOULD contain the table with entities
    assert "<table" in response.text
    assert "Alpha Feature" in response.text


# ---------------------------------------------------------------------------
# Task 4.3.3: Missing DB returns error.html content
# ---------------------------------------------------------------------------
def test_integration_entities_missing_db_error():
    """App with nonexistent DB path returns error page for /entities."""
    from ui import create_app

    app = create_app(db_path="/nonexistent/path.db")
    client = TestClient(app)
    response = client.get("/entities")

    assert response.status_code == 200
    assert "Database Not Found" in response.text
    assert "ENTITY_DB_PATH" in response.text


# ===========================================================================
# Test Deepening Phase — Dimensions 1-5
# ===========================================================================


# ---------------------------------------------------------------------------
# Dimension 1: BDD Scenarios — spec-driven scenarios not in TDD tests
# derived_from: spec:FR-1 (entity list sorted by updated_at DESC)
# ---------------------------------------------------------------------------
def test_entity_list_sorted_by_updated_at_descending(tmp_path):
    """Given entities with different updated_at timestamps, when listing,
    then they appear in descending updated_at order (most recent first).

    Anticipate: If sort is ascending instead of descending, or sort key is
    wrong, the order will be reversed or arbitrary.
    Challenge: Asserting index positions pins the sort direction.
    Verify: Swapping reverse=True to reverse=False would put 'older' first,
    failing the assertion.
    """
    # Given entities with different updated_at timestamps
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    db.register_entity("feature", "older", "Older Feature", status="active")
    db.register_entity("feature", "newer", "Newer Feature", status="active")

    # Manually set different updated_at values via raw SQL
    conn = sqlite3.connect(db_file)
    conn.execute(
        "UPDATE entities SET updated_at = '2026-01-01T00:00:00Z' "
        "WHERE type_id = 'feature:older'"
    )
    conn.execute(
        "UPDATE entities SET updated_at = '2026-03-08T00:00:00Z' "
        "WHERE type_id = 'feature:newer'"
    )
    conn.commit()
    conn.close()

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)

    # When listing entities
    response = client.get("/entities")

    # Then 'Newer Feature' appears before 'Older Feature' in the HTML
    assert response.status_code == 200
    newer_pos = response.text.index("Newer Feature")
    older_pos = response.text.index("Older Feature")
    assert newer_pos < older_pos, "Entities should be sorted by updated_at DESC"


# ---------------------------------------------------------------------------
# derived_from: spec:FR-2 (invalid type parameter shows all entities)
# ---------------------------------------------------------------------------
def test_entity_list_invalid_type_shows_all_entities(integration_client):
    """Given an invalid type parameter not in ENTITY_TYPES, when requesting
    the entity list, then all entities are shown (no error).

    Anticipate: If invalid type is passed through to list_entities, it may
    return empty results instead of all entities.
    """
    # When requesting with an invalid type parameter
    response = integration_client.get("/entities?type=nonexistent_type")

    # Then all entities are shown
    assert response.status_code == 200
    assert "Alpha Feature" in response.text
    assert "Beta Feature" in response.text
    assert "Brainstorm One" in response.text
    assert "Project One" in response.text
    assert "4 entities" in response.text


# ---------------------------------------------------------------------------
# derived_from: spec:FR-3 (combinable type+status filters)
# ---------------------------------------------------------------------------
def test_entity_list_combined_type_and_status_filter(integration_client):
    """Given entities of different types and statuses, when filtering by both
    type=feature and status=active, then only active features are returned.

    Anticipate: If filters aren't combined properly, we'd get either all
    features (ignoring status) or all active entities (ignoring type).
    """
    # When combining type and status filters
    response = integration_client.get("/entities?type=feature&status=active")

    # Then only active features are returned
    assert response.status_code == 200
    assert "Alpha Feature" in response.text  # feature + active
    assert "Beta Feature" not in response.text  # feature + completed
    assert "Brainstorm One" not in response.text  # brainstorm + active
    assert "1 entities" in response.text


# ---------------------------------------------------------------------------
# derived_from: spec:FR-4 (detail page shows all entity fields)
# ---------------------------------------------------------------------------
def test_entity_detail_shows_all_required_fields(integration_client):
    """Given a feature entity, when viewing its detail page, then all required
    fields from FR-4 are displayed: name, type_id, uuid, entity_type,
    entity_id, status, created_at, updated_at.

    Anticipate: If a field is missing from the template, the page would
    render but lack that information.
    """
    response = integration_client.get("/entities/feature:feat-alpha")

    assert response.status_code == 200
    # Entity Info section should contain all core fields
    assert "Alpha Feature" in response.text  # name
    assert "feature:feat-alpha" in response.text  # type_id
    assert "feature" in response.text  # entity_type
    assert "feat-alpha" in response.text  # entity_id
    assert "active" in response.text  # status
    # UUID should be present (generated by register_entity)
    assert "UUID" in response.text  # section label
    # Created/Updated should be present
    assert "Created" in response.text
    assert "Updated" in response.text


# ---------------------------------------------------------------------------
# derived_from: spec:FR-4 (detail page shows workflow fields for features)
# ---------------------------------------------------------------------------
def test_entity_detail_no_workflow_for_non_feature(integration_client):
    """Given a non-feature entity (brainstorm), when viewing its detail page,
    then the Workflow State section is NOT rendered.

    Anticipate: If workflow section renders unconditionally, non-feature
    entities would show empty/broken workflow data.
    """
    response = integration_client.get("/entities/brainstorm:bs-one")

    assert response.status_code == 200
    assert "Brainstorm One" in response.text
    # Workflow State section body (with workflow fields like "Workflow Phase",
    # "Last Completed Phase") should NOT be rendered for non-feature entities.
    # Note: HTML comment <!-- Workflow State --> is always present in source,
    # but the actual section card (with h2 heading) is gated by {% if workflow %}
    assert "Workflow Phase" not in response.text
    assert "Last Completed Phase" not in response.text


# ---------------------------------------------------------------------------
# derived_from: spec:FR-7 (navbar active state)
# ---------------------------------------------------------------------------
def test_navbar_active_state_on_entity_list(integration_client):
    """Given the entity list page, when rendered, then the 'Entities' navbar
    link has the btn-active class and 'Board' does not.

    Anticipate: If active_page context variable is wrong or missing, the
    wrong link (or no link) gets the active class.
    """
    response = integration_client.get("/entities")

    assert response.status_code == 200
    # The Entities link should be active — check for the pattern in HTML
    # base.html: class="btn btn-sm btn-ghost {{ 'btn-active' if active_page... == 'entities' }}"
    # So we expect 'btn-active' near 'Entities'
    text = response.text
    # Find the entities link and verify it has btn-active
    entities_link_start = text.index('href="/entities"')
    # Expand window to capture class attribute which follows the href
    entities_section = text[entities_link_start - 100:entities_link_start + 150]
    assert "btn-active" in entities_section


# ---------------------------------------------------------------------------
# derived_from: spec:FR-8 (search combinable with type filter)
# ---------------------------------------------------------------------------
def test_search_combined_with_type_filter(integration_client):
    """Given entities of different types, when searching with a type filter,
    then only matching entities of that type are returned.

    Anticipate: If search_entities ignores entity_type param, all matching
    entities regardless of type would be returned.
    """
    response = integration_client.get("/entities?q=Feature&type=feature")

    assert response.status_code == 200
    assert "Alpha Feature" in response.text
    assert "Beta Feature" in response.text
    # Brainstorm entities should not appear even if they match search
    assert "Brainstorm One" not in response.text


# ---------------------------------------------------------------------------
# derived_from: spec:FR-8 (empty search results message)
# ---------------------------------------------------------------------------
def test_search_no_results_shows_empty_message(integration_client):
    """Given a search term that matches no entities, when searching,
    then 'No entities match your search' message is displayed.

    Anticipate: If the empty state doesn't check search_query, it would
    show the generic 'No entities found' instead of search-specific message.
    """
    response = integration_client.get("/entities?q=zzzznonexistent")

    assert response.status_code == 200
    assert "No entities match your search" in response.text


# ---------------------------------------------------------------------------
# derived_from: spec:FR-1 (empty state message when no entities)
# ---------------------------------------------------------------------------
def test_entity_list_empty_db_shows_no_entities_message(tmp_path):
    """Given an empty database, when listing entities,
    then 'No entities found' message is displayed (not 'no search match').

    Anticipate: If the template uses the wrong conditional, it might show
    the search-specific message even when no search was performed.
    """
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities")

    assert response.status_code == 200
    assert "No entities found" in response.text
    assert "No entities match your search" not in response.text


# ---------------------------------------------------------------------------
# derived_from: spec:FR-6 (kanban card click-through)
# ---------------------------------------------------------------------------
def test_card_template_has_clickable_link():
    """Given the _card.html template, when rendered, then the entire card is
    wrapped in an <a> tag linking to /entities/{type_id}.

    Anticipate: If the link is missing or wrong, cards won't navigate to
    entity detail pages.
    """
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "templates" / "_card.html"
    content = template_path.read_text()

    assert 'href="/entities/{{ item.type_id }}"' in content
    assert "block" in content  # link fills card area
    assert "no-underline" in content  # no text decoration
    assert "[color:inherit]" in content  # no link color override


# ---------------------------------------------------------------------------
# derived_from: spec:FR-9 (HTMX partial for filters with type parameter)
# ---------------------------------------------------------------------------
def test_htmx_partial_with_type_filter(integration_client):
    """Given a type filter with HX-Request header, when requesting entities,
    then only the content partial is returned with filtered entities.

    Anticipate: If HTMX detection runs before filtering, the partial might
    return unfiltered data.
    """
    response = integration_client.get(
        "/entities?type=feature",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    # No full page wrapper
    assert "<html" not in response.text
    # Has table with filtered content
    assert "<table" in response.text
    assert "Alpha Feature" in response.text
    assert "Beta Feature" in response.text
    # Non-features should not appear
    assert "Brainstorm One" not in response.text


# ---------------------------------------------------------------------------
# Dimension 2: Boundary Values & Equivalence Partitioning
# ---------------------------------------------------------------------------

# derived_from: dimension:boundary (single entity in DB)
def test_entity_list_single_entity(tmp_path):
    """Given exactly one entity in the database, when listing entities,
    then exactly one row is shown with '1 entities' count.

    Anticipate: Off-by-one or pluralization issues with entity count display.
    """
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    db.register_entity("feature", "solo", "Solo Feature", status="active")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities")

    assert response.status_code == 200
    assert "Solo Feature" in response.text
    assert "1 entities" in response.text


# derived_from: dimension:boundary (entity with None/null fields)
def test_entity_detail_with_null_fields(tmp_path):
    """Given an entity with minimal fields (null artifact_path, metadata),
    when viewing its detail page, then it renders without error using '-'
    placeholders.

    Anticipate: If template doesn't handle None values, Jinja2 might render
    'None' strings or throw errors.
    """
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    db.register_entity("brainstorm", "minimal", "Minimal Entity", status="active")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities/brainstorm:minimal")

    assert response.status_code == 200
    assert "Minimal Entity" in response.text
    # Null fields should not render as literal 'None'
    assert ">None<" not in response.text
    assert "No parent" in response.text


# derived_from: dimension:boundary (special characters in type_id)
def test_entity_detail_with_colon_in_type_id(integration_client):
    """Given a type_id containing a colon (standard format like feature:xxx),
    when requesting the detail page, then the path converter handles it
    correctly.

    Anticipate: If the path converter doesn't use {identifier:path},
    Starlette would split on the colon and return 404.
    """
    # This is already working via integration_client, but let's verify
    # the path converter specifically with a type_id containing colons
    response = integration_client.get("/entities/feature:feat-alpha")

    assert response.status_code == 200
    assert "feature:feat-alpha" in response.text


# derived_from: dimension:boundary (empty search query string)
def test_entity_list_empty_search_query_shows_all(integration_client):
    """Given an empty search query parameter (q=), when listing entities,
    then all entities are shown (not treated as search).

    Anticipate: If empty string is treated as truthy, search_entities might
    be called with empty query causing unexpected results.
    """
    response = integration_client.get("/entities?q=")

    assert response.status_code == 200
    assert "Alpha Feature" in response.text
    assert "Beta Feature" in response.text
    assert "4 entities" in response.text


# derived_from: dimension:boundary (status filter with no matches)
def test_entity_list_status_filter_no_matches(integration_client):
    """Given a status filter that matches no entities, when listing,
    then the empty state message is shown.

    Anticipate: If status filtering is skipped, all entities would show.
    """
    response = integration_client.get("/entities?status=planned")

    assert response.status_code == 200
    assert "No entities found" in response.text


# ---------------------------------------------------------------------------
# Dimension 3: Adversarial / Negative Testing
# ---------------------------------------------------------------------------

# derived_from: dimension:adversarial (invalid status parameter)
def test_entity_list_invalid_status_returns_empty(integration_client):
    """Given an invalid status value, when filtering by status,
    then no entities match and empty state is shown.

    Anticipate: If status filtering doesn't do exact match, it could
    partially match or ignore the filter.
    """
    response = integration_client.get("/entities?status=nonexistent_status")

    assert response.status_code == 200
    # No entities have this status, so empty state
    assert "No entities found" in response.text


# derived_from: dimension:adversarial (SQL injection in search parameter)
def test_entity_list_search_with_sql_injection_attempt(integration_client):
    """Given a search query containing SQL injection attempt, when searching,
    then the application does not crash and returns safely.

    Anticipate: If search is not parameterized, SQL injection could corrupt
    data or cause errors.
    """
    response = integration_client.get(
        "/entities?q=' OR 1=1 --"
    )

    assert response.status_code == 200
    # Should not crash — either returns matches or empty


# derived_from: dimension:adversarial (XSS in entity names — auto-escaped by Jinja2)
def test_entity_list_xss_in_entity_name(tmp_path):
    """Given an entity with HTML/script tags in its name, when listing,
    then the name is HTML-escaped by Jinja2 autoescaping.

    Anticipate: If Jinja2 autoescaping is disabled, script tags would
    be rendered as executable HTML.
    """
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    db.register_entity(
        "feature", "xss-test",
        '<script>alert("xss")</script>',
        status="active",
    )

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities")

    assert response.status_code == 200
    # Raw <script> should be escaped — not present as-is
    assert '<script>alert("xss")</script>' not in response.text
    # The escaped version should be present
    assert "&lt;script&gt;" in response.text or "alert" in response.text


# derived_from: dimension:adversarial (concurrent type+status+search filters)
def test_entity_list_all_three_filters_combined(integration_client):
    """Given all three filter parameters (type, status, search), when applied
    together, then all filters are AND-combined correctly.

    Anticipate: If filter order matters or filters are OR-combined, wrong
    entities could appear.
    """
    response = integration_client.get(
        "/entities?type=feature&status=active&q=Alpha"
    )

    assert response.status_code == 200
    assert "Alpha Feature" in response.text
    assert "Beta Feature" not in response.text  # completed, not active
    assert "Brainstorm One" not in response.text  # not feature


# ---------------------------------------------------------------------------
# Dimension 4: Error Propagation & Failure Modes
# ---------------------------------------------------------------------------

# derived_from: dimension:error_propagation (lineage query failure)
def test_entity_detail_lineage_error_shows_error_page(tmp_path):
    """Given a valid entity but get_lineage raises an exception, when viewing
    the detail page, then the error page is shown (not a partial crash).

    Anticipate: If lineage errors aren't caught by the outer try/except,
    the page could crash with 500 instead of showing error.html.
    """
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    db.register_entity("feature", "lin-err", "Lineage Error Test", status="active")

    from ui import create_app

    app = create_app(db_path=db_file)
    # Mock get_lineage to raise after get_entity succeeds
    app.state.db.get_lineage = unittest.mock.MagicMock(
        side_effect=Exception("lineage query failed")
    )
    client = TestClient(app)
    response = client.get("/entities/feature:lin-err")

    assert response.status_code == 200
    assert "An error occurred while querying the database" in response.text


# derived_from: dimension:error_propagation (workflow_phase query failure)
def test_entity_detail_workflow_error_shows_error_page(tmp_path):
    """Given a valid entity but get_workflow_phase raises an exception, when
    viewing the detail page, then the error page is shown.

    Anticipate: If workflow errors aren't caught, the page crashes with 500.
    """
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    db.register_entity("feature", "wf-err", "Workflow Error Test", status="active")

    from ui import create_app

    app = create_app(db_path=db_file)
    # get_lineage needs to work, but get_workflow_phase fails
    app.state.db.get_workflow_phase = unittest.mock.MagicMock(
        side_effect=Exception("workflow query failed")
    )
    client = TestClient(app)
    response = client.get("/entities/feature:wf-err")

    assert response.status_code == 200
    assert "An error occurred while querying the database" in response.text


# derived_from: dimension:error_propagation (list_workflow_phases failure in entity_list)
def test_entity_list_workflow_lookup_error_shows_error_page(tmp_path):
    """Given a valid DB but list_workflow_phases raises, when listing entities,
    then the error page is shown (not a crash).

    Anticipate: If the workflow lookup error is outside the try/except,
    the page crashes instead of showing error.html.
    """
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    db.register_entity("feature", "wl-err", "Workflow Lookup Error", status="active")

    from ui import create_app

    app = create_app(db_path=db_file)
    app.state.db.list_workflow_phases = unittest.mock.MagicMock(
        side_effect=Exception("workflow phases query failed")
    )
    client = TestClient(app)
    response = client.get("/entities")

    assert response.status_code == 200
    assert "An error occurred while querying the database" in response.text


# derived_from: dimension:error_propagation (entity_detail missing DB error)
def test_entity_detail_missing_db_includes_entity_db_path(tmp_path):
    """Given a nonexistent DB, when requesting entity detail,
    then the error page mentions ENTITY_DB_PATH for user guidance.

    Anticipate: If the error template lacks ENTITY_DB_PATH guidance,
    the user won't know how to fix the issue.
    """
    from ui import create_app

    app = create_app(db_path="/nonexistent/deep/path.db")
    client = TestClient(app)
    response = client.get("/entities/feature:test")

    assert response.status_code == 200
    assert "ENTITY_DB_PATH" in response.text


# ---------------------------------------------------------------------------
# Dimension 5: Mutation Mindset
# ---------------------------------------------------------------------------

# derived_from: dimension:mutation (verify type filter validation — invalid type treated as None)
def test_entity_list_type_validation_rejects_invalid(integration_client):
    """Mutation check: verify that the type validation normalizes invalid
    types to None (show all) rather than passing them to list_entities.

    If type validation is removed (line deletion), invalid types would be
    passed to list_entities which might return empty results.
    """
    # Invalid type should show all entities (same as no filter)
    response_invalid = integration_client.get("/entities?type=INVALID")
    response_all = integration_client.get("/entities")

    # Both should contain the same entities
    assert "4 entities" in response_invalid.text
    assert "4 entities" in response_all.text


# derived_from: dimension:mutation (verify status filter is exact match, not substring)
def test_entity_list_status_filter_exact_match(integration_client):
    """Mutation check: verify status filter uses exact equality (==) not
    substring match (in).

    If 'in' is used instead of '==', status='act' would match 'active'.
    """
    response = integration_client.get("/entities?status=act")

    assert response.status_code == 200
    # 'act' should not match 'active' — no entities should pass
    assert "No entities found" in response.text


# derived_from: dimension:mutation (kanban_column annotation correctness)
def test_entity_list_kanban_column_annotation(integration_client):
    """Mutation check: verify that kanban_column from workflow_phases is
    correctly annotated on entity rows.

    If the workflow lookup dict is keyed wrong or annotation is skipped,
    kanban_column would be blank for all entities.
    """
    response = integration_client.get("/entities")

    assert response.status_code == 200
    # feat-alpha has workflow phase with kanban_column='wip'
    assert "wip" in response.text


# derived_from: dimension:mutation (entity list table columns match spec)
def test_entity_list_table_has_required_columns():
    """Mutation check: verify _entities_content.html table has all required
    columns from spec FR-1: Name, Type ID, Type, Status, Kanban Column, Updated.

    If a column header is deleted, data would be misaligned or missing.
    """
    from pathlib import Path

    template_path = (
        Path(__file__).parent.parent / "templates" / "_entities_content.html"
    )
    content = template_path.read_text()

    required_columns = ["Name", "Type ID", "Type", "Status", "Kanban Column", "Updated"]
    for col in required_columns:
        assert col in content, f"Missing required column header: {col}"


# derived_from: dimension:mutation (404 page has back link to entity list)
def test_404_page_has_back_link_to_entity_list():
    """Mutation check: verify 404.html has a link back to /entities.

    If the back link is deleted, users are stuck on the 404 page.
    """
    from pathlib import Path

    template_path = Path(__file__).parent.parent / "templates" / "404.html"
    content = template_path.read_text()

    assert 'href="/entities"' in content
    assert "Entity not found" in content


# derived_from: dimension:mutation (entity detail back link exists)
def test_entity_detail_has_back_link_to_list():
    """Mutation check: verify entity_detail.html has a back link to /entities.

    If the back link is deleted, users can't navigate back to the list.
    """
    from pathlib import Path

    template_path = (
        Path(__file__).parent.parent / "templates" / "entity_detail.html"
    )
    content = template_path.read_text()

    assert 'href="/entities"' in content
    # Breadcrumbs replaced the old "Back to Entity List" button
    assert "Entities" in content


# derived_from: dimension:mutation (search limit=100 passed to search_entities)
def test_entity_list_search_passes_limit_100(tmp_path):
    """Mutation check: verify search_entities is called with limit=100 per spec.

    If limit is changed to a different value or removed, search results
    could be silently truncated at FTS default (e.g., 10).
    """
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    db.register_entity("feature", "lim", "Limit Test", status="active")

    from ui import create_app

    app = create_app(db_path=db_file)
    mock_search = unittest.mock.MagicMock(return_value=[])
    app.state.db.search_entities = mock_search
    client = TestClient(app)
    client.get("/entities?q=test")

    # Verify search_entities was called with limit=100
    mock_search.assert_called_once()
    call_kwargs = mock_search.call_args
    assert call_kwargs[1].get("limit") == 100 or (
        len(call_kwargs[0]) >= 3 and call_kwargs[0][2] == 100
    )


# derived_from: dimension:mutation (ENTITY_TYPES constant correctness)
def test_entity_types_constant_matches_spec():
    """Mutation check: verify ENTITY_TYPES matches the spec-defined entity
    types from the CHECK constraint.

    If a type is added or removed from the constant, filter tabs would
    be wrong.
    """
    from ui.routes.entities import ENTITY_TYPES

    expected = ["backlog", "brainstorm", "project", "feature"]
    assert ENTITY_TYPES == expected


# derived_from: dimension:mutation (lineage ancestors use direction="up", children use "down")
def test_entity_detail_lineage_directions(tmp_path):
    """Mutation check: verify get_lineage is called with correct directions
    (up for ancestors, down for children).

    If directions are swapped, ancestors would show children and vice versa.
    """
    db_file = str(tmp_path / "test.db")
    db = EntityDatabase(db_file)
    db.register_entity("feature", "dir-test", "Direction Test", status="active")

    from ui import create_app

    app = create_app(db_path=db_file)

    lineage_calls = []
    original_get_lineage = app.state.db.get_lineage

    def tracking_get_lineage(type_id, direction, max_depth):
        lineage_calls.append((type_id, direction, max_depth))
        return original_get_lineage(type_id, direction, max_depth)

    app.state.db.get_lineage = tracking_get_lineage
    client = TestClient(app)
    client.get("/entities/feature:dir-test")

    # Should call with "up" for ancestors and "down" for children
    assert len(lineage_calls) == 2
    directions = {c[1] for c in lineage_calls}
    assert directions == {"up", "down"}
    # Ancestors: direction="up", max_depth=10
    up_call = [c for c in lineage_calls if c[1] == "up"][0]
    assert up_call[2] == 10
    # Children: direction="down", max_depth=10
    down_call = [c for c in lineage_calls if c[1] == "down"][0]
    assert down_call[2] == 10


# ===========================================================================
# Feature 021: Lineage DAG Visualization — Integration Tests
# ===========================================================================

import uuid as uuid_mod


def _seed_entity_with_parent(db_file, type_id, name, entity_type,
                             parent_type_id=None):
    """Insert an entity with proper parent_uuid for get_lineage CTE traversal.

    Must be called in parent-first order so parent_uuid lookup resolves.
    """
    entity_uuid = str(uuid_mod.uuid4())
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = OFF")

    parent_uuid = None
    if parent_type_id:
        row = conn.execute(
            "SELECT uuid FROM entities WHERE type_id = ?",
            (parent_type_id,),
        ).fetchone()
        if row:
            parent_uuid = row[0]

    now = "2026-03-08T12:00:00Z"
    conn.execute(
        "INSERT OR IGNORE INTO entities "
        "(uuid, type_id, entity_type, entity_id, name, status, "
        "parent_type_id, parent_uuid, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entity_uuid, type_id, entity_type, type_id, name, "active",
         parent_type_id, parent_uuid, now, now),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Task 3.2: Mermaid DAG in entity detail route
# ---------------------------------------------------------------------------
def test_entity_detail_has_mermaid_dag(tmp_path):
    """Entity detail response contains 'flowchart TD'."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_entity_with_parent(db_file, "feature:dag-test", "DAG Test", "feature")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities/feature:dag-test")

    assert response.status_code == 200
    assert "flowchart TD" in response.text


def test_entity_detail_mermaid_dag_contains_entity_node(tmp_path):
    """Mermaid DAG contains the sanitized node ID for the entity."""
    from ui.mermaid import _sanitize_id

    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_entity_with_parent(db_file, "feature:node-test", "Node Test", "feature")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities/feature:node-test")

    expected_node_id = _sanitize_id("feature:node-test")
    assert response.status_code == 200
    assert expected_node_id in response.text


def test_entity_detail_children_depth_beyond_one(tmp_path):
    """Grandchild entity appears in response (depth > 1)."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    # Seed in parent-first order
    _seed_entity_with_parent(db_file, "project:gp", "Grandparent", "project")
    _seed_entity_with_parent(db_file, "feature:parent", "Parent", "feature",
                             parent_type_id="project:gp")
    _seed_entity_with_parent(db_file, "feature:child", "Child", "feature",
                             parent_type_id="feature:parent")
    _seed_entity_with_parent(db_file, "feature:grandchild", "Grandchild", "feature",
                             parent_type_id="feature:child")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    # View parent's detail page — should show grandchild (depth > 1)
    response = client.get("/entities/feature:parent")

    assert response.status_code == 200
    assert "feature:grandchild" in response.text


# ---------------------------------------------------------------------------
# Task 4.1: Template integration tests
# ---------------------------------------------------------------------------
def test_entity_detail_contains_mermaid_pre(tmp_path):
    """Entity detail page contains <pre class="mermaid">."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_entity_with_parent(db_file, "feature:pre-test", "Pre Test", "feature")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities/feature:pre-test")

    assert response.status_code == 200
    assert '<pre class="mermaid">' in response.text


def test_entity_detail_flat_list_in_details(tmp_path):
    """Response contains <details> wrapping lineage lists, no open attribute."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)
    _seed_entity_with_parent(db_file, "feature:details-test", "Details Test",
                             "feature")

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities/feature:details-test")

    assert response.status_code == 200
    assert "<details" in response.text
    # The details tag should NOT have open attribute (collapsed by default)
    # Find the details tag and check it doesn't have 'open'
    import re as re_mod
    details_tags = re_mod.findall(r"<details[^>]*>", response.text)
    assert len(details_tags) >= 1
    for tag in details_tags:
        assert "open" not in tag


def test_board_page_no_mermaid_script(tmp_path):
    """Board page (/) does not contain mermaid CDN reference."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "cdn.jsdelivr.net/npm/mermaid" not in response.text


def test_entity_list_no_mermaid_script(tmp_path):
    """Entity list page (/entities) does not contain mermaid CDN reference."""
    db_file = str(tmp_path / "test.db")
    EntityDatabase(db_file)

    from ui import create_app

    app = create_app(db_path=db_file)
    client = TestClient(app)
    response = client.get("/entities")

    assert response.status_code == 200
    assert "cdn.jsdelivr.net/npm/mermaid" not in response.text
