"""board-archived: the kanban board hides archived entities.

User decision 2026-09-25. The board (``GET /`` and its HTMX partial) renders
the rows ``list_workflow_phases`` returns. Before this change that query
LEFT JOINed entities with no archive filter, so the board showed archived
entities too, including, since C22, each archived backlog original beside
the entity that replaced it.

The board now asks for ``include_archived=False``. In the fixtures below the
live and the archived entity of a pair share kind, status, column and phase,
so the ``is_archived`` flag is what decides which card is shown.

What stays on the board:

- **live entities**: unchanged.
- **orphan rows** (a workflow_phases row with no entities row): unchanged,
  with no kind badge and the whole type_id as the title.
- **soft-deleted entities** (``is_deleted = 1``, not archived): unchanged.
  The decision covers archiving only; an entity that is both archived and
  soft-deleted is archived, so it is hidden.

The column count badges and the empty state are computed from the rows the
route passes to the template, so they count only the cards shown.
"""
from __future__ import annotations

import re
import sqlite3

import pytest
from starlette.testclient import TestClient

from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import bootstrap_test_workspace
from ui.routes.helpers import COOKIE_NAME

_NOW = "2026-09-25T00:00:00Z"

_COLUMN_HEADER = re.compile(
    r'<h2 class="text-sm font-semibold uppercase tracking-wide">([^<]+)</h2>\s*'
    r'<span class="badge badge-sm badge-ghost">(\d+)</span>'
)
_CARD_LINK = re.compile(r'<a href="/entities/([^"]+)"')
_TITLE = re.compile(r'<div class="font-semibold text-sm truncate">\s*(.*?)\s*</div>', re.S)
_KIND_DRIVEN = (
    re.compile(r'<span class="badge badge-xs badge-(?:info|ghost|secondary) badge-outline">'),
    # the feature mode badge; the orphan fixture has no workflow_phase, so no
    # phase badge (same markup when phase_colors has no entry) can match it
    re.compile(r'<span class="badge badge-xs badge-ghost">'),
    re.compile(r"last: "),  # feature-only last-phase line
)
_EMPTY_STATE = "No features yet"


@pytest.fixture
def db_file(tmp_path) -> str:
    return str(tmp_path / "entities.db")


@pytest.fixture
def db(db_file):
    database = EntityDatabase(db_file)
    yield database
    database.close()


@pytest.fixture
def workspace_uuid(db) -> str:
    return bootstrap_test_workspace(db, "board-archived")


def _add(db, workspace_uuid, kind, seq, slug, *, status, column, phase,
         archived=False, deleted=False) -> str:
    """Register an entity with a workflow row in *column*; return its type_id."""
    entity_uuid = db.register_entity(
        kind, name=slug.replace("-", " ").capitalize(), seq=seq, slug=slug,
        status=status, workspace_uuid=workspace_uuid,
    )
    type_id = db.get_entity_by_uuid(entity_uuid)["type_id"]
    db.create_workflow_phase(type_id, kanban_column=column, workflow_phase=phase)
    if archived:
        db.set_archived(type_id, workspace_uuid=workspace_uuid)
    if deleted:
        db.set_deleted(type_id, workspace_uuid=workspace_uuid)
    return type_id


def _add_orphan_row(db_file, workspace_uuid, type_id, *, column) -> None:
    """Raw SQL: a workflow_phases row with no entities row behind it. The
    explicit workspace_uuid lets it past the wp_reject_orphaned_insert
    trigger. The feature-only fields are set so that a kind wrongly given to
    the orphan would show up as a mode badge or a ``last:`` line."""
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "INSERT INTO workflow_phases (type_id, kanban_column, workflow_phase, "
            "mode, last_completed_phase, updated_at, workspace_uuid) "
            "VALUES (?, ?, NULL, 'light', 'specify', ?, ?)",
            (type_id, column, _NOW, workspace_uuid),
        )
        conn.commit()
    finally:
        conn.close()


def _page_html(db_file, path="/", *, scope="*", htmx=False) -> str:
    """GET *path* (the board by default) as the browser does. *scope* is the
    workspace cookie: ``"*"`` for all workspaces, or one workspace uuid."""
    from ui import create_app

    client = TestClient(create_app(db_path=db_file))
    client.cookies.set(COOKIE_NAME, scope)
    response = client.get(path, headers={"HX-Request": "true"} if htmx else {})
    assert response.status_code == 200
    return response.text


def _columns(html: str) -> dict[str, tuple[int, list[str]]]:
    """``{column: (count badge, sorted type_ids of its cards)}`` for every
    rendered column. Empty when the board renders its empty state."""
    headers = list(_COLUMN_HEADER.finditer(html))
    columns = {}
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(html)
        cards = _CARD_LINK.findall(html, header.end(), end)
        columns[header.group(1)] = (int(header.group(2)), sorted(cards))
    return columns


def _card(html: str, type_id: str) -> str:
    start = html.index(f'<a href="/entities/{type_id}"')
    return html[start:html.index("</a>", start)]


def _live_and_archived_pairs(db, workspace_uuid) -> dict[str, str]:
    """One live and one archived entity per kind, each pair sharing a column."""
    return {
        "live feature": _add(db, workspace_uuid, "feature", 1, "live-feature",
                             status="active", column="wip", phase="implement"),
        "archived feature": _add(db, workspace_uuid, "feature", 2, "archived-feature",
                                 status="active", column="wip", phase="implement",
                                 archived=True),
        "live backlog": _add(db, workspace_uuid, "backlog", 3, "live-backlog",
                             status="open", column="backlog", phase="open"),
        "archived backlog": _add(db, workspace_uuid, "backlog", 4, "archived-backlog",
                                 status="open", column="backlog", phase="open",
                                 archived=True),
    }


def _expected_live_only(ids: dict[str, str]) -> dict[str, tuple[int, list[str]]]:
    return {
        "backlog": (1, [ids["live backlog"]]),
        "prioritised": (0, []),
        "ready": (0, []),
        "wip": (1, [ids["live feature"]]),
        "blocked": (0, []),
        "documenting": (0, []),
        "completed": (0, []),
    }


class TestArchivedCardsAreHidden:

    def test_each_column_shows_the_live_card_and_not_the_archived_one(
        self, db, db_file, workspace_uuid,
    ):
        ids = _live_and_archived_pairs(db, workspace_uuid)

        html = _page_html(db_file)

        assert {column: cards for column, (_, cards) in _columns(html).items()} == {
            column: cards for column, (_, cards) in _expected_live_only(ids).items()
        }
        assert f'/entities/{ids["archived feature"]}"' not in html
        assert f'/entities/{ids["archived backlog"]}"' not in html

    def test_column_counts_exclude_the_archived_entity(
        self, db, db_file, workspace_uuid,
    ):
        ids = _live_and_archived_pairs(db, workspace_uuid)

        columns = _columns(_page_html(db_file))

        assert {column: count for column, (count, _) in columns.items()} == {
            column: count for column, (count, _) in _expected_live_only(ids).items()
        }

    def test_the_htmx_refresh_partial_hides_them_too(
        self, db, db_file, workspace_uuid,
    ):
        ids = _live_and_archived_pairs(db, workspace_uuid)

        html = _page_html(db_file, htmx=True)

        assert "<html" not in html  # the partial, not the full page
        assert _columns(html) == _expected_live_only(ids)

    def test_a_board_scoped_to_the_workspace_hides_them_too(
        self, db, db_file, workspace_uuid,
    ):
        ids = _live_and_archived_pairs(db, workspace_uuid)

        html = _page_html(db_file, scope=workspace_uuid)

        assert _columns(html) == _expected_live_only(ids)

    def test_a_board_holding_only_archived_entities_shows_the_empty_state(
        self, db, db_file, workspace_uuid,
    ):
        _add(db, workspace_uuid, "feature", 1, "only-archived-feature",
             status="active", column="wip", phase="implement", archived=True)
        _add(db, workspace_uuid, "backlog", 2, "only-archived-backlog",
             status="open", column="backlog", phase="open", archived=True)

        html = _page_html(db_file)

        assert _EMPTY_STATE in html
        assert _columns(html) == {}


class TestOrphanRowIsUnchanged:

    def test_orphan_row_renders_as_at_the_base(self, db, db_file, workspace_uuid):
        """An orphan has no entities row, so it has no ``is_archived`` flag to
        test. The board keeps it, as before: counted in its column, with no
        kind badge, no feature-only lines, and its whole type_id as the
        title. The last assertion shows the same render hid an archived
        card, so the orphan went through the filter rather than around it."""
        live = _add(db, workspace_uuid, "backlog", 3, "live-backlog",
                    status="open", column="backlog", phase="open")
        archived = _add(db, workspace_uuid, "backlog", 4, "archived-backlog",
                        status="open", column="backlog", phase="open", archived=True)
        orphan = "feature:097-orphan-beside-archived"
        _add_orphan_row(db_file, workspace_uuid, orphan, column="backlog")

        html = _page_html(db_file)

        count, cards = _columns(html)["backlog"]
        assert orphan in cards and live in cards
        assert count == len(cards)
        card = _card(html, orphan)
        assert _TITLE.search(card).group(1) == orphan
        assert [pattern.pattern for pattern in _KIND_DRIVEN if pattern.search(card)] == []
        assert archived not in cards


class TestSoftDeletedEntities:

    def test_a_soft_deleted_entity_keeps_its_card_while_the_archived_one_goes(
        self, db, db_file, workspace_uuid,
    ):
        deleted = _add(db, workspace_uuid, "feature", 5, "soft-deleted-feature",
                       status="active", column="wip", phase="implement", deleted=True)
        _add(db, workspace_uuid, "feature", 6, "archived-feature",
             status="active", column="wip", phase="implement", archived=True)

        html = _page_html(db_file)

        assert _columns(html)["wip"] == (1, [deleted])
        assert _TITLE.search(_card(html, deleted)).group(1) == "Soft deleted feature"

    def test_an_entity_both_archived_and_soft_deleted_is_hidden(
        self, db, db_file, workspace_uuid,
    ):
        live = _add(db, workspace_uuid, "feature", 7, "live-feature",
                    status="active", column="wip", phase="implement")
        _add(db, workspace_uuid, "feature", 8, "archived-and-deleted-feature",
             status="active", column="wip", phase="implement",
             archived=True, deleted=True)

        assert _columns(_page_html(db_file))["wip"] == (1, [live])


class TestEntitiesPagesAreUnchanged:

    def test_the_entities_pages_still_show_the_archived_entity_and_its_workflow(
        self, db, db_file, workspace_uuid,
    ):
        """Scope is the board only. ``/entities`` labels each row with its
        column from list_workflow_phases, and the detail page shows the
        entity's workflow row; both still do so for an archived entity. The
        last assertion shows the board hides that same entity."""
        archived = _live_and_archived_pairs(db, workspace_uuid)["archived feature"]

        listing = _page_html(db_file, "/entities")
        detail = _page_html(db_file, f"/entities/{archived}")

        row_start = listing.index(f'<a href="/entities/{archived}" class="link link-primary">')
        assert "<td>wip</td>" in listing[row_start:listing.index("</tr>", row_start)]
        assert "Workflow State" in detail and ">implement</span>" in detail
        assert f'/entities/{archived}"' not in _page_html(db_file)
