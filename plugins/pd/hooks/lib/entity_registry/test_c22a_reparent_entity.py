"""C22a: ``EntityDatabase.reparent_entity`` moves a child onto a new parent by uuid.

Completion plan decision 3 (docs/plans/2026-09-22-structural-identity-completion-plan.md):

- **The new parent is named by uuid only** — no type_id lookup, no text.
- **The write emits an ``events`` row** like the other event-emitting
  mutations (``delete_entity``'s ``entity_deleted``, ``rename_entity``'s
  ``renamed``).
- **The self-reference triggers still apply.**

C22 calls it to move the children of legacy projects onto their recreations.
Every refusal test asserts the registry is untouched: the child's parent
link and ``updated_at``, the events ledger, and SQLite's change counter.
"""
from __future__ import annotations

import sqlite3
import uuid as uuid_module

import pytest

from entity_registry import schema_v2
from entity_registry.database import EntityDatabase
# Imported at module (collection) time, not inside the v2_db fixture: this is
# load-bearing. See test_database.py's identically-documented import — it
# registers "events"/"views"/"axes" into schema_v2.DDL_REGISTRY before the
# snapshot fixture below first runs, so the restore never wipes them out.
from entity_registry import rebuild_tool
from entity_registry.test_helpers import bootstrap_test_workspace, seed_legacy_entity

REPARENT_ACTOR = "live:reparent_entity"


@pytest.fixture(autouse=True)
def _reset_ddl_registry_for_v2_fixtures():
    """Snapshot/restore ``schema_v2.DDL_REGISTRY`` around every test — see
    test_database.py's identically-named fixture. ``build_staging_database``
    registers the axis vocabulary triggers as production behaviour."""
    original_registry = list(schema_v2.DDL_REGISTRY)
    yield
    schema_v2.DDL_REGISTRY[:] = original_registry


@pytest.fixture
def v2_db(tmp_path):
    """A v2-generation EntityDatabase — the generation the live registry is."""
    staging_path = str(tmp_path / "entities.db.v2-test")
    rebuild_tool.build_staging_database(staging_path)
    database = EntityDatabase(staging_path)
    yield database
    database.close()


@pytest.fixture
def v1_db(tmp_path):
    """A v1-generation EntityDatabase: no ``events`` table exists at all."""
    database = EntityDatabase(str(tmp_path / "entities.db"))
    yield database
    database.close()


def _project(db, workspace_uuid: str, seq: int, slug: str) -> str:
    return db.register_entity(
        "project", name=f"Project {slug}", seq=seq, slug=slug,
        status="active", workspace_uuid=workspace_uuid,
    )


def _feature(db, workspace_uuid: str, seq: int, slug: str, parent_uuid: str | None = None) -> str:
    return db.register_entity(
        "feature", name=f"Feature {slug}", seq=seq, slug=slug,
        status="completed", parent_uuid=parent_uuid, workspace_uuid=workspace_uuid,
    )


def _parent_of(db, entity_uuid: str) -> str | None:
    return db._conn.execute(
        "SELECT parent_uuid FROM entities WHERE uuid = ?", (entity_uuid,)
    ).fetchone()[0]


def _child_count(db, parent_uuid: str) -> int:
    return db._conn.execute(
        "SELECT COUNT(*) FROM entities WHERE parent_uuid = ?", (parent_uuid,)
    ).fetchone()[0]


def _reparented_events(db, entity_uuid: str) -> list[tuple]:
    rows = db._conn.execute(
        "SELECT event_type, axis, from_value, to_value, actor, payload "
        "FROM events WHERE entity_uuid = ? AND event_type = 'reparented' "
        "ORDER BY uuid",
        (entity_uuid,),
    ).fetchall()
    return [tuple(row) for row in rows]


def _registry_fingerprint(db, child_uuid: str) -> dict:
    """Everything a refused re-parent must leave exactly as it was."""
    parent_uuid, updated_at = db._conn.execute(
        "SELECT parent_uuid, updated_at FROM entities WHERE uuid = ?", (child_uuid,)
    ).fetchone()
    return {
        "parent_uuid": parent_uuid,
        "updated_at": updated_at,
        "event_count": db._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "total_changes": db._conn.total_changes,
    }


class TestReparentMovesTheLink:
    def test_children_of_an_archived_legacy_project_move_onto_its_recreation(self, v2_db):
        """The C22 shape: legacy parent (uuid4, is_legacy, archived) -> new project."""
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        legacy_project = seed_legacy_entity(
            v2_db, "project", "P004-entity-db-redesign", "entity db redesign",
            workspace_uuid=workspace, status="active",
        )
        v2_db.set_archived("project:P004-entity-db-redesign", workspace_uuid=workspace)
        recreated_project = _project(v2_db, workspace, 4, "entity-db-redesign")
        first_child = _feature(v2_db, workspace, 1, "first", parent_uuid=legacy_project)
        second_child = _feature(v2_db, workspace, 2, "second", parent_uuid=legacy_project)
        assert (_child_count(v2_db, legacy_project), _child_count(v2_db, recreated_project)) == (2, 0)

        returned = v2_db.reparent_entity(first_child, recreated_project)

        assert returned == first_child
        assert _parent_of(v2_db, first_child) == recreated_project
        assert (_child_count(v2_db, legacy_project), _child_count(v2_db, recreated_project)) == (1, 1)
        assert _parent_of(v2_db, second_child) == legacy_project

        v2_db.reparent_entity(second_child, recreated_project)

        assert (_child_count(v2_db, legacy_project), _child_count(v2_db, recreated_project)) == (0, 2)

    def test_child_named_by_type_id_resolves_within_the_given_workspace(self, v2_db):
        home = bootstrap_test_workspace(v2_db, "c22a-home")
        elsewhere = bootstrap_test_workspace(v2_db, "c22a-elsewhere")
        new_parent = _project(v2_db, home, 1, "new-home")
        home_child = _feature(v2_db, home, 1, "same-name")
        elsewhere_child = _feature(v2_db, elsewhere, 1, "same-name")
        child_type_id = v2_db._conn.execute(
            "SELECT type_id FROM entities WHERE uuid = ?", (home_child,)
        ).fetchone()[0]
        before = _registry_fingerprint(v2_db, home_child)

        # Unscoped, the type_id exists in two workspaces: refused, not guessed.
        with pytest.raises(ValueError, match="Ambiguous"):
            v2_db.reparent_entity(child_type_id, new_parent)
        assert _registry_fingerprint(v2_db, home_child) == before

        returned = v2_db.reparent_entity(child_type_id, new_parent, workspace_uuid=home)

        assert returned == home_child
        assert _parent_of(v2_db, home_child) == new_parent
        assert _parent_of(v2_db, elsewhere_child) is None

    def test_a_legacy_cross_workspace_link_can_be_moved_home(self, v2_db):
        """The workspace check compares the child with its NEW parent, so a
        child can leave a cross-workspace parent for one in its own workspace."""
        home = bootstrap_test_workspace(v2_db, "c22a-home")
        elsewhere = bootstrap_test_workspace(v2_db, "c22a-elsewhere")
        foreign_parent = _project(v2_db, elsewhere, 1, "foreign-parent")
        home_parent = _project(v2_db, home, 1, "home-parent")
        child = _feature(v2_db, home, 1, "child", parent_uuid=foreign_parent)

        v2_db.reparent_entity(child, home_parent)

        assert _parent_of(v2_db, child) == home_parent
        assert _reparented_events(v2_db, child) == [
            ("reparented", "lifecycle", foreign_parent, home_parent, REPARENT_ACTOR, None),
        ]

    def test_works_on_a_v1_generation_file_with_no_events_table(self, v1_db):
        assert v1_db._is_v2_generation is False
        assert v1_db._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'events'"
        ).fetchone() is None
        workspace = bootstrap_test_workspace(v1_db, "c22a-home")
        old_parent = _project(v1_db, workspace, 1, "old")
        new_parent = _project(v1_db, workspace, 2, "new")
        child = _feature(v1_db, workspace, 1, "child", parent_uuid=old_parent)

        v1_db.reparent_entity(child, new_parent)

        assert _parent_of(v1_db, child) == new_parent


class TestReparentEmitsAnEvent:
    def test_one_reparented_lifecycle_event_records_old_and_new_parent_uuid(self, v2_db):
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        old_parent = _project(v2_db, workspace, 1, "old")
        new_parent = _project(v2_db, workspace, 2, "new")
        child = _feature(v2_db, workspace, 1, "child", parent_uuid=old_parent)
        child_events_before = v2_db._conn.execute(
            "SELECT COUNT(*) FROM events WHERE entity_uuid = ?", (child,)
        ).fetchone()[0]

        v2_db.reparent_entity(child, new_parent)

        assert _reparented_events(v2_db, child) == [
            ("reparented", "lifecycle", old_parent, new_parent, REPARENT_ACTOR, None),
        ]
        assert v2_db._conn.execute(
            "SELECT COUNT(*) FROM events WHERE entity_uuid = ?", (child,)
        ).fetchone()[0] == child_events_before + 1

    def test_first_parent_is_recorded_with_a_null_from_value(self, v2_db):
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        new_parent = _project(v2_db, workspace, 1, "new")
        orphan = _feature(v2_db, workspace, 1, "orphan")

        v2_db.reparent_entity(orphan, new_parent)

        assert _parent_of(v2_db, orphan) == new_parent
        assert _reparented_events(v2_db, orphan) == [
            ("reparented", "lifecycle", None, new_parent, REPARENT_ACTOR, None),
        ]

    def test_moving_onto_the_current_parent_writes_nothing(self, v2_db):
        """Idempotent: a re-run after a partial C22 must not mint a second
        immutable event for a move that already happened."""
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        parent = _project(v2_db, workspace, 1, "parent")
        child = _feature(v2_db, workspace, 1, "child", parent_uuid=parent)
        before = _registry_fingerprint(v2_db, child)

        returned = v2_db.reparent_entity(child, parent)

        assert returned == child
        assert _registry_fingerprint(v2_db, child) == before
        assert _reparented_events(v2_db, child) == []


class TestReparentRefusesAndWritesNothing:
    def test_a_type_id_parent_is_refused_not_resolved(self, v2_db):
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        legacy_project = seed_legacy_entity(
            v2_db, "project", "P002", "memory flywheel", workspace_uuid=workspace,
        )
        child = _feature(v2_db, workspace, 1, "child")
        # Non-vacuity: this text DOES name an existing entity through the
        # type_id resolver, so only a uuid-only parent lookup can refuse it.
        assert v2_db._resolve_identifier("project:P002")[0] == legacy_project
        before = _registry_fingerprint(v2_db, child)

        with pytest.raises(ValueError, match="not the uuid of an existing entity"):
            v2_db.reparent_entity(child, "project:P002")

        assert _registry_fingerprint(v2_db, child) == before

    def test_an_unknown_uuid_parent_is_refused(self, v2_db):
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        child = _feature(v2_db, workspace, 1, "child")
        before = _registry_fingerprint(v2_db, child)

        with pytest.raises(ValueError, match="not the uuid of an existing entity"):
            v2_db.reparent_entity(child, str(uuid_module.uuid4()))

        assert _registry_fingerprint(v2_db, child) == before

    def test_self_parent_is_refused(self, v2_db):
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        child = _feature(v2_db, workspace, 1, "child")
        before = _registry_fingerprint(v2_db, child)

        with pytest.raises(ValueError, match="own parent"):
            v2_db.reparent_entity(child, child)

        assert _registry_fingerprint(v2_db, child) == before

    def test_a_cycle_is_refused(self, v2_db):
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        top = _project(v2_db, workspace, 1, "top")
        middle = _feature(v2_db, workspace, 1, "middle", parent_uuid=top)
        bottom = _feature(v2_db, workspace, 2, "bottom", parent_uuid=middle)
        before = _registry_fingerprint(v2_db, top)

        with pytest.raises(ValueError, match="[Cc]ircular"):
            v2_db.reparent_entity(top, bottom)

        assert _registry_fingerprint(v2_db, top) == before

    def test_a_parent_in_another_workspace_is_refused(self, v2_db):
        home = bootstrap_test_workspace(v2_db, "c22a-home")
        elsewhere = bootstrap_test_workspace(v2_db, "c22a-elsewhere")
        home_parent = _project(v2_db, home, 1, "home-parent")
        foreign_parent = _project(v2_db, elsewhere, 1, "foreign-parent")
        child = _feature(v2_db, home, 1, "child", parent_uuid=home_parent)
        before = _registry_fingerprint(v2_db, child)

        with pytest.raises(ValueError, match="cross-workspace"):
            v2_db.reparent_entity(child, foreign_parent)

        assert _registry_fingerprint(v2_db, child) == before
        assert _child_count(v2_db, foreign_parent) == 0

    def test_a_soft_deleted_parent_is_refused(self, v2_db):
        """delete_entity refuses to delete a row with children; moving a child
        under an already-deleted row would break that invariant from the other
        side."""
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        deleted_parent = _project(v2_db, workspace, 1, "gone")
        v2_db.delete_entity(deleted_parent)
        child = _feature(v2_db, workspace, 1, "child")
        before = _registry_fingerprint(v2_db, child)

        with pytest.raises(ValueError, match="soft-deleted"):
            v2_db.reparent_entity(child, deleted_parent)

        assert _registry_fingerprint(v2_db, child) == before

    def test_a_soft_deleted_child_is_refused(self, v2_db):
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        new_parent = _project(v2_db, workspace, 1, "new")
        deleted_child = _feature(v2_db, workspace, 1, "gone")
        v2_db.delete_entity(deleted_child)
        before = _registry_fingerprint(v2_db, deleted_child)

        with pytest.raises(ValueError, match="soft-deleted"):
            v2_db.reparent_entity(deleted_child, new_parent)

        assert _registry_fingerprint(v2_db, deleted_child) == before


class TestSelfParentTriggerStillApplies:
    def test_the_uuid_trigger_exists_and_rejects_a_raw_self_parent_update(self, v2_db):
        """Defence in depth under the API's own check: the schema still refuses
        ``parent_uuid = uuid`` for a writer that bypasses every method."""
        workspace = bootstrap_test_workspace(v2_db, "c22a-home")
        child = _feature(v2_db, workspace, 1, "child")
        assert v2_db._conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'trigger' AND name = 'enforce_no_self_parent_uuid_update'"
        ).fetchone() is not None

        with pytest.raises(sqlite3.IntegrityError, match="own parent"):
            v2_db._conn.execute(
                "UPDATE entities SET parent_uuid = uuid WHERE uuid = ?", (child,)
            )
        v2_db._conn.rollback()

        assert _parent_of(v2_db, child) is None
