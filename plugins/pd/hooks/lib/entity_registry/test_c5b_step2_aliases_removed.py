"""C5b step 2: the registration aliases and the allocator's project_id are gone.

Removed parameters:

* ``project_id`` (was an alias for ``workspace_uuid``) and ``parent_type_id``
  (was an alias for ``parent_uuid``) from ``register_entity`` and
  ``upsert_entity``.
* ``project_id`` from ``register_entities_batch``.
* ``project_id`` from the allocator: ``generate_entity_id`` (keyword or 4th
  positional) and ``next_sequence_value`` (keyword or 1st positional).

Each test passes a removed parameter to an otherwise valid call and pins three
facts:

* **It is refused with TypeError** that names the parameter or the extra
  positional.
* **Nothing is written**: no entity row, display row, phase event or counter
  change.
* **The same call without the removed parameter succeeds.** This proves the
  refusal came from that parameter alone.

The ``entity_created`` label now always comes from the workspace, never from
the caller. The last test pins that for all three kinds of workspace.
"""
from __future__ import annotations

import pytest

from entity_registry.database import _UNKNOWN_WORKSPACE_UUID, EntityDatabase
from entity_registry.id_generator import generate_entity_id
from entity_registry.test_helpers import bootstrap_test_workspace

LEGACY_ID = "c5b-step2-ws"
UNKNOWN_LABEL = "__unknown__"
PARENT_TYPE_ID = "project:001-parent"


@pytest.fixture
def db():
    database = EntityDatabase(":memory:")
    yield database
    database.close()


@pytest.fixture
def workspace_uuid(db):
    """A workspace that a legacy id also names, so a ``project_id`` value
    would have resolved to the same workspace before this step."""
    return bootstrap_test_workspace(db, LEGACY_ID)


@pytest.fixture
def parent_uuid(db, workspace_uuid):
    """A parent that ``PARENT_TYPE_ID`` would have resolved to."""
    return db.register_entity("project", name="Parent", seq=1, slug="parent",
                              workspace_uuid=workspace_uuid)


def _registry_state(db: EntityDatabase) -> tuple:
    """Everything registration or allocation could write."""
    def count(table: str) -> int:
        return db._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    counters = db._conn.execute(
        "SELECT workspace_uuid, entity_type, next_val FROM sequences "
        "ORDER BY workspace_uuid, entity_type"
    ).fetchall()
    return (count("entities"), count("entity_display"), count("phase_events"),
            [tuple(row) for row in counters])


def _counter(db: EntityDatabase, workspace_uuid: str, kind: str) -> int | None:
    row = db._conn.execute(
        "SELECT next_val FROM sequences WHERE workspace_uuid = ? AND entity_type = ?",
        (workspace_uuid, kind),
    ).fetchone()
    return None if row is None else row[0]


def _created_label(db: EntityDatabase, type_id: str) -> str:
    rows = db._conn.execute(
        "SELECT project_id FROM phase_events "
        "WHERE type_id = ? AND event_type = 'entity_created'",
        (type_id,),
    ).fetchall()
    assert len(rows) == 1, rows
    return rows[0][0]


# ---------------------------------------------------------------------------
# register_entity
# ---------------------------------------------------------------------------


def test_register_entity_rejects_project_id(db, workspace_uuid):
    before = _registry_state(db)

    with pytest.raises(TypeError, match="'project_id'"):
        db.register_entity("feature", name="Refused", seq=5, slug="refused",
                           workspace_uuid=workspace_uuid, project_id=LEGACY_ID)

    assert _registry_state(db) == before
    db.register_entity("feature", name="Refused", seq=5, slug="refused",
                       workspace_uuid=workspace_uuid)
    assert db.get_entity("feature:005-refused")["workspace_uuid"] == workspace_uuid


def test_register_entity_rejects_parent_type_id(db, workspace_uuid, parent_uuid):
    before = _registry_state(db)

    with pytest.raises(TypeError, match="'parent_type_id'"):
        db.register_entity("feature", name="Child", seq=6, slug="child",
                           workspace_uuid=workspace_uuid, parent_type_id=PARENT_TYPE_ID)

    assert _registry_state(db) == before
    db.register_entity("feature", name="Child", seq=6, slug="child",
                       workspace_uuid=workspace_uuid, parent_uuid=parent_uuid)
    assert db.get_entity("feature:006-child")["parent_uuid"] == parent_uuid


# ---------------------------------------------------------------------------
# upsert_entity
# ---------------------------------------------------------------------------


def test_upsert_entity_rejects_project_id(db, workspace_uuid):
    before = _registry_state(db)

    with pytest.raises(TypeError, match="'project_id'"):
        db.upsert_entity("feature", name="Refused", seq=7, slug="refused",
                         workspace_uuid=workspace_uuid, project_id=LEGACY_ID)

    assert _registry_state(db) == before
    db.upsert_entity("feature", name="Refused", seq=7, slug="refused",
                     workspace_uuid=workspace_uuid)
    assert db.get_entity("feature:007-refused")["workspace_uuid"] == workspace_uuid


def test_upsert_entity_rejects_parent_type_id(db, workspace_uuid, parent_uuid):
    before = _registry_state(db)

    with pytest.raises(TypeError, match="'parent_type_id'"):
        db.upsert_entity("feature", name="Child", seq=8, slug="child",
                         workspace_uuid=workspace_uuid, parent_type_id=PARENT_TYPE_ID)

    assert _registry_state(db) == before
    db.upsert_entity("feature", name="Child", seq=8, slug="child",
                     workspace_uuid=workspace_uuid, parent_uuid=parent_uuid)
    assert db.get_entity("feature:008-child")["parent_uuid"] == parent_uuid


# ---------------------------------------------------------------------------
# register_entities_batch
# ---------------------------------------------------------------------------


def test_register_entities_batch_rejects_project_id(db, workspace_uuid):
    batch = [{"entity_type": "feature", "name": "Batched", "seq": 9, "slug": "batched"}]
    before = _registry_state(db)

    with pytest.raises(TypeError, match="'project_id'"):
        db.register_entities_batch(batch, workspace_uuid=workspace_uuid, project_id=LEGACY_ID)

    assert _registry_state(db) == before
    db.register_entities_batch(batch, workspace_uuid=workspace_uuid)
    assert db.get_entity("feature:009-batched")["workspace_uuid"] == workspace_uuid


# ---------------------------------------------------------------------------
# The allocator: generate_entity_id and next_sequence_value
# ---------------------------------------------------------------------------


def test_generate_entity_id_rejects_project_id(db, workspace_uuid):
    before = _registry_state(db)

    with pytest.raises(TypeError, match="'project_id'"):
        generate_entity_id(db, "feature", "Refused", project_id=LEGACY_ID,
                           workspace_uuid=workspace_uuid)
    with pytest.raises(TypeError, match="positional"):
        generate_entity_id(db, "feature", "Refused", LEGACY_ID)

    assert _registry_state(db) == before
    assert generate_entity_id(db, "feature", "Refused", workspace_uuid=workspace_uuid) == (1, "refused")
    assert _counter(db, workspace_uuid, "feature") == 2


def test_next_sequence_value_rejects_project_id(db, workspace_uuid):
    before = _registry_state(db)

    with pytest.raises(TypeError, match="'project_id'"):
        db.next_sequence_value(project_id=LEGACY_ID, entity_type="feature",
                               workspace_uuid=workspace_uuid)
    with pytest.raises(TypeError, match="positional"):
        db.next_sequence_value(LEGACY_ID, "feature")

    assert _registry_state(db) == before
    assert db.next_sequence_value(entity_type="feature", workspace_uuid=workspace_uuid) == 1
    assert _counter(db, workspace_uuid, "feature") == 2


# ---------------------------------------------------------------------------
# The entity_created label comes from the workspace
# ---------------------------------------------------------------------------


def _workspace_with_no_legacy_id(db: EntityDatabase) -> str:
    workspace = "01900000-0000-7000-8000-0000000c5b02"
    now = db._now_iso()
    db._conn.execute(
        "INSERT INTO workspaces (uuid, project_id_legacy, project_root, created_at, updated_at) "
        "VALUES (?, NULL, NULL, ?, ?)",
        (workspace, now, now),
    )
    db._conn.commit()
    return workspace


@pytest.mark.parametrize("workspace_kind, expected_label", [
    ("legacy id set", LEGACY_ID),
    ("legacy id NULL", UNKNOWN_LABEL),
    ("the unknown workspace", UNKNOWN_LABEL),
])
def test_the_entity_created_label_is_the_workspace_legacy_id_or_unknown(
    db, workspace_kind, expected_label,
):
    """``workspaces.project_id_legacy`` of the workspace the row lands in,
    else ``"__unknown__"``. Production callers passed no ``project_id`` since
    C5b step 1, so this is the label they always wrote."""
    workspace = {
        "legacy id set": lambda: bootstrap_test_workspace(db, LEGACY_ID),
        "legacy id NULL": lambda: _workspace_with_no_legacy_id(db),
        "the unknown workspace": lambda: _UNKNOWN_WORKSPACE_UUID,
    }[workspace_kind]()

    db.register_entity("feature", name="Registered", seq=11, slug="registered",
                       workspace_uuid=workspace)
    db.upsert_entity("feature", name="Upserted", seq=12, slug="upserted",
                     workspace_uuid=workspace, status="planned")
    db.upsert_entity("feature", name="Upserted", seq=12, slug="upserted",
                     workspace_uuid=workspace, status="active")

    assert _created_label(db, "feature:011-registered") == expected_label
    assert _created_label(db, "feature:012-upserted") == expected_label
    changed = db._conn.execute(
        "SELECT project_id FROM phase_events "
        "WHERE type_id = 'feature:012-upserted' AND event_type = 'entity_status_changed'"
    ).fetchall()
    assert [row[0] for row in changed] == [expected_label]
