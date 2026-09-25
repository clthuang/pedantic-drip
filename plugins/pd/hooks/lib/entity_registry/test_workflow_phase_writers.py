"""W2.1: the ``workflow_phases`` row writers take the workspace, and never
guess it.

Design: ``docs/plans/2026-09-25-release-c-followups-design.md``, W2 change 1.

- ``create_workflow_phase`` and ``upsert_workflow_phase`` resolve the entity
  with ``_resolve_identifier``: scoped when a workspace is given, globally
  unique otherwise, so an ambiguous type_id is refused.
- Every insert stores the resolved entity's ``workspace_uuid`` and ``uuid``,
  so the ``wp_autofill_workspace_uuid`` trigger never picks one.
- ``upsert_workflow_phase`` refuses, rather than overwrites, a row that
  belongs to another workspace, and has no ``__unknown__`` default.

The fixture makes every guess name the wrong workspace: B's uuid sorts
first, and B registers the shared type_id first, so the smallest uuid, the
first registration and the lowest rowid all name B.
"""
from __future__ import annotations

import pytest

from entity_registry.database import EntityDatabase

WORKSPACE_B = "00000000-0000-4000-8000-0000000000bb"  # sorts first
WORKSPACE_A = "ffffffff-0000-4000-8000-0000000000aa"
SHARED_TYPE_ID = "feature:001-shared"


def _add_workspace(db: EntityDatabase, workspace_uuid: str, legacy_id: str) -> None:
    """A workspaces row with a fixed uuid (``bootstrap_test_workspace``
    mints a random one, which would not fix the sort order)."""
    now = db._now_iso()
    db._conn.execute(
        "INSERT INTO workspaces (uuid, project_id_legacy, project_root, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (workspace_uuid, legacy_id, None, now, now),
    )
    db._conn.commit()


@pytest.fixture
def db(tmp_path):
    database = EntityDatabase(str(tmp_path / "entities.db"))
    _add_workspace(database, WORKSPACE_B, "writers-b")
    _add_workspace(database, WORKSPACE_A, "writers-a")
    yield database
    database.close()


def _register_shared(db: EntityDatabase, workspace_uuid: str) -> str:
    """Register ``feature:001-shared`` in *workspace_uuid*; return its uuid."""
    return db.register_entity(
        "feature", name="Shared", seq=1, slug="shared", status="active",
        workspace_uuid=workspace_uuid,
    )


# ---------------------------------------------------------------------------
# create_workflow_phase
# ---------------------------------------------------------------------------


def test_create_stores_the_given_workspace_and_its_entitys_uuid(db):
    _register_shared(db, WORKSPACE_B)
    uuid_a = _register_shared(db, WORKSPACE_A)

    returned = db.create_workflow_phase(
        SHARED_TYPE_ID, workspace_uuid=WORKSPACE_A, kanban_column="backlog",
    )

    stored = db.get_workflow_phase(SHARED_TYPE_ID)
    assert (stored["workspace_uuid"], stored["uuid"]) == (WORKSPACE_A, uuid_a)
    assert (returned["workspace_uuid"], returned["uuid"]) == (WORKSPACE_A, uuid_a)


def test_create_without_a_workspace_refuses_a_type_id_two_workspaces_hold(db):
    _register_shared(db, WORKSPACE_B)
    _register_shared(db, WORKSPACE_A)

    with pytest.raises(ValueError, match="Ambiguous type_id"):
        db.create_workflow_phase(SHARED_TYPE_ID, kanban_column="backlog")

    assert db.get_workflow_phase(SHARED_TYPE_ID) is None


def test_create_without_a_workspace_stores_the_sole_holders_identity(db):
    uuid_b = _register_shared(db, WORKSPACE_B)

    db.create_workflow_phase(SHARED_TYPE_ID, kanban_column="backlog")

    stored = db.get_workflow_phase(SHARED_TYPE_ID)
    assert (stored["workspace_uuid"], stored["uuid"]) == (WORKSPACE_B, uuid_b)


def test_create_scoped_to_a_workspace_without_the_entity_refuses(db):
    _register_shared(db, WORKSPACE_B)

    with pytest.raises(ValueError, match="Entity not found"):
        db.create_workflow_phase(SHARED_TYPE_ID, workspace_uuid=WORKSPACE_A)

    assert db.get_workflow_phase(SHARED_TYPE_ID) is None


# ---------------------------------------------------------------------------
# upsert_workflow_phase
# ---------------------------------------------------------------------------


def test_upsert_from_a_refuses_bs_row_and_leaves_it_unchanged(db):
    _register_shared(db, WORKSPACE_B)
    # B is the type_id's only holder here, so the row is B's on any code.
    db.create_workflow_phase(
        SHARED_TYPE_ID, workflow_phase="design", kanban_column="prioritised",
    )
    _register_shared(db, WORKSPACE_A)
    before = dict(db.get_workflow_phase(SHARED_TYPE_ID))
    assert before["workspace_uuid"] == WORKSPACE_B

    with pytest.raises(ValueError, match="belongs to workspace"):
        db.upsert_workflow_phase(
            SHARED_TYPE_ID, workspace_uuid=WORKSPACE_A,
            workflow_phase="implement", kanban_column="wip",
        )

    assert dict(db.get_workflow_phase(SHARED_TYPE_ID)) == before


def test_upsert_inserts_the_resolved_entitys_workspace_and_uuid(db):
    _register_shared(db, WORKSPACE_B)
    uuid_a = _register_shared(db, WORKSPACE_A)

    db.upsert_workflow_phase(
        SHARED_TYPE_ID, workspace_uuid=WORKSPACE_A,
        workflow_phase="design", kanban_column="prioritised",
    )

    stored = db.get_workflow_phase(SHARED_TYPE_ID)
    assert (stored["workspace_uuid"], stored["uuid"]) == (WORKSPACE_A, uuid_a)
    assert stored["workflow_phase"] == "design"


def test_upsert_without_a_workspace_resolves_a_globally_unique_type_id(db):
    """No ``__unknown__`` default: with neither a workspace nor a legacy
    project id, the type_id resolves like ``create_workflow_phase``'s."""
    uuid_a = _register_shared(db, WORKSPACE_A)

    db.upsert_workflow_phase(
        SHARED_TYPE_ID, workflow_phase="design", kanban_column="prioritised",
    )

    stored = db.get_workflow_phase(SHARED_TYPE_ID)
    assert (stored["workspace_uuid"], stored["uuid"], stored["workflow_phase"]) == (
        WORKSPACE_A, uuid_a, "design",
    )


def test_upsert_without_a_workspace_refuses_a_type_id_two_workspaces_hold(db):
    _register_shared(db, WORKSPACE_B)
    _register_shared(db, WORKSPACE_A)

    with pytest.raises(ValueError, match="Ambiguous type_id"):
        db.upsert_workflow_phase(SHARED_TYPE_ID, workflow_phase="design")

    assert db.get_workflow_phase(SHARED_TYPE_ID) is None
