"""C8: the board card reads the kind from ``entities.kind``, never from
``type_id`` text.

The board's rows come from ``db.list_workflow_phases``, which LEFT JOINs
entities and already carries ``e.kind AS entity_type`` and
``e.name AS entity_name``. ``_card.html`` renders the kind badge (and the
feature-only mode badge and ``last:`` line) from that ``entity_type``. The
card title is ``entity_name``, or the whole ``type_id`` when there is no
name; the id is never split.

Fixtures whose kind column DISAGREES with their type_id text prove that the
source moved: the card must follow the column. Only raw SQL can build them
(the live registry holds none). An ORPHAN ``workflow_phases`` row (no entities
row) has no kind and no name. It renders with no kind badge, and its title
is its whole ``type_id``. Before C8 the text gave it a kind (feature, so
mode badge and ``last:`` line) and a title (the part after ``:``).

Normal rows keep the same badge and title as before C8.
"""
from __future__ import annotations

import re
import sqlite3
import uuid as _uuid

import pytest
from starlette.testclient import TestClient

from entity_registry.database import EntityDatabase, _derive_type_and_lifecycle, _UNKNOWN_WORKSPACE_UUID
from entity_registry.test_helpers import bootstrap_test_workspace
from ui.routes.helpers import COOKIE_NAME

_NOW = "2026-09-24T00:00:00Z"

_TITLE = re.compile(r'<div class="font-semibold text-sm truncate">\s*(.*?)\s*</div>', re.S)
_MODE_BADGE = re.compile(r'<span class="badge badge-xs badge-ghost">([^<\s]+)</span>')
_LAST_LINE = re.compile(r"last: (\S+)")
_KIND_BADGES = {
    "brainstorm": '<span class="badge badge-xs badge-info badge-outline">brainstorm</span>',
    "backlog": '<span class="badge badge-xs badge-ghost badge-outline">backlog</span>',
    "project": '<span class="badge badge-xs badge-secondary badge-outline">project</span>',
}


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
    return bootstrap_test_workspace(db, "c8-card-kind")


def _insert_entity_row(db_file, workspace_uuid, *, type_id, entity_id, kind, name) -> None:
    """Raw SQL: an entities row whose ``kind`` column is *kind*, whatever
    *type_id* spells."""
    entity_type, lifecycle_class = _derive_type_and_lifecycle(kind)
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, "
            "name, created_at, updated_at, type, kind, lifecycle_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(_uuid.uuid4()), workspace_uuid, type_id, entity_id, name,
             _NOW, _NOW, entity_type, kind, lifecycle_class),
        )
        conn.commit()
    finally:
        conn.close()


def _insert_workflow_row(db_file, workspace_uuid, type_id, *, kanban_column="wip",
                         workflow_phase=None, mode=None, last_completed_phase=None) -> None:
    """Raw SQL: a workflow_phases row. With no entities row behind it, it is
    an orphan; the explicit workspace_uuid lets it past the
    wp_reject_orphaned_insert trigger."""
    conn = sqlite3.connect(db_file)
    try:
        conn.execute(
            "INSERT INTO workflow_phases (type_id, kanban_column, workflow_phase, "
            "mode, last_completed_phase, updated_at, workspace_uuid) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (type_id, kanban_column, workflow_phase, mode, last_completed_phase,
             _NOW, workspace_uuid),
        )
        conn.commit()
    finally:
        conn.close()


def _board_html(db_file) -> str:
    from ui import create_app

    client = TestClient(create_app(db_path=db_file))
    client.cookies.set(COOKIE_NAME, "*")  # unscoped: every workspace
    response = client.get("/")
    assert response.status_code == 200
    return response.text


def _card(html: str, type_id: str) -> str:
    start = html.index(f'<a href="/entities/{type_id}"')
    return html[start:html.index("</a>", start)]


def _title(card: str) -> str:
    return _TITLE.search(card).group(1)


def _kind_markers(card: str) -> set[str]:
    """Every kind-driven element the card rendered."""
    markers = {f"{kind} badge" for kind, badge in _KIND_BADGES.items() if badge in card}
    markers |= {f"mode badge {mode}" for mode in _MODE_BADGE.findall(card)}
    markers |= {f"last line {phase}" for phase in _LAST_LINE.findall(card)}
    return markers


class TestCardKindFollowsKindColumn:

    def test_brainstorm_kind_under_a_feature_prefix_renders_as_brainstorm(
        self, db, db_file, workspace_uuid,
    ):
        type_id = "feature:095-stored-as-brainstorm"
        _insert_entity_row(
            db_file, workspace_uuid, type_id=type_id,
            entity_id="095-stored-as-brainstorm", kind="brainstorm",
            name="Stored as brainstorm",
        )
        _insert_workflow_row(
            db_file, workspace_uuid, type_id, workflow_phase="draft",
            mode="standard", last_completed_phase="draft",
        )

        card = _card(_board_html(db_file), type_id)

        assert _kind_markers(card) == {"brainstorm badge"}
        assert _title(card) == "Stored as brainstorm"

    def test_feature_kind_under_a_brainstorm_prefix_renders_as_feature(
        self, db, db_file, workspace_uuid,
    ):
        type_id = "brainstorm:20260924-000004-stored-as-feature"
        _insert_entity_row(
            db_file, workspace_uuid, type_id=type_id,
            entity_id="20260924-000004-stored-as-feature", kind="feature",
            name="Stored as feature",
        )
        _insert_workflow_row(
            db_file, workspace_uuid, type_id, workflow_phase="design",
            mode="full", last_completed_phase="specify",
        )

        card = _card(_board_html(db_file), type_id)

        assert _kind_markers(card) == {"mode badge full", "last line specify"}
        assert _title(card) == "Stored as feature"


class TestOrphanCard:

    def test_orphan_row_has_no_kind_badge_and_its_whole_type_id_as_title(
        self, db, db_file, workspace_uuid,
    ):
        type_id = "feature:096-orphan-card"
        _insert_workflow_row(
            db_file, workspace_uuid, type_id, kanban_column="backlog",
            mode="light", last_completed_phase="specify",
        )

        card = _card(_board_html(db_file), type_id)

        assert _kind_markers(card) == set()
        assert _title(card) == type_id


class TestNormalCardsUnchanged:

    def test_each_kind_renders_its_badge_and_entity_name(self, db, db_file):
        db.register_entity(
            entity_type="feature", seq=7, slug="plain-feature", name="Plain feature",
            status="active", workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.create_workflow_phase(
            "feature:007-plain-feature", workflow_phase="implement",
            kanban_column="wip", mode="standard", last_completed_phase="create-plan",
        )
        db.register_entity(
            entity_type="brainstorm", display_id="20260924-000005-plain-brainstorm",
            name="Plain brainstorm", status="draft", workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.create_workflow_phase(
            "brainstorm:20260924-000005-plain-brainstorm", workflow_phase="draft",
            kanban_column="wip",
        )
        db.register_entity(
            entity_type="backlog", seq=8, slug="plain-backlog", name="Plain backlog",
            status="open", workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.create_workflow_phase(
            "backlog:008-plain-backlog", workflow_phase="open", kanban_column="backlog",
        )
        db.register_entity(
            entity_type="project", seq=9, slug="plain-project", name="Plain project",
            status="active", workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.create_workflow_phase(
            "project:009-plain-project", workflow_phase="discover", kanban_column="backlog",
        )

        html = _board_html(db_file)

        expected = {
            "feature:007-plain-feature": (
                "Plain feature", {"mode badge standard", "last line create-plan"},
            ),
            "brainstorm:20260924-000005-plain-brainstorm": (
                "Plain brainstorm", {"brainstorm badge"},
            ),
            "backlog:008-plain-backlog": ("Plain backlog", {"backlog badge"}),
            "project:009-plain-project": ("Plain project", {"project badge"}),
        }
        rendered = {
            type_id: (_title(_card(html, type_id)), _kind_markers(_card(html, type_id)))
            for type_id in expected
        }
        assert rendered == expected
