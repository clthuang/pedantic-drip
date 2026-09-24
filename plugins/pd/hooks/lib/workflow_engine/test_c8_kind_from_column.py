"""C8: the kind comes from ``entities.kind``, never from ``type_id`` text.

Each fixture gives an entity a ``kind`` column that DISAGREES with the kind
its ``type_id`` text spells, for example ``feature:...`` stored as a backlog.
Only raw SQL can build such a row (the live registry holds none), and a
reader that still parses the text gets it wrong. Asserting unchanged output
for consistent rows would pass either way, so every test here asserts the
answer the ``kind`` column gives.

Sites covered:

- **``router.init_entity_workflow``**: the feature/project rejection and the
  lifecycle machine the phase is validated against. Because the kind no
  longer comes from the text, the check also runs when the argument is an
  entity uuid (no ``:``), which ``get_entity`` resolves.
- **``router.transition_entity_phase``**: the lifecycle-kind gate. Deliberate
  error-order change: the entity is fetched BEFORE the kind gate, so an
  id with no live entity row (unregistered, or soft-deleted) is
  ``entity_not_found`` whatever kind its text spells.
  Today's ``invalid_entity_type`` answer for such an id came from parsing
  the id. The malformed-id guard (no ``:``) still runs first, unchanged.
- **``reconciliation.check_workflow_drift``** (bulk path): which
  ``workflow_phases`` rows count as db_only feature candidates. An ORPHAN row
  (no entities row; ``list_workflow_phases`` keeps it for anomaly visibility)
  has no kind, so it stays a candidate whatever its text says. A
  feature-prefixed orphan keeps today's db_only status; an orphan with any
  other prefix is now reported as well.
"""
from __future__ import annotations

import os
import sqlite3
import uuid as _uuid

import pytest

from entity_registry.database import EntityDatabase, _derive_type_and_lifecycle, _UNKNOWN_WORKSPACE_UUID
from entity_registry.test_helpers import bootstrap_test_workspace
from workflow_engine.engine import WorkflowStateEngine
from workflow_engine.reconciliation import check_workflow_drift
from workflow_engine.router import init_entity_workflow, transition_entity_phase

_NOW = "2026-09-24T00:00:00Z"


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "entities.db")


@pytest.fixture
def db(db_path):
    database = EntityDatabase(db_path)
    yield database
    database.close()


@pytest.fixture
def workspace_uuid(db) -> str:
    return bootstrap_test_workspace(db, "c8-kind-from-column")


def _insert_entity_row(
    db_path: str,
    workspace_uuid: str,
    *,
    type_id: str,
    entity_id: str,
    kind: str,
    status: str | None = None,
) -> str:
    """Raw SQL: an entities row whose ``kind`` column is *kind*, whatever
    *type_id* spells. ``type``/``lifecycle_class`` follow *kind* so the
    table's CHECK accepts the row. Returns the row's uuid."""
    entity_type, lifecycle_class = _derive_type_and_lifecycle(kind)
    entity_uuid = str(_uuid.uuid4())
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, "
            "name, status, created_at, updated_at, type, kind, lifecycle_class) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_uuid, workspace_uuid, type_id, entity_id,
             f"Row stored as {kind}", status, _NOW, _NOW,
             entity_type, kind, lifecycle_class),
        )
        conn.commit()
    finally:
        conn.close()
    return entity_uuid


def _insert_orphan_workflow_row(db_path: str, workspace_uuid: str, type_id: str) -> None:
    """Raw SQL: a workflow_phases row with NO entities row. The explicit
    workspace_uuid is what lets it past the wp_reject_orphaned_insert trigger."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO workflow_phases (type_id, kanban_column, updated_at, "
            "workspace_uuid) VALUES (?, ?, ?, ?)",
            (type_id, "backlog", _NOW, workspace_uuid),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# router.init_entity_workflow
# ---------------------------------------------------------------------------


class TestInitEntityWorkflowReadsKindColumn:

    def test_feature_kind_under_a_brainstorm_prefix_is_rejected(
        self, db, db_path, workspace_uuid,
    ):
        type_id = "brainstorm:20260924-000001-stored-as-feature"
        _insert_entity_row(
            db_path, workspace_uuid, type_id=type_id,
            entity_id="20260924-000001-stored-as-feature", kind="feature",
        )

        with pytest.raises(ValueError) as excinfo:
            init_entity_workflow(
                db, type_id, "draft", "wip", workspace_uuid=workspace_uuid,
            )

        assert str(excinfo.value) == (
            "invalid_entity_type: feature entities use the feature workflow engine"
        )
        assert db.get_workflow_phase(type_id) is None

    def test_brainstorm_kind_under_a_feature_prefix_is_initialised(
        self, db, db_path, workspace_uuid,
    ):
        type_id = "feature:777-stored-as-brainstorm"
        _insert_entity_row(
            db_path, workspace_uuid, type_id=type_id,
            entity_id="777-stored-as-brainstorm", kind="brainstorm",
        )

        result = init_entity_workflow(
            db, type_id, "draft", "wip", workspace_uuid=workspace_uuid,
        )

        assert result == {
            "created": True, "type_id": type_id,
            "workflow_phase": "draft", "kanban_column": "wip",
        }
        assert db.get_workflow_phase(type_id)["workflow_phase"] == "draft"

    def test_phase_is_validated_against_the_kind_columns_machine(
        self, db, db_path, workspace_uuid,
    ):
        # "draft" is a brainstorm phase and not a backlog one; the text
        # spells backlog, the column says brainstorm.
        type_id = "backlog:00042-stored-as-brainstorm"
        _insert_entity_row(
            db_path, workspace_uuid, type_id=type_id,
            entity_id="00042-stored-as-brainstorm", kind="brainstorm",
        )

        result = init_entity_workflow(
            db, type_id, "draft", "wip", workspace_uuid=workspace_uuid,
        )

        assert result["created"] is True
        assert db.get_workflow_phase(type_id)["kanban_column"] == "wip"

    def test_entity_uuid_argument_is_kind_checked(self, db):
        # The kind check no longer depends on the argument containing ":".
        # get_entity resolves a uuid, so a feature's uuid is rejected by kind.
        # Before C8 the check was skipped and the call failed later, inside
        # upsert_workflow_phase, with an unstructured "not found" error.
        feature_uuid = db.register_entity(
            entity_type="feature", seq=1, slug="by-uuid", name="By uuid",
            status="active", workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )

        with pytest.raises(ValueError) as excinfo:
            init_entity_workflow(db, feature_uuid, "draft", "wip")

        assert str(excinfo.value).startswith("invalid_entity_type: feature ")


# ---------------------------------------------------------------------------
# router.transition_entity_phase
# ---------------------------------------------------------------------------


class TestTransitionEntityPhaseReadsKindColumn:

    def test_feature_kind_under_a_backlog_prefix_is_rejected(
        self, db, db_path, workspace_uuid,
    ):
        type_id = "backlog:00043-stored-as-feature"
        _insert_entity_row(
            db_path, workspace_uuid, type_id=type_id,
            entity_id="00043-stored-as-feature", kind="feature", status="open",
        )
        db.create_workflow_phase(type_id, workflow_phase="open", kanban_column="backlog")

        with pytest.raises(ValueError) as excinfo:
            transition_entity_phase(db, type_id, "triaged", workspace_uuid=workspace_uuid)

        assert str(excinfo.value) == (
            "invalid_entity_type: feature — only brainstorm and backlog supported"
        )
        row = db.get_workflow_phase(type_id)
        assert (row["workflow_phase"], row["kanban_column"]) == ("open", "backlog")

    def test_backlog_kind_under_a_feature_prefix_transitions(
        self, db, db_path, workspace_uuid,
    ):
        type_id = "feature:778-stored-as-backlog"
        _insert_entity_row(
            db_path, workspace_uuid, type_id=type_id,
            entity_id="778-stored-as-backlog", kind="backlog", status="open",
        )
        db.create_workflow_phase(type_id, workflow_phase="open", kanban_column="backlog")

        result = transition_entity_phase(
            db, type_id, "triaged", workspace_uuid=workspace_uuid,
        )

        assert result == {
            "transitioned": True, "type_id": type_id, "from_phase": "open",
            "to_phase": "triaged", "kanban_column": "prioritised",
        }
        assert db.get_entity(type_id)["status"] == "triaged"

    def test_unregistered_id_is_entity_not_found_whatever_its_prefix(self, db):
        # Deliberate change: before C8 the kind was parsed from the text
        # first, so this call raised "invalid_entity_type: feature ...".
        # With no entity there is no kind to read.
        with pytest.raises(ValueError) as excinfo:
            transition_entity_phase(db, "feature:001-never-registered", "reviewing")

        assert str(excinfo.value) == "entity_not_found: feature:001-never-registered"

    def test_soft_deleted_entity_is_entity_not_found_whatever_its_kind(self, db):
        # get_entity hides a soft-deleted row (#081), so there is no kind to
        # read. A soft-deleted brainstorm or backlog already answered
        # entity_not_found before C8; a soft-deleted feature answered
        # "invalid_entity_type: feature ...", parsed from its text.
        db.register_entity(
            entity_type="feature", seq=2, slug="soft-deleted", name="Soft-deleted",
            status="active", workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        type_id = "feature:002-soft-deleted"
        db.delete_entity(type_id)
        assert db.get_entity(type_id, include_deleted=True)["is_deleted"] == 1

        with pytest.raises(ValueError) as excinfo:
            transition_entity_phase(db, type_id, "reviewing")

        assert str(excinfo.value) == f"entity_not_found: {type_id}"

    def test_malformed_id_is_rejected_before_any_lookup(self, db):
        # Unchanged: the no-":" guard still runs first. So a registered
        # entity's uuid (which get_entity would resolve) is refused as
        # malformed instead of being used as a workflow_phases key.
        backlog_uuid = db.register_entity(
            entity_type="backlog", seq=1, slug="by-uuid", name="By uuid",
            status="open", workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )

        with pytest.raises(ValueError) as excinfo:
            transition_entity_phase(db, backlog_uuid, "triaged")

        assert str(excinfo.value) == (
            f"invalid_entity_type: malformed type_id: {backlog_uuid}"
        )


# ---------------------------------------------------------------------------
# reconciliation.check_workflow_drift: db_only candidates (bulk path)
# ---------------------------------------------------------------------------


def _db_only_ids(db: EntityDatabase, artifacts_root: str) -> set[str]:
    engine = WorkflowStateEngine(db, artifacts_root)
    result = check_workflow_drift(engine, db, artifacts_root)
    return {r.feature_type_id for r in result.features if r.status == "db_only"}


class TestDriftDbOnlyReadsKindColumn:

    def test_feature_prefixed_row_of_another_kind_is_not_db_only(
        self, db, db_path, workspace_uuid, tmp_path,
    ):
        type_id = "feature:090-stored-as-backlog"
        _insert_entity_row(
            db_path, workspace_uuid, type_id=type_id,
            entity_id="090-stored-as-backlog", kind="backlog", status="open",
        )
        db.create_workflow_phase(type_id, workflow_phase="open", kanban_column="backlog")

        assert type_id not in _db_only_ids(db, str(tmp_path))

    def test_feature_kind_row_under_another_prefix_is_db_only(
        self, db, db_path, workspace_uuid, tmp_path,
    ):
        type_id = "backlog:00091-stored-as-feature"
        _insert_entity_row(
            db_path, workspace_uuid, type_id=type_id,
            entity_id="00091-stored-as-feature", kind="feature", status="active",
        )
        db.create_workflow_phase(type_id, workflow_phase="design", kanban_column="prioritised")

        assert _db_only_ids(db, str(tmp_path)) == {type_id}

    def test_orphan_rows_are_db_only_whatever_their_type_id_says(
        self, db, db_path, workspace_uuid, tmp_path,
    ):
        # An orphan has no entities row, so it has no kind. It stays a
        # db_only candidate for anomaly visibility, the same as before C8
        # for a feature-prefixed orphan. The brainstorm-prefixed orphan was
        # skipped before C8, because only the text was read; now it is
        # reported too.
        feature_shaped = "feature:092-orphan"
        brainstorm_shaped = "brainstorm:20260924-000002-orphan"
        _insert_orphan_workflow_row(db_path, workspace_uuid, feature_shaped)
        _insert_orphan_workflow_row(db_path, workspace_uuid, brainstorm_shaped)
        # A live brainstorm with a workflow_phases row is still excluded:
        # its kind column says it is not a feature.
        db.register_entity(
            entity_type="brainstorm", display_id="20260924-000003-live",
            name="Live brainstorm", status="draft", workspace_uuid=_UNKNOWN_WORKSPACE_UUID,
        )
        db.create_workflow_phase(
            "brainstorm:20260924-000003-live", workflow_phase="draft",
            kanban_column="wip",
        )

        assert _db_only_ids(db, str(tmp_path)) == {feature_shaped, brainstorm_shaped}

    def test_orphan_row_is_not_given_a_kind_by_the_join(self, db, db_path, workspace_uuid):
        # Guards the premise the orphan decision rests on: list_workflow_phases
        # LEFT JOINs entities, so an orphan row carries entity_type None,
        # not a kind taken from its text.
        _insert_orphan_workflow_row(db_path, workspace_uuid, "feature:093-orphan")

        rows = {r["type_id"]: r for r in db.list_workflow_phases()}

        assert rows["feature:093-orphan"]["entity_type"] is None
