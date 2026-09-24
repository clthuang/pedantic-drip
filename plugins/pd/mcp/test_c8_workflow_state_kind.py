"""C8: the feature-kanban writes in ``transition_phase``/``complete_phase``
read the kind from ``entities.kind``, never from ``type_id`` text.

Both ``_process_transition_phase`` and ``_process_complete_phase`` move a
feature's ``workflow_phases.kanban_column`` along with its phase, and only a
feature's. Most fixtures here give the entity a ``kind`` column that
DISAGREES with the kind its ``type_id`` spells. Only raw SQL can build such
a row (the live registry holds none). The tests assert that the kanban
write follows the column.

The cross-workspace class covers the same type_id registered in two
workspaces, where the unscoped ``get_entity`` read is None. The kind must
come from the row in this server's workspace. With a feature there, the
kanban moves as it did before C8; with a backlog there, the kanban stays,
although the text and the other workspace's row both say feature.

The soft-deleted class covers an entity ``delete_entity`` has hidden from
the live ``get_entity`` read. Its transition still goes through, so the
kind must come from the deleted row's kind column, in both server scopes.

Non-vacuity: each test first asserts that the transition or completion went
through, so the kanban step was reached. Each fixture starts in ``backlog``,
and the phase it lands on maps to ``prioritised``, so a write that
followed the wrong source would show up as a different column.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import uuid as _uuid

import pytest

# Ensure hooks/lib is on path for imports (mirrors test_workflow_state_server.py).
_hooks_lib = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "hooks", "lib"))
if _hooks_lib not in sys.path:
    sys.path.insert(0, _hooks_lib)

from entity_registry.database import EntityDatabase, _derive_type_and_lifecycle
from entity_registry.test_helpers import bootstrap_test_workspace
from workflow_engine.engine import WorkflowStateEngine

import workflow_state_server as wss

_NOW = "2026-09-24T00:00:00Z"

# (type_id, entity_id, kind): the text and the kind column disagree.
FEATURE_KIND_UNDER_BACKLOG_PREFIX = ("backlog:00211-stored-as-feature", "00211-stored-as-feature", "feature")
BACKLOG_KIND_UNDER_FEATURE_PREFIX = ("feature:210-stored-as-backlog", "210-stored-as-backlog", "backlog")


@pytest.fixture(autouse=True)
def _unscoped_server(monkeypatch):
    # The module-level workspace starts empty; pin that, so a global leaked
    # by another test file cannot scope these calls elsewhere.
    monkeypatch.setattr(wss, "_workspace_uuid", "")


@pytest.fixture
def db(tmp_path):
    database = EntityDatabase(str(tmp_path / "entities.db"))
    yield database
    database.close()


def _seed_disagreeing_entity(db: EntityDatabase, tmp_path, row: tuple[str, str, str]) -> str:
    """Raw SQL: an entity whose ``kind`` column disagrees with its type_id,
    at phase ``specify`` in kanban column ``backlog``. Returns the type_id.

    The artifact directory is the one the frozen engine derives from the
    type_id, and it holds ``shape.md`` so the ``design`` prerequisite gate
    passes.
    """
    type_id, entity_id, kind = row
    workspace_uuid = bootstrap_test_workspace(db, "c8-workflow-state-kind")
    feature_dir = tmp_path / "features" / entity_id
    feature_dir.mkdir(parents=True)
    (feature_dir / ".meta.json").write_text(
        json.dumps({"id": entity_id, "slug": entity_id, "status": "active", "mode": "standard"})
    )
    (feature_dir / "shape.md").write_text("# Shape\n")

    entity_type, lifecycle_class = _derive_type_and_lifecycle(kind)
    conn = sqlite3.connect(str(tmp_path / "entities.db"))
    try:
        conn.execute(
            "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, "
            "name, status, artifact_path, created_at, updated_at, type, kind, "
            "lifecycle_class) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(_uuid.uuid4()), workspace_uuid, type_id, entity_id,
             f"Row stored as {kind}", "active", str(feature_dir), _NOW, _NOW,
             entity_type, kind, lifecycle_class),
        )
        conn.commit()
    finally:
        conn.close()
    db.create_workflow_phase(type_id, workflow_phase="specify", kanban_column="backlog")
    return type_id


def _transition_to_design(db: EntityDatabase, tmp_path, type_id: str) -> dict:
    engine = WorkflowStateEngine(db, str(tmp_path))
    return json.loads(wss._process_transition_phase(
        engine, type_id, "design", yolo_active=False, db=db, skipped_phases=None,
    ))


def _complete_specify(db: EntityDatabase, tmp_path, type_id: str) -> dict:
    engine = WorkflowStateEngine(db, str(tmp_path))
    return json.loads(wss._process_complete_phase(
        engine, type_id, "specify", db=db, iterations=None, reviewer_notes=None,
    ))


class TestTransitionPhaseKanbanFollowsKindColumn:

    def test_feature_kind_under_a_backlog_prefix_moves_its_kanban_column(self, db, tmp_path):
        type_id = _seed_disagreeing_entity(db, tmp_path, FEATURE_KIND_UNDER_BACKLOG_PREFIX)

        result = _transition_to_design(db, tmp_path, type_id)

        assert result["transitioned"] is True
        assert db.get_workflow_phase(type_id)["kanban_column"] == "prioritised"

    def test_backlog_kind_under_a_feature_prefix_keeps_its_kanban_column(self, db, tmp_path):
        type_id = _seed_disagreeing_entity(db, tmp_path, BACKLOG_KIND_UNDER_FEATURE_PREFIX)

        result = _transition_to_design(db, tmp_path, type_id)

        assert result["transitioned"] is True
        assert db.get_workflow_phase(type_id)["kanban_column"] == "backlog"


class TestCompletePhaseKanbanFollowsKindColumn:

    def test_feature_kind_under_a_backlog_prefix_moves_its_kanban_column(self, db, tmp_path):
        type_id = _seed_disagreeing_entity(db, tmp_path, FEATURE_KIND_UNDER_BACKLOG_PREFIX)

        result = _complete_specify(db, tmp_path, type_id)

        assert "error" not in result, result
        assert result["current_phase"] == "design"
        assert db.get_workflow_phase(type_id)["kanban_column"] == "prioritised"

    def test_backlog_kind_under_a_feature_prefix_keeps_its_kanban_column(self, db, tmp_path):
        type_id = _seed_disagreeing_entity(db, tmp_path, BACKLOG_KIND_UNDER_FEATURE_PREFIX)

        result = _complete_specify(db, tmp_path, type_id)

        assert "error" not in result, result
        assert result["current_phase"] == "design"
        assert db.get_workflow_phase(type_id)["kanban_column"] == "backlog"


class TestTransitionPhaseKanbanOnTheCrossWorkspaceEdge:
    """The same type_id registered in two workspaces (the qa-server H2 edge).

    The unscoped ``get_entity`` read is None there (ambiguous), yet the
    transition goes through, scoped to this server's workspace. The kind
    must then come from THIS workspace's row.
    """

    def _seed_shared_type_id(self, db, tmp_path, monkeypatch, *, this_workspace_kind):
        type_id, entity_id = "feature:001-shared", "001-shared"
        this_workspace = bootstrap_test_workspace(db, "c8-h2-this")
        other_workspace = bootstrap_test_workspace(db, "c8-h2-other")
        feature_dir = tmp_path / "features" / entity_id
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text(
            json.dumps({"id": "001", "slug": "shared", "status": "active", "mode": "standard"})
        )
        (feature_dir / "shape.md").write_text("# Shape\n")

        rows = [(this_workspace, this_workspace_kind), (other_workspace, "feature")]
        db_file = str(tmp_path / "entities.db")
        conn = sqlite3.connect(db_file)
        try:
            for workspace_uuid, kind in rows:
                entity_type, lifecycle_class = _derive_type_and_lifecycle(kind)
                conn.execute(
                    "INSERT INTO entities (uuid, workspace_uuid, type_id, entity_id, "
                    "name, status, artifact_path, created_at, updated_at, type, kind, "
                    "lifecycle_class) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(_uuid.uuid4()), workspace_uuid, type_id, entity_id,
                     f"Shared id stored as {kind}", "active", str(feature_dir),
                     _NOW, _NOW, entity_type, kind, lifecycle_class),
                )
            conn.commit()
        finally:
            conn.close()
        db.create_workflow_phase(type_id, workflow_phase="specify", kanban_column="backlog")
        # The insert trigger fills workspace_uuid from whichever entities row
        # its subquery meets first; pin it to this workspace, the scope the
        # engine's update_workflow_phase asserts.
        conn = sqlite3.connect(db_file)
        try:
            conn.execute(
                "UPDATE workflow_phases SET workspace_uuid = ? WHERE type_id = ?",
                (this_workspace, type_id),
            )
            conn.commit()
        finally:
            conn.close()
        monkeypatch.setattr(wss, "_workspace_uuid", this_workspace)
        assert db.get_entity(type_id) is None  # the edge: the unscoped read is ambiguous
        return type_id

    def test_this_workspaces_feature_moves_the_kanban_column(self, db, tmp_path, monkeypatch):
        type_id = self._seed_shared_type_id(
            db, tmp_path, monkeypatch, this_workspace_kind="feature",
        )

        result = _transition_to_design(db, tmp_path, type_id)

        assert result["transitioned"] is True
        assert db.get_workflow_phase(type_id)["kanban_column"] == "prioritised"

    def test_this_workspaces_backlog_keeps_the_kanban_column(self, db, tmp_path, monkeypatch):
        # The other workspace's row is a feature. The kind that counts is
        # this workspace's row, and neither the text nor the other row.
        type_id = self._seed_shared_type_id(
            db, tmp_path, monkeypatch, this_workspace_kind="backlog",
        )

        result = _transition_to_design(db, tmp_path, type_id)

        assert result["transitioned"] is True
        assert db.get_workflow_phase(type_id)["kanban_column"] == "backlog"


class TestTransitionPhaseKanbanForASoftDeletedEntity:
    """A soft-deleted entity: ``delete_entity`` sets ``is_deleted = 1`` and
    keeps both its entities row and its workflow_phases row (#081).

    Nothing blocks ``transition_phase`` on it: the frozen engine reads
    workflow_phases and ``update_entity`` does not filter ``is_deleted``, so
    the phase moves. The live ``get_entity`` read hides the row, so the kind
    must come from the deleted row's ``kind`` column, in both server scopes.
    Before C8 the text check moved a soft-deleted feature's kanban column;
    these tests pin that the kind-column read still moves it.
    """

    @pytest.fixture(params=["unscoped", "scoped"])
    def server_scope(self, request) -> str:
        return request.param

    def _soft_delete(self, db, monkeypatch, type_id: str, server_scope: str) -> None:
        db.delete_entity(type_id)
        assert db.get_entity(type_id) is None  # the live read hides the row
        assert db.get_entity(type_id, include_deleted=True)["is_deleted"] == 1
        if server_scope == "scoped":
            workspace_uuid = bootstrap_test_workspace(db, "c8-workflow-state-kind")
            monkeypatch.setattr(wss, "_workspace_uuid", workspace_uuid)

    def test_soft_deleted_feature_moves_its_kanban_column(
        self, db, tmp_path, monkeypatch, server_scope,
    ):
        # Registered the normal way, so its type_id and kind agree.
        workspace_uuid = bootstrap_test_workspace(db, "c8-workflow-state-kind")
        feature_dir = tmp_path / "features" / "301-soft-deleted"
        feature_dir.mkdir(parents=True)
        (feature_dir / ".meta.json").write_text(
            json.dumps({"id": "301", "slug": "soft-deleted", "status": "active", "mode": "standard"})
        )
        (feature_dir / "shape.md").write_text("# Shape\n")
        db.register_entity(
            "feature", name="Soft-deleted feature", seq=301, slug="soft-deleted",
            workspace_uuid=workspace_uuid, artifact_path=str(feature_dir),
            status="active",
        )
        type_id = "feature:301-soft-deleted"
        db.create_workflow_phase(type_id, workflow_phase="specify", kanban_column="backlog")
        self._soft_delete(db, monkeypatch, type_id, server_scope)

        result = _transition_to_design(db, tmp_path, type_id)

        assert result["transitioned"] is True
        assert db.get_workflow_phase(type_id)["workflow_phase"] == "design"
        assert db.get_workflow_phase(type_id)["kanban_column"] == "prioritised"

    def test_soft_deleted_feature_kind_under_a_backlog_prefix_moves_its_kanban_column(
        self, db, tmp_path, monkeypatch, server_scope,
    ):
        # The text says backlog and the deleted row's kind column says
        # feature: the kanban moves only if the kind is read from the row.
        type_id = _seed_disagreeing_entity(db, tmp_path, FEATURE_KIND_UNDER_BACKLOG_PREFIX)
        self._soft_delete(db, monkeypatch, type_id, server_scope)

        result = _transition_to_design(db, tmp_path, type_id)

        assert result["transitioned"] is True
        assert db.get_workflow_phase(type_id)["kanban_column"] == "prioritised"
