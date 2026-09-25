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
- **Callers pass their workspace:** ``promote_task``, ``activate_feature``
  and ``init_feature_state`` create the row for the workspace that holds
  the entity they just wrote.

The fixture makes every guess name the wrong workspace: B's uuid sorts
first, and B registers the shared type_id first, so the smallest uuid, the
first registration and the lowest rowid all name B.
"""
from __future__ import annotations

import inspect
import textwrap

import pytest

from entity_registry.database import _UNKNOWN_WORKSPACE_UUID, EntityDatabase
from workflow_engine import feature_lifecycle, task_promotion

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


def test_upsert_without_a_workspace_names_no_scope_for_a_missing_entity(db):
    """Unscoped, a missing entity is reported without a scope: there is
    none to name (the legacy text named ``project None``)."""
    with pytest.raises(ValueError) as refusal:
        db.upsert_workflow_phase("feature:099-missing", workflow_phase="design")

    assert str(refusal.value) == "Entity 'feature:099-missing' not found"


# ---------------------------------------------------------------------------
# Callers pass their workspace
# ---------------------------------------------------------------------------

_TASK_HEADING = "Task 1.1: Log fields"
_PLAN_MD = textwrap.dedent(f"""\
    # Tasks

    ## Phase 1

    #### {_TASK_HEADING}
    - **Do:** Add the fields.
""")


def _record_calls(monkeypatch, db: EntityDatabase, method_name: str) -> list[dict]:
    """Wrap ``db.<method_name>``; return every call's arguments by
    parameter name, as the caller passed them (defaults not filled in)."""
    calls: list[dict] = []
    original = getattr(db, method_name)
    signature = inspect.signature(original)

    def recording(*args, **kwargs):
        calls.append(dict(signature.bind(*args, **kwargs).arguments))
        return original(*args, **kwargs)

    monkeypatch.setattr(db, method_name, recording)
    return calls


def _feature_directory(artifacts_root, name: str):
    directory = artifacts_root / "features" / name
    directory.mkdir(parents=True)
    return directory


def test_promote_task_creates_the_tasks_row_for_the_callers_workspace(db, tmp_path):
    """B already holds the task type_id that promotion allocates in A, with
    no row. The row is created for A's new task: without A's workspace the
    type_id would be ambiguous and the row refused."""
    feature_dir = _feature_directory(tmp_path, "052-promoting")
    (feature_dir / "plan.md").write_text(_PLAN_MD)
    db.register_entity(
        "feature", name="Promoting", seq=52, slug="promoting",
        status="active", workspace_uuid=WORKSPACE_A,
    )
    held_by_b = db.get_entity_by_uuid(db.register_entity(
        "task", name=_TASK_HEADING, seq=1, slug="task-1-1-log-fields",
        status="planned", workspace_uuid=WORKSPACE_B,
    ))["type_id"]

    result = task_promotion.promote_task(
        db, "feature:052-promoting", _TASK_HEADING,
        artifacts_root=str(tmp_path), workspace_uuid=WORKSPACE_A,
    )

    assert result["promoted"] is True
    assert result["task_type_id"] == held_by_b
    row = db.get_workflow_phase(held_by_b)
    assert row is not None
    assert (row["workspace_uuid"], row["uuid"]) == (WORKSPACE_A, result["task_uuid"])


def test_activate_feature_seeds_the_row_through_the_writer_with_its_workspace(
    db, tmp_path, monkeypatch,
):
    """The writer gets the caller's workspace. Activation's own unscoped
    ``get_entity`` refuses a type_id two workspaces hold before the writer
    runs, so no stored row can yet tell a scoped seed from an unscoped one:
    the call itself is checked. A row-level test waits for the
    ``workflow_phases`` re-key per entity (the plan's D3 ruling, Phase R)."""
    _feature_directory(tmp_path, "061-activating")
    uuid_a = db.register_entity(
        "feature", name="Activating", seq=61, slug="activating",
        status="planned", workspace_uuid=WORKSPACE_A,
    )
    seeds = _record_calls(monkeypatch, db, "create_workflow_phase")

    feature_lifecycle.activate_feature(
        db, None, str(tmp_path), "feature:061-activating",
        workspace_uuid=WORKSPACE_A,
    )

    assert [call.get("workspace_uuid") for call in seeds] == [WORKSPACE_A]
    row = db.get_workflow_phase("feature:061-activating")
    assert (row["workspace_uuid"], row["uuid"]) == (WORKSPACE_A, uuid_a)


def test_init_feature_state_without_a_workspace_seeds_the_entity_it_registered(db, tmp_path):
    """No workspace: the feature registers in ``__unknown__``, and its row
    is created there too. A and B already hold the type_id, so an unscoped
    create would be refused as ambiguous (and swallowed), leaving no row."""
    feature_dir = _feature_directory(tmp_path, "062-thrice")
    for workspace_uuid in (WORKSPACE_B, WORKSPACE_A):
        db.register_entity(
            "feature", name="Thrice", seq=62, slug="thrice",
            status="active", workspace_uuid=workspace_uuid,
        )

    feature_lifecycle.init_feature_state(
        db, None, str(tmp_path), str(feature_dir), "062", "thrice",
        "standard", "feature/062-thrice",
    )

    [registered_uuid] = [
        entity["uuid"]
        for entity in db.list_entities(workspace_uuid=_UNKNOWN_WORKSPACE_UUID)
        if entity["type_id"] == "feature:062-thrice"
    ]
    row = db.get_workflow_phase("feature:062-thrice")
    assert row is not None
    assert (row["workspace_uuid"], row["uuid"]) == (_UNKNOWN_WORKSPACE_UUID, registered_uuid)
