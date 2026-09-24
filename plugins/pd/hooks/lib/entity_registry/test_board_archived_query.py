"""board-archived: the board's query drops archived entities; no other
caller's query changes.

``EntityDatabase.list_workflow_phases(include_archived=False)`` is what the
kanban board (``ui/routes/board.py``) asks for. It drops the rows whose
joined entity has ``is_archived = 1`` and keeps everything else:

- **orphan rows** (no entities row, so ``e.uuid IS NULL``): kept, exactly as
  the workspace scope already keeps them.
- **soft-deleted entities** (``is_deleted = 1``): kept. The flag plays no
  part in the filter.

Every other caller omits the keyword, so the default (``True``) must return
the archived rows with the same keys as before. The filter sits in the WHERE
clause: in the join's ON clause an archived entity would fail the join and
come back as an orphan row, which both the board and the workspace scope
keep.
"""
from __future__ import annotations

import sqlite3

import pytest

from entity_registry.database import EntityDatabase
from entity_registry.test_helpers import bootstrap_test_workspace

_NOW = "2026-09-25T00:00:00Z"

# How each caller other than the board calls list_workflow_phases (re-derived
# from source at 3d4d125e). None of them passes include_archived.
_OTHER_CALLERS = [
    # ui/routes/entities.py entity_detail
    pytest.param(lambda workspace_uuid: {}, id="unscoped"),
    # ui/routes/entities.py _build_workflow_lookup (entity_list),
    # entity_registry/backfill.py run_backfill,
    # workflow_engine/reconciliation.py check_workflow_drift (db_only),
    # workflow_engine/engine.py list_by_status
    pytest.param(lambda workspace_uuid: {"workspace_uuid": workspace_uuid},
                 id="workspace-scoped"),
    # workflow_engine/engine.py list_by_phase
    pytest.param(lambda workspace_uuid: {"workflow_phase": "implement",
                                         "workspace_uuid": workspace_uuid},
                 id="phase-and-workspace"),
]

# The keys every row carried before the keyword existed: the workflow_phases
# columns (wp.*) plus the five joined or aliased keys the SELECT adds.
_ADDED_KEYS = {
    "execution_status", "pipeline_phase", "entity_name", "entity_type",
    "entity_artifact_path",
}


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
    return bootstrap_test_workspace(db, "board-archived-query")


def _add_feature(db, workspace_uuid, seq, slug, *, archived=False, deleted=False) -> str:
    """Register an active feature in the implement phase; return its type_id."""
    entity_uuid = db.register_entity(
        "feature", name=slug, seq=seq, slug=slug, status="active",
        workspace_uuid=workspace_uuid,
    )
    type_id = db.get_entity_by_uuid(entity_uuid)["type_id"]
    db.create_workflow_phase(type_id, kanban_column="wip", workflow_phase="implement")
    if archived:
        db.set_archived(type_id, workspace_uuid=workspace_uuid)
    if deleted:
        db.set_deleted(type_id, workspace_uuid=workspace_uuid)
    return type_id


def _add_orphan_row(db_path, workspace_uuid, type_id) -> None:
    """Raw SQL: a workflow_phases row with no entities row behind it. The
    explicit workspace_uuid lets it past the wp_reject_orphaned_insert
    trigger."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO workflow_phases (type_id, kanban_column, workflow_phase, "
            "updated_at, workspace_uuid) VALUES (?, 'wip', 'implement', ?, ?)",
            (type_id, _NOW, workspace_uuid),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def mixed(db, db_path, workspace_uuid) -> dict[str, str]:
    """A live, an archived and a soft-deleted feature, plus an orphan row,
    all in the same column and phase."""
    orphan = "feature:099-orphan-row"
    _add_orphan_row(db_path, workspace_uuid, orphan)
    return {
        "live": _add_feature(db, workspace_uuid, 1, "live"),
        "archived": _add_feature(db, workspace_uuid, 2, "archived", archived=True),
        "soft-deleted": _add_feature(db, workspace_uuid, 3, "soft-deleted", deleted=True),
        "orphan": orphan,
    }


def _type_ids(rows: list[dict]) -> set[str]:
    return {row["type_id"] for row in rows}


class TestBoardQuery:

    @pytest.mark.parametrize("scoped", [False, True], ids=["unscoped", "workspace-scoped"])
    def test_drops_the_archived_row_and_keeps_live_orphan_and_soft_deleted(
        self, db, workspace_uuid, mixed, scoped,
    ):
        scope = {"workspace_uuid": workspace_uuid} if scoped else {}

        rows = db.list_workflow_phases(include_archived=False, **scope)

        assert _type_ids(rows) == {mixed["live"], mixed["orphan"], mixed["soft-deleted"]}

    def test_a_type_id_archived_in_one_workspace_stays_for_the_other(self, db):
        """One workflow row, one type_id, archived in workspace A and live in
        workspace B. The filter tests each joined entity, not the type_id:
        B's entity keeps its row unscoped and under B's scope, and A's
        scope returns nothing."""
        workspace_a = bootstrap_test_workspace(db, "board-archived-a")
        workspace_b = bootstrap_test_workspace(db, "board-archived-b")
        type_id = _add_feature(db, workspace_a, 5, "collide", archived=True)
        db.register_entity("feature", name="collide in B", seq=5, slug="collide",
                           status="active", workspace_uuid=workspace_b)

        unscoped = db.list_workflow_phases(include_archived=False)
        scoped_a = db.list_workflow_phases(include_archived=False, workspace_uuid=workspace_a)
        scoped_b = db.list_workflow_phases(include_archived=False, workspace_uuid=workspace_b)

        assert [(row["type_id"], row["entity_name"]) for row in unscoped] == [
            (type_id, "collide in B")
        ]
        assert scoped_a == []
        assert [row["entity_name"] for row in scoped_b] == ["collide in B"]


class TestOtherCallersKeepTheArchivedRow:

    @pytest.mark.parametrize("call_shape", _OTHER_CALLERS)
    def test_the_archived_row_is_still_returned(
        self, db, workspace_uuid, mixed, call_shape,
    ):
        kwargs = call_shape(workspace_uuid)

        rows = db.list_workflow_phases(**kwargs)

        assert _type_ids(rows) == set(mixed.values())
        # The same call on the board's terms drops it, so the row above is
        # there because the default keeps it, not because it was never
        # archived.
        assert mixed["archived"] not in _type_ids(
            db.list_workflow_phases(include_archived=False, **kwargs)
        )

    @pytest.mark.parametrize("call_shape", _OTHER_CALLERS)
    def test_rows_carry_the_same_keys_as_before(
        self, db, db_path, workspace_uuid, mixed, call_shape,
    ):
        conn = sqlite3.connect(db_path)
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(workflow_phases)")}
        finally:
            conn.close()

        rows = db.list_workflow_phases(**call_shape(workspace_uuid))

        assert rows
        assert {frozenset(row) for row in rows} == {frozenset(columns | _ADDED_KEYS)}
